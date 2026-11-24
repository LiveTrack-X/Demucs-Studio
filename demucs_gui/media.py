"""Local media probing, PCM decoding, and stem export."""

from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from .config import Options, QUALITY_OPTIONS

Progress = Callable[[float, str], None]
Cancelled = Callable[[], bool]
QUALITY_CHOICES = {fmt: tuple(dict(choices)) for fmt, choices in QUALITY_OPTIONS.items()}
MODEL_RATE = 44100
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    audio_index: int
    audio_start: float
    audio_rate: int
    audio_frames: int | None
    video_index: int | None
    video_start: float
    codec_padding: bool = False

    @property
    def has_video(self) -> bool:
        return self.video_index is not None


def _binary(name: str) -> str:
    filename = name + (".exe" if os.name == "nt" else "")
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    local = base / "bin" / filename
    if local.is_file():
        return str(local)
    located = shutil.which(filename)
    if located:
        return located
    raise RuntimeError(f"{filename} 파일을 찾을 수 없습니다. 설치 폴더의 bin 폴더를 확인해 주세요.")


def _number(value, default=0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _preferred(streams, kind):
    eligible = [s for s in streams if s["codec_type"] == kind and
                not s.get("disposition", {}).get("attached_pic")]
    return max(eligible, key=lambda s: s.get("disposition", {}).get("default", 0), default=None)


def probe(path: Path) -> MediaInfo:
    path = Path(path).resolve(strict=True)
    result = subprocess.run(
        [_binary("ffprobe"), "-v", "error", "-protocol_whitelist", "file",
         "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        creationflags=_NO_WINDOW,
    )
    if result.returncode:
        raise ValueError(f"미디어 정보를 읽을 수 없습니다. {result.stderr.strip()}")
    data = json.loads(result.stdout)
    audio = _preferred(data["streams"], "audio")
    if audio is None:
        raise ValueError("입력 파일에 분리할 오디오 트랙이 없습니다.")
    video = _preferred(data["streams"], "video")
    fmt = data.get("format", {})
    file_start = _number(fmt.get("start_time"))
    audio_start = _number(audio.get("start_time"), file_start)
    video_start = _number(video.get("start_time"), file_start) if video else file_start
    audio_rate = int(audio["sample_rate"])
    audio_frames = None
    # In MOV/MP4, a presentation edit can end part-way through the final AAC
    # codec frame. Its stream ticks, rather than the full packet, set the end.
    iso_audio = "mov" in fmt.get("format_name", "").split(",") and audio["codec_name"] in ("aac", "alac")
    if audio["codec_name"].startswith("pcm_") or audio["codec_name"] == "flac" or iso_audio:
        if audio.get("duration_ts") is not None and audio.get("time_base"):
            frames = int(audio["duration_ts"]) * Fraction(audio["time_base"]) * audio_rate
            if frames.denominator == 1 and frames > 0 and Fraction(audio["time_base"]) <= Fraction(1, audio_rate):
                audio_frames = int(frames)
    streams = [(audio, audio_start)] + ([(video, video_start)] if video else [])
    if all(_number(s.get("duration")) > 0 for s, _ in streams):
        duration = max(start + _number(s["duration"]) for s, start in streams) - min(
            start for _, start in streams)
    else:
        duration = _number(fmt.get("duration"))
        if "matroska" in fmt.get("format_name", "").split(",") and duration > file_start > 0:
            # Matroska Segment Duration is measured from timestamp zero.
            duration -= file_start
    return MediaInfo(duration, audio["index"], audio_start, audio_rate, audio_frames,
                     video["index"] if video else None, video_start, iso_audio and audio["codec_name"] == "aac")


def _check_cancel(cancelled: Cancelled) -> None:
    if cancelled():
        raise InterruptedError("작업을 취소했습니다.")


@contextmanager
def _new_output(dest: Path):
    # Reserve exclusively so failed jobs cannot damage an input or prior export.
    with dest.open("xb"):
        pass
    try:
        yield
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


class _EncodingError(RuntimeError):
    pass


def _run(args: list[str], duration: float, label: str, progress: Progress,
         cancelled: Cancelled, loglevel: str = "error") -> str:
    _check_cancel(cancelled)
    progress(0.0, label)
    command = [_binary("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", loglevel,
               "-y", "-stats_period", "0.25", "-nostats", "-progress", "pipe:1", *args]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=errors, encoding="utf-8", errors="replace",
                                   creationflags=_NO_WINDOW)
        events: queue.Queue = queue.Queue()

        def read_progress() -> None:
            try:
                for line in process.stdout:
                    if line.startswith("out_time_us="):
                        events.put(_number(line.partition("=")[2]) / 1_000_000)
            finally:
                events.put(None)

        reader = threading.Thread(target=read_progress, daemon=True)
        reader.start()
        try:
            while True:
                _check_cancel(cancelled)
                try:
                    timestamp = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if timestamp is None:
                    break
                if duration > 0:
                    progress(max(0.0, min(timestamp / duration, 0.999)), label)
            status = process.wait()
            errors.seek(max(0, errors.tell() - 8192))
            log = errors.read().decode("utf-8", "replace").strip()
            if status:
                raise _EncodingError(log or "FFmpeg 변환 실패")
            _check_cancel(cancelled)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join()
            process.stdout.close()
    progress(1.0, label)
    return log


def _input(path: Path) -> list[str]:
    return ["-protocol_whitelist", "file", "-i", str(Path(path).resolve(strict=True))]


def decode(path: Path, dest: Path, info: MediaInfo, progress: Progress, cancelled: Cancelled) -> MediaInfo:
    # Joined recordings can advance the clock by one AAC packet at a cut.
    # The default 100 ms sync threshold drops those short gaps. MP4's audio
    # clock is sample-accurate, while Matroska commonly rounds to milliseconds.
    tolerance = 1.5 / info.audio_rate if info.codec_padding else 0.003
    filters = ["asetpts=PTS-STARTPTS",
               f"aresample={info.audio_rate}:async=1:min_hard_comp={tolerance:.9f}:first_pts=0"]
    if info.codec_padding and info.audio_frames is not None:
        # Respect the container's declared playback end if its final codec
        # packet contains extra samples.
        filters.append(f"atrim=end_sample={info.audio_frames}")
    # MP3, Ogg and many Matroska tracks lack sample-exact header durations.
    # Count their native frames here before resampling, in the same decode pass.
    measure = info.audio_frames is None
    if measure:
        filters.append("astats=measure_perchannel=none:measure_overall=Number_of_samples")
    filters.append(f"aresample={MODEL_RATE}")
    with _new_output(dest):
        log = _run([*_input(path), "-map", f"0:{info.audio_index}", "-map_metadata", "-1",
                    "-af", ",".join(filters), "-ac", "2", "-c:a", "pcm_f32le", "-rf64", "auto",
                    "-f", "wav", str(dest)], info.duration, "오디오 읽는 중", progress, cancelled,
                   "info" if measure else "error")
        if measure:
            matched = re.search(r"\] Number of samples: (\d+)", log)
            if matched:
                return replace(info, audio_frames=int(matched[1]))
    return info


def _native_lossless(stem: Path, dest: Path, info: MediaInfo, fmt: str, quality: str,
                     progress: Progress, cancelled: Cancelled) -> None:
    """Evaluate a band-limited stem on each sample position of the source clock."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import firwin, upfirdn

    rate = info.audio_rate
    count = info.audio_frames
    divisor = math.gcd(MODEL_RATE, rate)
    up, down = rate // divisor, MODEL_RATE // divisor
    # Integer group delay on the output grid makes block stitching phase-exact.
    radius = math.ceil(10 * max(up, down) / down) * down
    kernel = firwin(2 * radius + 1, 1 / max(up, down), window=("kaiser", 5.0))
    kernel = np.asarray(kernel * up, dtype=np.float32)
    halo = math.ceil(radius / up) + 1
    subtype = {"16": "PCM_16", "24": "PCM_24", "32f": "FLOAT"}[quality]
    container = fmt.upper()
    if fmt == "wav" and count * 2 * {"16": 2, "24": 3, "32f": 4}[quality] + 4096 >= 2**32:
        container = "RF64"
    label = "원본 샘플레이트로 음원 저장 중"
    progress(0.0, label)
    with sf.SoundFile(stem) as src, sf.SoundFile(dest, mode="w", samplerate=rate, channels=2,
                                                format=container, subtype=subtype) as output:
        if abs(src.frames - count * MODEL_RATE / rate) > 2:
            raise ValueError("원본과 분리 음원의 샘플 길이가 일치하지 않습니다.")
        for start in range(0, count, 131072):
            _check_cancel(cancelled)
            end = min(start + 131072, count)
            left = max(0, (start * down // up - halo) // down * down)
            right = min(src.frames, math.ceil(end * down / up) + halo)
            src.seek(left)
            samples = src.read(right - left, dtype="float32", always_2d=True)
            filtered = upfirdn(kernel, samples, up, down, axis=0)
            first = start - left * up // down + radius // down
            block = filtered[first:first + end - start]
            if len(block) != end - start:
                raise ValueError("원본 타임라인의 샘플 위치를 재구성하지 못했습니다.")
            output.write(block)
            progress(end / count, label)


def _audio_args(fmt: str, quality: str, info: MediaInfo) -> list[str]:
    if fmt == "wav":
        codec = {"16": "pcm_s16le", "24": "pcm_s24le", "32f": "pcm_f32le"}[quality]
        return ["-ar", str(info.audio_rate), "-c:a", codec, "-rf64", "auto", "-f", "wav"]
    if fmt == "flac":
        return ["-ar", str(info.audio_rate), "-c:a", "flac", "-sample_fmt",
                "s16" if quality == "16" else "s32", "-bits_per_raw_sample", quality, "-f", "flac"]
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", f"{quality}k", "-f", "mp3"]
    if fmt == "aac":
        return ["-c:a", "aac", "-b:a", f"{quality}k", "-f", "adts"]
    return ["-c:a", "aac", "-b:a", f"{quality}k", "-movflags", "+faststart",
            "-movie_timescale", str(MODEL_RATE), "-f", "mp4"]


def export(source: Path, stem: Path, dest: Path, info: MediaInfo, options: Options,
           progress: Progress, cancelled: Cancelled) -> None:
    fmt = options.video_format if options.output_kind == "video" else options.audio_format
    quality = options.quality
    if quality not in QUALITY_CHOICES.get(fmt, ()):
        raise ValueError("출력 형식에 맞는 음질을 선택해 주세요.")
    _check_cancel(cancelled)
    with _new_output(dest):
        if options.output_kind == "audio":
            if fmt in ("wav", "flac") and info.audio_frames and info.audio_rate != MODEL_RATE:
                _native_lossless(stem, dest, info, fmt, quality, progress, cancelled)
            else:
                _run([*_input(stem), "-map", "0:a:0", "-map_metadata", "-1",
                      *_audio_args(fmt, quality, info), str(dest)], info.duration,
                     "음원 저장 중", progress, cancelled)
            return

        if not info.has_video:
            raise ValueError("원본 파일에 화면이 없습니다. 음원 출력을 선택해 주세요.")
        # Rebase the two streams to the same origin, retaining late audio or late
        # video. Do not stop when the shorter stream ends (a VOD may have a tail).
        origin = min(info.audio_start, info.video_start)
        inputs = ["-copyts", "-itsoffset", f"{-origin:.9f}", *_input(source),
                  "-itsoffset", f"{info.audio_start - origin:.9f}", *_input(stem),
                  "-map", f"0:{info.video_index}", "-map", "1:a:0", "-map_metadata", "0",
                  "-map_chapters", "-1"]
        mux = ["-c:a", "aac", "-b:a", f"{quality}k", "-avoid_negative_ts", "disabled"]
        if fmt == "mp4":
            mux.extend(["-movflags", "+faststart", "-movie_timescale", str(MODEL_RATE), "-f", "mp4"])
        else:
            mux.extend(["-f", "matroska"])
        try:
            _run([*inputs, "-c:v", "copy", *mux, str(dest)], info.duration,
                 "원본 화면과 분리 음원 저장 중", progress, cancelled)
        except _EncodingError as exc:
            # Only retry codec/container incompatibility, not read or disk errors.
            if not any(term in str(exc).lower() for term in
                       ("not supported in", "not currently supported", "could not find tag for codec")):
                raise
            _run([*inputs, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-fps_mode", "passthrough", *mux, str(dest)], info.duration,
                 "호환 영상으로 변환 중 (H.264)", progress, cancelled)
