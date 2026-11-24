import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from demucs_gui import engine
from demucs_gui.config import Options


class EngineTests(unittest.TestCase):
    def test_crossfades_preserve_every_sample(self):
        for length, overlap in ((1, 0.99), (19, 0), (20, 0.25), (21, 0.50), (67, 0.99)):
            with self.subTest(length=length, overlap=overlap), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                data = np.random.default_rng(12).normal(size=(length, 2)).astype("float32")
                source_path, result_path = folder / "source.wav", folder / "stem.wav"
                sf.write(source_path, data, 44100, subtype="FLOAT")
                processed = []

                def identity(samples, position, flush):
                    self.assertLessEqual(len(samples), 20)
                    self.assertEqual(position, sum(processed))
                    processed.append(flush)
                    return samples.T[None]

                with sf.SoundFile(source_path) as source, sf.SoundFile(
                    result_path, "w", 44100, 2, subtype="FLOAT"
                ) as result:
                    engine._overlap_add(source, [result], 20, overlap, identity, lambda: False)
                output, _ = sf.read(result_path)
                np.testing.assert_allclose(output, data, atol=1e-6)
                self.assertEqual(sum(processed), length)

    def test_stem_selection_and_six_source_grouping(self):
        _, groups = engine._stem_groups(Options(model="htdemucs_6s", stem_mode="4",
                                                 selected_stem="other"))
        self.assertEqual(groups, {"other": ("other", "guitar", "piano")})
        _, groups = engine._stem_groups(Options(model="htdemucs_6s", selected_stem="accompaniment"))
        self.assertEqual(groups, {"accompaniment": ("drums", "bass", "other", "guitar", "piano")})
        for mode in ("2", "4", "6"):
            _, groups = engine._stem_groups(Options(model="htdemucs_6s", stem_mode=mode,
                                                     vocals_only=True))
            self.assertEqual(groups, {"vocals": ("vocals",)})

    def test_cancelled_or_corrupt_model_download_never_enters_cache(self):
        good = b"some model data"
        checksum = hashlib.sha256(good).hexdigest()[:8]
        url = f"https://models.example/sample-{checksum}.th"

        def response(payload):
            stream = io.BytesIO(payload)
            stream.headers = {"Content-Length": str(len(payload))}
            return stream

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            for payload, cancelled, error in [(b"bad", False, RuntimeError),
                                               (good, True, InterruptedError)]:
                with patch.object(engine, "urlopen", return_value=response(payload)):
                    with self.assertRaises(error):
                        engine._checkpoint(url, cache, lambda *_: None, lambda: cancelled)
                self.assertEqual(list(cache.iterdir()), [])
            with patch.object(engine, "urlopen", return_value=response(good)):
                path = engine._checkpoint(url, cache, lambda *_: None, lambda: False)
            with patch.object(engine, "urlopen", side_effect=AssertionError("unexpected download")):
                self.assertEqual(engine._checkpoint(url, cache, lambda *_: None, lambda: False), path)
            self.assertEqual(path.read_bytes(), good)

    def test_mid_separation_cancel_removes_partial_stems(self):
        import torch

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source, work = folder / "source.wav", folder / "work"
            samples = np.random.default_rng(2).normal(scale=0.1, size=(4096, 2))
            sf.write(source, samples, 44100, subtype="FLOAT")
            original = source.read_bytes()
            cancel = False

            def progress(fraction, message):
                nonlocal cancel
                cancel = fraction > 0.08

            model = SimpleNamespace(segment=0.04)
            ensemble = [(model, torch.ones((1, 1)))]
            with patch.object(engine, "_load_ensemble", return_value=ensemble), patch(
                "demucs.apply.apply_model", side_effect=lambda _, mix, **kwargs: mix[:, None]
            ):
                with self.assertRaises(InterruptedError):
                    engine.separate(source, work, Options(device="cpu", shifts=0, vocals_only=True),
                                    progress, lambda: cancel)
            self.assertEqual(list(work.iterdir()), [])
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
