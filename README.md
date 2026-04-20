# Beatsync Engine

A config-driven beat-synced video editor in Python. Point it at a handful of source videos and an audio track, pick a mode, and it detects the BPM, alternates clips on the beat, applies a color grade, and renders a finished 9:16 MP4.

Works for music videos, reels, shorts, sports highlights, or any use case where you want cuts that land on the beat without manual editing.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Features

- **BPM detection** via librosa, with half/double clamping for trap and hip-hop
- **Sub-bass onset detection** for 808 snap cuts in hybrid modes
- **N source videos** with optional per-source weighting
- **Five built-in modes** covering everything from 10-second hooks to 90-second long-form edits
- **Distributed clip sampling** that spreads picks across the full duration of each source
- **Brightness gate** with auto-resample for dark frames
- **FFmpeg filter chain** passed through as a config value, no hardcoded grade
- **9:16 output** with center crop from 16:9 sources, configurable resolution and bitrate
- **Dockerfile** included for zero-setup runs

## Modes

| Mode | Length | Cut Trigger | Min Segment | Tolerance | Max 808 snaps | Feel |
|---|---|---|---|---|---|---|
| `strobe` | 10s | `beat_grid` | 500ms | 30-50ms | 0 | Dense rapid cuts for viral hooks |
| `drill` | 15s | `beat_grid` | 1500ms | 50-70ms | 0 | Tight grid, rap visualizer energy |
| `float` | 30s | `hybrid` | 2500ms | 80-100ms | 4 | Loose with bass snaps, cinematic |
| `cascade` | 45s | `hybrid` | 2000ms | 80-120ms | 6 | Moderate density, long-form |
| `epic` | 90s | `hybrid` | 5000ms | 100-150ms | 10 | Few cuts, scene-level storytelling |

Every timing parameter is overridable in the config. Modes are just named presets.

## Install

### From source

```bash
git clone https://github.com/Antiarin/beatsync-engine
cd beatsync-engine
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install
```

Requires Python 3.12+, FFmpeg 5.0+ (with `ffprobe`), and libsndfile (`brew install libsndfile` on macOS).

### With Docker

```bash
docker compose run --rm beatsync --config examples/drill.json
```

First run auto-builds the image. No FFmpeg or Python install needed on the host.

## Quick Start

1. Drop source videos and an audio file into `media/` (paths are relative to your working directory).
2. Pick a mode and point a config at your files:

```json
{
  "config_name": "my_edit",
  "config_version": "1.0",
  "mode": "drill",
  "sources": [
    "media/artist_visual.mp4",
    "media/cultural_reference.mp4"
  ],
  "audio": "media/song.mp3"
}
```

3. Render:

```bash
beatsync --config my_config.json
```

Add `--seed 42` for reproducible output. The finished MP4 lands in `output/`.

## Using N Sources

Pass any number of sources (>=2). Weights default to equal; set `source_weights` to bias specific sources:

```json
{
  "mode": "cascade",
  "sources": [
    "media/artist.mp4",
    "media/b_roll.mp4",
    "media/archival.mp4"
  ],
  "source_weights": [0.5, 0.3, 0.2]
}
```

Weights are auto-normalized so they do not need to sum to 1.0.

## Config Parameter Reference

### Required

| Parameter | Description |
|---|---|
| `config_name` | Name embedded in the output filename |
| `config_version` | Config iteration version |
| `mode` | One of `strobe`, `drill`, `float`, `cascade`, `epic` |
| `sources` | Array of paths to source video files (>=2) |
| `audio` | Path to audio track |

### Optional (sensible defaults)

