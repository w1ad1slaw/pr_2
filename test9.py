from __future__ import annotations

import csv
import random
import statistics
import sys
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, QTimer, QPointF, QRectF, QEasingCurve, QPropertyAnimation, QRect,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QIntValidator,
    QPainter,
    QPen,
    QPolygonF,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Параметры
# ---------------------------------------------------------------------------
N_MIN = 1
N_MAX = 1000
N_DEFAULT = 500

VALUE_MIN_DEFAULT = 0
VALUE_MAX_DEFAULT = 100

MARKER_PRESETS = [50, 100, 250, 500, 1000]

MARKER_DOT = "dot"
MARKER_TRIANGLE = "triangle"
MARKER_SQUARE = "square"
MARKER_DIAMOND = "diamond"

MARKER_SIZE = {
    MARKER_DOT: 3,
    MARKER_TRIANGLE: 5,
    MARKER_SQUARE: 4,
    MARKER_DIAMOND: 5,
}

PLOT_PAD_LEFT = 100
PLOT_PAD_RIGHT = 50
PLOT_PAD_TOP = 50
PLOT_PAD_BOTTOM = 70

GRID_X_DIVISIONS = 10
GRID_Y_DIVISIONS = 10

DRAWER_WIDTH = 420
DRAWER_ANIM_MS = 220


# ---------------------------------------------------------------------------
# ТЕМЫ: тёмная и светлая
# ---------------------------------------------------------------------------
THEME_DARK: Dict[str, str] = {
    "BG": "#1e1e1e",
    "CANVAS": "#181818",
    "GRID": "#2b2b2b",
    "AXIS": "#5a5a5a",
    "TEXT": "#e8e8e8",
    "TEXT_MUTED": "#8a8a8a",
    "ACCENT": "#f59e0b",
    "ACCENT_HOVER": "#d97706",
    "ACCENT_PRESSED": "#b45309",
    "ON_ACCENT": "#1a1400",
    "CARD": "#262626",
    "CARD_SOFT": "#2e2e2e",
    "BORDER": "#3a3a3a",
    "POINT_HIGH": "#10b981",
    "POINT_LOW": "#f59e0b",
    "BADGE_BG": "#232323",
    "BADGE_BORDER": "#3a3a3a",
    "STATUS_BG": "#181818",
    "DANGER": "#ef4444",
    "DRAWER_BG": "rgba(38, 38, 38, 240)",
    "CORNER_BG": "rgba(38, 38, 38, 220)",
}

THEME_LIGHT: Dict[str, str] = {
    "BG": "#f0f2f5",
    "CANVAS": "#ffffff",
    "GRID": "#e0e3e8",
    "AXIS": "#5a6270",
    "TEXT": "#1f2328",
    "TEXT_MUTED": "#5a6270",
    "ACCENT": "#d97706",
    "ACCENT_HOVER": "#b45309",
    "ACCENT_PRESSED": "#92400e",
    "ON_ACCENT": "#ffffff",
    "CARD": "#ffffff",
    "CARD_SOFT": "#f7f8fa",
    "BORDER": "#c8ccd2",
    "POINT_HIGH": "#059669",
    "POINT_LOW": "#d97706",
    "BADGE_BG": "#ffffff",
    "BADGE_BORDER": "#c8ccd2",
    "STATUS_BG": "#e4e7ea",
    "DANGER": "#dc2626",
    "DRAWER_BG": "rgba(255, 255, 255, 245)",
    "CORNER_BG": "rgba(255, 255, 255, 235)",
}


# ---------------------------------------------------------------------------
# Бизнес-логика
# ---------------------------------------------------------------------------
class DataEngine:
    @staticmethod
    def generate(count: int, vmin: int, vmax: int) -> List[int]:
        randint = random.randint
        return [randint(vmin, vmax) for _ in range(count)]

    @staticmethod
    def stats(data: List[int]) -> Tuple[int, int, float, int, float]:
        if not data:
            return 0, 0, 0.0, 0, 0.0
        vmin = min(data)
        vmax = max(data)
        avg = sum(data) / len(data)
        span = vmax - vmin
        median = statistics.median(data)
        return vmin, vmax, avg, span, float(median)


