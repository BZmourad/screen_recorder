"""A grid layout that reflows its items based on the available width.

Items are laid out left-to-right, top-to-bottom, and the number of columns
is recomputed whenever the container is resized. Items are expected to
implement `sizeHint()` or have a fixed size.
"""

import math
from typing import List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget


class ResponsiveGrid(QWidget):
    """A widget that arranges children in a responsive grid."""

    def __init__(
        self,
        item_min_width: int = 260,
        spacing: int = 14,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._items: List[QWidget] = []
        self._item_min_width = item_min_width
        self._spacing = spacing
        self._columns = 1

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)
        self._layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    # ---------------------------------------------------------------- public
    def set_item_min_width(self, width: int) -> None:
        self._item_min_width = max(120, width)
        self._relayout()

    def add_item(self, widget: QWidget) -> None:
        self._items.append(widget)
        self._relayout()

    def clear(self) -> None:
        """Remove all items from the grid (does not delete them)."""
        while self._layout.count():
            self._layout.takeAt(0)
        self._items.clear()
        self._columns = 0

    # --------------------------------------------------------------- events
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    # -------------------------------------------------------------- internal
    def _compute_columns(self) -> int:
        available = max(self.width(), 1)
        # Each column needs at least `_item_min_width` plus spacing
        cols = max(
            1,
            (available + self._spacing) // (self._item_min_width + self._spacing),
        )
        return int(cols)

    def _relayout(self) -> None:
        if not self._items:
            return

        new_cols = self._compute_columns()
        if new_cols == self._columns and self._layout.count() == len(self._items):
            return

        self._columns = new_cols
        # Remove all from layout (keep references)
        while self._layout.count():
            self._layout.takeAt(0)

        for i, widget in enumerate(self._items):
            row, col = divmod(i, new_cols)
            self._layout.addWidget(widget, row, col)

    # ------------------------------------------------------------ sizeHint
    def sizeHint(self) -> QSize:  # noqa: N802
        if not self._items:
            return QSize(0, 0)

        # Compute a reasonable height based on current column count
        cols = max(1, self._columns)
        rows = math.ceil(len(self._items) / cols)

        sample = self._items[0]
        item_h = sample.sizeHint().height() or 240
        total_h = rows * item_h + max(0, rows - 1) * self._spacing
        return QSize(0, total_h)