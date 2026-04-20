"""Tests for beatsync.sampler."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

from beatsync.planner import CutPlan, Segment, SnapType, SourceLabel
from beatsync.sampler import Clip, ClipAssignment, sample_clips


def _plan_with_segments(num: int, source: SourceLabel = SourceLabel.A) -> CutPlan:
    segs = [
        Segment(
            start_ms=i * 1000, end_ms=(i + 1) * 1000, source=source, snap_type=SnapType.BEAT_GRID
        )
        for i in range(num)
    ]
    return CutPlan(segments=segs)


def test_sampler_returns_one_clip_per_segment(tmp_path: Path) -> None:
    source_a = tmp_path / "a.mp4"
    source_b = tmp_path / "b.mp4"
    source_a.touch()
    source_b.touch()
    plan = _plan_with_segments(5)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            source_a_path=source_a,
            source_b_path=source_b,
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    assert isinstance(assignment, ClipAssignment)
    assert len(assignment.clips) == 5
    for clip in assignment.clips:
        assert isinstance(clip, Clip)
        assert clip.duration_s > 0


def test_sampler_distributes_across_source_duration(tmp_path: Path) -> None:
    source_a = tmp_path / "a.mp4"
    source_b = tmp_path / "b.mp4"
    source_a.touch()
    source_b.touch()
    plan = _plan_with_segments(10, source=SourceLabel.A)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            source_a_path=source_a,
            source_b_path=source_b,
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    starts = [c.seek_start_s for c in assignment.clips]
    assert max(starts) - min(starts) > 200.0


def test_sampler_no_zone_repeat(tmp_path: Path) -> None:
    source_a = tmp_path / "a.mp4"
    source_b = tmp_path / "b.mp4"
    source_a.touch()
    source_b.touch()
    plan = _plan_with_segments(8, source=SourceLabel.A)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            source_a_path=source_a,
            source_b_path=source_b,
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    starts = sorted(c.seek_start_s for c in assignment.clips)
    for a, b in pairwise(starts):
        assert b - a >= 50.0
