"""Beatsync CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import librosa

from beatsync.audio import analyze_audio, detect_silence_gaps
from beatsync.config import detect_mode, load_config
from beatsync.planner import plan_cuts
from beatsync.renderer import format_output_filename, render
from beatsync.sampler import sample_clips


def main(argv: list[str] | None = None) -> int:
    """Run the beatsync pipeline with the given CLI args."""
    parser = argparse.ArgumentParser(prog="beatsync")
    parser.add_argument("--config", type=Path, required=True, help="Path to config JSON")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory to write the final MP4 into",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=Path("output/.tmp"),
        help="Directory for intermediate clip files",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] Config: {e}", file=sys.stderr)
        return 1

    mode = detect_mode(config)
    print(
        f"[INFO] Mode: {mode.name} ({config.cut_trigger.value}, tolerance "
        f"{config.tolerance_ms_low}-{config.tolerance_ms_high}ms, "
        f"min_segment {config.min_segment_ms}ms)",
        file=sys.stderr,
    )

    y_full, sr_loaded = librosa.load(str(config.audio), sr=22050, mono=True)
    sr = int(sr_loaded)

    start_sample = int(config.audio_start_offset * sr)
    end_sample = start_sample + int(config.edit_length_seconds * sr)
    y = y_full[start_sample:end_sample]

    if config.audio_start_offset > 0:
        print(f"[INFO] Audio offset: {config.audio_start_offset}s", file=sys.stderr)

    analysis = analyze_audio(
        y=y,
        sr=sr,
        bpm_override=config.bpm_override,
        bass_hit_amplitude_threshold=config.bass_hit_amplitude_threshold,
    )
    if analysis.beat_times_ms.size == 0:
        print("[WARN] No beats detected; falling back to 120 BPM metronomic grid", file=sys.stderr)

    print(
        f"[INFO] BPM: {analysis.bpm:.1f}, {analysis.beat_times_ms.size} beats, "
        f"{analysis.bass_onset_times_ms.size} sub-bass onsets",
        file=sys.stderr,
    )

    silence_gaps = detect_silence_gaps(
        beat_times_ms=analysis.beat_times_ms,
        edit_length_ms=config.edit_length_seconds * 1000,
    )
    for gap in silence_gaps:
        print(
            f"[WARN] Silence gap {gap.start_ms:.0f}-{gap.end_ms:.0f}ms "
            f"({gap.duration_ms / 1000.0:.1f}s) — holding current clip",
            file=sys.stderr,
        )

    plan = plan_cuts(
        beat_times_ms=analysis.beat_times_ms,
        bass_onset_times_ms=analysis.bass_onset_times_ms,
        edit_length_ms=config.edit_length_seconds * 1000,
        cut_frequency=config.cut_frequency,
        cut_trigger=config.cut_trigger,
        tolerance_ms_low=config.tolerance_ms_low,
        tolerance_ms_high=config.tolerance_ms_high,
        max_bass_snaps=config.max_bass_snaps_per_edit,
        alternation_variation=config.alternation_variation,
        max_consecutive_same_source=config.max_consecutive_same_source,
        source_a_seconds=config.source_a_seconds,
        source_b_seconds=config.source_b_seconds,
        min_segment_ms=config.min_segment_ms,
        rng_seed=args.seed,
    )
    print(f"[INFO] Planned {len(plan.segments)} segments", file=sys.stderr)

    assignment = sample_clips(
        plan=plan,
        source_a_path=config.source_a,
        source_b_path=config.source_b,
        avoid_clip_repeat=config.avoid_clip_repeat,
        rng_seed=args.seed,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    song_title = config.audio.stem
    output_filename = format_output_filename(
        config_name=config.config_name,
        song_title=song_title,
        edit_length_seconds=config.edit_length_seconds,
    )
    output_path = args.output_dir / output_filename

    try:
        render(
            assignment=assignment,
            audio_path=config.audio,
            ffmpeg_filter=config.ffmpeg_filter,
            output_resolution=config.output_resolution,
            frame_rate=config.output_frame_rate,
            bitrate=config.output_bitrate,
            audio_fade_in_s=config.audio_fade_in_duration,
            audio_fade_out_s=config.audio_fade_out_duration,
            edit_length_s=float(config.edit_length_seconds),
            output_path=output_path,
            temp_dir=args.temp_dir,
            audio_start_offset_s=config.audio_start_offset,
        )
    except Exception as e:  # pragma: no cover
        print(f"[ERROR] Render failed: {e}", file=sys.stderr)
        return 2

    print(f"[OK] Wrote {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
