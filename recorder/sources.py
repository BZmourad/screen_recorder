"""Enumerate capturable monitors.

Only physical monitors are listed. Each `CaptureSource` is a monitor and
knows how to resolve its current screen-space bounding box, which the
recorder queries every frame (in case of a monitor change mid-recording).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import mss


@dataclass
class CaptureSource:
    """A capturable target: here, always a monitor."""

    kind: str                # always "monitor" in v6
    source_id: int           # mss monitor index (1-based)
    label: str               # human-readable label

    def resolve_bbox(self) -> Optional[dict]:
        """Return {'left','top','width','height'} or None if unavailable."""
        with mss.mss() as sct:
            idx = self.source_id
            if idx < 1 or idx >= len(sct.monitors):
                return None
            m = sct.monitors[idx]
            return {
                "left": m["left"],
                "top": m["top"],
                "width": m["width"],
                "height": m["height"],
            }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def list_monitors() -> List[CaptureSource]:
    """Return one CaptureSource per physical monitor."""
    sources: List[CaptureSource] = []
    with mss.mss() as sct:
        # Skip index 0 (the virtual "all monitors" entry)
        for i, mon in enumerate(sct.monitors[1:], start=1):
            label = f"Screen {i}  ({mon['width']}×{mon['height']})"
            sources.append(CaptureSource(kind="monitor", source_id=i, label=label))
    return sources


def list_all_sources() -> List[CaptureSource]:
    """Alias kept for backward compatibility — only monitors exist in v6."""
    return list_monitors()