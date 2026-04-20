"""Config loading, validation, and mode presets for beatsync."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from beatsync.planner import CutTrigger
from beatsync.renderer import default_resolution_for, parse_aspect_ratio


class Mode(StrEnum):
    """Built-in mode presets. Each defines a distinct cut character."""

    STROBE = "strobe"
    DRILL = "drill"
    FLOAT = "float"
    CASCADE = "cascade"
    EPIC = "epic"


@dataclass(frozen=True)
class ModePreset:
    """Default timing values for a mode."""

    name: Mode
    edit_length_seconds: int
    cut_trigger: CutTrigger
    min_segment_ms: int
    tolerance_ms_low: int
    tolerance_ms_high: int
    max_bass_snaps_per_edit: int


MODE_PRESETS: dict[Mode, ModePreset] = {
    Mode.STROBE: ModePreset(
        name=Mode.STROBE,
        edit_length_seconds=10,
        cut_trigger=CutTrigger.BEAT_GRID,
        min_segment_ms=500,
        tolerance_ms_low=30,
        tolerance_ms_high=50,
        max_bass_snaps_per_edit=0,
    ),
    Mode.DRILL: ModePreset(
        name=Mode.DRILL,
        edit_length_seconds=15,
        cut_trigger=CutTrigger.BEAT_GRID,
        min_segment_ms=1500,
        tolerance_ms_low=50,
        tolerance_ms_high=70,
        max_bass_snaps_per_edit=0,
    ),
    Mode.FLOAT: ModePreset(
        name=Mode.FLOAT,
        edit_length_seconds=30,
        cut_trigger=CutTrigger.HYBRID,
        min_segment_ms=2500,
        tolerance_ms_low=80,
        tolerance_ms_high=100,
        max_bass_snaps_per_edit=4,
    ),
    Mode.CASCADE: ModePreset(
        name=Mode.CASCADE,
        edit_length_seconds=45,
        cut_trigger=CutTrigger.HYBRID,
        min_segment_ms=2000,
        tolerance_ms_low=80,
        tolerance_ms_high=120,
        max_bass_snaps_per_edit=6,
    ),
    Mode.EPIC: ModePreset(
        name=Mode.EPIC,
        edit_length_seconds=90,
        cut_trigger=CutTrigger.HYBRID,
        min_segment_ms=5000,
        tolerance_ms_low=100,
        tolerance_ms_high=150,
        max_bass_snaps_per_edit=10,
    ),
}


@dataclass(frozen=True)
class Config:
    """Typed representation of a beatsync config file."""

    config_name: str
    config_version: str
    mode: Mode
    sources: tuple[Path, ...]
    source_weights: tuple[float, ...]
    audio: Path
    edit_length_seconds: int
    max_consecutive_same_source: int
    alternation_variation: float
    cut_frequency: float
    bpm_override: float
    bass_hit_amplitude_threshold: float
    max_bass_snaps_per_edit: int
    cut_trigger: CutTrigger
    min_segment_ms: int
    tolerance_ms_low: int
    tolerance_ms_high: int
    clip_selection: str
    avoid_clip_repeat: bool
    long_clip_sampling_strategy: str
    ffmpeg_filter: str
    aspect_ratio: str
    output_resolution: str
    output_frame_rate: int
    output_bitrate: str
    render_quality_tier: str
    audio_fade_in_duration: float
    audio_fade_out_duration: float
    audio_start_offset: float
    audio_end_offset: float


def _validate(config: Config) -> None:
    """Validate a Config. Raises ValueError or FileNotFoundError on problems."""
    if len(config.sources) < 2:
        raise ValueError(f"sources must have at least 2 entries, got {len(config.sources)}")
    if len(config.source_weights) != len(config.sources):
        raise ValueError(
            f"source_weights length ({len(config.source_weights)}) must equal sources length "
            f"({len(config.sources)})"
        )
    if any(w < 0 for w in config.source_weights):
        raise ValueError(f"source_weights must all be >= 0, got {config.source_weights}")
    if sum(config.source_weights) <= 0:
        raise ValueError("source_weights must sum to a positive value")
    if config.edit_length_seconds <= 0:
        raise ValueError(f"edit_length_seconds must be positive, got {config.edit_length_seconds}")
    if not 0.0 <= config.cut_frequency <= 1.0:
        raise ValueError(f"cut_frequency must be in [0.0, 1.0], got {config.cut_frequency}")
    if not 0.0 <= config.bass_hit_amplitude_threshold <= 1.0:
        raise ValueError(
            f"bass_hit_amplitude_threshold must be in [0.0, 1.0], "
            f"got {config.bass_hit_amplitude_threshold}"
        )
    if not 0.0 <= config.alternation_variation <= 1.0:
        raise ValueError(
            f"alternation_variation must be in [0.0, 1.0], got {config.alternation_variation}"
        )
    if config.max_consecutive_same_source < 2:
        raise ValueError(
            f"max_consecutive_same_source must be >= 2, got {config.max_consecutive_same_source}"
        )
    if config.bpm_override < 0:
        raise ValueError(f"bpm_override must be >= 0, got {config.bpm_override}")
    parse_aspect_ratio(config.aspect_ratio)
    for i, source in enumerate(config.sources):
        if not source.exists():
            raise FileNotFoundError(f"sources[{i}] file does not exist: {source}")
    if not config.audio.exists():
        raise FileNotFoundError(f"audio file does not exist: {config.audio}")


def _normalize_weights(weights: list[float] | None, n_sources: int) -> tuple[float, ...]:
    """Return n_sources weights summing to 1.0. Defaults to equal weighting."""
    if not weights:
        return tuple([1.0 / n_sources] * n_sources)
    total = sum(weights)
    if total <= 0:
        return tuple([1.0 / n_sources] * n_sources)
    return tuple(w / total for w in weights)


def load_config(path: Path) -> Config:
    """Load and return a Config from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    mode_str = str(data.get("mode", "drill"))
    try:
        mode = Mode(mode_str)
    except ValueError as exc:
        valid = ", ".join(m.value for m in Mode)
        raise ValueError(f"mode must be one of [{valid}], got '{mode_str}'") from exc
    preset = MODE_PRESETS[mode]

    sources_raw = data.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ValueError("sources must be a non-empty list of file paths")
    sources = tuple(Path(s) for s in sources_raw)
    weights = _normalize_weights(data.get("source_weights"), len(sources))

    aspect_ratio = str(data.get("aspect_ratio", "9:16"))
    output_resolution = str(data.get("output_resolution", default_resolution_for(aspect_ratio)))

    config = Config(
        config_name=data["config_name"],
        config_version=data["config_version"],
        mode=mode,
        sources=sources,
        source_weights=weights,
        audio=Path(data["audio"]),
        edit_length_seconds=int(data.get("edit_length_seconds", preset.edit_length_seconds)),
        max_consecutive_same_source=int(data.get("max_consecutive_same_source", 2)),
        alternation_variation=float(data.get("alternation_variation", 0.15)),
        cut_frequency=float(data.get("cut_frequency", 0.6)),
        bpm_override=float(data.get("bpm_override", 0)),
        bass_hit_amplitude_threshold=float(data.get("bass_hit_amplitude_threshold", 0.7)),
        max_bass_snaps_per_edit=int(
            data.get("max_bass_snaps_per_edit", preset.max_bass_snaps_per_edit)
        ),
        cut_trigger=CutTrigger(data.get("cut_trigger", preset.cut_trigger)),
        min_segment_ms=int(data.get("min_segment_ms", preset.min_segment_ms)),
        tolerance_ms_low=int(data.get("tolerance_ms_low", preset.tolerance_ms_low)),
        tolerance_ms_high=int(data.get("tolerance_ms_high", preset.tolerance_ms_high)),
        clip_selection=str(data.get("clip_selection", "random")),
        avoid_clip_repeat=bool(data.get("avoid_clip_repeat", True)),
        long_clip_sampling_strategy=str(data.get("long_clip_sampling_strategy", "distributed")),
        ffmpeg_filter=str(data.get("ffmpeg_filter", "")),
        aspect_ratio=aspect_ratio,
        output_resolution=output_resolution,
        output_frame_rate=int(data.get("output_frame_rate", 30)),
        output_bitrate=str(data.get("output_bitrate", "8M")),
        render_quality_tier=str(data.get("render_quality_tier", "draft")),
        audio_fade_in_duration=float(data.get("audio_fade_in_duration", 0.5)),
        audio_fade_out_duration=float(data.get("audio_fade_out_duration", 1.0)),
        audio_start_offset=float(data.get("audio_start_offset", 0.0)),
        audio_end_offset=float(data.get("audio_end_offset", 0.0)),
    )
    _validate(config)
    return config
