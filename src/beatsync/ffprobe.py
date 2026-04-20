"""Shared ffprobe utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_duration_seconds(source_path: Path, fallback: float = 600.0) -> float:
    """Return the duration of a media file in seconds via ffprobe.

    Returns *fallback* if ffprobe fails or produces no output.
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return fallback
    return float(result.stdout.strip())