| Parameter | Default | Description |
|---|---|---|
| `source_weights` | equal | Per-source weights, auto-normalized |
| `edit_length_seconds` | from mode | Override the mode's default length |
| `cut_frequency` | 0.6 | Probability a beat becomes a cut |
| `max_consecutive_same_source` | 2 | Max consecutive segments from the same source |
| `alternation_variation` | 0.15 | Probability of staying on the same source at a switch point |
| `bpm_override` | 0 | 0 to auto-detect, or a positive number to force BPM |
| `bass_hit_amplitude_threshold` | 0.7 | Minimum onset strength for an 808 snap (0.0-1.0) |
| `cut_trigger` | from mode | `beat_grid` or `hybrid` |
| `min_segment_ms` | from mode | Minimum duration between cuts |
| `tolerance_ms_low` / `tolerance_ms_high` | from mode | 808 snap window in ms |
| `max_bass_snaps_per_edit` | from mode | Cap on 808 snaps |
| `clip_selection` | `random` | Currently only `random` |
| `avoid_clip_repeat` | `true` | Prevent reusing zones of a source |
| `long_clip_sampling_strategy` | `distributed` | How to sample long sources |
| `ffmpeg_filter` | `""` | Custom FFmpeg filter chain applied to every clip |
| `aspect_ratio` | `9:16` | Output aspect ratio |
| `output_resolution` | `1080x1920` | Output WxH |
| `output_frame_rate` | `30` | Output FPS |
| `output_bitrate` | `8M` | Output video bitrate |
| `render_quality_tier` | `draft` | `draft` or `final_bake` |
| `audio_fade_in_duration` | 0.5 | Audio fade-in seconds |
| `audio_fade_out_duration` | 1.0 | Audio fade-out seconds |
| `audio_start_offset` | 0 | Skip this many seconds into the audio |
| `audio_end_offset` | 0 | Trim this many seconds off the end |

## Architecture

Five-stage pipeline. Each stage produces a typed dataclass consumed by the next:

```
Config -> AudioAnalysis -> CutPlan -> ClipAssignment -> Render
```

| Module | Responsibility |
|---|---|
| `config.py` | Load and validate JSON, resolve mode presets |
| `audio.py` | BPM detection, beat grid, sub-bass onset detection, silence gap detection |
| `planner.py` | Beat grid to cut points, 808 snap logic, N-source assignment by weighted deficit |
| `sampler.py` | Per-source distributed zone sampling |
| `renderer.py` | FFmpeg command construction, extract + concat + mux |
| `ffprobe.py` | Shared ffprobe utilities |

## Runtime Log Output

The engine writes a short log to stderr:

- `[INFO] Mode: ...` — mode and its resolved tolerance/min-segment
- `[INFO] Sources: N (weights: ...)` — source count and normalized weights
- `[INFO] BPM: X, N beats, M sub-bass onsets` — detected audio structure
- `[INFO] Planned N segments` — final cut count
- `[WARN] Silence gap Xms-Yms (Zs) — holding current clip` — stretches >2s without beats
- `[WARN] Clip N too dark (luma=...), resampling` — brightness gate firing

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg: command not found` | Install FFmpeg (`brew install ffmpeg` on macOS) or use the Docker path |
| `FileNotFoundError: sources[i] file does not exist` | Check the paths in your config JSON |
| `[WARN] No beats detected` | librosa could not find a beat grid; set `bpm_override` to force a tempo |
| `[WARN] Clip N still dark` after retries | Source has very little bright footage; pick a different source or lower `MIN_BRIGHTNESS_LUMA` in `renderer.py` |
| Source shorter than `edit_length_seconds` | Use a longer source or shorten `edit_length_seconds` |
| `KeyError` on config load | A required field is missing; copy from `examples/` rather than writing from scratch |

## Development

Run tests:

```bash
.venv/bin/pytest
```

Lint and typecheck:

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
.venv/bin/mypy src/
```

Pre-commit runs ruff check and format on every commit. Install once with:

```bash
.venv/bin/pre-commit install
```

## Contributing

Issues and pull requests welcome. Please run the test suite and `ruff` locally before opening a PR.

## License

MIT. See [LICENSE](LICENSE).
