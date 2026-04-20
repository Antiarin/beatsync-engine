"""Cut planning: beat grid -> cut points -> source assignment."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class SourceLabel(StrEnum):
    """Which source video a segment is assigned to."""

    A = "A"
    B = "B"


class SnapType(StrEnum):
    """How a cut point was determined."""

    BEAT_GRID = "beat_grid"
    BASS_808 = "bass_808"


class CutTrigger(StrEnum):
    """Cut triggering mode."""

    BEAT_GRID = "beat_grid"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class Segment:
    """A single segment of the final edit."""

    start_ms: int
    end_ms: int
    source: SourceLabel
    snap_type: SnapType


@dataclass(frozen=True)
class CutPlan:
    """Ordered list of segments that make up the final edit."""

    segments: list[Segment]


def plan_cuts(
    beat_times_ms: np.ndarray,
    bass_onset_times_ms: np.ndarray,
    edit_length_ms: int,
    cut_frequency: float,
    cut_trigger: CutTrigger,
    tolerance_ms_low: int,
    tolerance_ms_high: int,
    max_bass_snaps: int,
    alternation_variation: float,
    max_consecutive_same_source: int,
    source_a_seconds: int,
    source_b_seconds: int,
    min_segment_ms: int = 2000,
    rng_seed: int | None = None,
) -> CutPlan:
    """Generate a CutPlan from the beat grid and bass onsets."""
    rng = random.Random(rng_seed)
    cut_points_ms = _select_cut_points(
        beat_times_ms, edit_length_ms, cut_frequency, rng, min_segment_ms
    )
    cut_points_ms, snap_flags = _apply_808_snaps(
        cut_points_ms=cut_points_ms,
        bass_onset_times_ms=bass_onset_times_ms,
        cut_trigger=cut_trigger,
        tolerance_ms_low=tolerance_ms_low,
        tolerance_ms_high=tolerance_ms_high,
        max_bass_snaps=max_bass_snaps,
        edit_length_ms=edit_length_ms,
    )
    segments = _build_segments(
        cut_points_ms=cut_points_ms,
        snap_flags=snap_flags,
        edit_length_ms=edit_length_ms,
        alternation_variation=alternation_variation,
        max_consecutive_same_source=max_consecutive_same_source,
        source_a_seconds=source_a_seconds,
        source_b_seconds=source_b_seconds,
        rng=rng,
    )
    return CutPlan(segments=segments)


def _select_cut_points(
    beat_times_ms: np.ndarray,
    edit_length_ms: int,
    cut_frequency: float,
    rng: random.Random,
    min_segment_ms: int = 2000,
) -> list[int]:
    """Walk the beat grid and keep each beat with probability cut_frequency.

    Skips any beat that would create a segment shorter than min_segment_ms
    from the last accepted cut point.
    """
    kept: list[int] = [0]
    for t in beat_times_ms:
        t_int = round(float(t))
        if t_int <= 0 or t_int >= edit_length_ms:
            continue
        if t_int - kept[-1] < min_segment_ms:
            continue
        if rng.random() < cut_frequency:
            kept.append(t_int)
    kept.append(edit_length_ms)
    deduped = sorted(set(kept))
    return deduped


def _apply_808_snaps(
    cut_points_ms: list[int],
    bass_onset_times_ms: np.ndarray,
    cut_trigger: CutTrigger,
    tolerance_ms_low: int,
    tolerance_ms_high: int,
    max_bass_snaps: int,
    edit_length_ms: int,
) -> tuple[list[int], list[bool]]:
    """In hybrid mode, snap existing cuts to nearby bass onsets and inject
    bass onsets as new cuts where none was close by.

    808 snaps ignore the minimum segment duration so they always land on
    the actual bass attack rather than a quantized grid position.
    """
    is_snap_map: dict[int, bool] = {pt: False for pt in cut_points_ms}
    if cut_trigger != CutTrigger.HYBRID or bass_onset_times_ms.size == 0 or max_bass_snaps <= 0:
        result = list(cut_points_ms)
        return result, [False] * len(result)

    snaps_used = 0
    window = tolerance_ms_high

    for onset_f in bass_onset_times_ms:
        if snaps_used >= max_bass_snaps:
            break
        onset = round(float(onset_f))
        if onset <= 0 or onset >= edit_length_ms:
            continue

        nearby_cut = None
        for pt in cut_points_ms:
            if pt == 0 or pt == edit_length_ms:
                continue
            if abs(pt - onset) <= window:
                nearby_cut = pt
                break

        if nearby_cut is not None:
            is_snap_map.pop(nearby_cut, None)
            is_snap_map[onset] = True
            idx = cut_points_ms.index(nearby_cut)
            cut_points_ms[idx] = onset
            snaps_used += 1
        else:
            is_snap_map[onset] = True
            cut_points_ms.append(onset)
            snaps_used += 1

    deduped = sorted(set(cut_points_ms))
    is_snap = [is_snap_map.get(pt, False) for pt in deduped]
    return deduped, is_snap


def _build_segments(
    cut_points_ms: list[int],
    snap_flags: list[bool],
    edit_length_ms: int,
    alternation_variation: float,
    max_consecutive_same_source: int,
    source_a_seconds: int,
    source_b_seconds: int,
    rng: random.Random,
) -> list[Segment]:
    """Turn cut points into segments with alternating source assignments."""
    segments: list[Segment] = []
    if len(cut_points_ms) < 2:
        return segments
    target_a_ms = source_a_seconds * 1000
    target_b_ms = source_b_seconds * 1000
    current = SourceLabel.A
    consecutive = 0
    a_used_ms = 0
    b_used_ms = 0
    for i in range(len(cut_points_ms) - 1):
        start = cut_points_ms[i]
        end = cut_points_ms[i + 1]
        snap_type = SnapType.BASS_808 if snap_flags[i] else SnapType.BEAT_GRID
        duration = end - start

        if i == 0:
            chosen = current
        else:
            if consecutive >= max_consecutive_same_source:
                chosen = SourceLabel.B if current == SourceLabel.A else SourceLabel.A
            else:
                a_over = a_used_ms - target_a_ms
                b_over = b_used_ms - target_b_ms
                if a_over > duration and current == SourceLabel.A:
                    chosen = SourceLabel.B
                elif b_over > duration and current == SourceLabel.B:
                    chosen = SourceLabel.A
                else:
                    if rng.random() < alternation_variation:
                        chosen = current
                    else:
                        chosen = SourceLabel.B if current == SourceLabel.A else SourceLabel.A

        if chosen == current:
            consecutive += 1
        else:
            consecutive = 1
        current = chosen
        if current == SourceLabel.A:
            a_used_ms += duration
        else:
            b_used_ms += duration
        segments.append(Segment(start_ms=start, end_ms=end, source=current, snap_type=snap_type))
    return segments