# ---------------------------------------------------------------------------
# Диалог справки (свой, с полным контролем QSS)
# ---------------------------------------------------------------------------
class HelpDialog(QDialog):
    """Полностью кастомный диалог справки — не наследует стили главного окна."""

    HELP_HTML_DARK = """
    <html><body style="color: #e8e8e8; font-family: 'Segoe UI'; font-size: 11pt;">
    <h2 style="color: #f59e0b; margin-top: 0;">КОНСОЛЬНЫЙ ГРАФИК ВЫБОРКИ</h2>

    <h3 style="color: #f59e0b;">Основные действия</h3>
    <ul>
      <li>Задайте количество точек (1…1000) и диапазон значений.</li>
      <li>Нажмите <b>СГЕНЕРИРОВАТЬ</b> или клавишу <b>Space</b>.</li>
    </ul>

    <h3 style="color: #f59e0b;">Цветовая схема точек</h3>
    <ul>
      <li><span style="color: #10b981;">● Зелёные</span> — значения выше или равны медиане</li>
      <li><span style="color: #f59e0b;">● Янтарные</span> — значения ниже медианы</li>
    </ul>

    <h3 style="color: #f59e0b;">Управление</h3>
    <ul>
      <li><b>Tab</b> — открыть/закрыть панель управления</li>
      <li><b>Space</b> — новая генерация</li>
      <li><b>F11</b> — полноэкранный режим</li>
      <li><b>Esc</b> — выход из fullscreen или закрытие панели</li>
      <li>Наведение мыши на точку — подсказка с индексом и значением</li>
    </ul>

    <h3 style="color: #f59e0b;">Экспорт</h3>
    <ul>
      <li><b>CSV</b> — данные в текстовом формате</li>
      <li><b>PNG</b> — снимок графика</li>
    </ul>
    </body></html>
    """

    HELP_HTML_LIGHT = HELP_HTML_DARK.replace("#e8e8e8", "#1f2328")

    def __init__(self, theme: Dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Справка")
        self.resize(620, 620)
        self.setMinimumSize(560, 500)

        # Не наследуем стиль главного окна
        self.setStyleSheet("")

        bg = theme["BG"]
        fg = theme["TEXT"]
        border = theme["BORDER"]
        accent = theme["ACCENT"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        text = QTextEdit()
        text.setReadOnly(True)
        html = self.HELP_HTML_LIGHT if bg.startswith("#f") else self.HELP_HTML_DARK
        text.setHtml(html)
        text.setStyleSheet(
            f"""
            QTextEdit {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 14px;
                font-size: 11pt;
            }}
            """
        )
        layout.addWidget(text, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("ЗАКРЫТЬ")
        btn_close.setMinimumHeight(44)
        btn_close.setMinimumWidth(140)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(
            f"""
            QPushButton {{
                background: {accent};
                color: #ffffff;
                border: 2px solid {accent};
                border-radius: 6px;
                font-size: 12pt;
                font-weight: bold;
                letter-spacing: 1px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
            """
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


# ---------------------------------------------------------------------------
# График
# ---------------------------------------------------------------------------
class PlotWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._data: List[int] = []
        self._vmin = VALUE_MIN_DEFAULT
        self._vmax = VALUE_MAX_DEFAULT
        self._marker_type = MARKER_DOT
        self._show_grid = True
        self._sorted = False

        self._hover_index: Optional[int] = None
        self._hover_pos: Optional[QPointF] = None

        self._cached_points: List[Tuple[float, float]] = []
        self._cached_plot_rect = QRectF()
        self._cached_values: List[int] = []
        self._cached_median: float = 0.0

        self._theme = THEME_DARK

        self.setMouseTracking(True)
        self.setMinimumSize(500, 400)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_theme(self, theme: Dict[str, str]) -> None:
        self._theme = theme
        self.update()

    def set_data(self, data: List[int], vmin: int, vmax: int) -> None:
        self._data = data
        self._vmin = vmin
        self._vmax = vmax
        self._hover_index = None
        self._hover_pos = None
        self._recompute_layout()
        self.update()

    def set_marker_type(self, marker: str) -> None:
        self._marker_type = marker
        self.update()

    def set_show_grid(self, show: bool) -> None:
        self._show_grid = show
        self.update()

    def set_sorted(self, sorted_mode: bool) -> None:
        self._sorted = sorted_mode
        self._hover_index = None
        self._hover_pos = None
        self._recompute_layout()
        self.update()

    def _recompute_layout(self) -> None:
        self._cached_points = []
        self._cached_values = []
        self._cached_plot_rect = QRectF()

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0 or not self._data:
            return

        plot_x = PLOT_PAD_LEFT
        plot_y = PLOT_PAD_TOP
        plot_w = w - PLOT_PAD_LEFT - PLOT_PAD_RIGHT
        plot_h = h - PLOT_PAD_TOP - PLOT_PAD_BOTTOM
        if plot_w <= 10 or plot_h <= 10:
            return

        self._cached_plot_rect = QRectF(plot_x, plot_y, plot_w, plot_h)

        n = len(self._data)
        denom_x = max(n - 1, 1)

        ymin = min(self._data)
        ymax = max(self._data)
        if ymax <= ymin:
            ymax = ymin + 1
        yspan = ymax - ymin

        values = sorted(self._data) if self._sorted else self._data
        self._cached_values = list(values)
        self._cached_median = float(statistics.median(values))

        for i, v in enumerate(values):
            bx = plot_x + (i / denom_x) * plot_w
            by = plot_y + plot_h - ((v - ymin) / yspan) * plot_h
            self._cached_points.append((bx, by))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recompute_layout()

    def mouseMoveEvent(self, event) -> None:
        if not self._cached_points:
            return
        mx = event.position().x()
        my = event.position().y()

        best_i = -1
        best_d = 144.0

        for i, (bx, by) in enumerate(self._cached_points):
            dx = bx - mx
            dy = by - my
            d = dx * dx + dy * dy
            if d < best_d:
                best_d = d
                best_i = i

        new_index = best_i if best_i >= 0 else None
        if new_index != self._hover_index:
            self._hover_index = new_index
            if new_index is not None:
                self._hover_pos = QPointF(*self._cached_points[new_index])
            else:
                self._hover_pos = None
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hover_index is not None:
            self._hover_index = None
            self._hover_pos = None
            self.update()

    def paintEvent(self, event) -> None:
        T = self._theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.fillRect(self.rect(), QColor(T["CANVAS"]))

        if not self._data or self._cached_plot_rect.isEmpty():
            painter.setPen(QColor(T["TEXT_MUTED"]))
            f = painter.font()
            f.setPointSize(16)
            painter.setFont(f)
            painter.drawText(
                self.rect(), Qt.AlignCenter,
                "Нажмите «СГЕНЕРИРОВАТЬ»\nили клавишу Space",
            )
            return

        plot = self._cached_plot_rect

        if self._show_grid:
            self._draw_grid(painter, plot)

        self._draw_axes(painter, plot)
        self._draw_median_line(painter, plot)

        painter.save()
        painter.setClipRect(plot)
        self._draw_points(painter)
        painter.restore()

        if self._hover_index is None:
            self._draw_badges(painter)

        if self._hover_index is not None and self._hover_pos is not None:
            self._draw_hover(painter)

    def _draw_grid(self, painter: QPainter, plot: QRectF) -> None:
        T = self._theme
        pen = QPen(QColor(T["GRID"]))
        pen.setWidth(1)
        painter.setPen(pen)

        for i in range(1, GRID_X_DIVISIONS):
            x = plot.left() + plot.width() * i / GRID_X_DIVISIONS
            painter.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))
        for i in range(1, GRID_Y_DIVISIONS):
            y = plot.top() + plot.height() * i / GRID_Y_DIVISIONS
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

    def _draw_axes(self, painter: QPainter, plot: QRectF) -> None:
        T = self._theme
        pen = QPen(QColor(T["AXIS"]))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(int(plot.left()), int(plot.bottom()),
                         int(plot.right()), int(plot.bottom()))
        painter.drawLine(int(plot.left()), int(plot.top()),
                         int(plot.left()), int(plot.bottom()))

        ymin = min(self._data)
        ymax = max(self._data)
        if ymax <= ymin:
            ymax = ymin + 1

        f = painter.font()
        f.setFamily("Consolas")
        f.setPointSize(10)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(T["TEXT_MUTED"]))

        for i in range(GRID_Y_DIVISIONS + 1):
            y = plot.top() + plot.height() * i / GRID_Y_DIVISIONS
            val = int(round(ymax - (ymax - ymin) * i / GRID_Y_DIVISIONS))
            painter.drawText(
                QRectF(0, y - 10, plot.left() - 14, 20),
                Qt.AlignRight | Qt.AlignVCenter, str(val),
            )

        n = len(self._data)
        for i in range(GRID_X_DIVISIONS + 1):
            x = plot.left() + plot.width() * i / GRID_X_DIVISIONS
            idx = int(round((n - 1) * i / GRID_X_DIVISIONS))
            painter.drawText(
                QRectF(x - 30, plot.bottom() + 6, 60, 20),
                Qt.AlignHCenter | Qt.AlignTop, str(idx),
            )

        f.setFamily("Segoe UI")
        f.setPointSize(10)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(T["ACCENT"]))
        xlabel = "Индекс (упорядочено по значению)" if self._sorted else "Индекс точки"
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 32, plot.width(), 24),
            Qt.AlignHCenter | Qt.AlignTop, xlabel,
        )

        painter.save()
        painter.translate(28, plot.center().y())
        painter.rotate(-90)
        painter.drawText(
            QRectF(-plot.height() / 2, 0, plot.height(), 24),
            Qt.AlignCenter, "Значение",
        )
        painter.restore()

    def _draw_median_line(self, painter: QPainter, plot: QRectF) -> None:
        if not self._data:
            return
        T = self._theme
        ymin = min(self._data)
        ymax = max(self._data)
        if ymax <= ymin:
            ymax = ymin + 1

        y = plot.top() + plot.height() * (
            1.0 - (self._cached_median - ymin) / (ymax - ymin)
        )

        pen = QPen(QColor(T["TEXT_MUTED"]))
        pen.setWidth(1)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

        f = painter.font()
        f.setFamily("Consolas")
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(T["TEXT_MUTED"]))
        painter.drawText(
            int(plot.left()) + 6, int(y) - 4, 200, 18,
            Qt.AlignLeft | Qt.AlignBottom,
            f"медиана = {self._cached_median:.1f}",
        )

    def _draw_points(self, painter: QPainter) -> None:
        T = self._theme
        high_color = QColor(T["POINT_HIGH"])
        high_color.setAlpha(230)
        low_color = QColor(T["POINT_LOW"])
        low_color.setAlpha(230)

        painter.setPen(Qt.NoPen)

        marker = self._marker_type
        size = MARKER_SIZE.get(marker, 3)
        median = self._cached_median

        for i, (bx, by) in enumerate(self._cached_points):
            v = self._cached_values[i]
            color = high_color if v >= median else low_color
            painter.setBrush(color)
            p = QPointF(bx, by)
            if marker == MARKER_DOT:
                painter.drawEllipse(p, size, size)
            elif marker == MARKER_SQUARE:
                painter.drawRect(QRectF(bx - size, by - size, size * 2, size * 2))
            elif marker == MARKER_TRIANGLE:
                poly = QPolygonF([
                    QPointF(bx, by - size - 1),
                    QPointF(bx - size - 1, by + size),
                    QPointF(bx + size + 1, by + size),
                ])
                painter.drawPolygon(poly)
            elif marker == MARKER_DIAMOND:
                poly = QPolygonF([
                    QPointF(bx, by - size - 1),
                    QPointF(bx + size + 1, by),
                    QPointF(bx, by + size + 1),
                    QPointF(bx - size - 1, by),
                ])
                painter.drawPolygon(poly)

    def _draw_badges(self, painter: QPainter) -> None:
        T = self._theme
        n = len(self._data)
        vmin, vmax, avg, span, median = DataEngine.stats(self._data)

        left_lines = [
            ("ОБЪЁМ", f"{n}"),
            ("ДИАПАЗОН", f"{vmin} … {vmax}"),
        ]
        right_lines = [
            ("MIN", f"{vmin}"),
            ("MAX", f"{vmax}"),
            ("AVG", f"{avg:.1f}"),
            ("МЕДИАНА", f"{median:.1f}"),
        ]

        self._draw_badge_block(painter, left_lines, anchor="bottom-left")
        self._draw_badge_block(painter, right_lines, anchor="bottom-right")

    def _draw_badge_block(self, painter: QPainter, lines, anchor: str) -> None:
        T = self._theme
        f = painter.font()

        metrics = painter.fontMetrics()
        line_h = metrics.height() + 6
        pad = 14
        title_w = 110

        box_w = 220
        box_h = pad * 2 + line_h * len(lines)

        margin = 20
        w = self.width()
        h = self.height()
        if anchor == "bottom-left":
            bx = margin
            by = h - margin - box_h - 44
        else:
            bx = w - margin - box_w
            by = h - margin - box_h - 44

        bg = QColor(T["BADGE_BG"])
        bg.setAlpha(230)
        painter.setPen(QPen(QColor(T["BADGE_BORDER"]), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 6, 6)

        for i, (title, value) in enumerate(lines):
            y = by + pad + i * line_h

            f.setFamily("Segoe UI")
            f.setBold(True)
            f.setPointSize(9)
            painter.setFont(f)
            painter.setPen(QColor(T["TEXT_MUTED"]))
            painter.drawText(
                QRectF(bx + pad, y, title_w, line_h),
                Qt.AlignLeft | Qt.AlignVCenter, title,
            )

            f.setFamily("Consolas")
            f.setBold(True)
            f.setPointSize(12)
            painter.setFont(f)
            painter.setPen(QColor(T["ACCENT"]))
            painter.drawText(
                QRectF(bx + pad + title_w, y, box_w - pad * 2 - title_w, line_h),
                Qt.AlignRight | Qt.AlignVCenter, value,
            )

    def _draw_hover(self, painter: QPainter) -> None:
        if self._hover_pos is None or self._hover_index is None:
            return

        T = self._theme
        x, y = self._hover_pos.x(), self._hover_pos.y()
        value = self._cached_values[self._hover_index]
        median = self._cached_median
        status = "выше медианы" if value >= median else "ниже медианы"

        if self._sorted:
            text = f"ранг №{self._hover_index}   значение: {value}   ({status})"
        else:
            text = f"№{self._hover_index}   значение: {value}   ({status})"

        painter.setPen(QPen(QColor(T["ACCENT"]), 2))
        painter.setBrush(QColor(T["ACCENT"]))
        painter.drawEllipse(QPointF(x, y), 6, 6)

        f = painter.font()
        f.setFamily("Consolas")
        f.setPointSize(10)
        f.setBold(True)
        painter.setFont(f)

        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(text) + 24
        th = metrics.height() + 14

        bx = x + 16
        by = y - th - 8
        if bx + tw > self.width() - 6:
            bx = x - tw - 16
        if by < 6:
            by = y + 16

        bg = QColor(T["BADGE_BG"])
        bg.setAlpha(245)
        painter.setPen(QPen(QColor(T["ACCENT"]), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)

        painter.setPen(QColor(T["TEXT"]))
        painter.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)

    def snapshot(self):
        return self.grab()


# ---------------------------------------------------------------------------
# Drawer
# ---------------------------------------------------------------------------
class ControlDrawer(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("controlDrawer")
        self.setFixedWidth(DRAWER_WIDTH)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("ПАРАМЕТРЫ ГЕНЕРАЦИИ")
        title.setObjectName("drawerTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("drawerClose")
        self.btn_close.setFixedSize(38, 38)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        header.addWidget(self.btn_close)

        lbl_n = QLabel("Число точек (1 … 1000)")
        lbl_n.setObjectName("fieldLabel")

        self.spin_n = QSpinBox()
        self.spin_n.setObjectName("spinN")
        self.spin_n.setRange(N_MIN, N_MAX)
        self.spin_n.setValue(N_DEFAULT)
        self.spin_n.setSingleStep(1)
        self.spin_n.setMinimumHeight(52)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        self.preset_buttons = []
        for val in MARKER_PRESETS:
            btn = QPushButton(str(val))
            btn.setObjectName("presetButton")
            btn.setMinimumHeight(42)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("preset_value", val)
            presets_row.addWidget(btn)
            self.preset_buttons.append(btn)

        lbl_range = QLabel("Диапазон значений")
        lbl_range.setObjectName("fieldLabel")

        range_row = QHBoxLayout()
        range_row.setSpacing(10)

        min_box = QVBoxLayout()
        lbl_min = QLabel("от")
        lbl_min.setObjectName("fieldSubLabel")
        self.input_min = QLineEdit(str(VALUE_MIN_DEFAULT))
        self.input_min.setObjectName("rangeInput")
        self.input_min.setAlignment(Qt.AlignCenter)
        self.input_min.setValidator(QIntValidator(-1_000_000, 1_000_000, self))
        self.input_min.setMinimumHeight(52)
        min_box.addWidget(lbl_min)
        min_box.addWidget(self.input_min)

        max_box = QVBoxLayout()
        lbl_max = QLabel("до")
        lbl_max.setObjectName("fieldSubLabel")
        self.input_max = QLineEdit(str(VALUE_MAX_DEFAULT))
        self.input_max.setObjectName("rangeInput")
        self.input_max.setAlignment(Qt.AlignCenter)
        self.input_max.setValidator(QIntValidator(-1_000_000, 1_000_000, self))
        self.input_max.setMinimumHeight(52)
        max_box.addWidget(lbl_max)
        max_box.addWidget(self.input_max)

        range_row.addLayout(min_box, 1)
        range_row.addLayout(max_box, 1)

        lbl_marker = QLabel("Тип маркера")
        lbl_marker.setObjectName("fieldLabel")
        lbl_marker.setToolTip(
            "Разная форма маркеров используется для визуального\n"
            "различения серий или операторов при наложении данных."
        )

        marker_row = QHBoxLayout()
        marker_row.setSpacing(8)
        self.marker_group = QButtonGroup(self)

        self.radio_dot = self._make_marker_radio("●", MARKER_DOT, True)
        self.radio_triangle = self._make_marker_radio("▲", MARKER_TRIANGLE, False)
        self.radio_square = self._make_marker_radio("■", MARKER_SQUARE, False)
        self.radio_diamond = self._make_marker_radio("◆", MARKER_DIAMOND, False)

        for rb in (self.radio_dot, self.radio_triangle,
                   self.radio_square, self.radio_diamond):
            marker_row.addWidget(rb)
            self.marker_group.addButton(rb)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)

        self.chk_grid = QCheckBox("Сетка")
        self.chk_grid.setObjectName("toolbarCheck")
        self.chk_grid.setChecked(True)

        self.chk_sorted = QCheckBox("По возрастанию")
        self.chk_sorted.setObjectName("toolbarCheck")
        self.chk_sorted.setChecked(False)
        self.chk_sorted.setToolTip(
            "Упорядочить точки по значению вдоль оси X.\n"
            "Позволяет наглядно увидеть распределение."
        )

        opts_row.addWidget(self.chk_grid)
        opts_row.addWidget(self.chk_sorted)
        opts_row.addStretch(1)

        self.btn_generate = QPushButton("СГЕНЕРИРОВАТЬ")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(60)
        self.btn_generate.setCursor(Qt.PointingHandCursor)

        self.btn_reset = QPushButton("СБРОС ПАРАМЕТРОВ")
        self.btn_reset.setObjectName("secondaryButton")
        self.btn_reset.setMinimumHeight(48)
        self.btn_reset.setCursor(Qt.PointingHandCursor)

        layout.addLayout(header)
        layout.addSpacing(8)
        layout.addWidget(lbl_n)
        layout.addWidget(self.spin_n)
        layout.addLayout(presets_row)
        layout.addSpacing(4)
        layout.addWidget(lbl_range)
        layout.addLayout(range_row)
        layout.addSpacing(4)
        layout.addWidget(lbl_marker)
        layout.addLayout(marker_row)
        layout.addSpacing(4)
        layout.addLayout(opts_row)
        layout.addStretch(1)
        layout.addWidget(self.btn_generate)
        layout.addWidget(self.btn_reset)

    def _make_marker_radio(self, symbol: str, marker_id: str,
                           checked: bool) -> QRadioButton:
        rb = QRadioButton(symbol)
        rb.setObjectName("markerRadio")
        rb.setProperty("marker_id", marker_id)
        rb.setChecked(checked)
        rb.setMinimumHeight(48)
        rb.setCursor(Qt.PointingHandCursor)
        return rb


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class ConsolePlotApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Консольный график выборки")
        self.resize(1600, 960)
        self.setMinimumSize(1200, 800)

        self._data: List[int] = []
        self._drawer_open = True
        self._theme_name = "dark"
        self._theme = THEME_DARK

        self._build_ui()
        self._apply_styles()
        self._bind_shortcuts()

        self._drawer_anim = QPropertyAnimation(self.drawer, b"geometry")
        self._drawer_anim.setDuration(DRAWER_ANIM_MS)
        self._drawer_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._log("Консольный график готов. Тема: тёмная.")
        QTimer.singleShot(100, self._on_generate)

    # ==================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.plot = PlotWidget()
        self.drawer = ControlDrawer(self.plot)
        self.drawer.hide()

        # --- Угловые кнопки ---
        self.btn_toggle_drawer = QPushButton("☰", self.plot)
        self._init_corner_btn(self.btn_toggle_drawer, "Открыть/закрыть панель (Tab)")
        self.btn_toggle_drawer.clicked.connect(self._toggle_drawer)

        self.btn_export_csv = QPushButton("CSV", self.plot)
        self._init_corner_btn(self.btn_export_csv, "Экспорт данных в CSV")
        self.btn_export_csv.clicked.connect(self._export_csv)

        self.btn_export_png = QPushButton("PNG", self.plot)
        self._init_corner_btn(self.btn_export_png, "Сохранить график в PNG")
        self.btn_export_png.clicked.connect(self._export_png)

        self.btn_help = QPushButton("?", self.plot)
        self._init_corner_btn(self.btn_help, "Справка")
        self.btn_help.clicked.connect(self._show_help)

        self.btn_theme = QPushButton("☀", self.plot)
        self._init_corner_btn(self.btn_theme, "Переключить тему (светлая / тёмная)")
        self.btn_theme.clicked.connect(self._toggle_theme)

        self.btn_fullscreen = QPushButton("⛶", self.plot)
        self._init_corner_btn(self.btn_fullscreen, "Полноэкранный режим (F11)")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)

        # Сигналы drawer
        self.drawer.btn_close.clicked.connect(self._toggle_drawer)
        self.drawer.btn_generate.clicked.connect(self._on_generate)
        self.drawer.btn_reset.clicked.connect(self._on_reset)
        for btn in self.drawer.preset_buttons:
            btn.clicked.connect(
                lambda _checked=False, b=btn: self._on_preset(b.property("preset_value"))
            )
        self.drawer.marker_group.buttonClicked.connect(self._on_marker_changed)
        self.drawer.chk_grid.toggled.connect(self.plot.set_show_grid)
        self.drawer.chk_sorted.toggled.connect(self.plot.set_sorted)

        root.addWidget(self.plot, 1)

        # Статус-бар
        self.status = QFrame()
        self.status.setObjectName("statusBar")
        self.status.setFixedHeight(34)

        status_layout = QHBoxLayout(self.status)
        status_layout.setContentsMargins(16, 0, 16, 0)

        self.lbl_status = QLabel("Готово")
        self.lbl_status.setObjectName("statusText")

        self.lbl_shortcuts = QLabel(
            "Space — генерация · Tab — панель · F11 — fullscreen · Esc — выход"
        )
        self.lbl_shortcuts.setObjectName("shortcutHint")

        status_layout.addWidget(self.lbl_status, 1)
        status_layout.addWidget(self.lbl_shortcuts, 0)

        root.addWidget(self.status)

        self.drawer.show()
        self._position_drawer(open=True)

    def _init_corner_btn(self, btn: QPushButton, tooltip: str) -> None:
        btn.setObjectName("cornerButton")
        btn.setFixedSize(52, 52)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)

    def _position_drawer(self, open: bool) -> None:
        h = self.plot.height()
        drawer_w = self.drawer.width()
        x = 0 if open else -drawer_w
        self.drawer.setGeometry(QRect(x, 0, drawer_w, h))

    def _toggle_drawer(self) -> None:
        self._drawer_open = not self._drawer_open
        h = self.plot.height()
        drawer_w = self.drawer.width()

        start = self.drawer.geometry()
        if self._drawer_open:
            end = QRect(0, 0, drawer_w, h)
            self.drawer.show()
        else:
            end = QRect(-drawer_w, 0, drawer_w, h)

        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(start)
        self._drawer_anim.setEndValue(end)

        try:
            self._drawer_anim.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._drawer_anim.finished.connect(self._raise_corner_buttons)

        self._drawer_anim.start()
        self._log(
            f"Панель управления {'открыта' if self._drawer_open else 'закрыта'}."
        )

    def _raise_corner_buttons(self) -> None:
        for btn in self._corner_buttons():
            btn.raise_()

    def _corner_buttons(self):
        return (
            self.btn_toggle_drawer, self.btn_export_csv,
            self.btn_export_png, self.btn_help,
            self.btn_theme, self.btn_fullscreen,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_overlays()

    def _reposition_overlays(self) -> None:
        pw = self.plot.width()
        ph = self.plot.height()

        margin = 16
        gap = 8
        right = pw - margin
        for btn in self._corner_buttons():
            right -= btn.width()
            btn.move(right, margin)
            right -= gap

        dw = self.drawer.width()
        if self._drawer_open:
            self.drawer.setGeometry(QRect(0, 0, dw, ph))
        else:
            self.drawer.setGeometry(QRect(-dw, 0, dw, ph))

        self._raise_corner_buttons()

    # ---- СМЕНА ТЕМЫ
    def _toggle_theme(self) -> None:
        if self._theme_name == "dark":
            self._theme_name = "light"
            self._theme = THEME_LIGHT
            self.btn_theme.setText("☾")
            self._log("Тема: светлая.")
        else:
            self._theme_name = "dark"
            self._theme = THEME_DARK
            self.btn_theme.setText("☀")
            self._log("Тема: тёмная.")

        self.plot.set_theme(self._theme)
        self._apply_styles()

    # ---- слоты
    def _on_preset(self, value: int) -> None:
        self.drawer.spin_n.setValue(value)
        self._log(f"Пресет количества: {value} точек.")

    def _on_marker_changed(self, btn) -> None:
        marker_id = btn.property("marker_id")
        self.plot.set_marker_type(marker_id)
        self._log(f"Тип маркера: {marker_id}.")

    def _on_reset(self) -> None:
        self.drawer.spin_n.setValue(N_DEFAULT)
        self.drawer.input_min.setText(str(VALUE_MIN_DEFAULT))
        self.drawer.input_max.setText(str(VALUE_MAX_DEFAULT))
        self.drawer.radio_dot.setChecked(True)
        self.plot.set_marker_type(MARKER_DOT)
        self.drawer.chk_grid.setChecked(True)
        self.drawer.chk_sorted.setChecked(False)
        self._log("Параметры сброшены к значениям по умолчанию.")

    def _validate_int(self, field: QLineEdit) -> Optional[int]:
        text = field.text().strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _on_generate(self) -> None:
        count = self.drawer.spin_n.value()
        vmin = self._validate_int(self.drawer.input_min)
        vmax = self._validate_int(self.drawer.input_max)

        if vmin is None or vmax is None:
            QMessageBox.warning(
                self, "Некорректный ввод",
                "Диапазон должен содержать целые числа.",
            )
            return
        if vmin >= vmax:
            QMessageBox.warning(
                self, "Некорректный диапазон",
                "Минимум должен быть строго меньше максимума.",
            )
            return

        t0 = time.perf_counter()
        self._data = DataEngine.generate(count, vmin, vmax)
        elapsed = (time.perf_counter() - t0) * 1000

        self.plot.set_data(self._data, vmin, vmax)
        self._log(
            f"Сгенерировано {count} точек [{vmin}…{vmax}] за {elapsed:.2f} мс."
        )

    # ---- экспорт
    def _export_csv(self) -> None:
        if not self._data:
            QMessageBox.information(self, "Нет данных",
                                    "Сначала сгенерируйте точки.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить данные в CSV",
            "console_plot_data.csv",
            "CSV файлы (*.csv);;Все файлы (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Индекс", "Значение"])
                for i, v in enumerate(self._data):
                    writer.writerow([i, v])
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))
            return
        self._log(f"CSV: {path}")

    def _export_png(self) -> None:
        if not self._data:
            QMessageBox.information(self, "Нет данных",
                                    "Сначала сгенерируйте точки.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить график в PNG",
            "console_plot.png",
            "PNG изображения (*.png);;Все файлы (*)",
        )
        if not path:
            return
        pixmap = self.plot.snapshot()
        if pixmap.save(path, "PNG"):
            self._log(f"PNG: {path}")
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить PNG.")

    def _show_help(self) -> None:
        # Кастомный диалог с полным контролем цвета текста
        dlg = HelpDialog(self._theme, self)
        dlg.exec()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self._log("Оконный режим.")
        else:
            self.showFullScreen()
            self._log("Полноэкранный режим.")

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key_Space), self,
                  activated=self._on_generate)
        QShortcut(QKeySequence(Qt.Key_Tab), self,
                  activated=self._toggle_drawer)
        QShortcut(QKeySequence(Qt.Key_Escape), self,
                  activated=self._on_escape)
        QShortcut(QKeySequence(Qt.Key_F11), self,
                  activated=self._toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+T"), self,
                  activated=self._toggle_theme)

    def _on_escape(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        elif self._drawer_open:
            self._toggle_drawer()

    # ================================================================ Стили
    def _apply_styles(self) -> None:
        T = self._theme
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {T["BG"]};
            }}
            QLabel {{
                background: transparent;
                color: {T["TEXT"]};
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}

            QFrame#controlDrawer {{
                background: {T["DRAWER_BG"]};
                border-right: 2px solid {T["ACCENT"]};
            }}
            QLabel#drawerTitle {{
                font-size: 13pt;
                font-weight: 900;
                color: {T["TEXT"]};
                letter-spacing: 3px;
            }}
            QLabel#fieldLabel {{
                font-size: 11pt;
                font-weight: 900;
                color: {T["ACCENT"]};
                letter-spacing: 1px;
                padding-top: 4px;
            }}
            QLabel#fieldSubLabel {{
                font-size: 10pt;
                font-weight: bold;
                color: {T["TEXT_MUTED"]};
                padding-left: 4px;
            }}

            QPushButton#drawerClose {{
                background: transparent;
                color: {T["TEXT_MUTED"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 6px;
                font-size: 16pt;
                font-weight: 900;
                padding: 0;
            }}
            QPushButton#drawerClose:hover {{
                background: {T["DANGER"]};
                color: #ffffff;
                border: 2px solid {T["DANGER"]};
            }}

            QSpinBox#spinN, QLineEdit#rangeInput {{
                background: {T["BG"]};
                color: {T["ACCENT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 6px;
                padding: 6px 12px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 16pt;
                font-weight: 900;
                selection-background-color: {T["ACCENT"]};
                selection-color: {T["ON_ACCENT"]};
            }}
            QSpinBox#spinN:focus, QLineEdit#rangeInput:focus {{
                border: 2px solid {T["ACCENT"]};
            }}
            QSpinBox#spinN::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 26px;
                background: {T["CARD"]};
                border-left: 1px solid {T["BORDER"]};
                border-top-right-radius: 5px;
            }}
            QSpinBox#spinN::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 26px;
                background: {T["CARD"]};
                border-left: 1px solid {T["BORDER"]};
                border-bottom-right-radius: 5px;
            }}
            QSpinBox#spinN::up-button:hover,
            QSpinBox#spinN::down-button:hover {{
                background: {T["ACCENT"]};
            }}
            QSpinBox#spinN::up-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-bottom: 6px solid {T["ACCENT"]};
            }}
            QSpinBox#spinN::down-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {T["ACCENT"]};
            }}

            QPushButton#presetButton {{
                background: {T["CARD"]};
                color: {T["TEXT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12pt;
                font-weight: 900;
                padding: 6px 4px;
            }}
            QPushButton#presetButton:hover {{
                background: {T["CARD_SOFT"]};
                border: 2px solid {T["ACCENT"]};
                color: {T["ACCENT"]};
            }}
            QPushButton#presetButton:pressed {{
                background: {T["ACCENT"]};
                color: {T["ON_ACCENT"]};
            }}

            QRadioButton#markerRadio {{
                color: {T["TEXT_MUTED"]};
                font-size: 18pt;
                font-weight: 900;
                spacing: 0px;
                padding: 6px 14px;
                border: 2px solid {T["BORDER"]};
                border-radius: 6px;
                background: {T["CARD"]};
            }}
            QRadioButton#markerRadio:hover {{
                border: 2px solid {T["ACCENT"]};
                color: {T["ACCENT"]};
            }}
            QRadioButton#markerRadio:checked {{
                background: {T["ACCENT"]};
                color: {T["ON_ACCENT"]};
                border: 2px solid {T["ACCENT"]};
            }}
            QRadioButton#markerRadio::indicator {{
                width: 0; height: 0;
            }}

            QCheckBox#toolbarCheck {{
                font-size: 11pt;
                font-weight: bold;
                color: {T["TEXT"]};
                spacing: 10px;
            }}
            QCheckBox#toolbarCheck::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {T["BORDER"]};
                border-radius: 4px;
                background: {T["BG"]};
            }}
            QCheckBox#toolbarCheck::indicator:checked {{
                background: {T["ACCENT"]};
                border: 2px solid {T["ACCENT"]};
            }}

            QPushButton#primaryButton {{
                background: {T["ACCENT"]};
                color: {T["ON_ACCENT"]};
                border: 2px solid {T["ACCENT"]};
                border-radius: 6px;
                font-size: 14pt;
                font-weight: 900;
                letter-spacing: 2px;
            }}
            QPushButton#primaryButton:hover {{
                background: {T["ACCENT_HOVER"]};
                border: 2px solid {T["ACCENT_HOVER"]};
            }}
            QPushButton#primaryButton:pressed {{
                background: {T["ACCENT_PRESSED"]};
            }}

            QPushButton#secondaryButton {{
                background: {T["CARD"]};
                color: {T["TEXT_MUTED"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 6px;
                font-size: 11pt;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QPushButton#secondaryButton:hover {{
                background: {T["CARD_SOFT"]};
                color: {T["TEXT"]};
                border: 2px solid {T["ACCENT"]};
            }}

            QPushButton#cornerButton {{
                background: {T["CORNER_BG"]};
                color: {T["TEXT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 8px;
                font-size: 14pt;
                font-weight: 900;
                padding: 0;
            }}
            QPushButton#cornerButton:hover {{
                background: {T["ACCENT"]};
                color: {T["ON_ACCENT"]};
                border: 2px solid {T["ACCENT"]};
            }}

            QFrame#statusBar {{
                background: {T["STATUS_BG"]};
                border-top: 2px solid {T["BORDER"]};
            }}
            QLabel#statusText {{
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                font-weight: bold;
                color: {T["ACCENT"]};
            }}
            QLabel#shortcutHint {{
                font-size: 9pt;
                color: {T["TEXT_MUTED"]};
                letter-spacing: 1px;
            }}
            """
        )

    def _log(self, message: str) -> None:
        self.lbl_status.setText(message)
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] {message}")


# ---------------------------------------------------------------------------
def main() -> int:
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(msg, file=sys.stderr)
        QMessageBox.critical(
            None, "Критическая ошибка",
            f"Произошла непредвиденная ошибка:\n\n{exc_value}\n\n"
            "Приложение будет закрыто."
        )

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = ConsolePlotApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())