"""Dark, restrained theme for Airlift Audio."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#63d2c3"
ACCENT_DIM = "#2e8f84"

QSS = f"""
QWidget {{
    background: #14171d;
    color: #d8dee9;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: #14171d; }}
QToolBar {{
    background: #191d25;
    border: none;
    border-bottom: 1px solid #262c37;
    spacing: 6px;
    padding: 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 10px;
    color: #c8d0dc;
}}
QToolButton:hover {{ background: #232a35; border-color: #2f3847; }}
QToolButton:disabled {{ color: #5a626f; }}
QPushButton {{
    background: #232a35;
    border: 1px solid #2f3847;
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: #2b3442; }}
QPushButton:disabled {{ background: #1b2028; color: #5a626f; }}
QPushButton#primary {{
    background: {ACCENT_DIM};
    border-color: {ACCENT};
    color: #06110f;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT}; }}
QPushButton#primary:disabled {{ background: #24302f; color: #5f736f; border-color: #2c3b39; }}
QGroupBox {{
    border: 1px solid #262c37;
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px 10px 8px 10px;
    background: #171b22;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8b95a5;
    font-weight: 600;
}}
QTableWidget, QTableView {{
    background: #151920;
    alternate-background-color: #191e26;
    border: 1px solid #262c37;
    border-radius: 8px;
    gridline-color: #232a35;
    selection-background-color: #24423e;
    selection-color: #eafffb;
}}
QHeaderView::section {{
    background: #1b2029;
    color: #8b95a5;
    border: none;
    border-bottom: 1px solid #262c37;
    padding: 6px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: #1b2029; border: none; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: #10141a;
    border: 1px solid #2b3340;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT_DIM};
}}
QComboBox QAbstractItemView {{
    background: #171b22;
    border: 1px solid #2b3340;
    selection-background-color: #24423e;
}}
QProgressBar {{
    background: #10141a;
    border: 1px solid #262c37;
    border-radius: 6px;
    text-align: center;
    color: #cfe8e4;
    min-height: 16px;
}}
QProgressBar::chunk {{
    background: {ACCENT_DIM};
    border-radius: 5px;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #262c37;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT_DIM}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #cfd7e3;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QPlainTextEdit, QTextEdit {{
    background: #10141a;
    border: 1px solid #262c37;
    border-radius: 8px;
    color: #9aa6b6;
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}}
QDockWidget {{ color: #8b95a5; }}
QDockWidget::title {{ background: #191d25; padding: 6px; }}
QStatusBar {{ background: #191d25; border-top: 1px solid #262c37; color: #8b95a5; }}
QScrollBar:vertical {{ background: #14171d; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2f3847; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{
    background: #232a35;
    color: #d8dee9;
    border: 1px solid #37414f;
    padding: 4px 6px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#14171d"))
    palette.setColor(QPalette.WindowText, QColor("#d8dee9"))
    palette.setColor(QPalette.Base, QColor("#10141a"))
    palette.setColor(QPalette.AlternateBase, QColor("#191e26"))
    palette.setColor(QPalette.Text, QColor("#d8dee9"))
    palette.setColor(QPalette.Button, QColor("#232a35"))
    palette.setColor(QPalette.ButtonText, QColor("#d8dee9"))
    palette.setColor(QPalette.Highlight, QColor(ACCENT_DIM))
    palette.setColor(QPalette.HighlightedText, QColor("#eafffb"))
    palette.setColor(QPalette.ToolTipBase, QColor("#232a35"))
    palette.setColor(QPalette.ToolTipText, QColor("#d8dee9"))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
