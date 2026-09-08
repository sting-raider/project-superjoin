from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from record_demo_video import REDACTION_STYLE, STEPS, redaction_init_script


def test_optional_demo_recorder_stays_within_video_limit() -> None:
    assert sum(duration for _, duration in STEPS) <= 180
    assert all(text and duration > 0 for text, duration in STEPS)


def test_public_capture_masks_source_text_before_first_page_paint() -> None:
    assert ".document-info *" in REDACTION_STYLE
    assert ".inspector > :not(.inspector-top) *" in REDACTION_STYLE
    assert "Demo workspace" in REDACTION_STYLE
    script = redaction_init_script()
    assert script.startswith("(() => {")
    assert script.endswith("})();")
