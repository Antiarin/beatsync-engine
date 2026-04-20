"""Render stage: build and execute FFmpeg commands."""

from __future__ import annotations

import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from beatsync.ffprobe import get_duration_seconds
from beatsync.sampler import Clip, ClipAssignment

DEFAULT_RESOLUTIONS: dict[tuple[int, int], str] = {
    (9, 16): "1080x1920",
    (16, 9): "1920x1080",
    (1, 1): "1080x1080",
    (4, 5): "1080x1350",
    (5, 4): "1350x1080",
    (4, 3): "1440x1080",
    (3, 4): "1080x1440",
    (2, 3): "1080x1620",
    (3, 2): "1620x1080",
    (21, 9): "2560x1080",
}


def parse_aspect_ratio(aspect: str) -> tuple[int, int]:
    """Parse a 'W:H' aspect string into a (width, height) tuple of positive ints."""
    parts = aspect.split(":")
    if len(parts) != 2:
        raise ValueError(f"aspect_ratio must be in 'W:H' form, got '{aspect}'")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"aspect_ratio parts must be integers, got '{aspect}'") from exc
    if w <= 0 or h <= 0:
        raise ValueError(f"aspect_ratio parts must be positive, got '{aspect}'")
    return w, h


def default_resolution_for(aspect: str) -> str:
    """Return a sensible default output resolution for a given aspect ratio."""
    w, h = parse_aspect_ratio(aspect)
    if (w, h) in DEFAULT_RESOLUTIONS:
        return DEFAULT_RESOLUTIONS[(w, h)]
    base = 1080
    if w >= h:
        return f"{base * w // h}x{base}"
    return f"{base}x{base * h // w}"


def build_filter_chain(user_filter: str, output_resolution: str, aspect_ratio: str) -> str:
    """Compose the full video filter chain: crop -> scale -> user filter.

    Crops the source to match aspect_ratio regardless of source orientation,
    then scales to output_resolution. Uses min() in the crop expression so
    the same filter works whether the source is portrait, landscape, or square.
    """
    w, h = parse_aspect_ratio(aspect_ratio)
    out_w, out_h = output_resolution.split("x")
    crop = f"crop=min(iw\\,ih*{w}/{h}):min(ih\\,iw*{h}/{w})"
    scale = f"scale={out_w}:{out_h}"
    tail = f",{user_filter}" if user_filter else ""
    return f"{crop},{scale}{tail}"


def build_extract_command(
    clip: Clip,
    filter_chain: str,
    output_path: Path,
    frame_rate: int,
) -> list[str]:
    """Build an FFmpeg command that extracts one clip with the filter chain applied.

    Seeks before the -i flag, which is frame-accurate for re-encoded output
    (FFmpeg 2.1 and later). The -avoid_negative_ts make_zero flag prevents
    the timestamp drift that accumulates when many short clips are concatenated.
    """
    return [
        "ffmpeg",
        "-y",
        "-ss",
        f"{clip.seek_start_s:.3f}",
        "-i",
        str(clip.source_path),
        "-t",
        f"{clip.duration_s:.3f}",
        "-avoid_negative_ts",
        "make_zero",
        "-vf",
        filter_chain,
        "-r",
        str(frame_rate),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]


def write_concat_list(clip_paths: list[Path], list_path: Path) -> None:
    """Write an FFmpeg concat demuxer file list with absolute paths."""
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    list_path.write_text("\n".join(lines) + "\n")


