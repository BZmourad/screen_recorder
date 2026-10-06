"""Floating overlay showing a red dot + elapsed time during recording.

Two important behaviors:
  * The overlay is a borderless, always-on-top, click-through window.
  * On Windows 10 2004+ we call SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
    so the overlay is invisible to screen capture (mss / BitBlt), meaning it
    won't show up in the recorded video.
"""

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QApplication

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
    """Small circular indicator with REC dot and timer."""

    DIAMETER = 130
    MARGIN = 20

    def __init__(self) -> None:
        super().__init__(None)

        # Window flags: frameless, always on top, no taskbar entry, tool window
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

        self._seconds = 0
        self._dot_visible = True
        self._position_name = "bottom-right"
        self._capture_excluded = False

        # Blink timer — toggles the red dot every 500 ms
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_dot)

        # Clock timer — increments the displayed seconds
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- public
    def start(self, position_name: str = "bottom-right") -> None:
        """Show the overlay and start the timers."""
        self._seconds = 0
        self._dot_visible = True
        self._position_name = position_name

        self._reposition()
        self.show()
        self.raise_()

        # Must be called AFTER show() so the HWND exists
        QTimer.singleShot(0, self._try_exclude_from_capture)

        self._blink_timer.start()
        self._clock_timer.start()
        log.info("Overlay shown at %s (excluded=%s)", position_name, self._capture_excluded)

    def stop(self) -> None:
        """Hide the overlay and stop the timers."""
        self._blink_timer.stop()
        self._clock_timer.stop()
        self.hide()
        log.info("Overlay hidden")

    def set_position(self, position_name: str) -> None:
        """Update the position (can be called while visible)."""
        if position_name not in POSITIONS:
            position_name = "bottom-right"
        self._position_name = position_name
        self._reposition()

    # -------------------------------------------------------------- internal
    def _tick(self) -> None:
        self._seconds += 1
        self.update()

    def _toggle_dot(self) -> None:
        self._dot_visible = not self._dot_visible
        self.update()

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()

        m = self.MARGIN
        d = self.DIAMETER

        if self._position_name == "top-left":
            x, y = geo.left() + m, geo.top() + m
        elif self._position_name == "top-right":
            x, y = geo.right() - d - m, geo.top() + m
        elif self._position_name == "bottom-left":
            x, y = geo.left() + m, geo.bottom() - d - m
        else:  # bottom-right
            x, y = geo.right() - d - m, geo.bottom() - d - m

        self.move(x, y)

    def _try_exclude_from_capture(self) -> None:
        """Ask Windows to hide this window from screen capture."""
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

        # --- Dark circle background ---
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 20, 20, 200))  # semi-transparent dark
        painter.drawEllipse(QRectF(2, 2, d - 4, d - 4))

        # --- Subtle border ---
        pen = QPen(QColor(255, 255, 255, 60))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(2, 2, d - 4, d - 4))

        # --- Red blinking dot ---
        dot_r = 7.0
        dot_cx = cx
        dot_cy = cy - 22.0
        if self._dot_visible:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(230, 40, 40, 255))
            painter.drawEllipse(QRectF(dot_cx - dot_r, dot_cy - dot_r,
                                       dot_r * 2, dot_r * 2))

        # --- Timer text ---
        painter.setPen(QColor(255, 255, 255, 240))
        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)

        h = self._seconds // 3600
        m = (self._seconds % 3600) // 60
        s = self._seconds % 60
        text = f"{h:02d}:{m:02d}:{s:02d}"

        # Slightly below center
        painter.drawText(
            QRectF(0, cy - 6, d, d / 2),
            Qt.AlignHCenter | Qt.AlignTop,
            text,
        )

        painter.end()