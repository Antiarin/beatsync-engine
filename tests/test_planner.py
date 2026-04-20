"""Tests for beatsync.planner."""

from __future__ import annotations

import numpy as np

from beatsync.planner import CutPlan, CutTrigger, SnapType, plan_cuts


def _beat_grid(bpm: float, duration_s: float) -> np.ndarray:
    interval_ms = 60000.0 / bpm
    num = int(duration_s * 1000.0 / interval_ms) + 1
    return np.arange(num, dtype=np.float64) * interval_ms


def _plan(
    *,
    beat_grid: np.ndarray,
    edit_length_ms: int,
    cut_frequency: float = 0.6,
    cut_trigger: CutTrigger = CutTrigger.BEAT_GRID,
    bass_onsets: np.ndarray | None = None,
    max_bass_snaps: int = 4,
    alternation_variation: float = 0.0,
    max_consecutive_same_source: int = 2,
    source_weights: tuple[float, ...] = (0.5, 0.5),
    min_segment_ms: int = 2000,
    rng_seed: int = 42,
) -> CutPlan:
    return plan_cuts(
        beat_times_ms=beat_grid,
        bass_onset_times_ms=bass_onsets
        if bass_onsets is not None
        else np.array([], dtype=np.float64),
        edit_length_ms=edit_length_ms,
        cut_frequency=cut_frequency,
        cut_trigger=cut_trigger,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps=max_bass_snaps,
        alternation_variation=alternation_variation,
        max_consecutive_same_source=max_consecutive_same_source,
        source_weights=source_weights,
        min_segment_ms=min_segment_ms,
        rng_seed=rng_seed,
    )


def test_cut_frequency_point_six_roughly_matches() -> None:
    plan = _plan(beat_grid=_beat_grid(120.0, 30.0), edit_length_ms=30000)
    assert isinstance(plan, CutPlan)
    assert 5 <= len(plan.segments) <= 15
    assert plan.segments[0].start_ms == 0
    assert plan.segments[-1].end_ms == 30000


def test_cut_frequency_zero_single_segment() -> None:
    plan = _plan(beat_grid=_beat_grid(120.0, 30.0), edit_length_ms=30000, cut_frequency=0.0)
    assert len(plan.segments) == 1


def test_cut_frequency_one_fills_window() -> None:
    plan = _plan(beat_grid=_beat_grid(120.0, 30.0), edit_length_ms=30000, cut_frequency=1.0)
    assert 13 <= len(plan.segments) <= 16


def test_beat_grid_trigger_yields_no_808_snaps() -> None:
    grid = _beat_grid(135.0, 15.0)
    plan = _plan(
        beat_grid=grid,
        edit_length_ms=15000,
        cut_trigger=CutTrigger.BEAT_GRID,
        bass_onsets=grid + 20.0,
        min_segment_ms=1500,
    )
    assert all(seg.snap_type == SnapType.BEAT_GRID for seg in plan.segments)


def test_hybrid_trigger_snaps_to_808_within_tolerance() -> None:
    grid = _beat_grid(128.0, 30.0)
    onsets = np.array([grid[5] + 40.0, grid[10] - 30.0])
    plan = _plan(
        beat_grid=grid,
        edit_length_ms=30000,
        cut_trigger=CutTrigger.HYBRID,
        cut_frequency=1.0,
        bass_onsets=onsets,
    )
    snap_count = sum(1 for s in plan.segments if s.snap_type == SnapType.BASS_808)
    assert snap_count >= 1


def test_max_bass_snaps_cap_enforced() -> None:
    grid = _beat_grid(128.0, 30.0)
    plan = _plan(
        beat_grid=grid,
        edit_length_ms=30000,
        cut_trigger=CutTrigger.HYBRID,
        cut_frequency=1.0,
        bass_onsets=grid + 10.0,
        max_bass_snaps=3,
    )
    snap_count = sum(1 for s in plan.segments if s.snap_type == SnapType.BASS_808)
    assert snap_count <= 3


def test_two_source_alternation_cap_enforced() -> None:
    plan = _plan(
        beat_grid=_beat_grid(120.0, 30.0),
        edit_length_ms=30000,
        cut_frequency=1.0,
        alternation_variation=1.0,
        source_weights=(0.5, 0.5),
    )
    run_length = 1
    last = plan.segments[0].source_index
    for seg in plan.segments[1:]:
        if seg.source_index == last:
            run_length += 1
        else:
            run_length = 1
        last = seg.source_index
        assert run_length <= 2


def test_strict_two_source_alternation_with_zero_variation() -> None:
    plan = _plan(
        beat_grid=_beat_grid(120.0, 30.0),
        edit_length_ms=30000,
        cut_frequency=1.0,
        alternation_variation=0.0,
        source_weights=(0.5, 0.5),
    )
    for i, seg in enumerate(plan.segments):
        assert seg.source_index == i % 2


def test_three_source_rotation_respects_cap() -> None:
    plan = _plan(
        beat_grid=_beat_grid(120.0, 45.0),
        edit_length_ms=45000,
        cut_frequency=1.0,
        alternation_variation=0.0,
        source_weights=(1 / 3, 1 / 3, 1 / 3),
        min_segment_ms=2000,
    )
    assert {s.source_index for s in plan.segments} == {0, 1, 2}
    run_length = 1
    last = plan.segments[0].source_index
    for seg in plan.segments[1:]:
        if seg.source_index == last:
            run_length += 1
        else:
            run_length = 1
        last = seg.source_index
        assert run_length <= 2


def test_four_source_all_get_used() -> None:
    plan = _plan(
        beat_grid=_beat_grid(120.0, 60.0),
        edit_length_ms=60000,
        cut_frequency=1.0,
        source_weights=(0.25, 0.25, 0.25, 0.25),
        min_segment_ms=1500,
    )
    used = {s.source_index for s in plan.segments}
    assert used == {0, 1, 2, 3}


def test_source_weights_bias_allocation() -> None:
    plan = _plan(
        beat_grid=_beat_grid(120.0, 60.0),
        edit_length_ms=60000,
        cut_frequency=1.0,
        source_weights=(0.75, 0.25),
        min_segment_ms=1500,
    )
    time_per_source = [0, 0]
    for seg in plan.segments:
        time_per_source[seg.source_index] += seg.end_ms - seg.start_ms
    assert time_per_source[0] > time_per_source[1] * 1.5


def test_minimum_segment_duration_enforced() -> None:
    plan = _plan(
        beat_grid=_beat_grid(180.0, 30.0),
        edit_length_ms=30000,
        cut_frequency=1.0,
        min_segment_ms=2000,
    )
    for seg in plan.segments:
        assert seg.end_ms - seg.start_ms >= 2000
