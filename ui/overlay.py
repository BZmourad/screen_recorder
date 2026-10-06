"""Floating overlay for recording indicator OR countdown.

The overlay is positioned on the TARGET screen (the one being recorded),
not on the primary screen. This matters in multi-monitor setups: if the
user records Screen 2, the indicator must appear on Screen 2.

Two modes:
  * "recording" — dark circle with blinking red dot + elapsed timer
  * "countdown" — dark circle with a big number (3, 2, 1)

The overlay is excluded from screen capture with
SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) on Windows 10 2004+.
"""

import ctypes
import logging
from ctypes import wintypes
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QGuiApplication
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


# --- Windows API for capture exclusion ------------------------------------- #
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004+


POSITIONS = (
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)


class RecordingOverlay(QWidget):
    """Small circular indicator with REC dot / timer, or a countdown."""

    DIAMETER = 130
    MARGIN = 20

    def __init__(self) -> None:
        super().__init__(None)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.resize(self.DIAMETER, self.DIAMETER)

        self._mode = "recording"
        self._seconds = 0
        self._countdown_value = 3
        self._dot_visible = True
        self._position_name = "bottom-right"
        self._capture_excluded = False

        # Target screen rect in Qt logical coords: (x, y, w, h)
        self._target_rect: Optional[Tuple[int, int, int, int]] = None

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_dot)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- public
    def set_target_screen(self, source) -> None:
        """Tell the overlay which screen (CaptureSource) to attach to.

        `source` must expose `resolve_bbox()` returning
        {'left', 'top', 'width', 'height'} in PHYSICAL pixels.
        """
        self._target_rect = self._compute_target_rect(source)

    def start(self, position_name: str = "bottom-right") -> None:
        """Show the overlay in RECORDING mode (blinking dot + timer)."""
        self._mode = "recording"
        self._seconds = 0
        self._dot_visible = True
        self._position_name = position_name

        self._reposition()
        self.show()
        self.raise_()
        QTimer.singleShot(0, self._try_exclude_from_capture)

        self._blink_timer.start()
        self._clock_timer.start()
        log.info(
            "Overlay shown (recording mode) at %s on target rect=%s",
            position_name, self._target_rect,
        )

    def start_countdown(self, seconds: int, position_name: str = "top-right") -> None:
        """Show the overlay in COUNTDOWN mode (big number, seconds → 1)."""
        self._mode = "countdown"
        self._countdown_value = max(1, int(seconds))
        self._position_name = position_name

        self._reposition()
        self.show()
        self.raise_()
        QTimer.singleShot(0, self._try_exclude_from_capture)

        self._blink_timer.stop()
        self._clock_timer.start()
        log.info(
            "Overlay shown (countdown %ds) at %s on target rect=%s",
            seconds, position_name, self._target_rect,
        )

    def stop(self) -> None:
        self._blink_timer.stop()
        self._clock_timer.stop()
        self.hide()
        log.info("Overlay hidden")

    def set_position(self, position_name: str) -> None:
        if position_name not in POSITIONS:
            position_name = "bottom-right"
        self._position_name = position_name
        self._reposition()

    # -------------------------------------------------------------- internal
    def _compute_target_rect(self, source) -> Optional[Tuple[int, int, int, int]]:
        """Return the target screen's logical rect (x, y, w, h) in Qt coords.

        Strategy: match by device name.
          1. Enumerate Windows monitors with EnumDisplayMonitors to get the
             ordered list of device names (\\\\.\\DISPLAY1, \\\\.\\DISPLAY2, ...).
             This order is the SAME as mss.monitors[1:], because mss uses the
             same underlying API ordering.
          2. Use the CaptureSource.source_id (1-based) to index into that list.
          3. Find the QScreen whose name() matches the device name.
          4. Return that QScreen's logical geometry.

        This avoids all DPI / size / position ambiguity, which was causing the
        wrong screen to be selected when both monitors have identical
        resolutions but different DPI scaling.
        """
        # --- Step 1: enumerate Windows device names in the same order as mss --
        device_names = self._enum_display_device_names()
        if not device_names:
            log.warning("Could not enumerate Windows display device names")
            return self._fallback_rect()

        # mss.monitors[0] is the virtual screen, so mss index N == device_names[N-1]
        idx = source.source_id - 1
        if idx < 0 or idx >= len(device_names):
            log.warning(
                "source_id=%d out of range for %d device(s): %s",
                source.source_id, len(device_names), device_names,
            )
            return self._fallback_rect()

        target_device = device_names[idx]
        log.debug(
            "Target device for source_id=%d is '%s' (all: %s)",
            source.source_id, target_device, device_names,
        )

        # --- Step 2: find the QScreen with matching name ---------------------
        screens = QGuiApplication.screens()
        for qscreen in screens:
            # QScreen.name() returns something like '\\\\.\\DISPLAY1'
            if qscreen.name() == target_device:
                g = qscreen.geometry()
                log.info(
                    "Overlay target matched by NAME: source_id=%d → '%s' "
                    "(logical %d,%d %dx%d @ %.2fx)",
                    source.source_id, qscreen.name(),
                    g.x(), g.y(), g.width(), g.height(),
                    qscreen.devicePixelRatio(),
                )
                return (g.x(), g.y(), g.width(), g.height())

        # --- Step 3: fallback by index (if names don't match anywhere) -------
        log.warning(
            "No QScreen with name '%s' found. Available: %s",
            target_device, [s.name() for s in screens],
        )
        if 0 <= idx < len(screens):
            g = screens[idx].geometry()
            log.warning(
                "Falling back to QScreen index %d ('%s') at (%d,%d,%d,%d)",
                idx, screens[idx].name(),
                g.x(), g.y(), g.width(), g.height(),
            )
            return (g.x(), g.y(), g.width(), g.height())

        return self._fallback_rect()

    def _fallback_rect(self) -> Optional[Tuple[int, int, int, int]]:
        """Return the primary screen's logical rect."""
        primary = QGuiApplication.primaryScreen()
        if primary is None:
            return None
        g = primary.geometry()
        log.error(
            "Overlay falling back to primary screen '%s' at (%d,%d,%d,%d)",
            primary.name(), g.x(), g.y(), g.width(), g.height(),
        )
        return (g.x(), g.y(), g.width(), g.height())

    @staticmethod
    def _enum_display_device_names():
        """Return the ordered list of Windows display device names.

        Uses EnumDisplayMonitors + GetMonitorInfoW. The resulting order is
        the same as mss.monitors[1:], because mss uses the same Windows API
        underneath. Each entry looks like '\\\\.\\DISPLAY1'.
        """
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )

        user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR,
            ctypes.POINTER(MONITORINFOEXW),
        ]
        user32.GetMonitorInfoW.restype = wintypes.BOOL

        names = []

        def _callback(hmonitor, _hdc, _rect, _lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                names.append(str(info.szDevice))
            return True

        user32.EnumDisplayMonitors(
            None, None, MonitorEnumProc(_callback), 0
        )
        return names

    def _tick(self) -> None:
        if self._mode == "recording":
            self._seconds += 1
            self.update()
        elif self._mode == "countdown":
            self._countdown_value -= 1
            if self._countdown_value <= 0:
                self._clock_timer.stop()
                self.hide()
            else:
                self.update()

    def _toggle_dot(self) -> None:
        self._dot_visible = not self._dot_visible
        if self._mode == "recording":
            self.update()

    def _reposition(self) -> None:
        """Move the overlay to the requested corner of the TARGET screen."""
        if self._target_rect is not None:
            x0, y0, w, h = self._target_rect
            left = x0
            top = y0
            right = x0 + w
            bottom = y0 + h
        else:
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            left, top = geo.left(), geo.top()
            right, bottom = geo.right(), geo.bottom()

        m = self.MARGIN
        d = self.DIAMETER

        if self._position_name == "top-left":
            x, y = left + m, top + m
        elif self._position_name == "top-right":
            x, y = right - d - m, top + m
        elif self._position_name == "bottom-left":
            x, y = left + m, bottom - d - m
        else:  # bottom-right
            x, y = right - d - m, bottom - d - m

        self.move(x, y)

    def _try_exclude_from_capture(self) -> None:
        try:
            hwnd = int(self.winId())
            ok = _user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if ok:
                self._capture_excluded = True
                log.debug("Overlay excluded from screen capture")
            else:
                err = ctypes.get_last_error()
                log.warning(
                    "SetWindowDisplayAffinity failed (err=%d). "
                    "Overlay may appear in the recording. "
                    "Windows 10 2004+ required.", err,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not exclude overlay from capture: %s", exc)

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        d = self.DIAMETER
        cx = d / 2.0
        cy = d / 2.0

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 20, 20, 200))
        painter.drawEllipse(QRectF(2, 2, d - 4, d - 4))

        pen = QPen(QColor(255, 255, 255, 60))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(2, 2, d - 4, d - 4))

        if self._mode == "countdown":
            painter.setPen(QColor(255, 255, 255, 245))
            font = painter.font()
            font.setPointSize(48)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(0, 0, d, d),
                Qt.AlignCenter,
                str(max(self._countdown_value, 0)),
            )
            painter.end()
            return

        dot_r = 7.0
        dot_cx = cx
        dot_cy = cy - 22.0
        if self._dot_visible:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(230, 40, 40, 255))
            painter.drawEllipse(
                QRectF(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2)
            )

        painter.setPen(QColor(255, 255, 255, 240))
        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)

        h = self._seconds // 3600
        m = (self._seconds % 3600) // 60
        s = self._seconds % 60
        text = f"{h:02d}:{m:02d}:{s:02d}"

        painter.drawText(
            QRectF(0, cy - 6, d, d / 2),
            Qt.AlignHCenter | Qt.AlignTop,
            text,
        )

        painter.end()