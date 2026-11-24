import numpy as np
import pytest
import soundfile as sf

from demucs_gui import stem_mix


def render(tmp_path, mix, stem, strength, reduction, container="WAV"):
    source, target = tmp_path / "mix.wav", tmp_path / "stem.wav"
    sf.write(source, mix, 44100, subtype="FLOAT", format=container)
    sf.write(target, stem, 44100, subtype="FLOAT", format=container)
    reports = []
    stem_mix.apply_in_place(source, target, strength, reduction,
                            lambda value, _: reports.append(value), lambda: False)
    assert reports[-1] == 1 and reports == sorted(reports)
    np.testing.assert_array_equal(sf.read(source, dtype="float32")[0], mix)
    assert sf.info(target).frames == len(mix) and sf.info(target).format == container
    return sf.read(target, dtype="float32")[0]


@pytest.mark.parametrize(("length", "fmt"), [(1, "WAV"), (511, "RF64"), (512, "WAV"),
                                             (2049, "WAV"), (65537, "RF64")])
def test_clean_stereo_foreground_is_unchanged_at_maximum_reduction(tmp_path, length, fmt):
    samples = np.random.default_rng(7).normal(0, 0.15, size=(length, 2)).astype("float32")
    output = render(tmp_path, samples, samples, 100, 24, fmt)
    np.testing.assert_array_equal(output, samples)


def test_dry_wet_percent_is_a_linear_amplitude_blend(tmp_path):
    rng = np.random.default_rng(81)
    source = rng.normal(0, 0.15, size=(100003, 2)).astype("float32")
    stem = rng.normal(0, 0.10, size=source.shape).astype("float32")
    for db in (0, 18):
        full = render(tmp_path, source, stem, 100, db)
        partial = render(tmp_path, source, stem, 35, db)
        np.testing.assert_allclose(partial, 0.65 * source + 0.35 * full, atol=1e-7, rtol=0)


def test_residual_dominant_tone_is_cut_by_requested_db_with_linked_stereo_gain(tmp_path):
    # Both tones are active simultaneously. Bleed has opposite stereo polarity.
    x = np.arange(3 * 65536, dtype="float64")
    tones = np.column_stack((np.sin(x * 2*np.pi*32/2048), np.sin(x * 2*np.pi*137/2048)))
    mix = (tones @ [[0.25, 0.15], [0.40, -0.20]]).astype("float32")
    stem = (tones @ [[0.25, 0.15], [0.025, -0.0125]]).astype("float32")
    interior = slice(2048, -2048)
    for db in (6, 12, 24):
        result = render(tmp_path, mix, stem, 100, db)
        fitted = np.linalg.lstsq(tones[interior], result[interior], rcond=None)[0]
        np.testing.assert_allclose(fitted[0], [0.25, 0.15], atol=1e-5)
        np.testing.assert_allclose(fitted[1], np.array([0.025, -0.0125]) * 10**(-db/20), atol=1e-5)


def test_streaming_result_is_independent_of_io_block_edges(tmp_path, monkeypatch):
    rng = np.random.default_rng(257)
    mix = rng.normal(0, 0.1, size=(35033, 2)).astype("float32")
    stem = (0.05 * mix + rng.normal(0, 0.02, mix.shape)).astype("float32")
    large = render(tmp_path, mix, stem, 88, 20)
    monkeypatch.setattr(stem_mix, "_BLOCK", 4096)
    small = render(tmp_path, mix, stem, 88, 20)
    np.testing.assert_allclose(small, large, atol=2e-7, rtol=0)
    assert np.isfinite(small).all()


def test_quiet_harmonic_in_its_own_bins_responds_to_loud_surrounding_backing(tmp_path):
    t = np.arange(3 * 65536)
    # The estimate owns 100% of the harmonic at bin 100. Backing is 16 dB
    # stronger overall in a separate set of bins, like an isolated spill tone.
    harmonic = np.sin(t * 2 * np.pi * 100 / 2048)
    backing = np.sin(t * 2 * np.pi * 30 / 2048) * 10 ** (16 / 20)
    stem = np.column_stack((0.025 * harmonic, -0.015 * harmonic)).astype("float32")
    mix = stem + np.column_stack((0.025 * backing, 0.015 * backing)).astype("float32")
    core = slice(2048, -2048)
    for amount in (6, 24):
        output = render(tmp_path, mix, stem, 100, amount)
        # Halfway along the smooth 10–22 dB ramp, the cut is half the setting.
        np.testing.assert_allclose(output[core], stem[core] * 10 ** (-amount * .5 / 20),
                                   atol=1e-6, rtol=0)


def test_short_transient_uses_surrounding_backing_across_a_block_boundary(tmp_path, monkeypatch):
    frames = np.arange(32768)
    t = (frames - 12288) / 44100  # The transient peaks exactly on a small-block edge.
    burst = 0.18 * np.exp(-0.5 * (t / 0.008) ** 2) * np.sin(2 * np.pi * frames * 90 / 2048)
    backing = 0.24 * np.sin(2 * np.pi * frames * 32 / 2048)
    stem = np.column_stack((burst, -burst)).astype("float32")
    mix = stem + np.column_stack((backing, backing)).astype("float32")
    large = render(tmp_path, mix, stem, 100, 6)
    monkeypatch.setattr(stem_mix, "_BLOCK", 4096)
    small = render(tmp_path, mix, stem, 100, 6)
    np.testing.assert_allclose(small, large, atol=2e-7, rtol=0)
    core = np.abs(t) < 0.008
    change_db = 10 * np.log10(np.sum(small[core] ** 2) / np.sum(stem[core] ** 2))
    assert -6 <= change_db <= -1


def test_renderer_stops_between_blocks_without_modifying_original(tmp_path):
    mix = np.full((65543, 2), 0.2, dtype=np.float32)
    stem = np.full_like(mix, 0.01)
    source, target = tmp_path / "mix.wav", tmp_path / "stem.wav"
    sf.write(source, mix, 44100, subtype="FLOAT")
    sf.write(target, stem, 44100, subtype="FLOAT")
    reports = []
    with pytest.raises(InterruptedError):
        stem_mix.apply_in_place(source, target, 100, 24, lambda value, _: reports.append(value),
                                lambda: bool(reports))
    assert len(reports) == 1 and reports[0] < 1
    np.testing.assert_array_equal(sf.read(source, dtype="float32")[0], mix)
