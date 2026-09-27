"""Offline DSP toolkit for Black Room's generated audio (numpy only - no scipy).

    from dsp import *

Everything here is written for OFFLINE rendering: filters are applied with a chunked
closed-form recursion (exact, but only valid on a whole buffer), so nothing in this file
is suitable for real-time use. The game only ever loads the rendered files.

Why this exists (see tools/design/open_issues.md §3): the first generation of sfx was
22050 Hz mono one-poles with no space around them. Sounds cheap by construction. This
module gives the generators 48 kHz, real envelopes, causal multi-stage filters, modal
(ring-modulated) resonances, a Freeverb-style room, and RMS-based levelling.
"""
from __future__ import annotations

import os
import subprocess
import wave

import numpy as np

SR = 48000


# =============================================================================
# Oscillators / noise
# =============================================================================

def t(sec: float, sr: int = SR) -> np.ndarray:
	return np.arange(int(sr * sec)) / sr


def osc(freq, sec: float, phase: float = 0.0, sr: int = SR) -> np.ndarray:
	"""Sine at a constant or per-sample frequency array (float or ndarray)."""
	n = int(sr * sec)
	f = np.full(n, float(freq)) if np.isscalar(freq) else np.asarray(freq, dtype=float)
	return np.sin(phase + 2 * np.pi * np.cumsum(f) / sr)


def noise(sec: float, seed: int = 0, sr: int = SR) -> np.ndarray:
	return np.random.default_rng(seed).uniform(-1.0, 1.0, int(sr * sec))


def drift(sec: float, rate: float, depth: float, seed: int = 0, sr: int = SR) -> np.ndarray:
	"""Slow smooth wander (for stick-slip wobble, tape-ish instability)."""
	n = int(sr * sec)
	w = np.random.default_rng(seed).uniform(-1.0, 1.0, n)
	k = max(2, int(sr / max(rate, 1e-3) / 8))
	kernel = np.hanning(k)
	kernel /= kernel.sum()
	return np.convolve(w, kernel, mode="same") * depth * 8.0


# =============================================================================
# Envelopes
# =============================================================================

def env(sec: float, attack: float, decay: float, sustain: float = 0.0, release: float = 0.0,
		curve: float = 3.0, sr: int = SR) -> np.ndarray:
	"""Exponential ADSR. `curve` shapes the decay (higher = faster collapse)."""
	n = int(sr * sec)
	a = min(n, max(1, int(attack * sr)))
	d = min(n - a, max(1, int(decay * sr))) if n > a else 0
	r = min(n - a - d, max(1, int(release * sr))) if release > 0 else 0
	s = max(0, n - a - d - r)
	out = np.zeros(n)
	out[:a] = np.linspace(0.0, 1.0, a) ** 0.6
	if d:
		out[a:a + d] = np.exp(-curve * np.linspace(0.0, 1.0, d)) * (1.0 - sustain) + sustain
	if s:
		out[a + d:a + d + s] = sustain
	if r:
		out[a + d + s:] = np.linspace(sustain, 0.0, len(out) - (a + d + s))
	return out


def swell(sec: float, peak_at: float = 0.7, sr: int = SR) -> np.ndarray:
	"""Rise then fall - reversed-cymbal / breath shapes."""
	n = int(sr * sec)
	k = int(n * peak_at)
	out = np.zeros(n)
	out[:k] = np.linspace(0.0, 1.0, k) ** 2.2
	out[k:] = np.linspace(1.0, 0.0, n - k) ** 0.8
	return out


# =============================================================================
# Filters
# =============================================================================
# Zero-phase magnitude shaping in the frequency domain. Offline rendering only, but it
# is exact at any cutoff, needs no recursion, and every buffer here starts and ends at
# silence, so the circular tail has nothing to wrap into. `slope` counts one-pole
# equivalents: slope=2 is about -12 dB/oct.

