from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from check_video import validate_probe


def test_validate_probe_accepts_short_video_with_stream() -> None:
    result = validate_probe({"format": {"duration": "42.5"}, "streams": [{"codec_type": "video"}]})

    assert result == {"duration_seconds": 42.5, "video_streams": 1}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"format": {"duration": "181"}, "streams": [{"codec_type": "video"}]}, "exceeds"),
        ({"format": {"duration": "10"}, "streams": [{"codec_type": "audio"}]}, "no video stream"),
        ({"format": {}, "streams": [{"codec_type": "video"}]}, "duration is missing"),
    ],
)
def test_validate_probe_rejects_unpublishable_video(payload: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_probe(payload)
