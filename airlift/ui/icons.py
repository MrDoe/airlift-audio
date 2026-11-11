"""Small, dependency-free vector icons drawn with QPainter.

Qt's standard icons look inconsistent across platforms; Airlift uses this set
instead so the toolbar, queue and player share one visual language.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

_CACHE: dict[tuple[str, str, int], QIcon] = {}


def _pen(color: str, width: float = 1.8) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _draw(name: str, painter: QPainter, color: str) -> None:
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)

    if name == "play":
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(
            QPolygonF([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)])
        )
    elif name == "pause":
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(7, 5, 4, 14), 1.2, 1.2)
        painter.drawRoundedRect(QRectF(13, 5, 4, 14), 1.2, 1.2)
    elif name == "stop":
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(6, 6, 12, 12), 2.0, 2.0)
    elif name == "plus":
        painter.drawLine(QPointF(12, 5), QPointF(12, 19))
        painter.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(9, 7)
        path.lineTo(11, 9)
        path.lineTo(21, 9)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "trash":
        painter.drawLine(QPointF(4, 7), QPointF(20, 7))
        painter.drawLine(QPointF(9, 7), QPointF(9, 4))
        painter.drawLine(QPointF(15, 7), QPointF(15, 4))
        painter.drawRoundedRect(QRectF(6, 7, 12, 13), 2, 2)
        painter.drawLine(QPointF(10, 11), QPointF(10, 16))
        painter.drawLine(QPointF(14, 11), QPointF(14, 16))
    elif name == "layers":
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(12, 3),
                    QPointF(21, 8),
                    QPointF(12, 13),
                    QPointF(3, 8),
                ]
            )
        )
        painter.drawLine(QPointF(3, 12), QPointF(12, 17))
        painter.drawLine(QPointF(21, 12), QPointF(12, 17))
        painter.drawLine(QPointF(3, 16), QPointF(12, 21))
        painter.drawLine(QPointF(21, 16), QPointF(12, 21))
    elif name == "copy":
        painter.drawRoundedRect(QRectF(8, 8, 11, 12), 2, 2)
        path = QPainterPath()
        path.moveTo(5, 16)
        path.lineTo(4, 16)
        path.lineTo(4, 4)
        path.lineTo(15, 4)
        path.lineTo(15, 5)
        painter.drawPath(path)
    elif name == "external":
        painter.drawRoundedRect(QRectF(4, 6, 14, 14), 2, 2)
        painter.drawLine(QPointF(13, 4), QPointF(20, 4))
        painter.drawLine(QPointF(20, 4), QPointF(20, 11))
        painter.drawLine(QPointF(20, 4), QPointF(11, 13))
    elif name == "settings":
        painter.drawEllipse(QPointF(12, 12), 3.2, 3.2)
        painter.drawEllipse(QPointF(12, 12), 7.2, 7.2)
        for x1, y1, x2, y2 in (
            (12, 2, 12, 5),
            (12, 19, 12, 22),
            (2, 12, 5, 12),
            (19, 12, 22, 12),
        ):
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "file":
        path = QPainterPath()
        path.moveTo(6, 3)
        path.lineTo(14, 3)
        path.lineTo(19, 8)
        path.lineTo(19, 21)
        path.lineTo(6, 21)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(14, 3), QPointF(14, 8))
        painter.drawLine(QPointF(14, 8), QPointF(19, 8))
    elif name == "close":
        painter.drawLine(QPointF(6, 6), QPointF(18, 18))
        painter.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "chevron-left":
        painter.drawPolyline(
            QPolygonF([QPointF(15, 5), QPointF(9, 12), QPointF(15, 19)])
        )
    elif name == "chevron-right":
        painter.drawPolyline(
            QPolygonF([QPointF(9, 5), QPointF(15, 12), QPointF(9, 19)])
        )
    elif name == "chevron-down":
        painter.drawPolyline(
            QPolygonF([QPointF(5, 9), QPointF(12, 15), QPointF(19, 9)])
        )
    elif name == "swap":
        painter.drawLine(QPointF(5, 8), QPointF(19, 8))
        painter.drawLine(QPointF(16, 5), QPointF(19, 8))
        painter.drawLine(QPointF(16, 11), QPointF(19, 8))
        painter.drawLine(QPointF(19, 16), QPointF(5, 16))
        painter.drawLine(QPointF(8, 13), QPointF(5, 16))
        painter.drawLine(QPointF(8, 19), QPointF(5, 16))
    elif name == "volume":
        painter.drawPolygon(
            QPolygonF(
                [QPointF(4, 10), QPointF(8, 10), QPointF(12, 6), QPointF(12, 18), QPointF(8, 14), QPointF(4, 14)]
            )
        )
        painter.drawArc(QRectF(11, 8, 8, 8), -60 * 16, 120 * 16)
    elif name == "retry":
        path = QPainterPath()
        path.arcMoveTo(QRectF(5, 5, 14, 14), 40)
        path.arcTo(QRectF(5, 5, 14, 14), 40, 270)
        painter.drawPath(path)
        painter.drawLine(QPointF(17, 4), QPointF(17, 10))
        painter.drawLine(QPointF(17, 10), QPointF(11, 10))
    elif name == "check":
        painter.drawPolyline(
            QPolygonF([QPointF(5, 12), QPointF(10, 17), QPointF(19, 7)])
        )
    elif name == "warning":
        painter.drawPolygon(
            QPolygonF([QPointF(12, 3), QPointF(21, 20), QPointF(3, 20)])
        )
        painter.drawLine(QPointF(12, 9), QPointF(12, 14))
        painter.drawPoint(QPointF(12, 17))
    else:  # pragma: no cover - defensive fallback
        painter.drawEllipse(QPointF(12, 12), 7, 7)


def icon(name: str, color: str = "#94A3B8", size: int = 18) -> QIcon:
    """Return a cached QIcon for ``name`` in a single color."""
    key = (name, color, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(size / 24.0, size / 24.0)
    _draw(name, painter, color)
    painter.end()

    result = QIcon(pixmap)
    _CACHE[key] = result
    return result
