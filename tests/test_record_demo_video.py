from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from record_demo_video import STEPS


def test_optional_demo_recorder_stays_within_video_limit() -> None:
    assert sum(duration for _, duration in STEPS) <= 180
    assert all(text and duration > 0 for text, duration in STEPS)
