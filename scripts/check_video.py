"""Validate a Project SuperJoin demo video before external publication."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any


def validate_probe(payload: dict[str, Any], max_seconds: float = 180.0) -> dict[str, Any]:
    """Return safe video metadata or raise a clear validation error."""

    raw_duration = (payload.get("format") or {}).get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("video duration is missing or invalid") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("video duration must be a positive finite number")
    if duration > max_seconds:
        raise ValueError(f"video duration {duration:.2f}s exceeds the {max_seconds:.0f}s limit")
    streams = payload.get("streams") or []
    if not any(isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams):
        raise ValueError("video file has no video stream")
    video_streams = sum(
        1 for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"
    )
    return {"duration_seconds": round(duration, 3), "video_streams": video_streams}


def check_video(path: Path, max_seconds: float = 180.0) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"video file not found: {path}")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("ffprobe is required to validate a video")
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or "ffprobe failed"
        raise ValueError(detail)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    metadata = validate_probe(payload, max_seconds)
    return {"status": "ok", "path": str(path), **metadata}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-seconds", type=float, default=180.0)
    args = parser.parse_args()
    result = check_video(args.path, args.max_seconds)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
