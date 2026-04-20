# Beatsync Engine

Two-source beat-synced video editor. Takes two source videos and one audio track,
detects the BPM, alternates clips on the beat, applies a subtle color grade, and
exports a finished 9:16 MP4 in either **15-second Punch** or **30-second Breathe** mode.

## Mode Overview

| Mode | Length | Default Cut Trigger | Default Tolerance | Default Min Segment |
|---|---|---|---|---|
| Punch | 15s | `beat_grid` (strict) | 50-70 ms | 1500 ms |
| Breathe | 30s | `hybrid` (beat grid + 808 snap) | 80-100 ms | 2500 ms |

The mode is chosen automatically from `edit_length_seconds` in the config. All timing values (`cut_trigger`, `min_segment_ms`, `tolerance_ms_low`, `tolerance_ms_high`, `max_bass_snaps_per_edit`) can be overridden directly in the config JSON.

## Requirements

**With Docker (no local setup needed):**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

**Without Docker:**
- Python 3.12+
- FFmpeg 5.0+ (with `ffprobe`)
- libsndfile (`brew install libsndfile` on macOS)

## Quick Start

1. **Clone the repo:**
   ```bash
   git clone <repo-url> beatsync
   cd beatsync
   ```

2. **Drop your media files into `media/`:**
   - Source A: the artist video (music video, live performance)
   - Source B: the cultural reference video
   - Audio: the song (MP3 or WAV)

3. **Edit your config JSON** (see `config_punch.json` or `config_breathe.json` for examples):
   ```json
   {
     "source_a": "media/your_artist_video.mp4",
     "source_b": "media/your_cultural_reference.mp4",
     "audio": "media/your_song.mp3"
   }
   ```

