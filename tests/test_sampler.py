"""Tests for beatsync.sampler."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

from beatsync.planner import CutPlan, Segment, SnapType
from beatsync.sampler import Clip, ClipAssignment, sample_clips


def _plan_with_segments(num: int, source_index: int = 0) -> CutPlan:
    segs = [
        Segment(
            start_ms=i * 1000,
            end_ms=(i + 1) * 1000,
            source_index=source_index,
            snap_type=SnapType.BEAT_GRID,
        )
        for i in range(num)
    ]
    return CutPlan(segments=segs)


def test_sampler_returns_one_clip_per_segment(tmp_path: Path) -> None:
    s1, s2 = tmp_path / "s1.mp4", tmp_path / "s2.mp4"
    s1.touch()
    s2.touch()
    plan = _plan_with_segments(5)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            sources=[s1, s2],
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    assert isinstance(assignment, ClipAssignment)
    assert len(assignment.clips) == 5
    for clip in assignment.clips:
        assert isinstance(clip, Clip)
        assert clip.duration_s > 0


def test_sampler_distributes_across_source_duration(tmp_path: Path) -> None:
    s1, s2 = tmp_path / "s1.mp4", tmp_path / "s2.mp4"
    s1.touch()
    s2.touch()
    plan = _plan_with_segments(10, source_index=0)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            sources=[s1, s2],
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    starts = [c.seek_start_s for c in assignment.clips]
    assert max(starts) - min(starts) > 200.0


def test_sampler_no_zone_repeat(tmp_path: Path) -> None:
    s1, s2 = tmp_path / "s1.mp4", tmp_path / "s2.mp4"
    s1.touch()
    s2.touch()
    plan = _plan_with_segments(8, source_index=0)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            sources=[s1, s2],
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    starts = sorted(c.seek_start_s for c in assignment.clips)
    for a, b in pairwise(starts):
        assert b - a >= 50.0


def test_sampler_handles_three_sources(tmp_path: Path) -> None:
    sources = [tmp_path / f"s{i}.mp4" for i in range(3)]
    for s in sources:
        s.touch()
    segs = [
        Segment(
            start_ms=i * 1000,
            end_ms=(i + 1) * 1000,
            source_index=i % 3,
            snap_type=SnapType.BEAT_GRID,
        )
        for i in range(9)
    ]
    plan = CutPlan(segments=segs)
    with patch("beatsync.sampler.get_duration_seconds", return_value=600.0):
        assignment = sample_clips(
            plan=plan,
            sources=sources,
            avoid_clip_repeat=True,
            rng_seed=42,
        )
    assert len(assignment.clips) == 9
    paths_used = {c.source_path for c in assignment.clips}
    assert paths_used == set(sources)
