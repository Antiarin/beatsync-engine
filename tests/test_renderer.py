"""Tests for beatsync.renderer."""

from __future__ import annotations

from pathlib import Path

from beatsync.renderer import (
    build_extract_command,
    build_filter_chain,
    build_final_mux_command,
    format_output_filename,
)
from beatsync.sampler import Clip


def test_build_filter_chain_includes_crop_scale_and_user_filter() -> None:
    chain = build_filter_chain(
        user_filter="eq=saturation=0.88",
        output_resolution="1080x1920",
    )
    assert chain.startswith("crop=ih*9/16:ih,")
    assert "scale=1080:1920" in chain
    assert chain.endswith("eq=saturation=0.88")
    assert chain.index("crop") < chain.index("scale") < chain.index("eq=")


def test_build_extract_command_uses_input_seek_with_timestamp_fix() -> None:
    clip = Clip(
        source_path=Path("/in.mp4"),
        seek_start_s=12.5,
        duration_s=1.2,
        output_index=0,
    )
    cmd = build_extract_command(
        clip=clip,
        filter_chain="crop=ih*9/16:ih,scale=1080:1920",
        output_path=Path("/tmp/clip_000.mp4"),
        frame_rate=30,
    )
    # Single -ss before -i (frame-accurate when re-encoding since FFmpeg 2.1).
    ss_idx = cmd.index("-ss")
    i_idx = cmd.index("-i")
    assert ss_idx < i_idx
    assert cmd[ss_idx + 1] == "12.500"
    # -avoid_negative_ts prevents timestamp issues during concat.
    assert "-avoid_negative_ts" in cmd
    assert cmd[cmd.index("-avoid_negative_ts") + 1] == "make_zero"
    assert "-t" in cmd
    assert "1.200" in cmd
    assert "-vf" in cmd
    assert cmd[-1] == "/tmp/clip_000.mp4"


def test_build_final_mux_command_maps_video_and_audio() -> None:
    concat_list = Path("/tmp/list.txt")
    audio_path = Path("/in/song.mp3")
    output_path = Path("/out/final.mp4")
    cmd = build_final_mux_command(
        concat_list_path=concat_list,
        audio_path=audio_path,
        output_path=output_path,
        frame_rate=30,
        bitrate="8M",
        audio_fade_in_s=0.5,
        audio_fade_out_s=1.0,
        edit_length_s=30,
    )
    assert "-fflags" in cmd
    assert "+genpts" in cmd
    assert "-f" in cmd
    assert "concat" in cmd
    assert "-map" in cmd
    map_indices = [i for i, a in enumerate(cmd) if a == "-map"]
    assert len(map_indices) == 2
    mapped = {cmd[i + 1] for i in map_indices}
    assert "0:v" in mapped
    assert "1:a" in mapped
    assert any("afade" in a for a in cmd)
    assert "+faststart" in " ".join(cmd)
    assert cmd[-1] == str(output_path)


def test_build_final_mux_command_with_audio_offset() -> None:
    cmd = build_final_mux_command(
        concat_list_path=Path("/tmp/list.txt"),
        audio_path=Path("/in/song.mp3"),
        output_path=Path("/out/final.mp4"),
        frame_rate=30,
        bitrate="8M",
        audio_fade_in_s=0.3,
        audio_fade_out_s=0.5,
        edit_length_s=15,
        audio_start_offset_s=14.0,
    )
    # -ss must appear before the audio -i for input seeking.
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    assert cmd[ss_idx + 1] == "14.000"
    # The -ss should be before the second -i (audio input).
    i_indices = [i for i, a in enumerate(cmd) if a == "-i"]
    assert len(i_indices) == 2
    assert ss_idx < i_indices[1]


def test_build_final_mux_command_no_offset_no_seek() -> None:
    cmd = build_final_mux_command(
        concat_list_path=Path("/tmp/list.txt"),
        audio_path=Path("/in/song.mp3"),
        output_path=Path("/out/final.mp4"),
        frame_rate=30,
        bitrate="8M",
        audio_fade_in_s=0.5,
        audio_fade_out_s=1.0,
        edit_length_s=30,
        audio_start_offset_s=0.0,
    )
    # No -ss when offset is 0.
    assert "-ss" not in cmd


def test_format_output_filename_matches_spec() -> None:
    name = format_output_filename(
        config_name="two_source_default",
        song_title="Zodiac",
        edit_length_seconds=30,
        timestamp="20260412_143022",
    )
    assert name == "two_source_default_Zodiac_30s_20260412_143022.mp4"