4. **Run beatsync:**

   **With Docker:**
   ```bash
   docker compose run --rm beatsync --config config_punch.json
   ```

   The first run auto-builds the image. If you later edit `Dockerfile` or `pyproject.toml`, rebuild before running again:
   ```bash
   docker compose build
   ```

   **Without Docker:**
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -e .
   .venv/bin/python -m beatsync --config config_punch.json
   ```

   Add `--seed 42` for reproducible output.

The finished MP4 lands in `output/` on your machine (mapped to `/app/output` inside the Docker container via docker-compose volumes).

## Switching Modes

Set `edit_length_seconds` in your config JSON:

- `15` for Punch (tight beat grid cuts)
- `30` for Breathe (looser cuts with optional 808 bass snaps)

Update `source_a_seconds` and `source_b_seconds` so they sum to `edit_length_seconds`:
```json
"edit_length_seconds": 15,
"source_a_seconds": 7,
"source_b_seconds": 8
```

## Config Parameter Reference

| Parameter | Description |
|---|---|
| `config_name` | Name embedded in the output filename |
| `config_version` | Config iteration version |
| `source_a` | Path to Artist Visual video file |
| `source_b` | Path to Cultural Reference video file |
| `audio` | Path to audio track |
| `edit_length_seconds` | `15` (Punch) or `30` (Breathe) |
| `source_a_seconds` | Target seconds from Source A |
| `source_b_seconds` | Target seconds from Source B |
| `max_consecutive_same_source` | Max consecutive segments from the same source (>= 2) |
| `alternation_variation` | 0.0-1.0 probability of staying on the same source |
| `cut_frequency` | 0.0-1.0 probability a beat becomes a cut |
| `bpm_override` | `0` for auto-detect, or a positive number to force BPM |
| `bass_hit_amplitude_threshold` | 0.0-1.0 minimum strength for an 808 snap |
| `max_bass_snaps_per_edit` | Upper bound on 808 snaps per edit |
| `cut_trigger` | `beat_grid` (cuts on beats only) or `hybrid` (beats + 808 snaps). Optional, defaults by mode |
| `min_segment_ms` | Minimum duration between cuts in milliseconds. Optional, defaults by mode |
| `tolerance_ms_low` | Lower bound of the 808 snap window in ms. Optional, defaults by mode |
| `tolerance_ms_high` | Upper bound of the 808 snap window in ms. Optional, defaults by mode |
| `ffmpeg_filter` | FFmpeg filter chain applied to every clip |
| `output_resolution` | Output WxH (default `1080x1920`) |
| `output_frame_rate` | Output FPS (default `30`) |
| `output_bitrate` | Output video bitrate (default `8M`) |
| `audio_fade_in_duration` | Audio fade-in in seconds. Optional, defaults to `0.5` |
| `audio_fade_out_duration` | Audio fade-out in seconds. Optional, defaults to `1.0` |
| `audio_start_offset` | Start the audio from this many seconds in. Optional, defaults to `0` |
| `audio_end_offset` | Trim this many seconds off the end of the audio. Optional, defaults to `0` |

## How Changing Parameters Affects the Output

- **Change `source_b`**: swap the cultural reference video for a completely different edit feel
- **Change `edit_length_seconds` (15 vs 30)**: toggles tight mechanical cuts (Punch) vs looser humanized cuts with bass snaps (Breathe)
- **Change split ratio (`source_a_seconds`/`source_b_seconds`)**: e.g., `20/10` in a 30s edit makes Source A dominant
- **Set `bpm_override`**: forces a specific BPM when auto-detection gets it wrong
- **Re-run same config**: fresh random seed each run means different clip sampling. Use `--seed <int>` for reproducibility

## Development

Local install (requires Python 3.12+):
```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install
```

The last line registers a git hook that runs `ruff check --fix` and `ruff format` on every commit.

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

## Runtime Log Output

The engine writes a short log to stderr for every run. Key lines:

- `[INFO] Mode: …` — which preset (Punch/Breathe) was selected and its tolerance/min-segment values
- `[INFO] BPM: …, N beats, M sub-bass onsets` — detected tempo and beat/onset counts
- `[INFO] Planned N segments` — final cut count after probability filter and min-segment gate
- `[WARN] Silence gap Xms-Yms (Zs) — holding current clip` — fired when a stretch of the timeline has no detected beats for longer than 2 seconds. The engine holds the current clip through the gap rather than forcing cuts through silence.
- `[WARN] Clip N too dark (luma=…), resampling` — a sampled clip's first frame was below the brightness threshold; the engine picks a different position in the same source file

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `ffmpeg: command not found` on local run | Install FFmpeg: `brew install ffmpeg` on macOS, or use the Docker path instead |
| `FileNotFoundError: source_a file does not exist` | Check the path in your config JSON matches a file in `media/`. Paths are resolved relative to your working directory |
| `[WARN] No beats detected; falling back to 120 BPM` | librosa could not find a beat grid in the audio. Set `bpm_override` in the config to force a known tempo |
| `[WARN] Clip N still dark` after retries | Source video has very little bright footage. Pick a different source or lower `MIN_BRIGHTNESS_LUMA` in `renderer.py` |
| Source video shorter than `edit_length_seconds` | Distributed sampling needs duration > edit length. Use a longer source or shorten `edit_length_seconds` |
| Docker: permission denied writing to `output/` | The mounted `output/` directory needs to be writable by your user. Run `chmod u+w output` on the host |
| `KeyError` on config load | A required field is missing from your JSON. Copy `config.json` or `config_punch.json` and edit from there rather than writing one from scratch |

## Architecture

Five-stage pipeline:
```
Config -> AudioAnalysis -> CutPlan -> ClipAssignment -> Render
```

Modules in `src/beatsync/`:

| Module | Responsibility |
|---|---|
| `config.py` | Load and validate JSON config, detect mode |
| `audio.py` | BPM detection, beat grid, sub-bass onset detection (librosa) |
| `planner.py` | Beat grid to cut points, 808 snap logic, A/B source assignment |
| `sampler.py` | Map segments to time ranges in source videos (zone-based sampling) |
| `renderer.py` | FFmpeg command construction, clip extraction, concat, final mux |
| `ffprobe.py` | Shared ffprobe utilities (media duration) |

## License

MIT
