"""Clickable thumbnail widget for one monitor.

Captures a small preview of the screen with mss, displays it inside a card
with hover and selected states, and emits `clicked` on left-click.

The preview size is configurable so the widget can scale with the window.
"""

import logging
from typing import Optional

import mss
import numpy as np
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from recorder import CaptureSource
from ui.icons import make_icon
from ui.theme import Colors

log = logging.getLogger(__name__)


class ScreenThumbnail(QFrame):
    """A clickable card showing a live preview of one monitor."""

    clicked = Signal(object)   # emits the CaptureSource

    def __init__(
        self,
        source: CaptureSource,
        preview_size: QSize = QSize(320, 180),
    ) -> None:
        super().__init__()
        self.source = source
        self._selected = False
        self._preview_size = preview_size

        self.setObjectName("screenThumbnail")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(240)
        self.setMinimumHeight(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- Preview ---
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(preview_size)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setStyleSheet(
            f"background-color: #0a0c12; "
            f"border: 1px solid {Colors.BORDER}; "
            f"border-radius: 8px; "
            f"color: {Colors.TEXT_DIM};"
        )
        self.image_label.setText("Loading…")
        layout.addWidget(self.image_label, stretch=1)

        # --- Footer: icon + label + selection badge ---
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(
            make_icon("monitor", Colors.TEXT_MUTED, 16).pixmap(16, 16)
        )
        footer.addWidget(self.icon_label)

        self.caption = QLabel(source.label)
        self.caption.setStyleSheet(
            f"color: {Colors.TEXT}; font-weight: 600; font-size: 10pt;"
        )
        footer.addWidget(self.caption, stretch=1)

        self.badge = QLabel("✓")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(22, 22)
        self.badge.setStyleSheet(
            f"background-color: {Colors.PRIMARY}; "
            f"color: white; font-size: 11pt; font-weight: 700; "
            f"border-radius: 11px;"
        )
        self.badge.setVisible(False)
        footer.addWidget(self.badge)

        layout.addLayout(footer)

        self._apply_style()
        self.refresh_preview()

    # ---------------------------------------------------------------- public
    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.badge.setVisible(selected)
        self._apply_style()

    def is_selected(self) -> bool:
        return self._selected

    def set_preview_size(self, size: QSize) -> None:
        """Resize the preview area (called when the layout changes)."""
        self._preview_size = size
        self.image_label.setMinimumSize(size)
        self.refresh_preview()

    def refresh_preview(self) -> None:
        """Re-grab a fresh screenshot of the monitor and update the preview."""
        pix = self._grab_pixmap()
        if pix is None:
            self.image_label.setText("Preview unavailable")
            return
        self.image_label.setPixmap(pix)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(
            self._preview_size.width() + 24,
            self._preview_size.height() + 60,
        )

    # --------------------------------------------------------------- events
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit(self.source)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        if not self._selected and self.isEnabled():
            self.setStyleSheet(self._card_style(hover=True, selected=False))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._selected:
            self._apply_style()
        super().leaveEvent(event)

    # -------------------------------------------------------------- internal
    def _apply_style(self) -> None:
        self.setStyleSheet(self._card_style(hover=False, selected=self._selected))

    @staticmethod
    def _card_style(hover: bool, selected: bool) -> str:
        if selected:
            border = f"2px solid {Colors.PRIMARY}"
            bg = Colors.SELECTED_BG
        elif hover:
            border = f"1px solid {Colors.BORDER_SOLID}"
            bg = Colors.BG_CARD_HOVER
        else:
            border = f"1px solid {Colors.BORDER}"
            bg = Colors.BG_CARD
        return (
            f"QFrame#screenThumbnail {{ "
            f"background-color: {bg}; "
            f"border: {border}; "
            f"border-radius: 12px; }}"
        )

    def _grab_pixmap(self) -> Optional[QPixmap]:
        """Capture the target monitor and scale it to the preview size."""
        try:
            bbox = self.source.resolve_bbox()
            if bbox is None:
                return None
            with mss.mss() as sct:
                raw = np.array(sct.grab(bbox))  # BGRA

            h, w = raw.shape[:2]
            rgba = np.ascontiguousarray(raw[:, :, [2, 1, 0, 3]])
            qimg = QImage(
                rgba.data, w, h, w * 4, QImage.Format_RGBA8888
            ).copy()
            pix = QPixmap.fromImage(qimg)

            target_w = max(self.image_label.width(), self._preview_size.width())
            target_h = max(self.image_label.height(), self._preview_size.height())

            return pix.scaled(
                target_w,
                target_h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Thumbnail capture failed for %s: %s", self.source.label, exc)
            return None