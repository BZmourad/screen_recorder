"""Enumerate capturable sources: monitors and top-level windows.

Returns a list of CaptureSource objects that the UI can display in a combo box.
The recorder uses `resolve_bbox()` on each frame so window moves/resizes are
tracked live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import mss


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class CaptureSource:
    """A capturable target: either a monitor or a window."""

    kind: str                # "monitor" or "window"
    source_id: int           # mss monitor index, or HWND for windows
    label: str               # human-readable label for the UI

    def resolve_bbox(self) -> Optional[dict]:
        """Return {'left','top','width','height'} or None if unavailable."""
        if self.kind == "monitor":
            with mss.mss() as sct:
                # mss.monitors[0] is the "all monitors" virtual screen.
                # Real monitors start at index 1.
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

        if self.kind == "window":
            return _window_bbox(self.source_id)

        return None


# --------------------------------------------------------------------------- #
# Monitors
# --------------------------------------------------------------------------- #
def list_monitors() -> List[CaptureSource]:
    """Return one CaptureSource per physical monitor."""
    sources: List[CaptureSource] = []
    with mss.mss() as sct:
        # Skip index 0 (virtual "all monitors" entry)
        for i, mon in enumerate(sct.monitors[1:], start=1):
            label = f"Screen {i}  ({mon['width']}×{mon['height']})"
            sources.append(CaptureSource(kind="monitor", source_id=i, label=label))
    return sources


# --------------------------------------------------------------------------- #
# Windows (Windows-only)
# --------------------------------------------------------------------------- #
def _window_bbox(hwnd: int) -> Optional[dict]:
    """Return the current screen-space bounding box of a window, or None."""
    try:
        import win32gui
    except ImportError:
        return None

    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        return None

    # Skip minimized windows — GetWindowRect returns nonsense for them
    if win32gui.IsIconic(hwnd):
        return None

    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None

    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    return {"left": left, "top": top, "width": width, "height": height}


def _is_capturable_window(hwnd: int) -> bool:
    """Filter out tool windows, hidden windows, and untitled shells."""
    try:
        import win32gui
        import win32con
    except ImportError:
        return False

    if not win32gui.IsWindowVisible(hwnd):
        return False
    if win32gui.GetParent(hwnd) != 0:
        return False  # top-level windows only
    if not win32gui.GetWindowText(hwnd).strip():
        return False  # skip untitled

    # Skip tool windows (floating palettes etc.)
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False

    # Skip minimized windows
    if win32gui.IsIconic(hwnd):
        return False

    # Skip tiny windows (usually invisible shells / tray helpers)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    if (right - left) < 100 or (bottom - top) < 100:
        return False

    return True


def list_windows() -> List[CaptureSource]:
    """Return one CaptureSource per visible top-level window."""
    try:
        import win32gui
    except ImportError:
        return []

    sources: List[CaptureSource] = []

    def _callback(hwnd: int, _lparam) -> bool:
        if not _is_capturable_window(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        if len(title) > 60:
            title = title[:57] + "…"
        sources.append(
            CaptureSource(
                kind="window",
                source_id=hwnd,
                label=f"Window: {title}",
            )
        )
        return True

    win32gui.EnumWindows(_callback, None)
    sources.sort(key=lambda s: s.label.lower())
    return sources


# --------------------------------------------------------------------------- #
# Combined
# --------------------------------------------------------------------------- #
def list_all_sources() -> List[CaptureSource]:
    """Monitors first, then windows."""
    return list_monitors() + list_windows()