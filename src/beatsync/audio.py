"""Audio analysis: BPM detection, beat grid, sub-bass onset detection."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import librosa
import numpy as np
from scipy.signal import butter, sosfilt

SILENCE_GAP_THRESHOLD_MS: float = 2000.0


@dataclass(frozen=True)
class SilenceGap:
    """A stretch of the timeline with no detected beat hits."""

    start_ms: float
    end_ms: float

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class AudioAnalysis:
    """Result of analyzing an audio track."""

    bpm: float
    beat_times_ms: np.ndarray
    bass_onset_times_ms: np.ndarray


def detect_silence_gaps(
    beat_times_ms: np.ndarray,
    edit_length_ms: float,
    threshold_ms: float = SILENCE_GAP_THRESHOLD_MS,
) -> list[SilenceGap]:
    """Return stretches longer than threshold_ms with no detected beats.

    Covers leading silence (0 to first beat), inter-beat gaps, and trailing
    silence. The engine holds the current clip through these rather than
    cutting into them.
    """
    if edit_length_ms <= 0:
        return []
    if beat_times_ms.size == 0:
        return [SilenceGap(start_ms=0.0, end_ms=float(edit_length_ms))]
    bounded = np.concatenate(([0.0], beat_times_ms.astype(np.float64), [float(edit_length_ms)]))
    gaps: list[SilenceGap] = []
    for start, end in pairwise(bounded):
        if end - start > threshold_ms:
            gaps.append(SilenceGap(start_ms=float(start), end_ms=float(end)))
    return gaps


def _clamp_bpm_to_range(bpm: float, low: float = 60.0, high: float = 180.0) -> float:
    """Halve or double a BPM value until it's in the target range."""
    while bpm > high:
        bpm /= 2.0
    while bpm < low:
        bpm *= 2.0
    return bpm


def analyze_audio(
    y: np.ndarray,
    sr: int,
    bpm_override: float,
    bass_hit_amplitude_threshold: float,
) -> AudioAnalysis:
    """Analyze an audio signal and return BPM, beat grid, and sub-bass onsets."""
    if bpm_override > 0:
        bpm = bpm_override
        beat_times_ms = _metronomic_beat_grid(bpm, y.shape[0] / sr)
    elif y.size == 0 or float(np.max(np.abs(y))) < 1e-6:
        bpm = 120.0
        beat_times_ms = np.array([], dtype=np.float64)
    else:
        # tightness=80 is looser than librosa's default of 100, which gives
        # trap and hip-hop beats more room to breathe around the grid.
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=120.0, tightness=80)
        tempo_arr = np.atleast_1d(tempo)
        raw_bpm = float(tempo_arr[0])
        bpm = _clamp_bpm_to_range(raw_bpm)
        beat_times_s = librosa.frames_to_time(beat_frames, sr=sr)
        beat_times_ms = (beat_times_s * 1000.0).astype(np.float64)

    bass_onset_times_ms = _detect_sub_bass_onsets(y, sr, bass_hit_amplitude_threshold)

    return AudioAnalysis(
        bpm=bpm,
        beat_times_ms=beat_times_ms,
        bass_onset_times_ms=bass_onset_times_ms,
    )


def _metronomic_beat_grid(bpm: float, duration_s: float) -> np.ndarray:
    """Generate evenly spaced beat timestamps (ms) at the given BPM."""
    interval_ms = 60000.0 / bpm
    num_beats = int(duration_s * 1000.0 / interval_ms) + 1
    return np.arange(num_beats, dtype=np.float64) * interval_ms


def _detect_sub_bass_onsets(y: np.ndarray, sr: int, amplitude_threshold: float) -> np.ndarray:
    """Bandpass filter the signal below 150 Hz and detect onset attacks."""
    if y.size == 0:
        return np.array([], dtype=np.float64)
    sos = butter(4, [20.0, 150.0], btype="band", fs=sr, output="sos")
    y_bass = sosfilt(sos, y).astype(np.float32)
    onset_env = librosa.onset.onset_strength(y=y_bass, sr=sr)
    if onset_env.size == 0 or onset_env.max() == 0:
        return np.array([], dtype=np.float64)
    onset_frames = librosa.onset.onset_detect(
        y=y_bass,
        sr=sr,
        onset_envelope=onset_env,
        backtrack=False,
        wait=10,
        delta=0.07,
    )
    if onset_frames.size == 0:
        return np.array([], dtype=np.float64)
    # Very quiet bass signals can still normalize to 1.0 and produce false
    # positives, so gate on absolute RMS before the normalized comparison.
    signal_rms = float(np.sqrt(np.mean(y_bass**2)))
    if signal_rms < 0.01 and amplitude_threshold > 0:
        return np.array([], dtype=np.float64)
    normalized = onset_env / onset_env.max()
    kept = [f for f in onset_frames if normalized[f] >= amplitude_threshold]
    if not kept:
        return np.array([], dtype=np.float64)
    times_s: np.ndarray = librosa.frames_to_time(np.array(kept), sr=sr)
    return (times_s * 1000.0).astype(np.float64)