def build_final_mux_command(
    concat_list_path: Path,
    audio_path: Path,
    output_path: Path,
    frame_rate: int,
    bitrate: str,
    audio_fade_in_s: float,
    audio_fade_out_s: float,
    edit_length_s: float,
    audio_start_offset_s: float = 0.0,
) -> list[str]:
    """Build the final FFmpeg command that concats the clip list and muxes audio."""
    afade = (
        f"afade=t=in:st=0:d={audio_fade_in_s},"
        f"afade=t=out:st={edit_length_s - audio_fade_out_s}:d={audio_fade_out_s}"
    )
    buf = _double_bitrate(bitrate)
    audio_input: list[str] = []
    if audio_start_offset_s > 0:
        audio_input = ["-ss", f"{audio_start_offset_s:.3f}"]
    audio_input += ["-i", str(audio_path)]
    return [
        "ffmpeg",
        "-y",
        "-fflags",
        "+genpts",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        *audio_input,
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-af",
        afade,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        bitrate,
        "-maxrate",
        bitrate,
        "-bufsize",
        buf,
        "-r",
        str(frame_rate),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _double_bitrate(bitrate: str) -> str:
    """Return 2x the bitrate string for use as bufsize."""
    if bitrate.endswith("M"):
        return f"{int(bitrate[:-1]) * 2}M"
    if bitrate.endswith("k"):
        return f"{int(bitrate[:-1]) * 2}k"
    return bitrate


def format_output_filename(
    config_name: str,
    song_title: str,
    edit_length_seconds: int,
    timestamp: str | None = None,
) -> str:
    """Return an output filename matching the spec format."""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{config_name}_{song_title}_{edit_length_seconds}s_{timestamp}.mp4"


MIN_BRIGHTNESS_LUMA = 30
MAX_BRIGHTNESS_RETRIES = 3


def _check_clip_brightness(clip_path: Path) -> float:
    """Return the average luma (Y) of a clip's first frame via ffprobe signalstats."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"movie='{clip_path.resolve().as_posix()}',signalstats",
            "-show_entries",
            "frame_tags=lavfi.signalstats.YAVG",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            "-read_intervals",
            "%+#1",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        # If ffprobe can not read the frame, give the clip the benefit of the doubt.
        return 255.0
    return float(result.stdout.strip().split("\n")[0])


def render(
    assignment: ClipAssignment,
    audio_path: Path,
    ffmpeg_filter: str,
    output_resolution: str,
    aspect_ratio: str,
    frame_rate: int,
    bitrate: str,
    audio_fade_in_s: float,
    audio_fade_out_s: float,
    edit_length_s: float,
    output_path: Path,
    temp_dir: Path,
    audio_start_offset_s: float = 0.0,
    min_brightness: int = MIN_BRIGHTNESS_LUMA,
) -> Path:
    """Execute the full render pipeline: extract each clip, concat, mux."""
    rng = random.Random()
    temp_dir.mkdir(parents=True, exist_ok=True)
    filter_chain = build_filter_chain(ffmpeg_filter, output_resolution, aspect_ratio)
    clip_paths: list[Path] = []
    for clip in assignment.clips:
        clip_path = temp_dir / f"clip_{clip.output_index:04d}.mp4"
        current_clip = clip

        for attempt in range(MAX_BRIGHTNESS_RETRIES + 1):
            cmd = build_extract_command(
                clip=current_clip,
                filter_chain=filter_chain,
                output_path=clip_path,
                frame_rate=frame_rate,
            )
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg clip extraction failed (exit {result.returncode}):\n{result.stderr}"
                )

            avg_luma = _check_clip_brightness(clip_path)
            if avg_luma >= min_brightness:
                break

            if attempt < MAX_BRIGHTNESS_RETRIES:
                source_dur = get_duration_seconds(current_clip.source_path)
                new_start = rng.uniform(0.0, max(0.0, source_dur - current_clip.duration_s))
                current_clip = Clip(
                    source_path=current_clip.source_path,
                    seek_start_s=new_start,
                    duration_s=current_clip.duration_s,
                    output_index=current_clip.output_index,
                )
                print(
                    f"[WARN] Clip {clip.output_index} too dark (luma={avg_luma:.0f}), "
                    f"resampling (attempt {attempt + 2}/{MAX_BRIGHTNESS_RETRIES + 1})",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[WARN] Clip {clip.output_index} still dark (luma={avg_luma:.0f}) "
                    f"after {MAX_BRIGHTNESS_RETRIES} retries, keeping it",
                    file=sys.stderr,
                )

        clip_paths.append(clip_path)

    list_path = temp_dir / "concat.txt"
    write_concat_list(clip_paths, list_path)

    mux_cmd = build_final_mux_command(
        concat_list_path=list_path,
        audio_path=audio_path,
        output_path=output_path,
        frame_rate=frame_rate,
        bitrate=bitrate,
        audio_fade_in_s=audio_fade_in_s,
        audio_fade_out_s=audio_fade_out_s,
        edit_length_s=edit_length_s,
        audio_start_offset_s=audio_start_offset_s,
    )
    mux_result = subprocess.run(mux_cmd, capture_output=True, text=True)
    if mux_result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg mux failed (exit {mux_result.returncode}):\n{mux_result.stderr}"
        )
    return output_path