def shape(x: np.ndarray, lo: float | None = None, hi: float | None = None, slope: float = 2.0,
		sr: int = SR) -> np.ndarray:
	n = len(x)
	f = np.fft.rfftfreq(n, 1.0 / sr)
	f[0] = 1.0
	h = np.ones_like(f)
	if hi is not None:
		h /= np.sqrt(1.0 + (f / float(hi)) ** (2.0 * slope))
	if lo is not None:
		h /= np.sqrt(1.0 + (float(lo) / f) ** (2.0 * slope))
	h[0] = 0.0
	return np.fft.irfft(np.fft.rfft(x) * h, n)


def onepole(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
	return shape(x, hi=cutoff, slope=1.0, sr=sr)


def lowpass(x: np.ndarray, cutoff: float, stages: float = 2, sr: int = SR) -> np.ndarray:
	return shape(x, hi=cutoff, slope=float(stages), sr=sr)


def highpass(x: np.ndarray, cutoff: float, stages: float = 2, sr: int = SR) -> np.ndarray:
	return shape(x, lo=cutoff, slope=float(stages), sr=sr)


def bandpass(x: np.ndarray, lo: float, hi: float, stages: float = 2, sr: int = SR) -> np.ndarray:
	return shape(x, lo=lo, hi=hi, slope=float(stages), sr=sr)


def _freqs(f) -> list:
	return list(f) if isinstance(f, (list, tuple)) else [f]


def modal(drive: np.ndarray, freqs, decay: float, seed: int = 0, sr: int = SR) -> np.ndarray:
	"""Ring-modulated resonance bank: excitation * a sum of sine modes.

	This is how the creaks, metal knocks and growls get a body without biquads: the
	excitation carries the envelope, the modes carry the timbre. `freqs` entries may be
	per-sample arrays (drifting modes).
	"""
	out = np.zeros_like(drive)
	n = len(drive)
	for i, f in enumerate(_freqs(freqs)):
		if np.isscalar(f):
			fv = np.full(n, float(f) * (1.0 + 0.002 * i))
		else:
			fv = np.asarray(f, dtype=float).ravel() * (1.0 + 0.002 * i)
			fv = np.resize(fv, n)
		out += np.sin(i * 1.7 + 2.0 * np.pi * np.cumsum(fv) / sr) * (1.0 / (1.0 + 0.5 * i))
	return out * drive * decay


# =============================================================================
# Room (Freeverb-style: 8 damped combs -> 4 allpasses)
# =============================================================================

_COMB = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
_ALLPASS = [556, 441, 341, 225]


def _comb(x: np.ndarray, d: int, g: float) -> np.ndarray:
	out = x.copy()
	n = len(out)
	for start in range(d, n, d):
		stop = min(start + d, n)
		out[start:stop] = out[start:stop] + g * out[start - d:start - d + (stop - start)]
	return out


def _allpass(x: np.ndarray, d: int, g: float) -> np.ndarray:
	out = np.zeros_like(x)
	n = len(out)
	for start in range(0, n, d):
		stop = min(start + d, n)
		seg = out[start:stop] + x[start:stop] * -g
		if start >= d:
			seg = seg + x[start - d:start - d + (stop - start)] + g * out[start - d:start - d + (stop - start)]
		out[start:stop] = seg
	return out


def reverb(x: np.ndarray, wet: float = 0.25, room: float = 0.8, damp: float = 3800.0,
		spread: int = 0, sr: int = SR) -> np.ndarray:
	"""Returns the WET signal only (mix it yourself, keeps the dry signal intact)."""
	if wet <= 0.0:
		return np.zeros_like(x)
	scale = sr / 44100.0
	acc = np.zeros_like(x)
	for i, base in enumerate(_COMB):
		d = int(base * scale) + spread
		g = min(0.93, 0.70 + 0.22 * room + 0.01 * (i % 3))
		acc += _comb(x, d, g)
	acc /= len(_COMB)
	acc = onepole(acc, damp, sr)
	for i, base in enumerate(_ALLPASS):
		acc = _allpass(acc, int(base * scale) + spread, 0.5 - 0.03 * i)
	return acc * wet


# =============================================================================
# Stereo / loop / level
# =============================================================================

def widen(x: np.ndarray, width: float = 0.6, decorrelate_ms: float = 7.0, seed: int = 3,
		sr: int = SR) -> np.ndarray:
	"""Mono -> (n, 2). The right channel gets its own tail, so the bed breathes."""
	delay = int(decorrelate_ms / 1000.0 * sr)
	r = np.concatenate([np.zeros(delay), x[:-delay]]) if delay > 0 else x.copy()
	r = r * (1.0 - 0.06 * width) + reverb(x, 0.18 * width, 0.85, 3200.0, spread=37, sr=sr)[:len(x)]
	l = x * (1.0 + 0.03 * width)
	return np.stack([l, r], axis=1)


def loop_crossfade(x: np.ndarray, fade: float = 2.5, sr: int = SR) -> np.ndarray:
	"""Fold the tail of `x` back over its head so the loop has no seam."""
	n = len(x)
	f = min(int(fade * sr), n // 3)
	if f <= 1:
		return x
	head, tail = x[:f].copy(), x[n - f:].copy()
	ramp = np.linspace(0.0, 1.0, f)
	if x.ndim == 2:
		ramp = ramp[:, None]
	x = x[:n - f].copy()
	x[:f] = head * ramp + tail * (1.0 - ramp)
	return x


def level(x: np.ndarray, lufs_like: float = -18.0) -> np.ndarray:
	"""RMS levelling with a true-peak safety net (replaces the old double normalise)."""
	rms = float(np.sqrt(np.mean(x ** 2))) or 1e-9
	x = x * (10.0 ** (lufs_like / 20.0) / rms)
	peak = float(np.max(np.abs(x))) or 1e-9
	if peak > 0.89:
		x = x * (0.89 / peak)
	return x


def fades(x: np.ndarray, ms: float = 4.0, sr: int = SR) -> np.ndarray:
	f = max(1, int(ms / 1000.0 * sr))
	f = min(f, len(x) // 3)
	if f <= 1:
		return x
	ramp = np.linspace(0.0, 1.0, f)
	if x.ndim == 2:
		ramp = ramp[:, None]
	x[:f] *= ramp
	x[-f:] *= ramp[::-1]
	return x


# =============================================================================
# Output
# =============================================================================

def write_wav(path: str, x: np.ndarray, sr: int = SR) -> None:
	"""1-D input stays MONO (positional 2D/3D sources must stay mono so panning works);
	2-D input is written as stereo (music / ambience beds only)."""
	os.makedirs(os.path.dirname(path), exist_ok=True)
	pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
	channels = 1 if x.ndim == 1 else pcm.shape[1]
	if x.ndim == 1:
		pcm = pcm.reshape(-1, 1)
	with wave.open(path, "wb") as w:
		w.setnchannels(channels)
		w.setsampwidth(2)
		w.setframerate(sr)
		w.writeframes(pcm.tobytes())


def write_ogg(path: str, x: np.ndarray, quality: int = 5, sr: int = SR) -> bool:
	"""Vorbis encode via ffmpeg (music beds only: loopable and ~40x smaller)."""
	os.makedirs(os.path.dirname(path), exist_ok=True)
	raw = path + ".tmp.wav"
	write_wav(raw, x, sr)
	try:
		subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
			"-c:a", "libvorbis", "-q:a", str(quality), path], check=True)
	finally:
		if os.path.exists(raw):
			os.remove(raw)
	return os.path.exists(path)


def wav_stats(path: str) -> str:
	with wave.open(path) as w:
		return "%d Hz  %dch  %.2fs  %d KB" % (w.getframerate(), w.getnchannels(),
			w.getnframes() / w.getframerate(), os.path.getsize(path) / 1024)
