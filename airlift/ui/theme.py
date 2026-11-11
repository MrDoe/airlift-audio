"""Dark studio theme for Airlift Audio."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0F141B"
SURFACE = "#161C26"
ELEVATED = "#1C2430"
BORDER = "#2A3442"
TEXT = "#E6EDF5"
MUTED = "#94A3B8"
ACCENT = "#2DD4BF"
ACCENT_DIM = "#14B8A6"
DANGER = "#F87171"
WARNING = "#F59E0B"
SUCCESS = "#34D399"

UI_FONTS = ("IBM Plex Sans", "Inter", "Noto Sans", "DejaVu Sans")
MONO_FONTS = ("JetBrains Mono", "Cascadia Code", "DejaVu Sans Mono")

QSS = f"""
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QFrame#header {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QFrame#panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#emptyState {{
    background: {SURFACE};
    border: 1px dashed #354255;
    border-radius: 12px;
}}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel[role="subtitle"] {{ font-size: 11px; color: {MUTED}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="mono"] {{
    font-family: "JetBrains Mono", "Cascadia Code", "DejaVu Sans Mono", monospace;
    color: {MUTED};
}}
QLabel[role="accent"] {{ color: {ACCENT}; font-weight: 600; }}
QLabel[role="danger"] {{ color: {DANGER}; }}
QLabel#statusChip {{
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
    background: #202836;
    color: {MUTED};
}}
QLabel#statusChip[state="pending"] {{ background: #202836; color: {MUTED}; }}
QLabel#statusChip[state="queued"] {{ background: #233043; color: #93C5FD; }}
QLabel#statusChip[state="processing"] {{ background: #1F3A38; color: {ACCENT}; }}
QLabel#statusChip[state="done"] {{ background: #14382D; color: {SUCCESS}; }}
QLabel#statusChip[state="failed"] {{ background: #3A1D24; color: {DANGER}; }}
QLabel#statusChip[state="cancelled"] {{ background: #3A2E1B; color: {WARNING}; }}
QLabel#statusChip[state="missing"] {{ background: #3A1D24; color: {DANGER}; }}
QPushButton {{
    background: {ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 12px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #24303E; border-color: #3A4757; }}
QPushButton:pressed {{ background: #202A36; }}
QPushButton:disabled {{
    background: #141A22;
    border-color: #222B36;
    color: #5B6573;
}}
QPushButton[variant="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #06201C;
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: #5EEAD4; }}
QPushButton[variant="primary"]:pressed {{ background: {ACCENT_DIM}; }}
QPushButton[variant="primary"]:disabled {{
    background: #1B302D;
    border-color: #24423E;
    color: #5F736F;
}}
QPushButton[variant="danger"] {{
    background: transparent;
    border-color: #7F1D1D;
    color: {DANGER};
}}
QPushButton[variant="danger"]:hover {{ background: #2A1A1F; }}
QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: transparent;
    color: {MUTED};
}}
QPushButton[variant="ghost"]:hover {{ background: {ELEVATED}; color: {TEXT}; }}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px;
    color: {MUTED};
}}
QToolButton:hover {{ background: {ELEVATED}; border-color: {BORDER}; color: {TEXT}; }}
QToolButton:checked {{ background: #123B36; border-color: {ACCENT_DIM}; color: {ACCENT}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: #0B1016;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: #134E4A;
    min-height: 18px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT_DIM};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: #5B6573;
    background: #10151C;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {ELEVATED};
    border: 1px solid {BORDER};
    selection-background-color: #123B36;
    selection-color: {TEXT};
    outline: none;
    padding: 4px;
}}
QGroupBox {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {MUTED};
    font-weight: 600;
}}
QTableWidget, QTableView {{
    background: #111821;
    alternate-background-color: #141C25;
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #123B36;
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item {{ padding: 0 8px; border: none; }}
QTableWidget::item:selected {{ background: #123B36; }}
QHeaderView::section {{
    background: #111821;
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px;
    font-size: 11px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: #111821; border: none; }}
QProgressBar {{
    background: #0B1016;
    border: none;
    border-radius: 3px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QProgressBar#overall {{ min-height: 8px; max-height: 8px; }}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT_DIM}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #DDE6F2;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QPlainTextEdit, QTextEdit {{
    background: #0B1016;
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: #AAB6C5;
    font-family: "JetBrains Mono", "Cascadia Code", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    padding: 6px;
}}
QDockWidget {{ color: {MUTED}; }}
QDockWidget::title {{ background: {SURFACE}; padding: 6px; }}
QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {MUTED};
}}
QStatusBar::item {{ border: none; }}
QMenu {{
    background: {ELEVATED};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: #123B36; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2F3847; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #3A4757; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2F3847; border-radius: 4px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: #0B1016;
}}
QCheckBox::indicator:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QToolTip {{
    background: {ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px 7px;
}}
"""


def _pick_font(families: tuple[str, ...], fallback: str) -> str:
    available = set(QFontDatabase.families())
    for family in families:
        if family in available:
            return family
    return fallback


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont(_pick_font(UI_FONTS, "DejaVu Sans"), 10))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor("#0B1016"))
    palette.setColor(QPalette.AlternateBase, QColor("#141C25"))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(ELEVATED))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor("#123B36"))
    palette.setColor(QPalette.HighlightedText, QColor(TEXT))
    palette.setColor(QPalette.ToolTipBase, QColor(ELEVATED))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.PlaceholderText, QColor("#64748B"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#5B6573"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5B6573"))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
