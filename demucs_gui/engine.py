"""Local, bounded-memory inference using the Demucs 4.0.1 Python API."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Callable
from urllib.request import urlopen


Progress = Callable[[float, str], None]
Cancellation = Callable[[], bool]
SAMPLE_RATE = 44100
FOUR_SOURCES = ("drums", "bass", "other", "vocals")
SUPPORTED_MODELS = {"htdemucs", "htdemucs_ft", "htdemucs_6s", "mdx_extra"}


def _check_cancel(cancelled: Cancellation) -> None:
    if cancelled():
        raise InterruptedError("분리를 취소했습니다.")


def _stem_groups(options):
    if options.model not in SUPPORTED_MODELS:
        raise ValueError(f"지원하지 않는 모델입니다. {options.model}")
    sources = FOUR_SOURCES
    if options.model == "htdemucs_6s":
        sources += ("guitar", "piano")
    mode = str(options.stem_mode)
    if mode == "2":
        groups = {"vocals": ("vocals",),
                  "accompaniment": tuple(s for s in sources if s != "vocals")}
    elif mode == "4":
        groups = {s: (s,) for s in FOUR_SOURCES}
        groups["other"] += sources[4:]
    elif mode == "6" and len(sources) == 6:
        groups = {s: (s,) for s in sources}
    else:
        raise ValueError("선택한 모델과 스템 수의 조합을 지원하지 않습니다.")
    selected = "vocals" if options.vocals_only else options.selected_stem
    if selected != "all":
        if selected not in groups:
            raise ValueError(f"현재 설정에서 저장할 수 없는 스템입니다. {selected}")
        groups = {selected: groups[selected]}
    return sources, groups


def _cached(path: Path, checksum: str, cancelled: Cancellation) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            _check_cancel(cancelled)
            digest.update(block)
    return digest.hexdigest().startswith(checksum)


def _checkpoint(url: str, cache: Path, notify, cancelled: Cancellation) -> Path:
    """Publish a verified file atomically, including when two jobs download it."""
    filename = url.rsplit("/", 1)[-1]
    destination = cache / filename
    expected = destination.stem.split("-")[1]
    if _cached(destination, expected, cancelled):
        return destination

    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    temporary = None
    try:
        notify(0.0, "모델 다운로드 연결 중")
        with urlopen(url, timeout=20) as response:
            length = int(response.headers.get("Content-Length") or 0)
            with tempfile.NamedTemporaryFile(dir=cache, suffix=".part", delete=False) as stream:
                temporary = Path(stream.name)
                received = 0
                while block := response.read(1024 * 1024):
                    _check_cancel(cancelled)
                    stream.write(block)
                    digest.update(block)
                    received += len(block)
                    fraction = min(1.0, received / length) if length else 0.0
                    amount = f"{received / 2**20:.0f} MB"
                    if length:
                        amount = f"{fraction:.0%} · {amount}"
                    notify(fraction, f"모델 다운로드 {amount}")
        if not digest.hexdigest().startswith(expected):
            raise RuntimeError(f"다운로드한 모델의 체크섬이 일치하지 않습니다. {filename}")
        _check_cancel(cancelled)
        try:
            temporary.replace(destination)
        except PermissionError:
            # Another Windows instance may already be loading its verified copy.
            if not _cached(destination, expected, cancelled):
                raise
        return destination
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _load_ensemble(options, sources, groups, device, progress, cancelled):
    import torch
    import yaml
    from demucs.pretrained import REMOTE_ROOT, _parse_remote_files
    from demucs.states import load_model

    manifest = yaml.safe_load((REMOTE_ROOT / f"{options.model}.yaml").read_text(encoding="utf-8"))
    urls = _parse_remote_files(REMOTE_ROOT / "files.txt")
    signatures = manifest["models"]
    weights = manifest.get("weights", [[1.0] * len(sources) for _ in signatures])
    totals = [sum(column) for column in zip(*weights)]
    selected = {s for group in groups.values() for s in group}
    # Each htdemucs_ft checkpoint contributes to exactly one stem.
    needed = [(sig, row) for sig, row in zip(signatures, weights)
              if any(w and s in selected for s, w in zip(sources, row))]
    ensemble = []
    cache = Path(torch.hub.get_dir()) / "checkpoints"
    for index, (sig, row) in enumerate(needed):
        _check_cancel(cancelled)

        def notify(fraction, message):
            ratio = (index + fraction) / len(needed)
            progress(0.04 * ratio, f"{message} ({index + 1}/{len(needed)})")

        notify(0, "모델 확인 중")
        path = _checkpoint(urls[sig], cache, notify, cancelled)
        # Official Demucs checkpoints contain the model class and constructor arguments.
        model = load_model(torch.load(path, map_location="cpu", weights_only=False)).eval()
        if (set(model.sources) != set(sources) or model.samplerate != SAMPLE_RATE
                or model.audio_channels != 2):
            raise RuntimeError("모델의 스템 구성 또는 오디오 규격이 예상과 다릅니다.")
        mix = []
        for group in groups.values():
            mix.append([row[i] / totals[i] if s in group else 0.0
                        for i, s in enumerate(model.sources)])
        ensemble.append((model.to(device), torch.tensor(mix, dtype=torch.float32, device=device)))
    return ensemble


def _normalization(source, progress, cancelled):
    """Compute the full-track mono mean and std while retaining one block."""
    import numpy as np

    total = squared = 0.0
    for block in source.blocks(blocksize=SAMPLE_RATE * 10, dtype="float32", always_2d=True):
        _check_cancel(cancelled)
        mono = block.mean(axis=1, dtype=np.float64)
        total += mono.sum()
        squared += np.square(mono).sum()
        progress(0.04 + 0.04 * source.tell() / source.frames, "오디오 레벨 분석 중")
    count = source.frames
    mean = total / count
    variance = max(0.0, (squared - total * mean) / max(1, count - 1))
    deviation = variance ** 0.5
    if not np.isfinite(mean) or not np.isfinite(deviation):
        raise ValueError("입력 오디오에 유효하지 않은 샘플이 있습니다.")
    return mean, deviation if deviation > 1e-8 else 1.0


def _overlap_add(source, writers, window, overlap, predict, cancelled):
    """Crossfade model windows and immediately flush finalized stereo samples."""
    import numpy as np

    length = source.frames
    window = min(window, length)
    hop = max(1, int(window * (1 - overlap)))
    indices = np.arange(window, dtype=np.float32)
    weights = np.minimum(indices + 1, window - indices)
    weights /= weights.max()
    accumulated = np.zeros((len(writers), 2, window), dtype=np.float32)
    normalizer = np.zeros(window, dtype=np.float32)
    start = 0
    while True:
        _check_cancel(cancelled)
        source.seek(start)
        audio = source.read(window, dtype="float32", always_2d=True)
        if audio.shape != (window, 2):
            raise RuntimeError("디코딩된 오디오의 샘플 수가 헤더와 다릅니다.")
        end = start + window
        finished = end == length
        # Anchor the final full window to EOF to preserve context at the tail.
        flush = window if finished else min(hop, length - end)
        estimates = predict(audio, start, flush)
        if estimates.shape != accumulated.shape or not np.isfinite(estimates).all():
            raise RuntimeError("모델 출력의 샘플 수 또는 값이 올바르지 않습니다.")
        accumulated += estimates * weights
        normalizer += weights
        for writer, stem in zip(writers, accumulated):
            writer.write((stem[:, :flush] / normalizer[:flush]).T)
        if finished:
            return
        keep = window - flush
        accumulated[:, :, :keep] = accumulated[:, :, flush:]
        normalizer[:keep] = normalizer[flush:]
        accumulated[:, :, keep:] = 0
        normalizer[keep:] = 0
        start += flush


def separate(input_pcm: Path, work_dir: Path, options, progress: Progress,
             cancelled: Cancellation) -> dict[str, Path]:
    """Separate stereo 44.1 kHz PCM. Progress is fractional and paths are temporary."""
    _check_cancel(cancelled)
    import soundfile as sf
    import torch
    from demucs.apply import apply_model

    sources, groups = _stem_groups(options)
    if not 0 <= options.shifts <= 10 or not 0 <= options.overlap <= 0.99:
        raise ValueError("Shifts 또는 Overlap이 지원 범위를 벗어났습니다.")
    device = options.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU를 사용할 수 없습니다. 자동 또는 CPU를 선택해 주세요.")
    if device not in {"cuda", "cpu"}:
        raise ValueError(f"지원하지 않는 장치입니다. {device}")
    if device == "cpu":
        torch.set_num_threads(min(8, max(1, (os.cpu_count() or 2) // 2)))
    label = f"GPU · {torch.cuda.get_device_name()}" if device == "cuda" else "CPU"
    progress(0.0, f"{label} · 모델 준비 중")
    with sf.SoundFile(input_pcm) as source:
        if source.frames <= 0 or source.channels != 2 or source.samplerate != SAMPLE_RATE:
            raise ValueError("44.1 kHz 스테레오 PCM 입력이 필요합니다.")
        ensemble = _load_ensemble(options, sources, groups, device, progress, cancelled)
        mean, std = _normalization(source, progress, cancelled)
        seconds = min(8.0, *(float(model.segment) for model, _ in ensemble))
        # The Demucs shift trick adds up to half a second before the forward pass.
        window = int(SAMPLE_RATE * seconds) - (SAMPLE_RATE // 2 if options.shifts else 0)
        repeats = max(1, options.shifts)
        dc = torch.tensor([len(group) * mean for group in groups.values()],
                          dtype=torch.float32, device=device).reshape(-1, 1, 1)

        @torch.inference_mode()
        def predict(audio, start, flush):
            mix = torch.from_numpy(audio.T.copy()).to(device)
            mix.sub_(mean).div_(std)
            result = torch.zeros((len(groups), 2 * len(audio)), device=device)
            steps = len(ensemble) * repeats
            done = 0
            for model, matrix in ensemble:
                for _ in range(repeats):
                    _check_cancel(cancelled)
                    stems = apply_model(model, mix[None], shifts=int(options.shifts > 0),
                                        split=False, device=device)[0]
                    result.addmm_(matrix, stems.flatten(1))
                    done += 1
                    completed = (start + flush * done / steps) / source.frames
                    progress(0.08 + 0.92 * completed, f"{label} · 스템 분리 중")
            shaped = result.view(len(groups), 2, len(audio))
            return shaped.mul_(std / repeats).add_(dc).cpu().numpy()

        work_dir.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="stems-", dir=work_dir))
        paths = {name: folder / f"{name}.wav" for name in groups}
        fmt = "RF64" if source.frames * 8 + 4096 >= 2**32 else "WAV"
        try:
            with ExitStack() as stack:
                writers = [stack.enter_context(sf.SoundFile(path, "w", SAMPLE_RATE, 2,
                                                            subtype="FLOAT", format=fmt))
                           for path in paths.values()]
                _overlap_add(source, writers, window, options.overlap, predict, cancelled)
                _check_cancel(cancelled)
                if any(writer.tell() != source.frames for writer in writers):
                    raise RuntimeError("완성된 스템의 샘플 수가 입력과 다릅니다.")
        except BaseException:
            for path in paths.values():
                path.unlink(missing_ok=True)
            folder.rmdir()
            raise
    return paths
