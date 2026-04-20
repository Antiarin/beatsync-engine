"""Tests for beatsync.audio."""

from __future__ import annotations

import numpy as np

from beatsync.audio import AudioAnalysis, analyze_audio, detect_silence_gaps
from tests.conftest import ClickTrack, make_bass_pulse_signal


def test_bpm_detection_120(click_track_120: ClickTrack) -> None:
    result = analyze_audio(
        y=click_track_120.signal,
        sr=click_track_120.sample_rate,
        bpm_override=0.0,
        bass_hit_amplitude_threshold=0.0,
    )
    assert isinstance(result, AudioAnalysis)
    assert abs(result.bpm - 120.0) < 5.0


def test_bpm_detection_90(click_track_90: ClickTrack) -> None:
    result = analyze_audio(
        y=click_track_90.signal,
        sr=click_track_90.sample_rate,
        bpm_override=0.0,
        bass_hit_amplitude_threshold=0.0,
    )
    assert abs(result.bpm - 90.0) < 5.0


def test_bpm_detection_140(click_track_140: ClickTrack) -> None:
    result = analyze_audio(
        y=click_track_140.signal,
        sr=click_track_140.sample_rate,
        bpm_override=0.0,
        bass_hit_amplitude_threshold=0.0,
    )
    assert abs(result.bpm - 140.0) < 5.0


def test_bpm_override_returns_exact_value(click_track_120: ClickTrack) -> None:
    result = analyze_audio(
        y=click_track_120.signal,
        sr=click_track_120.sample_rate,
        bpm_override=128.0,
        bass_hit_amplitude_threshold=0.0,
    )
    assert result.bpm == 128.0


def test_bpm_override_generates_metronomic_grid() -> None:
    sr = 22050
    duration_s = 10.0
    y = np.zeros(int(sr * duration_s), dtype=np.float32)
    result = analyze_audio(y=y, sr=sr, bpm_override=120.0, bass_hit_amplitude_threshold=0.0)
    assert result.beat_times_ms.size >= 20
    diffs = np.diff(result.beat_times_ms)
    assert np.allclose(diffs, 500.0, atol=1.0)


def test_silent_audio_no_crash() -> None:
    sr = 22050
    y = np.zeros(sr * 5, dtype=np.float32)
    result = analyze_audio(y=y, sr=sr, bpm_override=0.0, bass_hit_amplitude_threshold=0.5)
    assert result.bass_onset_times_ms.size == 0


def test_sub_bass_onsets_detected_at_known_positions() -> None:
    sr = 22050
    pulse_times = [1.0, 3.0, 5.5, 8.0]
    y = make_bass_pulse_signal(pulse_times, amplitude=1.0, duration_s=10.0, sr=sr)
    result = analyze_audio(y=y, sr=sr, bpm_override=120.0, bass_hit_amplitude_threshold=0.1)
    onset_s = result.bass_onset_times_ms / 1000.0
    for expected in pulse_times:
        nearest = min(onset_s, key=lambda o: abs(o - expected), default=None)
        assert nearest is not None
        assert abs(nearest - expected) < 0.2, f"pulse at {expected}s not detected"


def test_sub_bass_low_amplitude_filtered_out() -> None:
    sr = 22050
    pulse_times = [1.0, 3.0, 5.0]
    y = make_bass_pulse_signal(pulse_times, amplitude=0.05, duration_s=10.0, sr=sr)
    result = analyze_audio(y=y, sr=sr, bpm_override=120.0, bass_hit_amplitude_threshold=0.9)
    assert result.bass_onset_times_ms.size == 0


def test_detect_silence_gaps_flags_long_inter_beat_gap() -> None:
    """A 3s gap in the middle of a beat grid must surface as a silence gap."""
    beats = np.array([500.0, 1000.0, 1500.0, 5000.0, 5500.0, 6000.0])
    gaps = detect_silence_gaps(beats, edit_length_ms=7000.0)
    assert any(1500.0 <= g.start_ms <= 1500.0 and g.end_ms == 5000.0 for g in gaps)


def test_detect_silence_gaps_flags_leading_and_trailing_silence() -> None:
    """Gaps at the head and tail of the edit should also be reported."""
    beats = np.array([3000.0, 3500.0, 4000.0])
    gaps = detect_silence_gaps(beats, edit_length_ms=10000.0)
    # Leading 0→3000 and trailing 4000→10000 both exceed the 2s threshold.
    gap_pairs = [(g.start_ms, g.end_ms) for g in gaps]
    assert (0.0, 3000.0) in gap_pairs
    assert (4000.0, 10000.0) in gap_pairs


def test_detect_silence_gaps_empty_grid_one_long_gap() -> None:
    gaps = detect_silence_gaps(np.array([], dtype=np.float64), edit_length_ms=30000.0)
    assert len(gaps) == 1
    assert gaps[0].start_ms == 0.0
    assert gaps[0].end_ms == 30000.0


def test_detect_silence_gaps_dense_grid_none() -> None:
    """Beats spaced 500ms apart should produce zero silence gaps."""
    beats = np.arange(0.0, 10000.0, 500.0)
    gaps = detect_silence_gaps(beats, edit_length_ms=10000.0)
    assert gaps == []


def test_audio_offset_trimming_produces_correct_window() -> None:
    """Simulate the audio offset trim that __main__.py applies."""
    sr = 22050
    duration_s = 30.0
    y_full = np.zeros(int(sr * duration_s), dtype=np.float32)
    # Place clicks only between 14-29 seconds.
    for t in np.arange(14.0, 29.0, 0.5):
        idx = int(t * sr)
        end = min(idx + 200, y_full.shape[0])
        y_full[idx:end] = 0.5
    # Trim to 15s window starting at 14s (what __main__.py does).
    start_sample = int(14.0 * sr)
    end_sample = start_sample + int(15.0 * sr)
    y_trimmed = y_full[start_sample:end_sample]
    result = analyze_audio(y=y_trimmed, sr=sr, bpm_override=120.0, bass_hit_amplitude_threshold=0.0)
    # Trimmed signal should have beats and be 15s long.
    assert len(y_trimmed) == int(15.0 * sr)
    assert result.bpm == 120.0
    assert result.beat_times_ms.size >= 10
