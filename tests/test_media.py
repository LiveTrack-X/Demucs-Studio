import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from demucs_gui import media
from demucs_gui.config import Options


def progress(_fraction, _label):
    pass


def running():
    return False


def make_media(*args):
    subprocess.run([media._binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                    *map(str, args)], capture_output=True, check=True)


def metadata(path):
    result = subprocess.check_output([media._binary("ffprobe"), "-v", "error", "-show_streams",
                                      "-show_format", "-of", "json", str(path)])
    return json.loads(result)


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def test_native_sample_grid_and_quality(self):
        # Chosen length crosses two resampling blocks and has fractional 44.1 kHz duration.
        count, rate = 300003, 48000
        signal = np.sin(np.arange(count) * (2 * np.pi * 700 / rate)) * 0.2
        source = self.dir / "원본.wav"
        sf.write(source, np.column_stack([signal, signal]), rate, subtype="PCM_24")
        info = media.probe(source)
        self.assertEqual(info.audio_frames, count)
        stem = self.dir / "decoded.wav"
        media.decode(source, stem, info, progress, running)
        self.assertEqual(sf.info(stem).samplerate, 44100)
        for fmt, quality, subtype in [("wav", "16", "PCM_16"), ("wav", "32f", "FLOAT"),
                                      ("flac", "24", "PCM_24"), ("flac", "16", "PCM_16")]:
            with self.subTest(fmt=fmt, quality=quality):
                dest = self.dir / f"stem-{quality}.{fmt}"
                media.export(source, stem, dest, info, Options(audio_format=fmt, quality=quality),
                             progress, running)
                result, output_rate = sf.read(dest)
                self.assertEqual((len(result), output_rate, sf.info(dest).subtype), (count, rate, subtype))
                np.testing.assert_allclose(result[128:-128, 0], signal[128:-128], atol=0.0005)

    def test_audio_codecs_and_bitrates(self):
        source = self.dir / "곡.wav"
        make_media("-f", "lavfi", "-i", "anoisesrc=sample_rate=44100:duration=4:seed=8",
                   "-ac", "2", source)
        info = media.probe(source)
        stem = self.dir / "stem.wav"
        media.decode(source, stem, info, progress, running)
        for fmt in ["mp3", "m4a"]:
            sizes = []
            for quality in ["128", "320"]:
                dest = self.dir / f"{quality}.{fmt}"
                media.export(source, stem, dest, info, Options(audio_format=fmt, quality=quality),
                             progress, running)
                stream = metadata(dest)["streams"][0]
                self.assertEqual(stream["codec_name"], "aac" if fmt == "m4a" else "mp3")
                self.assertLess(abs(float(stream["duration"]) - 4), 0.1)
                sizes.append(dest.stat().st_size)
            self.assertGreater(sizes[1], sizes[0] * 1.5)

    def test_aac_presentation_edit_excludes_codec_padding(self):
        source = self.dir / "입력.mp4"
        make_media("-f", "lavfi", "-i", "testsrc2=s=64x48:r=25:d=1", "-f", "lavfi", "-i",
                   "sine=sample_rate=48000:duration=1", "-c:v", "libx264", "-c:a", "aac", source)
        info = media.probe(source)
        self.assertEqual(info.audio_frames, 48000)
        stem = self.dir / "stem.wav"
        media.decode(source, stem, info, progress, running)
        self.assertEqual(sf.info(stem).frames, 44100)
        dest = self.dir / "out.wav"
        media.export(source, stem, dest, info, Options(), progress, running)
        self.assertEqual((sf.info(dest).frames, sf.info(dest).samplerate), (48000, 48000))

    def test_packet_gap_at_recording_join_keeps_original_timeline(self):
        # A dropped AAC packet leaves 21.3 ms of presentation time at 48 kHz.
        source = self.dir / "recording.m4a"
        make_media("-f", "lavfi", "-i", "sine=sample_rate=48000:duration=2",
                   "-af", "aselect='not(eq(n,30))'", "-c:a", "aac", source)
        info = media.probe(source)
        stem = self.dir / "decoded.wav"
        media.decode(source, stem, info, progress, running)
        self.assertEqual(info.audio_frames, 96000)
        self.assertEqual(sf.info(stem).frames, 88200)

    def test_aac_file_uses_adts_and_selected_bitrate(self):
        source = self.dir / "stereo.wav"
        rate, seconds = 44100, 8
        noise = np.random.default_rng(512).uniform(-0.4, 0.4, (rate * seconds, 2))
        sf.write(source, noise, rate)
        info = media.probe(source)
        for bitrate in (128, 320):
            with self.subTest(bitrate=bitrate):
                dest = self.dir / f"결과 {bitrate}.aac"
                media.export(source, source, dest, info, Options(audio_format="aac", quality=str(bitrate)),
                             progress, running)
                description = metadata(dest)
                self.assertEqual(description["format"]["format_name"], "aac")
                self.assertEqual(description["streams"][0]["codec_name"], "aac")
                # The ADTS sync word occupies the first 12 bits.
                with dest.open("rb") as stream:
                    self.assertEqual(int.from_bytes(stream.read(2), "big") >> 4, 0xFFF)
                pcm = subprocess.check_output([media._binary("ffmpeg"), "-v", "error", "-i", str(dest),
                                               "-map", "0:a:0", "-f", "s16le", "-"])
                duration = len(pcm) / (rate * 2 * 2)
                # ADTS stores complete AAC frames and has no end edit.
                self.assertAlmostEqual(duration, seconds, delta=2 * 1024 / rate)
                average_kbps = dest.stat().st_size * 8 / duration / 1000
                self.assertAlmostEqual(average_kbps, bitrate, delta=bitrate * 0.10)

    def test_mp3_gapless_native_length_is_counted_during_decoding(self):
        source = self.dir / "original.mp3"
        original = self.dir / "input.wav"
        count = 72341
        sf.write(original, np.zeros(count, dtype=np.float32), 48000)
        make_media("-i", original, "-c:a", "libmp3lame", "-b:a", "128k", source)
        info = media.probe(source)
        self.assertIsNone(info.audio_frames)
        stem = self.dir / "decoded.wav"
        info = media.decode(source, stem, info, progress, running)
        self.assertEqual(info.audio_frames, count)
        dest = self.dir / "export.flac"
        media.export(source, stem, dest, info, Options(audio_format="flac"), progress, running)
        self.assertEqual((sf.info(dest).frames, sf.info(dest).samplerate), (count, 48000))

    def test_video_retains_offset_tail_and_replaces_original_track(self):
        for late_audio in (True, False):
            source = self.dir / f"원본 {late_audio}.mkv"
            make_media("-itsoffset", "0" if late_audio else "0.36", "-f", "lavfi", "-i",
                       "testsrc2=s=64x48:r=25:d=1.8", "-itsoffset", "0.36" if late_audio else "0",
                       "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=44100",
                       "-c:v", "libx264", "-bf", "0", "-c:a", "pcm_s16le", "-output_ts_offset", "3", source)
            info = media.probe(source)
            self.assertGreaterEqual(min(info.audio_start, info.video_start), 3)
            self.assertAlmostEqual(info.duration, 1.8 if late_audio else 2.16, delta=0.001)
            stem = self.dir / f"새 음원 {late_audio}.wav"
            make_media("-f", "lavfi", "-i", "sine=frequency=1760:duration=1:sample_rate=44100",
                       "-ac", "2", stem)
            for fmt in ["mp4", "mkv"]:
                with self.subTest(late_audio=late_audio, fmt=fmt):
                    dest = self.dir / f"출력 {late_audio}.{fmt}"
                    opts = Options(output_kind="video", video_format=fmt, quality="192")
                    media.export(source, stem, dest, info, opts, progress, running)
                    out = media.probe(dest)
                    # Container reporting includes AAC encoder priming (one frame).
                    self.assertAlmostEqual(out.audio_start - out.video_start,
                                           info.audio_start - info.video_start, delta=0.025)
                    streams = metadata(dest)["streams"]
                    self.assertEqual([s["codec_name"] for s in streams], ["h264", "aac"])
                    def video_hash(path):
                        return subprocess.check_output([media._binary("ffmpeg"), "-loglevel", "error",
                            "-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "hash", "-"])
                    self.assertEqual(video_hash(source), video_hash(dest))
                    # Inspect decoded samples to establish that the exported track is the replacement.
                    samples = subprocess.check_output([media._binary("ffmpeg"), "-loglevel", "error",
                        "-i", str(dest), "-map", "0:a:0", "-ac", "1", "-f", "f32le", "-"])
                    audio = np.frombuffer(samples, np.float32)[5000:32000]
                    peak_hz = np.argmax(abs(np.fft.rfft(audio))) * 44100 / len(audio)
                    self.assertAlmostEqual(peak_hz, 1760, delta=3)

    def test_incompatible_video_codec_converts_to_mp4(self):
        source = self.dir / "lossless.mkv"
        make_media("-f", "lavfi", "-i", "testsrc2=s=64x48:r=10:d=0.5", "-f", "lavfi", "-i",
                   "sine=duration=0.5", "-c:v", "huffyuv", "-c:a", "pcm_s16le", source)
        info = media.probe(source)
        stem = self.dir / "stem.wav"
        media.decode(source, stem, info, progress, running)
        dest = self.dir / "result.mp4"
        media.export(source, stem, dest, info, Options(output_kind="video", quality="128"), progress, running)
        self.assertEqual(metadata(dest)["streams"][0]["codec_name"], "h264")

    def test_cancel_and_existing_outputs(self):
        source = self.dir / "input.wav"
        sf.write(source, np.zeros(88200, dtype="float32"), 44100)
        info = media.probe(source)
        original = source.read_bytes()
        with self.assertRaises(FileExistsError):
            media.decode(source, source, info, progress, running)
        self.assertEqual(source.read_bytes(), original)
        dest = self.dir / "cancel.wav"
        reports = []
        with self.assertRaises(InterruptedError):
            media.decode(source, dest, info, lambda f, label: reports.append(f), lambda: bool(reports))
        self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
