from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from demucs_gui import pipeline
from demucs_gui.config import Options


@pytest.fixture
def job(tmp_path, monkeypatch):
    source = tmp_path / "원본.mp4"
    source.write_bytes(b"original")
    monkeypatch.setattr(pipeline.media, "probe", lambda path: SimpleNamespace(has_video=True))
    def decode(_source, dest, info, *_):
        dest.write_bytes(b"mix")
        return info

    monkeypatch.setattr(pipeline.media, "decode", decode)

    def separate(_mix, folder, *_):
        result = {key: folder / f"{key}.wav" for key in ("vocals", "accompaniment")}
        for key, path in result.items():
            path.write_bytes(key.encode())
        return result

    monkeypatch.setattr(pipeline.engine, "separate", separate)
    monkeypatch.setattr(pipeline.media, "export",
                        lambda _src, stem, dst, *_: dst.write_bytes(stem.read_bytes()))
    return source


def run(source, cancelled=lambda: False):
    return pipeline.process_file(source, Options(bleed_reduction_db=0), lambda *_: None, cancelled)


def test_simultaneous_jobs_publish_separate_complete_sets(job):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [job, job]))
    assert results[0]["vocals"].parent != results[1]["vocals"].parent
    for outputs in results:
        assert [path.read_bytes() for path in outputs.values()] == [b"vocals", b"accompaniment"]
        assert outputs["vocals"].name == "원본_vocals.wav"
    assert job.read_bytes() == b"original"


@pytest.mark.parametrize("kind,quality", [("audio", "24"), ("video", "320")])
def test_zero_strength_exports_original_for_every_selected_stem(job, monkeypatch, kind, quality):
    def unexpected(*_):
        pytest.fail("0% strength should skip inference and bleed reduction")

    monkeypatch.setattr(pipeline.engine, "separate", unexpected)
    monkeypatch.setattr(pipeline.stem_mix, "apply_in_place", unexpected)
    options = Options(model="htdemucs_6s", stem_mode="6", separation_strength=0, bleed_reduction_db=24,
                      output_kind=kind, quality=quality)
    result = pipeline.process_file(job, options, lambda *_: None, lambda: False)
    assert set(result) == set(pipeline.STEMS["6"])
    assert all(path.read_bytes() == b"mix" for path in result.values())
    assert all(path.suffix == (".mp4" if kind == "video" else ".wav") for path in result.values())


def test_file_keeps_its_own_options_snapshot(job, monkeypatch):
    options = Options(selected_stem="vocals", separation_strength=42, bleed_reduction_db=13)
    called = []

    def render(_mix, _stem, strength, reduction, *_):
        called.append((strength, reduction))

    def progress(*_):
        options.separation_strength = 0
        options.bleed_reduction_db = 24
        options.selected_stem = "accompaniment"

    monkeypatch.setattr(pipeline.stem_mix, "apply_in_place", render)
    outputs = pipeline.process_file(job, options, progress, lambda: False)
    assert called == [(42, 13)] and list(outputs) == ["vocals"]


@pytest.mark.parametrize("cancel", [True, False])
def test_incomplete_set_discarded_on_cancel_or_export_error(job, monkeypatch, cancel):
    base = job.parent / "separated"
    previous = base / job.stem
    previous.mkdir(parents=True)
    old = previous / "old.wav"
    old.write_bytes(b"previous")
    finished_one = False

    def export(_source, stem, destination, *_):
        nonlocal finished_one
        if finished_one:
            raise OSError("disk full")
        destination.write_bytes(stem.read_bytes())
        finished_one = True

    monkeypatch.setattr(pipeline.media, "export", export)
    with pytest.raises(InterruptedError if cancel else OSError):
        run(job, lambda: cancel and finished_one)
    assert list(base.iterdir()) == [previous]
    assert old.read_bytes() == b"previous"
    assert job.read_bytes() == b"original"
