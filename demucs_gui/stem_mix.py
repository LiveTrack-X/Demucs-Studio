"""Mix a separated stem with its source on the original model sample grid."""

from pathlib import Path
from typing import Callable

from .backend_i18n import msg


_WINDOW = 2048
_HOP = _WINDOW // 4
_CONTEXT_HOPS = 9  # 19 overlapping frames cover about 255 ms at 44.1 kHz.
_BLOCK = 65536  # An integer number of hops; working memory is independent of input length.


def _correction(mix, stem, window, amount_db):
    """Return the overlap-added change to the stem. Unity gain contributes exactly zero."""
    import numpy as np
    from scipy.fft import irfft, rfft
    from numpy.lib.stride_tricks import sliding_window_view

    def spectrum(samples):
        frames = sliding_window_view(samples, _WINDOW, axis=0)[::_HOP]
        return rfft(frames * window, axis=-1)

    target = spectrum(stem)
    other = spectrum(mix - stem)
    # Share one gain across L/R. Start reducing only when the other stems have
    # 6 dB more energy in this bin; reach the requested cut at 18 dB dominance.
    def stereo_power(bins):
        return np.sum(bins.real ** 2 + bins.imag ** 2, axis=1)

    def dominance(other_energy, target_energy, onset_db, span_db=12):
        difference = 10 * np.log10((other_energy + 1e-20) / (target_energy + 1e-20))
        ramp = np.clip((difference - onset_db) / span_db, 0, 1)
        return ramp * ramp * (3 - 2 * ramp)

    target_power, other_power = stereo_power(target), stereo_power(other)
    confidence = dominance(other_power, target_power, 6)
    # An isolated leakage harmonic can own its bin even when the surrounding
    # frame is almost entirely backing. Apply the frame cut only over 10–22 dB
    # of overall dominance. A genuinely quiet voice under loud music can also
    # be attenuated by this user-selected control.
    frame_target = target_power.sum(axis=1)
    frame_other = other_power.sum(axis=1)
    frame_confidence = dominance(frame_other, frame_target, 10)
    # A short target spike can mask its own backing in a single frame. For
    # spikes 3–9 dB above their local target energy, also consider the residual
    # dominance over the surrounding quarter second. Sustained foreground does
    # not activate this additional cut.
    width = 2 * _CONTEXT_HOPS + 1
    average = np.full(width, 1 / width, dtype="float32")
    local_target = np.convolve(frame_target, average, mode="same")
    local_other = np.convolve(frame_other, average, mode="same")
    spike = dominance(frame_target, local_target, 3, 6)
    contextual = spike * dominance(local_other, local_target, 6)
    np.maximum(confidence, np.maximum(frame_confidence, contextual)[:, None], out=confidence)
    delta_gain = np.expm1((-np.log(10) / 20 * amount_db) * confidence).astype("float32")
    changes = irfft(target * delta_gain[:, None, :], n=_WINDOW, axis=-1) * window

    result = np.zeros_like(stem)
    # Windows in each of these four groups do not overlap one another.
    overlaps = _WINDOW // _HOP
    for phase in range(overlaps):
        group = changes[phase::overlaps].transpose(0, 2, 1).reshape(-1, 2)
        offset = phase * _HOP
        result[offset:offset + len(group)] += group
    # Four overlapping periodic Hann analysis/synthesis windows have a constant
    # sum of squares of 3/2. The caller retains only fully overlapped samples.
    result *= 2 / 3
    return result


def apply_in_place(mix_path: Path, stem_path: Path, strength: int, reduction_db: int,
                   progress: Callable[[float, str], None], cancelled: Callable[[], bool]) -> None:
    """Update only a job's disposable FLOAT stem; keep the decoded mixture read-only."""
    import numpy as np
    import soundfile as sf

    label = msg("분리 강도와 잔여음 억제 적용 중")
    wet = np.float32(strength / 100)
    dry = np.float32(1 - strength / 100)
    halo = _WINDOW - _HOP + _CONTEXT_HOPS * _HOP
    window = np.hanning(_WINDOW + 1)[:-1].astype("float32")
    history = np.zeros((halo, 2), dtype="float32")
    with sf.SoundFile(mix_path) as mix, sf.SoundFile(stem_path, "r+") as stem:
        if (mix.frames != stem.frames or mix.frames < 1 or mix.channels != 2 or stem.channels != 2
                or mix.samplerate != stem.samplerate or stem.subtype != "FLOAT"):
            raise ValueError(msg("분리 음원과 원본의 샘플 형식 또는 길이가 일치하지 않습니다."))
        total = mix.frames
        for start in range(0, total, _BLOCK):
            if cancelled():
                raise InterruptedError(msg("작업을 취소했습니다."))
            count = min(_BLOCK, total - start)
            stem.seek(start)
            if reduction_db:
                # Every block uses the same global STFT grid. Retain original
                # stem history before overwriting its PCM in the scratch file.
                rounded = ((count + _HOP - 1) // _HOP) * _HOP
                length = rounded + 2 * halo
                stem_data = np.zeros((length, 2), dtype="float32")
                stem_data[:halo] = history
                available = min(total - start, rounded + halo)
                stem_data[halo:halo + available] = stem.read(available, dtype="float32")
                history[:] = stem_data[count:count + halo]
                mix_data = np.zeros_like(stem_data)
                left = max(0, start - halo)
                mix.seek(left)
                pos = halo + left - start
                frames = start + available - left
                mix_data[pos:pos + frames] = mix.read(frames, dtype="float32")
                core = slice(halo, halo + count)
                filtered = stem_data[core] + _correction(mix_data, stem_data, window, reduction_db)[core]
                original = mix_data[core]
            else:
                filtered = stem.read(count, dtype="float32")
                original = mix.read(count, dtype="float32")
            if strength < 100:
                filtered = dry * original + wet * filtered
            stem.seek(start)
            stem.write(filtered)
            progress((start + count) / total, label)
