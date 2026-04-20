"""Shared pytest fixtures for beatsync tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest


@dataclass
class ClickTrack:
    """A synthetic click track with known tempo and impulse positions."""

    signal: np.ndarray
    sample_rate: int
    bpm: float
    beat_times_s: np.ndarray


def _make_click_track(bpm: float, duration_s: float = 10.0, sr: int = 22050) -> ClickTrack:
    interval_s = 60.0 / bpm
    beat_times = np.arange(0.0, duration_s, interval_s)
    signal = np.zeros(int(sr * duration_s), dtype=np.float32)
    for t in beat_times:
        idx = int(t * sr)
        end = min(idx + 200, signal.shape[0])
        signal[idx:end] = (
            np.random.default_rng(42).standard_normal(end - idx).astype(np.float32) * 0.5
        )
    return ClickTrack(signal=signal, sample_rate=sr, bpm=bpm, beat_times_s=beat_times)


@pytest.fixture
def click_track_120() -> ClickTrack:
    """10-second 120 BPM click track."""
    return _make_click_track(120.0)


@pytest.fixture
def click_track_90() -> ClickTrack:
    """10-second 90 BPM click track."""
    return _make_click_track(90.0)


@pytest.fixture
def click_track_140() -> ClickTrack:
    """10-second 140 BPM click track."""
    return _make_click_track(140.0)


def make_bass_pulse_signal(
    pulse_times_s: list[float],
    amplitude: float = 0.8,
    duration_s: float = 10.0,
    sr: int = 22050,
) -> np.ndarray:
    """Generate a signal with low-frequency sine bursts at the given times."""
    signal = np.zeros(int(sr * duration_s), dtype=np.float32)
    burst_len = int(sr * 0.1)
    t = np.arange(burst_len) / sr
    burst = (amplitude * np.sin(2 * np.pi * 60.0 * t)).astype(np.float32)
    for pulse_t in pulse_times_s:
        idx = int(pulse_t * sr)
        end = min(idx + burst_len, signal.shape[0])
        signal[idx:end] += burst[: end - idx]
    return signal
