"""Tests for beatsync.config."""

import json
from pathlib import Path

import pytest

from beatsync.config import Config, detect_mode, load_config
from beatsync.planner import CutTrigger


def _write_config(tmp_path: Path, overrides: dict | None = None) -> Path:
    """Write a valid config JSON to tmp_path and return its path."""
    (tmp_path / "a.mp4").touch()
    (tmp_path / "b.mp4").touch()
    (tmp_path / "song.mp3").touch()
    base = {
        "config_name": "test",
        "config_version": "1.0",
        "source_a": str(tmp_path / "a.mp4"),
        "source_b": str(tmp_path / "b.mp4"),
        "audio": str(tmp_path / "song.mp3"),
        "edit_length_seconds": 30,
        "source_a_seconds": 15,
        "source_b_seconds": 15,
        "max_consecutive_same_source": 2,
        "alternation_variation": 0.15,
        "cut_frequency": 0.6,
        "bpm_override": 0,
        "bass_hit_amplitude_threshold": 0.7,
        "max_bass_snaps_per_edit": 4,
        "clip_selection": "random",
        "avoid_clip_repeat": True,
        "long_clip_sampling_strategy": "distributed",
        "ffmpeg_filter": "eq=saturation=0.88",
        "aspect_ratio": "9:16",
        "output_resolution": "1080x1920",
        "output_frame_rate": 30,
        "output_bitrate": "8M",
        "render_quality_tier": "draft",
        "audio_fade_in_duration": 0.5,
        "audio_fade_out_duration": 1.0,
        "audio_start_offset": 0,
        "audio_end_offset": 0,
    }
    if overrides:
        base.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(base))
    return path


def test_load_valid_config_returns_config_dataclass(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    assert isinstance(config, Config)
    assert config.config_name == "test"
    assert config.edit_length_seconds == 30
    assert config.source_a_seconds == 15
    assert config.cut_frequency == 0.6


def test_rejects_invalid_edit_length(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"edit_length_seconds": 20})
    with pytest.raises(ValueError, match="edit_length_seconds"):
        load_config(config_path)


def test_rejects_split_ratio_mismatch(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path, {"source_a_seconds": 10, "source_b_seconds": 10, "edit_length_seconds": 30}
    )
    with pytest.raises(ValueError, match="source_a_seconds"):
        load_config(config_path)


def test_rejects_cut_frequency_out_of_range(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"cut_frequency": 1.5})
    with pytest.raises(ValueError, match="cut_frequency"):
        load_config(config_path)


def test_rejects_bass_threshold_out_of_range(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"bass_hit_amplitude_threshold": -0.1})
    with pytest.raises(ValueError, match="bass_hit_amplitude_threshold"):
        load_config(config_path)


def test_rejects_alternation_variation_out_of_range(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"alternation_variation": 1.1})
    with pytest.raises(ValueError, match="alternation_variation"):
        load_config(config_path)


def test_rejects_max_consecutive_below_two(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"max_consecutive_same_source": 1})
    with pytest.raises(ValueError, match="max_consecutive_same_source"):
        load_config(config_path)


def test_rejects_negative_bpm_override(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"bpm_override": -10})
    with pytest.raises(ValueError, match="bpm_override"):
        load_config(config_path)


def test_rejects_missing_source_file(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"source_a": str(tmp_path / "nope.mp4")})
    with pytest.raises(FileNotFoundError, match="source_a"):
        load_config(config_path)


def test_punch_mode_for_15_seconds(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            {"edit_length_seconds": 15, "source_a_seconds": 7, "source_b_seconds": 8},
        )
    )
    mode = detect_mode(config)
    assert mode.name == "Punch"
    # Defaults applied from mode when not in JSON.
    assert config.cut_trigger == CutTrigger.BEAT_GRID
    assert config.tolerance_ms_low == 50
    assert config.tolerance_ms_high == 70
    assert config.min_segment_ms == 1500


def test_breathe_mode_for_30_seconds(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, {"edit_length_seconds": 30}))
    mode = detect_mode(config)
    assert mode.name == "Breathe"
    assert config.cut_trigger == CutTrigger.HYBRID
    assert config.tolerance_ms_low == 80
    assert config.tolerance_ms_high == 100
    assert config.min_segment_ms == 2500


def test_audio_fade_and_offset_fields_are_optional(tmp_path: Path) -> None:
    """Spec config omits audio_fade_* and audio_*_offset; loader should apply defaults."""
    (tmp_path / "a.mp4").touch()
    (tmp_path / "b.mp4").touch()
    (tmp_path / "song.mp3").touch()
    minimal = {
        "config_name": "test",
        "config_version": "1.0",
        "source_a": str(tmp_path / "a.mp4"),
        "source_b": str(tmp_path / "b.mp4"),
        "audio": str(tmp_path / "song.mp3"),
        "edit_length_seconds": 30,
        "source_a_seconds": 15,
        "source_b_seconds": 15,
        "max_consecutive_same_source": 2,
        "alternation_variation": 0.15,
        "cut_frequency": 0.6,
        "bpm_override": 0,
        "bass_hit_amplitude_threshold": 0.7,
        "max_bass_snaps_per_edit": 4,
        "clip_selection": "random",
        "avoid_clip_repeat": True,
        "long_clip_sampling_strategy": "distributed",
        "ffmpeg_filter": "eq=saturation=0.88",
        "aspect_ratio": "9:16",
        "output_resolution": "1080x1920",
        "output_frame_rate": 30,
        "output_bitrate": "8M",
        "render_quality_tier": "draft",
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(minimal))
    config = load_config(path)
    assert config.audio_fade_in_duration == 0.5
    assert config.audio_fade_out_duration == 1.0
    assert config.audio_start_offset == 0.0
    assert config.audio_end_offset == 0.0


def test_config_overrides_mode_defaults(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            {
                "edit_length_seconds": 15,
                "source_a_seconds": 7,
                "source_b_seconds": 8,
                "cut_trigger": "hybrid",
                "min_segment_ms": 2000,
            },
        )
    )
    mode = detect_mode(config)
    assert mode.name == "Punch"
    assert config.cut_trigger == CutTrigger.HYBRID
    assert config.min_segment_ms == 2000
