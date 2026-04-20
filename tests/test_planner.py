"""Tests for beatsync.planner."""

from __future__ import annotations

import numpy as np

from beatsync.planner import CutPlan, CutTrigger, SnapType, SourceLabel, plan_cuts


def _beat_grid(bpm: float, duration_s: float) -> np.ndarray:
    interval_ms = 60000.0 / bpm
    num = int(duration_s * 1000.0 / interval_ms) + 1
    return np.arange(num, dtype=np.float64) * interval_ms


def test_cut_frequency_point_six_roughly_matches() -> None:
    beat_grid = _beat_grid(120.0, 30.0)
    bass_onsets = np.array([], dtype=np.float64)
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=bass_onsets,
        edit_length_ms=30000,
        cut_frequency=0.6,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps=4,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=42,
    )
    assert isinstance(plan, CutPlan)
    # With 2000ms min segment, 120 BPM (500ms beats), max ~15 segments in 30s.
    assert 5 <= len(plan.segments) <= 15
    assert plan.segments[0].start_ms == 0
    assert plan.segments[-1].end_ms == 30000
    for a, b in zip(plan.segments, plan.segments[1:], strict=False):
        assert a.end_ms == b.start_ms


def test_cut_frequency_zero_single_segment() -> None:
    beat_grid = _beat_grid(120.0, 30.0)
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=np.array([], dtype=np.float64),
        edit_length_ms=30000,
        cut_frequency=0.0,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps=4,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=42,
    )
    assert len(plan.segments) == 1
    assert plan.segments[0].start_ms == 0
    assert plan.segments[0].end_ms == 30000


def test_cut_frequency_one_every_beat_in_window() -> None:
    beat_grid = _beat_grid(120.0, 30.0)
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=np.array([], dtype=np.float64),
        edit_length_ms=30000,
        cut_frequency=1.0,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps=4,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=42,
    )
    # With 2000ms min segment, max ~15 segments in 30s even at cut_frequency=1.0.
    assert 13 <= len(plan.segments) <= 16


def test_punch_mode_no_808_snaps() -> None:
    beat_grid = _beat_grid(135.0, 15.0)
    onsets = beat_grid + 20.0
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=onsets,
        edit_length_ms=15000,
        cut_frequency=0.6,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=50,
        tolerance_ms_high=70,
        max_bass_snaps=2,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=7,
        source_b_seconds=8,
        rng_seed=1,
    )
    assert all(seg.snap_type == SnapType.BEAT_GRID for seg in plan.segments)


def test_breathe_mode_snaps_to_808_within_tolerance() -> None:
    beat_grid = _beat_grid(128.0, 30.0)
    # Place onsets near beats that are well past the 2000ms minimum from each other.
    # At 128 BPM, beats are ~469ms apart. Beat index 5 = ~2344ms, index 10 = ~4688ms.
    onsets = np.array([beat_grid[5] + 40.0, beat_grid[10] - 30.0])
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=onsets,
        edit_length_ms=30000,
        cut_frequency=1.0,
        cut_trigger=CutTrigger.HYBRID,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps=4,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=1,
    )
    snap_count = sum(1 for s in plan.segments if s.snap_type == SnapType.BASS_808)
    assert snap_count >= 1


def test_max_bass_snaps_cap_enforced() -> None:
    beat_grid = _beat_grid(128.0, 30.0)
    onsets = beat_grid + 10.0
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=onsets,
        edit_length_ms=30000,
        cut_frequency=1.0,
        cut_trigger=CutTrigger.HYBRID,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps=3,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=1,
    )
    snap_count = sum(1 for s in plan.segments if s.snap_type == SnapType.BASS_808)
    assert snap_count <= 3


def test_max_consecutive_same_source_enforced() -> None:
    beat_grid = _beat_grid(120.0, 30.0)
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=np.array([], dtype=np.float64),
        edit_length_ms=30000,
        cut_frequency=1.0,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=50,
        tolerance_ms_high=70,
        max_bass_snaps=0,
        alternation_variation=1.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=1,
    )
    run_length = 1
    last_source = plan.segments[0].source
    for seg in plan.segments[1:]:
        if seg.source == last_source:
            run_length += 1
        else:
            run_length = 1
        last_source = seg.source
        assert run_length <= 2


def test_strict_alternation_no_variation() -> None:
    beat_grid = _beat_grid(120.0, 30.0)
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=np.array([], dtype=np.float64),
        edit_length_ms=30000,
        cut_frequency=1.0,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=50,
        tolerance_ms_high=70,
        max_bass_snaps=0,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=1,
    )
    for i, seg in enumerate(plan.segments):
        expected = SourceLabel.A if i % 2 == 0 else SourceLabel.B
        assert seg.source == expected


def test_minimum_segment_duration_enforced() -> None:
    # 180 BPM = 333ms between beats — well under the 2000ms minimum.
    beat_grid = _beat_grid(180.0, 30.0)
    plan = plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=np.array([], dtype=np.float64),
        edit_length_ms=30000,
        cut_frequency=1.0,
        cut_trigger=CutTrigger.BEAT_GRID,
        tolerance_ms_low=50,
        tolerance_ms_high=70,
        max_bass_snaps=0,
        alternation_variation=0.0,
        max_consecutive_same_source=2,
        source_a_seconds=15,
        source_b_seconds=15,
        rng_seed=1,
    )
    # Every segment must be at least 2000ms.
    for seg in plan.segments:
        assert seg.end_ms - seg.start_ms >= 2000, (
            f"Segment {seg.start_ms}-{seg.end_ms}ms is only "
            f"{seg.end_ms - seg.start_ms}ms (minimum 2000ms)"
        )
