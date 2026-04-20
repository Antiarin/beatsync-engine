"""Config loading, validation, and mode detection for beatsync."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from beatsync.planner import CutTrigger


@dataclass(frozen=True)
class Config:
    """Typed representation of a beatsync config file."""

    config_name: str
    config_version: str
    source_a: Path
    source_b: Path
    audio: Path
    edit_length_seconds: int
    source_a_seconds: int
    source_b_seconds: int
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


@dataclass(frozen=True)
class ModeSettings:
    """Mode name for logging purposes. All timing values come from Config."""

    name: str


def detect_mode(config: Config) -> ModeSettings:
    """Return the mode name based on edit_length_seconds."""
    name = "Punch" if config.edit_length_seconds == 15 else "Breathe"
    return ModeSettings(name=name)


def _validate(config: Config) -> None:
    """Validate a Config. Raises ValueError or FileNotFoundError on problems."""
    if config.edit_length_seconds not in (15, 30):
        raise ValueError(f"edit_length_seconds must be 15 or 30, got {config.edit_length_seconds}")
    if config.source_a_seconds + config.source_b_seconds != config.edit_length_seconds:
        raise ValueError(
            f"source_a_seconds ({config.source_a_seconds}) + source_b_seconds "
            f"({config.source_b_seconds}) must equal edit_length_seconds "
            f"({config.edit_length_seconds})"
        )
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
    for field_name, path in (
        ("source_a", config.source_a),
        ("source_b", config.source_b),
        ("audio", config.audio),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{field_name} file does not exist: {path}")


def _mode_defaults(edit_length: int) -> dict[str, CutTrigger | int]:
    """Return default cut_trigger, min_segment_ms, and tolerances for a mode."""
    if edit_length == 15:
        return {
            "cut_trigger": CutTrigger.BEAT_GRID,
            "min_segment_ms": 1500,
            "tolerance_ms_low": 50,
            "tolerance_ms_high": 70,
        }
    return {
        "cut_trigger": CutTrigger.HYBRID,
        "min_segment_ms": 2500,
        "tolerance_ms_low": 80,
        "tolerance_ms_high": 100,
    }


def load_config(path: Path) -> Config:
    """Load and return a Config from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    defaults = _mode_defaults(int(data["edit_length_seconds"]))
    config = Config(
        config_name=data["config_name"],
        config_version=data["config_version"],
        source_a=Path(data["source_a"]),
        source_b=Path(data["source_b"]),
        audio=Path(data["audio"]),
        edit_length_seconds=int(data["edit_length_seconds"]),
        source_a_seconds=int(data["source_a_seconds"]),
        source_b_seconds=int(data["source_b_seconds"]),
        max_consecutive_same_source=int(data["max_consecutive_same_source"]),
        alternation_variation=float(data["alternation_variation"]),
        cut_frequency=float(data["cut_frequency"]),
        bpm_override=float(data["bpm_override"]),
        bass_hit_amplitude_threshold=float(data["bass_hit_amplitude_threshold"]),
        max_bass_snaps_per_edit=int(data["max_bass_snaps_per_edit"]),
        cut_trigger=CutTrigger(data.get("cut_trigger", defaults["cut_trigger"])),
        min_segment_ms=int(data.get("min_segment_ms", defaults["min_segment_ms"])),
        tolerance_ms_low=int(data.get("tolerance_ms_low", defaults["tolerance_ms_low"])),
        tolerance_ms_high=int(data.get("tolerance_ms_high", defaults["tolerance_ms_high"])),
        clip_selection=str(data["clip_selection"]),
        avoid_clip_repeat=bool(data["avoid_clip_repeat"]),
        long_clip_sampling_strategy=str(data["long_clip_sampling_strategy"]),
        ffmpeg_filter=str(data["ffmpeg_filter"]),
        aspect_ratio=str(data["aspect_ratio"]),
        output_resolution=str(data["output_resolution"]),
        output_frame_rate=int(data["output_frame_rate"]),
        output_bitrate=str(data["output_bitrate"]),
        render_quality_tier=str(data["render_quality_tier"]),
        audio_fade_in_duration=float(data.get("audio_fade_in_duration", 0.5)),
        audio_fade_out_duration=float(data.get("audio_fade_out_duration", 1.0)),
        audio_start_offset=float(data.get("audio_start_offset", 0.0)),
        audio_end_offset=float(data.get("audio_end_offset", 0.0)),
    )
    _validate(config)
    return config
