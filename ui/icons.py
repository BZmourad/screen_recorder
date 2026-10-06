"""Inline SVG icons rendered to QIcon.

Keeps the app asset-free: no need to bundle PNG/SVG files. Colors are
injected at runtime so icons match the current theme.
"""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"
    stroke-linejoin="round">{body}</svg>"""


_SVG_BODIES = {
    "refresh": '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/>'
               '<path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/>',
    "cursor": '<path d="M4 4l7 17 2.5-6.5L20 12z"/>',
    "mic": '<rect x="9" y="3" width="6" height="12" rx="3"/>'
           '<path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>',
    "dot": '<circle cx="12" cy="12" r="6" fill="{color}"/>',
    "play": '<path d="M6 4l14 8-14 8z" fill="{color}"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" fill="{color}"/>'
             '<rect x="14" y="4" width="4" height="16" fill="{color}"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2" fill="{color}"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "monitor": '<rect x="2" y="4" width="20" height="13" rx="2"/>'
               '<path d="M8 21h8"/><path d="M12 17v4"/>',
    "check": '<path d="M5 13l4 4L19 7"/>',
}


def make_icon(name: str, color: str = "#e6e8ee", size: int = 18) -> QIcon:
    """Return a QIcon built from an inline SVG body."""
    body = _SVG_BODIES.get(name)
    if body is None:
        return QIcon()
    svg = _SVG_TEMPLATE.format(color=color, body=body.format(color=color))

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)