"""Application theme: palette + global Qt stylesheet.

A single `apply_theme(app)` call is enough to make the whole app look modern
and consistent. Colors are grouped in the `Colors` class so they can be
reused in custom widgets (e.g. thumbnails).
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


class Colors:
    # Backgrounds
    BG_APP = "#0d0f16"
    BG_PANEL = "#161a24"
    BG_PANEL_ALT = "#1a1f2b"
    BG_CARD = "#1d2230"
    BG_CARD_HOVER = "#242b3d"
    BG_INPUT = "#12151e"
    BG_INPUT_HOVER = "#161a25"

    # Borders
    BORDER = "#262c3a"
    BORDER_STRONG = "#38405248"  # semi-transparent tone for hover
    BORDER_SOLID = "#384052"

    # Text
    TEXT = "#eaecf2"
    TEXT_MUTED = "#96a0b4"
    TEXT_DIM = "#5c6579"

    # Accents
    PRIMARY = "#3b82f6"
    PRIMARY_HOVER = "#60a5fa"
    PRIMARY_PRESSED = "#2563eb"
    SUCCESS = "#22c55e"
    SUCCESS_HOVER = "#34d977"
    WARNING = "#f59e0b"
    WARNING_HOVER = "#fbbf24"
    DANGER = "#ef4444"
    DANGER_HOVER = "#f87171"

    # State
    REC_DOT = "#ef4444"
    SELECTED = PRIMARY
    SELECTED_BG = "#16233d"


def apply_theme(app: QApplication) -> None:
    """Install a dark modern stylesheet on the QApplication."""

    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    qss = f"""
    /* ============================================================
       Global
       ============================================================ */
    QWidget {{
        background-color: {Colors.BG_APP};
        color: {Colors.TEXT};
        font-family: "Segoe UI", "Inter", "SF Pro Text", sans-serif;
        font-size: 10pt;
    }}

    QMainWindow {{ background-color: {Colors.BG_APP}; }}

    /* ============================================================
       Tooltips
       ============================================================ */
    QToolTip {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT};
        border: 1px solid {Colors.BORDER_SOLID};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 9pt;
    }}

    /* ============================================================
       Group boxes (panels)
       ============================================================ */
    QGroupBox {{
        background-color: {Colors.BG_PANEL};
        border: 1px solid {Colors.BORDER};
        border-radius: 12px;
        margin-top: 18px;
        padding: 16px 14px 14px 14px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 16px;
        top: 6px;
        padding: 0 8px;
        color: {Colors.TEXT_MUTED};
        background-color: {Colors.BG_APP};
        letter-spacing: 0.5px;
    }}

    /* ============================================================
       Inputs
       ============================================================ */
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {Colors.BG_INPUT};
        border: 1px solid {Colors.BORDER};
        border-radius: 8px;
        padding: 8px 12px;
        selection-background-color: {Colors.PRIMARY};
        min-height: 18px;
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
        background-color: {Colors.BG_INPUT_HOVER};
        border: 1px solid {Colors.BORDER_SOLID};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {Colors.PRIMARY};
        background-color: {Colors.BG_INPUT};
    }}
    QLineEdit:disabled, QComboBox:disabled {{
        color: {Colors.TEXT_DIM};
        background-color: {Colors.BG_PANEL};
        border: 1px solid {Colors.BORDER};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}
    QComboBox::down-arrow {{
        width: 10px;
        height: 10px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {Colors.BG_CARD};
        border: 1px solid {Colors.BORDER_SOLID};
        border-radius: 8px;
        padding: 4px;
        selection-background-color: {Colors.PRIMARY};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 8px;
        border-radius: 4px;
        min-height: 22px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {Colors.BG_CARD_HOVER};
    }}

    /* ============================================================
       Checkboxes
       ============================================================ */
    QCheckBox {{
        spacing: 10px;
        color: {Colors.TEXT};
        padding: 4px 0;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {Colors.BORDER_SOLID};
        background-color: {Colors.BG_INPUT};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {Colors.PRIMARY};
        background-color: {Colors.BG_INPUT_HOVER};
    }}
    QCheckBox::indicator:checked {{
        background-color: {Colors.PRIMARY};
        border: 1px solid {Colors.PRIMARY};
    }}
    QCheckBox::indicator:checked:hover {{
        background-color: {Colors.PRIMARY_HOVER};
        border: 1px solid {Colors.PRIMARY_HOVER};
    }}
    QCheckBox:disabled {{
        color: {Colors.TEXT_DIM};
    }}

    /* ============================================================
       Buttons
       ============================================================ */
    QPushButton {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT};
        border: 1px solid {Colors.BORDER};
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 500;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {Colors.BG_CARD_HOVER};
        border: 1px solid {Colors.BORDER_SOLID};
    }}
    QPushButton:pressed {{
        background-color: {Colors.BG_PANEL};
        border: 1px solid {Colors.BORDER};
    }}
    QPushButton:disabled {{
        color: {Colors.TEXT_DIM};
        background-color: {Colors.BG_PANEL};
        border: 1px solid {Colors.BORDER};
    }}
    QPushButton:focus {{
        border: 1px solid {Colors.PRIMARY};
    }}

    /* --- Primary (green) --- */
    QPushButton#primaryButton {{
        background-color: {Colors.SUCCESS};
        border: 1px solid {Colors.SUCCESS};
        color: #0b0f14;
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {Colors.SUCCESS_HOVER};
        border: 1px solid {Colors.SUCCESS_HOVER};
    }}
    QPushButton#primaryButton:disabled {{
        background-color: #16381f;
        border: 1px solid #16381f;
        color: {Colors.TEXT_DIM};
    }}

    /* --- Warning (orange) --- */
    QPushButton#warningButton {{
        background-color: {Colors.WARNING};
        border: 1px solid {Colors.WARNING};
        color: #0b0f14;
        font-weight: 600;
    }}
    QPushButton#warningButton:hover {{
        background-color: {Colors.WARNING_HOVER};
        border: 1px solid {Colors.WARNING_HOVER};
    }}
    QPushButton#warningButton:disabled {{
        background-color: #3d2a0c;
        border: 1px solid #3d2a0c;
        color: {Colors.TEXT_DIM};
    }}

    /* --- Danger (red) --- */
    QPushButton#dangerButton {{
        background-color: {Colors.DANGER};
        border: 1px solid {Colors.DANGER};
        color: #ffffff;
        font-weight: 600;
    }}
    QPushButton#dangerButton:hover {{
        background-color: {Colors.DANGER_HOVER};
        border: 1px solid {Colors.DANGER_HOVER};
    }}
    QPushButton#dangerButton:disabled {{
        background-color: #3d1414;
        border: 1px solid #3d1414;
        color: {Colors.TEXT_DIM};
    }}

    /* --- Ghost --- */
    QPushButton#ghostButton {{
        background-color: transparent;
        border: 1px solid {Colors.BORDER};
        color: {Colors.TEXT_MUTED};
    }}
    QPushButton#ghostButton:hover {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT};
        border: 1px solid {Colors.BORDER_SOLID};
    }}

    /* --- Icon-only button --- */
    QPushButton#iconButton {{
        background-color: transparent;
        border: 1px solid {Colors.BORDER};
        border-radius: 8px;
        padding: 6px;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
    }}
    QPushButton#iconButton:hover {{
        background-color: {Colors.BG_CARD};
        border: 1px solid {Colors.BORDER_SOLID};
    }}

    /* ============================================================
       Scroll area
       ============================================================ */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.BORDER_SOLID};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {Colors.TEXT_DIM};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {Colors.BORDER_SOLID};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {Colors.TEXT_DIM};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ============================================================
       Labels
       ============================================================ */
    QLabel#statusBar {{
        background-color: {Colors.BG_PANEL};
        border: 1px solid {Colors.BORDER};
        border-radius: 10px;
        padding: 10px 14px;
        color: {Colors.TEXT_MUTED};
        font-size: 10pt;
    }}

    QLabel#timerLabel {{
        background-color: {Colors.BG_PANEL};
        border: 1px solid {Colors.BORDER};
        border-radius: 14px;
        padding: 20px;
        font-size: 44px;
        font-weight: 700;
        color: {Colors.TEXT};
        letter-spacing: 3px;
    }}
    QLabel#timerLabel[state="recording"] {{
        border: 1px solid {Colors.DANGER};
        color: {Colors.DANGER};
        background-color: #1a0f11;
    }}
    QLabel#timerLabel[state="paused"] {{
        border: 1px solid {Colors.WARNING};
        color: {Colors.WARNING};
        background-color: #1a140a;
    }}

    QLabel#sectionTitle {{
        color: {Colors.TEXT_MUTED};
        font-weight: 600;
        font-size: 9pt;
        letter-spacing: 1.2px;
    }}
    QLabel#hint {{
        color: {Colors.TEXT_DIM};
        font-size: 9pt;
    }}
    QLabel#titleLabel {{
        color: {Colors.TEXT};
        font-size: 20pt;
        font-weight: 700;
    }}
    QLabel#subtitleLabel {{
        color: {Colors.TEXT_MUTED};
        font-size: 10pt;
    }}

    /* ============================================================
       Separators
       ============================================================ */
    QFrame[frameShape="5"][frameShadow="16"] {{  /* HLine */
        color: {Colors.BORDER};
        max-height: 1px;
    }}
    """