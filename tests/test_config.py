"""Tests for beatsync.config."""

import json
from pathlib import Path

import pytest

from beatsync.config import MODE_PRESETS, Config, Mode, load_config
from beatsync.planner import CutTrigger


def _write_config(tmp_path: Path, overrides: dict | None = None) -> Path:
    """Write a minimal valid config JSON to tmp_path and return its path."""
    (tmp_path / "s1.mp4").touch()
    (tmp_path / "s2.mp4").touch()
    (tmp_path / "song.mp3").touch()
    base = {
        "config_name": "test",
        "config_version": "1.0",
        "mode": "drill",
        "sources": [str(tmp_path / "s1.mp4"), str(tmp_path / "s2.mp4")],
        "audio": str(tmp_path / "song.mp3"),
    }
    if overrides:
        base.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(base))
    return path


def test_load_valid_config_returns_config_dataclass(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert isinstance(config, Config)
    assert config.mode == Mode.DRILL
    assert len(config.sources) == 2
    assert config.edit_length_seconds == MODE_PRESETS[Mode.DRILL].edit_length_seconds


def test_rejects_invalid_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        load_config(_write_config(tmp_path, {"mode": "ultrawide"}))


def test_rejects_fewer_than_two_sources(tmp_path: Path) -> None:
    (tmp_path / "only.mp4").touch()
    path = _write_config(tmp_path, {"sources": [str(tmp_path / "only.mp4")]})
    with pytest.raises(ValueError, match="at least 2"):
        load_config(path)


def test_rejects_mismatched_weights_length(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_weights length"):
        load_config(_write_config(tmp_path, {"source_weights": [0.5, 0.3, 0.2]}))


def test_equal_weights_by_default(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.source_weights == (0.5, 0.5)


def test_weights_are_normalized(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, {"source_weights": [3.0, 1.0]}))
    assert config.source_weights == pytest.approx((0.75, 0.25))


def test_three_source_config_loads(tmp_path: Path) -> None:
    (tmp_path / "s3.mp4").touch()
    config = load_config(
        _write_config(
            tmp_path,
            {
                "sources": [
                    str(tmp_path / "s1.mp4"),
                    str(tmp_path / "s2.mp4"),
                    str(tmp_path / "s3.mp4"),
                ]
            },
        )
    )
    assert len(config.sources) == 3
    assert config.source_weights == pytest.approx((1 / 3, 1 / 3, 1 / 3))


def test_rejects_cut_frequency_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cut_frequency"):
        load_config(_write_config(tmp_path, {"cut_frequency": 1.5}))


def test_rejects_bass_threshold_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bass_hit_amplitude_threshold"):
        load_config(_write_config(tmp_path, {"bass_hit_amplitude_threshold": -0.1}))


def test_rejects_alternation_variation_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="alternation_variation"):
        load_config(_write_config(tmp_path, {"alternation_variation": 1.1}))


def test_rejects_max_consecutive_below_two(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_consecutive_same_source"):
        load_config(_write_config(tmp_path, {"max_consecutive_same_source": 1}))


def test_rejects_negative_bpm_override(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bpm_override"):
        load_config(_write_config(tmp_path, {"bpm_override": -10}))


def test_rejects_missing_source_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"sources\[0\]"):
        load_config(
            _write_config(
                tmp_path,
                {"sources": [str(tmp_path / "nope.mp4"), str(tmp_path / "s2.mp4")]},
            )
        )


@pytest.mark.parametrize(
    "mode,expected_length,expected_trigger",
    [
        (Mode.STROBE, 10, CutTrigger.BEAT_GRID),
        (Mode.DRILL, 15, CutTrigger.BEAT_GRID),
        (Mode.FLOAT, 30, CutTrigger.HYBRID),
        (Mode.CASCADE, 45, CutTrigger.HYBRID),
        (Mode.EPIC, 90, CutTrigger.HYBRID),
    ],
)
def test_each_mode_preset_applies_correct_defaults(
    tmp_path: Path, mode: Mode, expected_length: int, expected_trigger: CutTrigger
) -> None:
    config = load_config(_write_config(tmp_path, {"mode": mode.value}))
    assert config.edit_length_seconds == expected_length
    assert config.cut_trigger == expected_trigger


def test_config_overrides_mode_defaults(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            {"mode": "drill", "min_segment_ms": 800, "cut_trigger": "hybrid"},
        )
    )
    assert config.min_segment_ms == 800
    assert config.cut_trigger == CutTrigger.HYBRID
