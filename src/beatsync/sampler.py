"""Clip sampling: map segments to time ranges in the source videos."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from beatsync.ffprobe import get_duration_seconds
from beatsync.planner import CutPlan, Segment, SourceLabel


@dataclass(frozen=True)
class Clip:
    """A concrete video extraction target."""

    source_path: Path
    seek_start_s: float
    duration_s: float
    output_index: int


@dataclass(frozen=True)
class ClipAssignment:
    """Ordered list of clips making up the final edit."""

    clips: list[Clip]


_MIN_ZONE_GAP_S: float = 50.0


def sample_clips(
    plan: CutPlan,
    source_a_path: Path,
    source_b_path: Path,
    avoid_clip_repeat: bool,
    rng_seed: int | None = None,
) -> ClipAssignment:
    """Sample a clip for each segment from the appropriate source."""
    rng = random.Random(rng_seed)
    duration_a = get_duration_seconds(source_a_path)
    duration_b = get_duration_seconds(source_b_path)

    segs_a = [(i, s) for i, s in enumerate(plan.segments) if s.source == SourceLabel.A]
    segs_b = [(i, s) for i, s in enumerate(plan.segments) if s.source == SourceLabel.B]

    starts_a = _sample_distributed_starts(duration_a, segs_a, rng, avoid_clip_repeat)
    starts_b = _sample_distributed_starts(duration_b, segs_b, rng, avoid_clip_repeat)

    clips: list[Clip | None] = [None] * len(plan.segments)
    for (idx, seg), seek_start in zip(segs_a, starts_a, strict=True):
        duration_s = (seg.end_ms - seg.start_ms) / 1000.0
        clips[idx] = Clip(
            source_path=source_a_path,
            seek_start_s=seek_start,
            duration_s=duration_s,
            output_index=idx,
        )
    for (idx, seg), seek_start in zip(segs_b, starts_b, strict=True):
        duration_s = (seg.end_ms - seg.start_ms) / 1000.0
        clips[idx] = Clip(
            source_path=source_b_path,
            seek_start_s=seek_start,
            duration_s=duration_s,
            output_index=idx,
        )

    resolved = [c for c in clips if c is not None]
    return ClipAssignment(clips=resolved)


def _sample_distributed_starts(
    duration_s: float,
    indexed_segs: list[tuple[int, Segment]],
    rng: random.Random,
    avoid_repeat: bool,
) -> list[float]:
    """Return one seek-start per segment, spread across the full source duration.

    Uses stratified (zone-based) sampling. When avoid_repeat is True, adjacent
    samples are guaranteed to be at least _MIN_ZONE_GAP_S apart so no two
    clips come from the same stretch of the source. Otherwise zones are
    shuffled for variety with no minimum-gap guarantee.
    """
    num = len(indexed_segs)
    if num == 0:
        return []

    zone_width = duration_s / num
    zones = [(i * zone_width, (i + 1) * zone_width) for i in range(num)]

    if avoid_repeat:
        # Cap the jitter so that even with worst-case jitter on two adjacent
        # zones, the samples stay at least _MIN_ZONE_GAP_S apart.
        max_jitter = max(0.0, zone_width - _MIN_ZONE_GAP_S)
        starts: list[float] = []
        for zone_start, zone_end in zones:
            centre = (zone_start + zone_end) / 2.0
            half_jitter = max_jitter / 2.0
            lo = max(0.0, centre - half_jitter)
            hi = min(duration_s, centre + half_jitter)
            starts.append(rng.uniform(lo, hi) if hi > lo else centre)
        # Shuffle the assignments so segment 0 doesn't always get the first
        # zone in source-time order.
        rng.shuffle(starts)
        return starts
    else:
        rng.shuffle(zones)
        starts = []
        for zone_start, zone_end in zones:
            starts.append(rng.uniform(zone_start, zone_end))
        return starts
