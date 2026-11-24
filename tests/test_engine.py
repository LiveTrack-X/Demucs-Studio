import hashlib
import io
import random
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

    def test_seeded_ht_matches_official_full_bag_for_short_tail_and_grouped_stems(self):
        import torch
        from demucs.apply import BagOfModels, apply_model

        rate = 240
        seed = 6159
        self.addCleanup(random.setstate, random.getstate())

        class ContextModel(torch.nn.Module):
            sources = list(engine.FOUR_SOURCES)
            audio_channels = 2
            samplerate = rate
            segment = 0.20
            crosstransformer = SimpleNamespace(emb="sin", sin_random_shift=0)

            def __init__(self, index):
                super().__init__()
                self.scale = torch.nn.Parameter(torch.tensor((index + 1) / 4.0))

            def valid_length(self, size):
                return int(self.segment * self.samplerate)

            def forward(self, mix):
                # Context, local phase, edge padding and RNG all affect the reference.
                random.randrange(1)
                phase = torch.linspace(0.1, 0.9, mix.shape[-1])
                weighted = mix * phase + (mix * phase).mean(dim=-1, keepdim=True)
                return torch.stack([weighted * (self.scale + i) for i in range(4)], dim=1)

        signatures = ["f7e0c4bc", "d12395a8", "92cfc3b6", "04573f0d"]
        models = {sig: ContextModel(i) for i, sig in enumerate(signatures)}
        bag = BagOfModels(list(models.values()), torch.eye(4).tolist())

        def checkpoint(url, cache, notify, cancelled):
            return Path(url.rsplit("/", 1)[1].split("-")[0])

        for length, shifts, overlap, target in [
            (9, 1, 0.25, "vocals"), (541, 0, 0.25, "all"),
            (541, 3, 0.375, "all"), (541, 3, 0.375, "vocals"), (541, 3, 0.375, "accompaniment"),
        ]:
            with self.subTest(length=length, shifts=shifts, target=target), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                samples = np.random.default_rng(3).normal(0.2, 0.08, (length, 2)).astype("float32")
                source = folder / "input.wav"
                sf.write(source, samples, rate, subtype="FLOAT")
                wave = torch.from_numpy(samples.T.copy())
                mono = wave.mean(dim=0)
                normalized = (wave - mono.mean()) / mono.std()
                random.seed(seed)
                reference = apply_model(bag, normalized[None], shifts=shifts, overlap=overlap)[0]
                reference = reference * mono.std() + mono.mean()
                official_rng = random.getstate()
                expected = {"vocals": reference[3], "accompaniment": reference[:3].sum(dim=0)}

                options = Options(shifts=shifts, overlap=overlap, selected_stem=target, device="cpu")
                updates = []
                random.seed(seed)
                with patch.object(engine, "SAMPLE_RATE", rate), patch.object(engine, "_checkpoint", checkpoint), patch(
                    "torch.load", side_effect=lambda path, **kw: models[path.name]
                ) as loaded, patch("demucs.states.load_model", side_effect=lambda model: model):
                    paths = engine.separate(source, folder, options,
                                            lambda done, _: updates.append(done), lambda: False)
                self.assertEqual(random.getstate(), official_rng)
                self.assertEqual(loaded.call_count, {"vocals": 1, "accompaniment": 3, "all": 4}[target])
                self.assertEqual(updates, sorted(updates))
                self.assertEqual(updates[-1], 1.0)
                for stem, path in paths.items():
                    data, sample_rate = sf.read(path)
                    self.assertEqual(sample_rate, rate)
                    self.assertEqual(data.shape, samples.shape)
                    np.testing.assert_allclose(data.T, expected[stem].detach().numpy(), rtol=2e-5, atol=2e-6)


if __name__ == "__main__":
    unittest.main()
