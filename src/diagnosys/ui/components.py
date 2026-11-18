from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme.tokens import TOKENS


def add_shadow(widget: QFrame, blur: int = 24, y: int = 5) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    shadow = QColor(TOKENS.shadow)
    shadow.setAlpha(70)
    effect.setColor(shadow)
    widget.setGraphicsEffect(effect)


class MetricCard(QFrame):
    """A consistent bordered card that owns its header and content layout."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        add_shadow(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 17)
        outer.setSpacing(12)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("MetricName")
        self.header.addWidget(title_label)
        self.header.addStretch(1)
        outer.addLayout(self.header)

        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(10)
        outer.addLayout(self.content, 1)

    def add_badge(self, text: str, object_name: str = "PillGood") -> QLabel:
        badge = QLabel(text)
        badge.setObjectName(object_name)
        self.header.addWidget(badge)
        return badge


class SummaryCard(QFrame):
    def __init__(self, title: str, value: str = "—", detail: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SummaryCard")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        add_shadow(self, 18, 3)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(5)
        self.title = QLabel(title.upper())
        self.title.setObjectName("TinyLabel")
        self.value = QLabel(value)
        self.value.setObjectName("SummaryValue")
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(detail)
        self.detail.setObjectName("MetricDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_value(self, value: str, detail: str | None = None) -> None:
        self.value.setText(value)
        if detail is not None:
            self.detail.setText(detail)


class CircularGauge(QWidget):
    """Compact, accessible QPainter gauge for a percentage or unavailable value."""

    def __init__(self, caption: str = "USAGE", parent: QWidget | None = None):
        super().__init__(parent)
        self.caption = caption
        self.value: float | None = None
        self.setFixedSize(132, 132)
        self.setAccessibleName(f"{caption.title()} circular gauge")
        self.setAccessibleDescription("No reading yet")

    def set_value(self, value: float | None) -> None:
        self.value = None if value is None else max(0.0, min(100.0, value))
        self.setAccessibleDescription(
            "Unavailable" if self.value is None else f"{self.value:.1f} percent"
        )
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        arc_rect = QRectF((self.width() - side) / 2 + 12, (self.height() - side) / 2 + 12, side - 24, side - 24)
        pen = QPen(QColor(TOKENS.border), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc_rect, 225 * 16, -270 * 16)

        if self.value is not None:
            color = TOKENS.accent
            pen.setColor(QColor(color))
            painter.setPen(pen)
            painter.drawArc(arc_rect, 225 * 16, int(-270 * 16 * self.value / 100))

        painter.setPen(QColor(TOKENS.text))
        value_font = QFont("Segoe UI", 20, QFont.Weight.DemiBold)
        painter.setFont(value_font)
        value_text = "—" if self.value is None else f"{self.value:.0f}%"
        painter.drawText(QRectF(0, self.height() / 2 - 14, self.width(), 30), Qt.AlignmentFlag.AlignCenter, value_text)

        painter.setPen(QColor(TOKENS.muted))
        caption_font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        caption_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        painter.setFont(caption_font)
        painter.drawText(QRectF(0, self.height() / 2 + 15, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.caption)


class ProgressMetric(QWidget):
    """Label, right-aligned value, and themed progress bar for a resource metric."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("MetricDetail")
        self.value = QLabel("—")
        self.value.setObjectName("MetricName")
        heading.addWidget(self.title)
        heading.addStretch(1)
        heading.addWidget(self.value)
        layout.addLayout(heading)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setObjectName("TinyLabel")
        layout.addWidget(self.detail)

    def set_metric(self, percent: float | None, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.bar.setEnabled(percent is not None)
        self.bar.setValue(0 if percent is None else max(0, min(100, round(percent))))
        # Activity bars communicate magnitude only; they do not apply generic health cutoffs.
        self.bar.setProperty("tone", "neutral")
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)


class TrendChart(QFrame):
    """Lightweight, non-interactive trend plot drawn directly with QPainter."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.series: dict[str, list[float]] = {"CPU": [], "Memory": [], "Disk": []}
        self.colors = {
            "CPU": QColor(TOKENS.accent),
            "Memory": QColor(TOKENS.info),
            "Disk": QColor(TOKENS.warning),
        }

    def set_series(self, name: str, values: list[float]) -> None:
        self.series[name] = values[-60:]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, top, right, bottom = 42.0, 18.0, 18.0, 27.0
        plot = QRectF(self.rect()).adjusted(left, top, -right, -bottom)
        grid = QColor(TOKENS.border)
        painter.setFont(QFont("Segoe UI", 9))

        for fraction in (0, 0.25, 0.5, 0.75, 1):
            y = plot.bottom() - fraction * plot.height()
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(TOKENS.muted))
            painter.drawText(QRectF(0, y - 8, left - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{int(fraction * 100)}")

        painter.setPen(QColor(TOKENS.muted))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 7, 80, 16), Qt.AlignmentFlag.AlignLeft, "60 samples ago")
        painter.drawText(QRectF(plot.right() - 40, plot.bottom() + 7, 40, 16), Qt.AlignmentFlag.AlignRight, "now")

        legend_x = plot.left()
        for name, color in self.colors.items():
            painter.setPen(QPen(color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(legend_x, 7), QPointF(legend_x + 14, 7))
            painter.setPen(QColor(TOKENS.secondary))
            painter.drawText(QRectF(legend_x + 19, -1, 56, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            legend_x += 82

        for name, values in self.series.items():
            if len(values) < 2:
                continue
            path = QPainterPath()
            for index, value in enumerate(values):
                x = plot.left() + index * plot.width() / (len(values) - 1)
                y = plot.bottom() - max(0.0, min(100.0, value)) / 100 * plot.height()
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(self.colors[name], 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
