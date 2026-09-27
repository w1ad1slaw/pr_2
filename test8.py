from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QSettings
from PySide6.QtGui import (
    QColor,
    QFont,
    QIntValidator,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Параметры продукта
# ---------------------------------------------------------------------------
COUNT_DEFAULT = 1000
COUNT_MAX = 100_000

VALUE_MIN_DEFAULT = 0
VALUE_MAX_DEFAULT = 100

LSL_DEFAULT = 20
USL_DEFAULT = 80

LOG_MAX_LINES = 200

Y_MIN_AXIS = 0
Y_MAX_AXIS = 100

# Увеличены отступы, чтобы ось Y не прилипала к краю
PLOT_PAD_LEFT = 110
PLOT_PAD_RIGHT = 50
PLOT_PAD_TOP = 50
PLOT_PAD_BOTTOM = 70

POINT_RADIUS_SMALL = 2
POINT_RADIUS_NORMAL = 3
POINTS_RADIUS_THRESHOLD = 5000

POINT_ALPHA_NORMAL = 200
POINT_ALPHA_OUT = 240

GRID_X_DIVISIONS = 10
GRID_Y_DIVISIONS = 10

ZOOM_MIN = 0.5
ZOOM_MAX = 8.0
ZOOM_STEP = 1.15

EXPORT_FORMATS = ["CSV", "JSON"]
UNIT_PRESETS = ["усл. ед.", "мм", "кг", "В", "А", "°C", "%", "шт"]

SETTINGS_ORG = "IndustrialAnalytics"
SETTINGS_APP = "ScatterPointViewer"

# Порог значимости линии тренда
R2_SIGNIFICANCE_THRESHOLD = 0.1


# ---------------------------------------------------------------------------
# Палитры
# ---------------------------------------------------------------------------
THEME_DARK = {
    "BG": "#16181a",
    "CARD_BG": "#1e2124",
    "CARD_SOFT": "#262a2e",
    "TEXT": "#eaf0ee",
    "TEXT_MUTED": "#8a9694",
    "BORDER": "#3a4245",
    "BORDER_SUBTLE": "#2a3033",
    "BORDER_ERROR": "#ef4444",
    "ACCENT": "#10b981",
    "ACCENT_HOVER": "#059669",
    "ACCENT_PRESSED": "#047857",
    "ON_ACCENT": "#ffffff",
    "ACCENT_SOFT": "#34d399",
    "SECONDARY": "#0891b2",
    "SECONDARY_HOVER": "#0e7490",
    "DANGER": "#ef4444",
    "DANGER_SOFT": "#fca5a5",
    "WARNING": "#f59e0b",
    "GRAPH_BG": "#0f1214",
    "GRAPH_GRID": "#181d21",       # ещё темнее — POL-01
    "GRAPH_AXIS": "#5a666a",
    "GRAPH_TEXT": "#8a9694",
    "GRAPH_POINT": "#10b981",
    "GRAPH_POINT_OUT": "#f59e0b",
    "GRAPH_MEAN": "#34d399",
    "GRAPH_REGRESSION": "#0891b2",
    "GRAPH_HIST": "#10b981",
}

THEME_LIGHT = {
    "BG": "#f4f5f7",
    "CARD_BG": "#ffffff",
    "CARD_SOFT": "#f0f2f5",
    "TEXT": "#1f2328",
    "TEXT_MUTED": "#5a6270",
    "BORDER": "#959da5",
    "BORDER_SUBTLE": "#d0d5da",
    "BORDER_ERROR": "#dc2626",
    "ACCENT": "#0d9488",
    "ACCENT_HOVER": "#0f766e",
    "ACCENT_PRESSED": "#115e59",
    "ON_ACCENT": "#ffffff",
    "ACCENT_SOFT": "#14b8a6",
    "SECONDARY": "#0284c7",
    "SECONDARY_HOVER": "#0369a1",
    "DANGER": "#dc2626",
    "DANGER_SOFT": "#ef4444",
    "WARNING": "#d97706",
    "GRAPH_BG": "#ffffff",
    "GRAPH_GRID": "#ebedf0",
    "GRAPH_AXIS": "#5a6270",
    "GRAPH_TEXT": "#5a6270",
    "GRAPH_POINT": "#0d9488",
    "GRAPH_POINT_OUT": "#d97706",
    "GRAPH_MEAN": "#14b8a6",
    "GRAPH_REGRESSION": "#0284c7",
    "GRAPH_HIST": "#0d9488",
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
    def stats(data: List[int]) -> Tuple[int, int, float, float, float, float]:
        if not data:
            return 0, 0, 0.0, 0.0, 0.0, 0.0
        vmin = min(data)
        vmax = max(data)
        n = len(data)
        avg = sum(data) / n
        s = sorted(data)
        mid = n // 2
        median = float(s[mid]) if n % 2 else (s[mid - 1] + s[mid]) / 2.0
        if n > 1:
            var = sum((x - avg) ** 2 for x in data) / (n - 1)
            stddev = math.sqrt(var)
        else:
            stddev = 0.0
        cv = (stddev / avg * 100.0) if avg != 0 else 0.0
        return vmin, vmax, avg, median, stddev, cv

    @staticmethod
    def skewness_kurtosis(data: List[int]) -> Tuple[float, float]:
        n = len(data)
        if n < 4:
            return 0.0, 0.0
        avg = sum(data) / n
        var = sum((x - avg) ** 2 for x in data) / n
        sigma = math.sqrt(var)
        if sigma == 0:
            return 0.0, 0.0
        m3 = sum((x - avg) ** 3 for x in data) / n
        m4 = sum((x - avg) ** 4 for x in data) / n
        skew = m3 / (sigma ** 3)
        kurt = m4 / (sigma ** 4) - 3.0
        return skew, kurt

    @staticmethod
    def cp_cpk(data: List[int], lsl: float, usl: float):
        n = len(data)
        if n < 2:
            return 0.0, 0.0, 0.0
        avg = sum(data) / n
        var = sum((x - avg) ** 2 for x in data) / (n - 1)
        sigma = math.sqrt(var)
        if sigma == 0 or usl <= lsl:
            return 0.0, 0.0, 0.0
        cp = (usl - lsl) / (6.0 * sigma)
        cpu = (usl - avg) / (3.0 * sigma)
        cpl = (avg - lsl) / (3.0 * sigma)
        cpk = min(cpu, cpl)
        return cp, cpk, sigma

    @staticmethod
    def linear_regression(data: List[int]) -> Tuple[float, float, float]:
        n = len(data)
        if n < 2:
            return 0.0, 0.0, 0.0
        sum_x = sum_y = sum_xy = sum_xx = 0.0
        for i, y in enumerate(data):
            sum_x += i
            sum_y += y
            sum_xy += i * y
            sum_xx += i * i
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return sum_y / n, 0.0, 0.0
        b = (n * sum_xy - sum_x * sum_y) / denom
        a = (sum_y - b * sum_x) / n
        y_mean = sum_y / n
        ss_tot = sum((y - y_mean) ** 2 for y in data)
        if ss_tot == 0:
            return a, b, 1.0
        ss_res = sum((y - (a + b * x)) ** 2 for x, y in enumerate(data))
        r2 = 1.0 - ss_res / ss_tot
        return a, b, r2

    @staticmethod
    def histogram(data: List[int], vmin: float, vmax: float,
                  bins: int = 20) -> List[int]:
        result = [0] * bins
        if not data or vmax <= vmin:
            return result
        span = vmax - vmin
        for v in data:
            idx = int((v - vmin) * bins / span)
            idx = max(0, min(bins - 1, idx))
            result[idx] += 1
        return result


# ---------------------------------------------------------------------------
# Диалог настроек экспорта
# ---------------------------------------------------------------------------
class ExportSettingsDialog(QDialog):
    def __init__(self, parent=None, current_fmt: str = "CSV") -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки экспорта")
        self.setMinimumWidth(460)

        self.format = current_fmt
        self.delimiter = ","
        self.encoding = "utf-8"
        self.include_stats = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        g1 = QGroupBox("Разделитель (для CSV)")
        l1 = QVBoxLayout(g1)
        self.combo_delim = QComboBox()
        self.combo_delim.addItem("Запятая  ,", ",")
        self.combo_delim.addItem("Точка с запятой  ;", ";")
        self.combo_delim.addItem("Табуляция  \\t", "\t")
        self.combo_delim.addItem("Пробел", " ")
        l1.addWidget(self.combo_delim)

        g2 = QGroupBox("Кодировка")
        l2 = QVBoxLayout(g2)
        self.combo_enc = QComboBox()
        self.combo_enc.addItem("UTF-8", "utf-8")
        self.combo_enc.addItem("Windows-1251", "cp1251")
        l2.addWidget(self.combo_enc)

        self.chk_include_stats = QCheckBox("Добавить блок статистики в конец файла")
        self.chk_include_stats.setChecked(False)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QPushButton("ОТМЕНА")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("СОХРАНИТЬ")
        btn_ok.clicked.connect(self._on_ok)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)

        layout.addWidget(g1)
        layout.addWidget(g2)
        layout.addWidget(self.chk_include_stats)
        layout.addLayout(btns)

    def _on_ok(self) -> None:
        self.delimiter = self.combo_delim.currentData()
        self.encoding = self.combo_enc.currentData()
        self.include_stats = self.chk_include_stats.isChecked()
        self.accept()


# ---------------------------------------------------------------------------
# Диалог справки
# ---------------------------------------------------------------------------
class HelpDialog(QDialog):
    HELP_TEXT = """
    <h2 style="color:#10b981">СПРАВКА ПО МЕТРИКАМ</h2>
    <h3>Параметры выборки</h3>
    <p><b>Минимум / Максимум</b> — крайние значения в выборке.</p>
    <p><b>Среднее арифметическое</b> — сумма всех значений, делённая на их количество.</p>
    <p><b>Медиана</b> — значение, делящее упорядоченную выборку пополам.</p>
    <p><b>Стандартное отклонение (σ)</b> — мера разброса значений относительно среднего.</p>
    <p><b>Коэффициент вариации (CV)</b> — σ / среднее × 100%.</p>
    <p><b>Асимметрия</b> — скошенность распределения. 0 = симметрично.</p>
    <p><b>Эксцесс</b> — «острота» пика. 0 = нормальное распределение.</p>
    <h3>Контроль качества</h3>
    <p><b>LSL</b> (Lower Specification Limit) — нижний предел допуска.</p>
    <p><b>USL</b> (Upper Specification Limit) — верхний предел допуска.</p>
    <p><b>Cp</b> — потенциальная воспроизводимость: (USL − LSL) / (6σ).</p>
    <p><b>Cpk</b> — фактическая воспроизводимость с учётом смещения центра.</p>
    <p>Шкала: Cp/Cpk ≥ 1.33 — способен, ≥ 1.67 — высокий уровень, < 1.0 — вмешательство.</p>
    <h3>Управление графиком</h3>
    <p><b>Колесо мыши</b> — масштабирование. <b>ЛКМ</b> — панорамирование.</p>
    <p><b>Двойной клик</b> — сброс масштаба.</p>
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Справка")
        self.resize(760, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(self.HELP_TEXT)
        text.setStyleSheet(
            "QTextEdit { background: #f4f5f7; color: #1f2328; "
            "border: 1px solid #d0d5da; border-radius: 6px; "
            "padding: 16px; font-size: 11pt; }"
        )
        layout.addWidget(text)

        btn = QPushButton("ЗАКРЫТЬ")
        btn.setMinimumHeight(44)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


# ---------------------------------------------------------------------------
# График рассеяния
# ---------------------------------------------------------------------------
class ScatterPlotWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._data: List[int] = []
        self._vmin = VALUE_MIN_DEFAULT
        self._vmax = VALUE_MAX_DEFAULT
        self._lsl = LSL_DEFAULT
        self._usl = USL_DEFAULT
        self._show_regression = True
        self._show_mean = True

        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)
        self._panning = False
        self._pan_start = QPointF(0, 0)
        self._pan_start_offset = QPointF(0, 0)

        self._hover_index: Optional[int] = None
        self._hover_pos: Optional[QPointF] = None

        self._cached_points: List[Tuple[float, float]] = []
        self._cached_plot_rect = QRectF()

        self._theme = THEME_DARK
        self._unit = "усл. ед."

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(500, 400)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme
        self.update()

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        self.update()

    def set_data(self, data: List[int], vmin: int, vmax: int) -> None:
        self._data = data
        self._vmin = vmin
        self._vmax = vmax
        self._hover_index = None
        self._hover_pos = None
        self.reset_view()
        self._recompute_layout()
        self.update()

    def set_limits(self, lsl: int, usl: int) -> None:
        self._lsl = lsl
        self._usl = usl
        self.update()

    def set_show_regression(self, enabled: bool) -> None:
        self._show_regression = enabled
        self.update()

    def set_show_mean(self, enabled: bool) -> None:
        self._show_mean = enabled
        self.update()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_offset = QPointF(0, 0)

    # ---- layout
    def _recompute_layout(self) -> None:
        self._cached_points = []
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
        yspan = max(Y_MAX_AXIS - Y_MIN_AXIS, 1)
        denom_x = max(n - 1, 1)

        for i, v in enumerate(self._data):
            bx = plot_x + (i / denom_x) * plot_w
            clamped = max(Y_MIN_AXIS, min(Y_MAX_AXIS, v))
            by = plot_y + plot_h - ((clamped - Y_MIN_AXIS) / yspan) * plot_h
            self._cached_points.append((bx, by))

    def _transform_point(self, bx: float, by: float) -> QPointF:
        cx = self._cached_plot_rect.center().x()
        cy = self._cached_plot_rect.center().y()
        rx = (bx - cx) * self._zoom
        ry = (by - cy) * self._zoom
        return QPointF(cx + rx + self._pan_offset.x(),
                       cy + ry + self._pan_offset.y())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recompute_layout()

    # ---- Zoom / Pan
    def wheelEvent(self, event) -> None:
        if not self._data:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = ZOOM_STEP if delta > 0 else (1.0 / ZOOM_STEP)
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        self._zoom = new_zoom
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._data:
            self._panning = True
            self._pan_start = event.position()
            self._pan_start_offset = QPointF(self._pan_offset)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_offset = QPointF(
                self._pan_start_offset.x() + delta.x(),
                self._pan_start_offset.y() + delta.y(),
            )
            self.update()
            return

        if not self._cached_points:
            return

        mx = event.position().x()
        my = event.position().y()

        best_i = -1
        best_d = 144.0

        for i, (bx, by) in enumerate(self._cached_points):
            p = self._transform_point(bx, by)
            dx = p.x() - mx
            dy = p.y() - my
            d = dx * dx + dy * dy
            if d < best_d:
                best_d = d
                best_i = i

        new_index = best_i if best_i >= 0 else None
        if new_index != self._hover_index:
            self._hover_index = new_index
            if new_index is not None:
                self._hover_pos = self._transform_point(
                    *self._cached_points[new_index]
                )
            else:
                self._hover_pos = None
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hover_index is not None:
            self._hover_index = None
            self._hover_pos = None
            self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.reset_view()
            self.update()

    # ---- paint
    def paintEvent(self, event) -> None:
        T = self._theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.fillRect(self.rect(), QColor(T["GRAPH_BG"]))

        if not self._data or self._cached_plot_rect.isEmpty():
            painter.setPen(QColor(T["GRAPH_TEXT"]))
            f = painter.font()
            f.setPointSize(14)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Нажмите «СГЕНЕРИРОВАТЬ» для построения графика")
            return

        plot = self._cached_plot_rect

        self._draw_grid_and_axes(painter, plot)

        painter.save()
        painter.setClipRect(plot)
        self._draw_points(painter)
        painter.restore()

        # Определяем значимость линии тренда
        r2_significant = True
        if self._show_regression and len(self._data) >= 2:
            _a, _b, r2 = DataEngine.linear_regression(self._data)
            r2_significant = r2 >= R2_SIGNIFICANCE_THRESHOLD

        if self._show_mean:
            self._draw_mean_line(painter, plot)

        if self._show_regression and r2_significant:
            self._draw_regression(painter, plot)

        self._draw_legend(painter, plot, r2_significant)
        self._draw_regression_info(painter, plot, r2_significant)

        if abs(self._zoom - 1.0) > 0.01 or self._pan_offset.manhattanLength() > 2:
            self._draw_zoom_badge(painter, plot)

        if self._hover_index is not None and self._hover_pos is not None:
            self._draw_hover(painter)

    def _draw_grid_and_axes(self, painter: QPainter, plot: QRectF) -> None:
        T = self._theme

        grid_pen = QPen(QColor(T["GRAPH_GRID"]))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        for i in range(1, GRID_X_DIVISIONS):
            x = plot.left() + plot.width() * i / GRID_X_DIVISIONS
            painter.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))
        for i in range(1, GRID_Y_DIVISIONS):
            y = plot.top() + plot.height() * i / GRID_Y_DIVISIONS
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

        axis_pen = QPen(QColor(T["GRAPH_AXIS"]))
        axis_pen.setWidth(2)
        painter.setPen(axis_pen)
        painter.drawLine(int(plot.left()), int(plot.bottom()),
                         int(plot.right()), int(plot.bottom()))
        painter.drawLine(int(plot.left()), int(plot.top()),
                         int(plot.left()), int(plot.bottom()))

        f = painter.font()
        f.setPointSize(9)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(QColor(T["GRAPH_TEXT"]))

        n = len(self._data)
        for i in range(GRID_X_DIVISIONS + 1):
            x = plot.left() + plot.width() * i / GRID_X_DIVISIONS
            idx = int(round((n - 1) * i / GRID_X_DIVISIONS))
            painter.drawText(
                QRectF(x - 30, plot.bottom() + 8, 60, 20),
                Qt.AlignHCenter | Qt.AlignTop, str(idx),
            )

        for i in range(GRID_Y_DIVISIONS + 1):
            y = plot.top() + plot.height() * i / GRID_Y_DIVISIONS
            val = int(round(Y_MAX_AXIS - (Y_MAX_AXIS - Y_MIN_AXIS) * i / GRID_Y_DIVISIONS))
            # Отступ подписи от оси — 20px, чтобы цифры не прилипали
            painter.drawText(
                QRectF(0, y - 10, plot.left() - 24, 20),
                Qt.AlignRight | Qt.AlignVCenter, str(val),
            )

        # Подпись оси X
        f.setPointSize(10)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(T["ACCENT_SOFT"]))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 32, plot.width(), 24),
            Qt.AlignHCenter | Qt.AlignTop,
            f"Индекс точки (0 … {len(self._data) - 1})",
        )

        # Подпись оси Y — с достаточным отступом от цифр
        painter.save()
        painter.translate(26, plot.center().y())
        painter.rotate(-90)
        painter.drawText(
            QRectF(-plot.height() / 2, 0, plot.height(), 24),
            Qt.AlignCenter,
            f"Значение, {self._unit}",
        )
        painter.restore()

    def _draw_points(self, painter: QPainter) -> None:
        T = self._theme
        n = len(self._data)
        radius = POINT_RADIUS_NORMAL if n < POINTS_RADIUS_THRESHOLD else POINT_RADIUS_SMALL

        normal_color = QColor(T["GRAPH_POINT"])
        normal_color.setAlpha(POINT_ALPHA_NORMAL)
        out_color = QColor(T["GRAPH_POINT_OUT"])
        out_color.setAlpha(POINT_ALPHA_OUT)

        painter.setPen(Qt.NoPen)

        for i, (bx, by) in enumerate(self._cached_points):
            p = self._transform_point(bx, by)
            v = self._data[i]
            painter.setBrush(out_color if v < self._lsl or v > self._usl
                             else normal_color)
            painter.drawEllipse(p, radius, radius)

    def _draw_mean_line(self, painter: QPainter, plot: QRectF) -> None:
        """Линия среднего — только пунктир, БЕЗ текстовой подписи (LOG-02)."""
        T = self._theme
        if not self._data:
            return
        avg = sum(self._data) / len(self._data)
        if not (Y_MIN_AXIS <= avg <= Y_MAX_AXIS):
            return

        y_base = plot.top() + plot.height() * (
            1 - (avg - Y_MIN_AXIS) / (Y_MAX_AXIS - Y_MIN_AXIS)
        )
        y = y_base + self._pan_offset.y()

        pen = QPen(QColor(T["GRAPH_MEAN"]))
        pen.setWidth(2)
        pen.setStyle(Qt.DashDotLine)
        painter.setPen(pen)
        painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

    def _draw_regression(self, painter: QPainter, plot: QRectF) -> None:
        T = self._theme
        if len(self._data) < 2:
            return
        a, b, _r2 = DataEngine.linear_regression(self._data)
        n = len(self._data)
        y_left = a + b * 0
        y_right = a + b * (n - 1)

        yspan = max(Y_MAX_AXIS - Y_MIN_AXIS, 1)

        def to_y(v: float) -> float:
            clamped = max(Y_MIN_AXIS, min(Y_MAX_AXIS, v))
            base = plot.top() + plot.height() * (
                1 - (clamped - Y_MIN_AXIS) / yspan
            )
            return base + self._pan_offset.y()

        pen = QPen(QColor(T["GRAPH_REGRESSION"]))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(
            int(plot.left()), int(to_y(y_left)),
            int(plot.right()), int(to_y(y_right)),
        )

    def _draw_legend(self, painter: QPainter, plot: QRectF,
                     r2_significant: bool) -> None:
        T = self._theme
        lines = [
            (T["GRAPH_POINT"], "●", "В пределах нормы"),
            (T["GRAPH_POINT_OUT"], "●", "Вне допуска"),
        ]
        if self._show_mean:
            lines.append((T["GRAPH_MEAN"], "—", "Среднее"))
        if self._show_regression:
            if r2_significant:
                lines.append((T["GRAPH_REGRESSION"], "—", "Линия тренда"))
            else:
                lines.append((T["TEXT_MUTED"], "—", "Тренд (не значим)"))

        f = painter.font()
        f.setPointSize(9)
        f.setBold(False)
        painter.setFont(f)

        metrics = painter.fontMetrics()
        line_h = metrics.height() + 4
        pad = 10
        marker_w = 18

        max_text_w = max(metrics.horizontalAdvance(text) for _, _, text in lines)
        box_w = pad * 2 + marker_w + max_text_w + 12
        box_h = pad * 2 + line_h * len(lines)

        bx = plot.right() - box_w - 8
        by = plot.top() + 8

        bg = QColor(T["CARD_SOFT"])
        bg.setAlpha(225)
        painter.setPen(QPen(QColor(T["BORDER"]), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 6, 6)

        for i, (color, marker, text) in enumerate(lines):
            y = by + pad + i * line_h
            painter.setPen(QColor(color))
            f2 = painter.font()
            f2.setBold(True)
            f2.setPointSize(11)
            painter.setFont(f2)
            painter.drawText(
                QRectF(bx + pad, y, marker_w, line_h),
                Qt.AlignLeft | Qt.AlignVCenter, marker,
            )
            painter.setPen(QColor(T["TEXT"]))
            f2.setBold(False)
            f2.setPointSize(9)
            painter.setFont(f2)
            painter.drawText(
                QRectF(bx + pad + marker_w, y, max_text_w + 6, line_h),
                Qt.AlignLeft | Qt.AlignVCenter, text,
            )

    def _draw_regression_info(self, painter: QPainter, plot: QRectF,
                              r2_significant: bool) -> None:
        """
        Плашка с уравнением регрессии + R² в верхнем левом углу.
        При R² < порога — предупреждение вместо уравнения (LOG-01).
        """
        if not self._show_regression or len(self._data) < 2:
            return

        T = self._theme
        a, b, r2 = DataEngine.linear_regression(self._data)

        if r2_significant:
            text = f"y = {b:+.4f}·x + {a:.2f}    R² = {r2:.4f}"
            border_color = T["GRAPH_REGRESSION"]
        else:
            text = f"⚠ Линия тренда не значима (R² = {r2:.4f} < {R2_SIGNIFICANCE_THRESHOLD})"
            border_color = T["WARNING"]

        f = painter.font()
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)

        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(text) + 20
        th = metrics.height() + 10

        bx = plot.left() + 8
        by = plot.top() + 8

        bg = QColor(T["CARD_SOFT"])
        bg.setAlpha(225)
        painter.setPen(QPen(QColor(border_color), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)

        painter.setPen(QColor(T["TEXT"] if r2_significant else T["WARNING"]))
        painter.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)

    def _draw_zoom_badge(self, painter: QPainter, plot: QRectF) -> None:
        T = self._theme
        text = f"Масштаб ×{self._zoom:.2f}   (двойной клик — сброс)"
        f = painter.font()
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)

        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(text) + 20
        th = metrics.height() + 10

        bx = plot.left() + 8
        by = plot.bottom() - th - 8

        bg = QColor(T["CARD_SOFT"])
        bg.setAlpha(225)
        painter.setPen(QPen(QColor(T["ACCENT"]), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)

        painter.setPen(QColor(T["ACCENT_SOFT"]))
        painter.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)

    def _draw_hover(self, painter: QPainter) -> None:
        T = self._theme
        if self._hover_pos is None or self._hover_index is None:
            return

        x, y = self._hover_pos.x(), self._hover_pos.y()
        value = self._data[self._hover_index]

        painter.setPen(QPen(QColor(T["ACCENT_SOFT"]), 2))
        painter.setBrush(QColor(T["ACCENT"]))
        painter.drawEllipse(QPointF(x, y), POINT_RADIUS_NORMAL + 3,
                            POINT_RADIUS_NORMAL + 3)

        status = "В допуске" if self._lsl <= value <= self._usl else "БРАК"
        text = f"№{self._hover_index}   {value} {self._unit}   ·   {status}"

        f = painter.font()
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

        bg = QColor(T["CARD_SOFT"])
        bg.setAlpha(245)
        border_color = QColor(T["DANGER"] if status == "БРАК" else T["ACCENT"])
        painter.setPen(QPen(border_color, 2))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)

        painter.setPen(QColor(T["TEXT"]))
        painter.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)


# ---------------------------------------------------------------------------
# Гистограмма
# ---------------------------------------------------------------------------
class HistogramWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._counts: List[int] = []
        self._total = 0
        self._theme = THEME_DARK
        self._unit = "усл. ед."
        self._vmin = 0
        self._vmax = 100

        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme
        self.update()

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        self.update()

    def set_data(self, counts: List[int], total: int,
                 vmin: float, vmax: float) -> None:
        self._counts = counts
        self._total = total
        self._vmin = vmin
        self._vmax = vmax
        self.update()

    def paintEvent(self, event) -> None:
        T = self._theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.fillRect(self.rect(), QColor(T["CARD_BG"]))

        w = self.width()
        h = self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 20, 24, 28
        plot_w = max(w - pad_l - pad_r, 1)
        plot_h = max(h - pad_t - pad_b, 1)

        # Заголовок
        painter.setPen(QColor(T["TEXT_MUTED"]))
        f = painter.font()
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(0, 0, w, pad_t), Qt.AlignCenter,
                         f"Распределение (20 корзин), {self._unit}")

        if not self._counts or self._total == 0:
            painter.setPen(QColor(T["TEXT_MUTED"]))
            f.setPointSize(11)
            painter.setFont(f)
            painter.drawText(QRectF(0, pad_t, w, plot_h),
                             Qt.AlignCenter, "Нет данных")
            return

        max_count = max(self._counts) or 1
        bins = len(self._counts)
        slot_w = plot_w / bins
        bar_w = slot_w * 0.85
        offset = (slot_w - bar_w) / 2

        # Ось
        painter.setPen(QPen(QColor(T["BORDER"]), 1))
        painter.drawLine(int(pad_l), int(pad_t + plot_h),
                         int(pad_l + plot_w), int(pad_t + plot_h))

        # Столбики
        color = QColor(T["GRAPH_HIST"])
        for i, count in enumerate(self._counts):
            ratio = count / max_count
            bh = ratio * plot_h
            x = pad_l + i * slot_w + offset
            y = pad_t + plot_h - bh
            painter.fillRect(int(x), int(y), int(bar_w), int(bh), color)

        # Подписи границ
        painter.setPen(QColor(T["TEXT_MUTED"]))
        f.setPointSize(8)
        f.setBold(False)
        painter.setFont(f)
        painter.drawText(QRectF(pad_l, pad_t + plot_h + 4, plot_w / 2, 20),
                         Qt.AlignLeft, f"{int(self._vmin)}")
        painter.drawText(QRectF(pad_l + plot_w / 2, pad_t + plot_h + 4,
                                plot_w / 2, 20),
                         Qt.AlignRight, f"{int(self._vmax)}")


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class ScatterViewerApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Точечная диаграмма — промышленный анализ выборки")
        self.resize(1600, 960)
        self.setMinimumSize(1400, 880)

        self._data: List[int] = []
        self._current_theme_name = "dark"
        self._theme = THEME_DARK
        self._unit = "усл. ед."
        self._right_panel_visible = True

        self._export_delimiter = ","
        self._export_encoding = "utf-8"
        self._export_include_stats = False

        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        self._build_ui()
        self._apply_styles()
        self._load_settings()

        self._update_export_button_state()

        self._log("Система готова. Нажмите «СГЕНЕРИРОВАТЬ».")
        QTimer.singleShot(80, self._on_generate)

    # ==================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Виджеты, к которым обращается toolbar — создаём ДО toolbar
        self.plot = ScatterPlotWidget()
        self.histogram = HistogramWidget()
        self.chk_show_hist = QCheckBox("Показывать гистограмму распределения")
        self.chk_show_hist.setObjectName("checkInline")
        self.chk_show_hist.toggled.connect(self._on_toggle_hist)

        root.addWidget(self._build_toolbar(), 0)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(14, 14, 14, 14)
        body_layout.setSpacing(14)

        # Центр — стек график + гистограмма
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        center_layout.addWidget(self.plot, 3)
        center_layout.addWidget(self.histogram, 2)
        self.histogram.setVisible(False)

        body_layout.addWidget(center, 1)

        # Правая панель
        self.right_panel = self._build_right_panel()
        body_layout.addWidget(self.right_panel, 0)

        root.addWidget(body, 1)

    # ---- Toolbar — РАЗДЕЛЁН НА 3 РЯДА ---------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbar")

        outer = QVBoxLayout(bar)
        outer.setContentsMargins(20, 14, 20, 14)
        outer.setSpacing(10)

        # ============================================================
        # РЯД 1: Заголовок + статус + главные действия
        # ============================================================
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("ТОЧЕЧНАЯ ДИАГРАММА")
        title.setObjectName("appTitle")
        self.lbl_subtitle = QLabel("Точек: 0 · Диапазон: —")
        self.lbl_subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.lbl_subtitle)

        # Кнопки справа
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("iconButton")
        self.btn_help.setFixedSize(50, 50)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.setToolTip("Справка по метрикам")
        self.btn_help.clicked.connect(self._on_help)

        self.btn_theme = QPushButton("☾")
        self.btn_theme.setObjectName("iconButton")
        self.btn_theme.setFixedSize(50, 50)
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.setToolTip("Переключить тему")
        self.btn_theme.clicked.connect(self._on_toggle_theme)

        self.btn_export_settings = QPushButton("⚙")
        self.btn_export_settings.setObjectName("iconButton")
        self.btn_export_settings.setFixedSize(50, 50)
        self.btn_export_settings.setCursor(Qt.PointingHandCursor)
        self.btn_export_settings.setToolTip("Настройки экспорта")
        self.btn_export_settings.clicked.connect(self._on_export_settings)

        self.btn_export = QPushButton("ЭКСПОРТ")
        self.btn_export.setObjectName("primaryButton")
        self.btn_export.setMinimumHeight(50)
        self.btn_export.setMinimumWidth(140)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export)

        self.btn_generate = QPushButton("СГЕНЕРИРОВАТЬ")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(50)
        self.btn_generate.setMinimumWidth(220)
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.clicked.connect(self._on_generate)

        # Кнопка разворачивания правой панели — всегда доступна в toolbar
        self.btn_toggle_panel = QPushButton("◀")
        self.btn_toggle_panel.setObjectName("iconButton")
        self.btn_toggle_panel.setFixedSize(50, 50)
        self.btn_toggle_panel.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_panel.setToolTip("Свернуть / развернуть панель статистики")
        self.btn_toggle_panel.clicked.connect(self._toggle_right_panel)

        row1.addLayout(title_box, 0)
        row1.addStretch(1)
        row1.addWidget(self.btn_help, 0)
        row1.addWidget(self.btn_theme, 0)
        row1.addWidget(self.btn_export_settings, 0)
        row1.addWidget(self.btn_toggle_panel, 0)
        row1.addWidget(self.btn_export, 0)
        row1.addWidget(self.btn_generate, 0)

        # ============================================================
        # РЯД 2: Параметры (кол-во, диапазон, норма, ед. изм., чекбоксы)
        # ============================================================
        row2 = QHBoxLayout()
        row2.setSpacing(14)

        # Кол-во точек — QSpinBox со стилизованными кнопками
        g_count = self._make_param_group("Количество точек")
        self.spin_count = QSpinBox()
        self.spin_count.setObjectName("tinySpin")
        self.spin_count.setRange(10, COUNT_MAX)
        self.spin_count.setValue(COUNT_DEFAULT)
        self.spin_count.setSingleStep(100)
        self.spin_count.setMinimumHeight(38)
        self.spin_count.setFixedWidth(140)
        g_count.layout().addWidget(self.spin_count)

        # Диапазон
        g_range = self._make_param_group("Диапазон значений")
        rl = QHBoxLayout()
        rl.setSpacing(6)
        self.input_min = self._make_int_input(VALUE_MIN_DEFAULT)
        self.input_max = self._make_int_input(VALUE_MAX_DEFAULT)
        rl.addWidget(QLabel("от"))
        rl.addWidget(self.input_min)
        rl.addWidget(QLabel("до"))
        rl.addWidget(self.input_max)
        g_range.layout().addLayout(rl)

        # Норма
        g_limits = self._make_param_group("Границы нормы")
        ll = QHBoxLayout()
        ll.setSpacing(6)
        self.input_lsl = self._make_int_input(LSL_DEFAULT)
        self.input_usl = self._make_int_input(USL_DEFAULT)
        self.input_lsl.editingFinished.connect(self._on_limits_changed)
        self.input_usl.editingFinished.connect(self._on_limits_changed)
        ll.addWidget(QLabel("LSL"))
        ll.addWidget(self.input_lsl)
        ll.addSpacing(6)
        ll.addWidget(QLabel("USL"))
        ll.addWidget(self.input_usl)
        g_limits.layout().addLayout(ll)

        # Ед. изм. — стилизованный combobox со стрелкой
        g_unit = self._make_param_group("Единица измерения")
        self.combo_unit = QComboBox()
        self.combo_unit.setObjectName("formatCombo")
        for u in UNIT_PRESETS:
            self.combo_unit.addItem(u)
        self.combo_unit.setEditable(True)
        self.combo_unit.setMinimumHeight(38)
        self.combo_unit.setMinimumWidth(140)
        self.combo_unit.currentTextChanged.connect(self._on_unit_changed)
        g_unit.layout().addWidget(self.combo_unit)

        # Чекбоксы — в одном столбце, выровнены
        checks_box = QWidget()
        cbl = QVBoxLayout(checks_box)
        cbl.setContentsMargins(4, 4, 4, 4)
        cbl.setSpacing(6)

        self.chk_regression = QCheckBox("Линия тренда")
        self.chk_regression.setObjectName("toolbarCheck")
        self.chk_regression.setChecked(True)
        self.chk_regression.setFixedHeight(24)
        self.chk_regression.toggled.connect(self.plot.set_show_regression)

        self.chk_mean = QCheckBox("Среднее значение")
        self.chk_mean.setObjectName("toolbarCheck")
        self.chk_mean.setChecked(True)
        self.chk_mean.setFixedHeight(24)
        self.chk_mean.toggled.connect(self.plot.set_show_mean)

        cbl.addWidget(self.chk_regression)
        cbl.addWidget(self.chk_mean)

        row2.addWidget(g_count, 0)
        row2.addWidget(g_range, 0)
        row2.addWidget(g_limits, 0)
        row2.addWidget(g_unit, 0)
        row2.addWidget(checks_box, 0)
        row2.addStretch(1)

        # ============================================================
        # РЯД 3: Формат экспорта + гистограмма + прогресс
        # ============================================================
        row3 = QHBoxLayout()
        row3.setSpacing(14)

        lbl_export_fmt = QLabel("Формат экспорта:")
        lbl_export_fmt.setObjectName("smallLabel")

        self.combo_format = QComboBox()
        self.combo_format.setObjectName("formatCombo")
        for fmt in EXPORT_FORMATS:
            self.combo_format.addItem(fmt)
        self.combo_format.setFixedWidth(120)
        self.combo_format.setMinimumHeight(36)
        self.combo_format.currentTextChanged.connect(self._on_format_changed)

        row3.addWidget(lbl_export_fmt, 0)
        row3.addWidget(self.combo_format, 0)
        row3.addSpacing(20)
        row3.addWidget(self.chk_show_hist, 0)
        row3.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setObjectName("topProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setMinimumWidth(280)
        self.progress.setMaximumWidth(400)
        row3.addWidget(self.progress, 0)

        outer.addLayout(row1)
        outer.addLayout(row2)
        outer.addLayout(row3)

        return bar

    def _make_param_group(self, title: str) -> QGroupBox:
        g = QGroupBox(title)
        g.setObjectName("inlineGroup")
        l = QHBoxLayout(g)
        l.setContentsMargins(12, 12, 12, 10)
        l.setSpacing(6)
        return g

    def _make_int_input(self, value: int) -> QLineEdit:
        f = QLineEdit(str(value))
        f.setObjectName("tinyInput")
        f.setAlignment(Qt.AlignCenter)
        f.setValidator(QIntValidator(-1_000_000, 1_000_000, self))
        f.setFixedWidth(90)
        f.setMinimumHeight(38)
        f.returnPressed.connect(self._on_generate)
        return f

    # ---- Правая панель -------------------------------------------------------
    def _build_right_panel(self) -> QWidget:
        rail = QWidget()
        rail.setFixedWidth(380)
        rail.setObjectName("rightPanel")

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("sideTabs")
        self.tabs.addTab(self._build_stats_tab(), "СТАТИСТИКА")
        self.tabs.addTab(self._build_log_tab(), "ЖУРНАЛ")

        layout.addWidget(self.tabs)
        return rail

    def _build_stats_tab(self) -> QWidget:
        page = QWidget()

        # Прокрутка по вертикали — если контент не влез, будет скролл
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        # Группа 1 — параметры выборки
        g1 = QGroupBox("Параметры выборки")
        l1 = QVBoxLayout(g1)
        l1.setSpacing(8)
        l1.setContentsMargins(16, 22, 16, 16)

        self.card_count, self.lbl_stat_count = self._make_stat_row("Объём выборки", "—", "шт")
        self.card_min, self.lbl_stat_min = self._make_stat_row("Минимум", "—", "")
        self.card_max, self.lbl_stat_max = self._make_stat_row("Максимум", "—", "")
        self.card_avg, self.lbl_stat_avg = self._make_stat_row("Среднее арифм.", "—", "")
        self.card_median, self.lbl_stat_median = self._make_stat_row("Медиана", "—", "")
        self.card_std, self.lbl_stat_std = self._make_stat_row("Ст. отклонение", "—", "σ")
        self.card_cv, self.lbl_stat_cv = self._make_stat_row("Коэф. вариации", "—", "%")
        self.card_skew, self.lbl_stat_skew = self._make_stat_row("Асимметрия", "—", "")
        self.card_kurt, self.lbl_stat_kurt = self._make_stat_row("Эксцесс", "—", "")

        for c in (self.card_count, self.card_min, self.card_max,
                  self.card_avg, self.card_median,
                  self.card_std, self.card_cv,
                  self.card_skew, self.card_kurt):
            l1.addWidget(c)

        # Группа 2 — контроль качества
        g2 = QGroupBox("Контроль качества (LSL / USL)")
        l2 = QVBoxLayout(g2)
        l2.setSpacing(8)
        l2.setContentsMargins(16, 22, 16, 16)

        self.card_lsl, self.lbl_lsl = self._make_stat_row("Нижний предел (LSL)", "—", "")
        self.card_usl, self.lbl_usl = self._make_stat_row("Верхний предел (USL)", "—", "")
        self.card_defect, self.lbl_defect = self._make_stat_row(
            "Вне допуска", "—", "шт", critical=True)
        self.card_defect_pct, self.lbl_defect_pct = self._make_stat_row(
            "Доля брака", "—", "%", critical=True)
        self.card_cp, self.lbl_cp = self._make_stat_row("Cp (потенциал)", "—", "")
        self.card_cpk, self.lbl_cpk = self._make_stat_row("Cpk (факт)", "—", "")

        for c in (self.card_lsl, self.card_usl,
                  self.card_defect, self.card_defect_pct,
                  self.card_cp, self.card_cpk):
            l2.addWidget(c)

        layout.addWidget(g1)
        layout.addWidget(g2)
        layout.addStretch(1)

        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        return page

    def _make_stat_row(self, title: str, value: str, hint: str = "",
                       critical: bool = False):
        row = QFrame()
        row.setObjectName("statRowCritical" if critical else "statRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)

        t = QLabel(title)
        t.setObjectName("statTitle")

        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("statHint")
        hint_lbl.setMinimumWidth(30)

        v = QLabel(value)
        v.setObjectName("statValueCritical" if critical else "statValue")
        v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        v.setMinimumWidth(70)

        h.addWidget(t)
        h.addStretch(1)
        h.addWidget(hint_lbl)
        h.addWidget(v)

        return row, v

    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        lbl = QLabel("ПОСЛЕДНИЕ СОБЫТИЯ")
        lbl.setObjectName("sectionTitle")

        self.btn_clear_log = QPushButton("Очистить")
        self.btn_clear_log.setObjectName("collapseButton")
        self.btn_clear_log.setMinimumHeight(32)
        self.btn_clear_log.setCursor(Qt.PointingHandCursor)
        self.btn_clear_log.clicked.connect(self._clear_log)

        header.addWidget(lbl)
        header.addStretch(1)
        header.addWidget(self.btn_clear_log)

        self.log_label = QLabel("— журнал пуст —")
        self.log_label.setObjectName("logView")
        self.log_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.log_label.setTextFormat(Qt.PlainText)
        self.log_label.setWordWrap(True)
        self.log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addLayout(header)
        layout.addWidget(self.log_label, 1)
        return page

    # ================================================================ Стили
    def _apply_styles(self) -> None:
        T = self._theme
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {T["BG"]};
                color: {T["TEXT"]};
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}
            QWidget {{
                color: {T["TEXT"]};
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}
            QLabel {{
                background: transparent;
                font-size: 11pt;
                color: {T["TEXT"]};
            }}
            QLabel#smallLabel {{
                font-size: 10pt;
                color: {T["TEXT_MUTED"]};
                font-weight: bold;
            }}
            QLabel#sectionTitle {{
                font-size: 10pt;
                font-weight: bold;
                color: {T["TEXT_MUTED"]};
                letter-spacing: 3px;
            }}

            QFrame#toolbar {{
                background: {T["CARD_BG"]};
                border-bottom: 2px solid {T["BORDER_SUBTLE"]};
            }}
            QLabel#appTitle {{
                font-size: 15pt;
                font-weight: 900;
                color: {T["TEXT"]};
                letter-spacing: 4px;
            }}
            QLabel#appSubtitle {{
                font-size: 10pt;
                font-weight: bold;
                color: {T["ACCENT_SOFT"]};
                letter-spacing: 1px;
            }}

            QGroupBox#inlineGroup {{
                background: {T["CARD_SOFT"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-radius: 6px;
                margin-top: 14px;
                padding: 14px 10px 10px 10px;
                font-weight: 700;
                font-size: 10pt;
                color: {T["TEXT_MUTED"]};
            }}
            QGroupBox#inlineGroup::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 6px;
                color: {T["TEXT_MUTED"]};
                background: {T["CARD_SOFT"]};
            }}

            QLineEdit#tinyInput {{
                background: {T["BG"]};
                color: {T["ACCENT_SOFT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12pt;
                font-weight: 900;
                selection-background-color: {T["ACCENT"]};
                selection-color: #ffffff;
            }}
            QLineEdit#tinyInput:focus {{
                border: 2px solid {T["ACCENT"]};
            }}
            QLineEdit#tinyInput[invalid="true"] {{
                border: 2px solid {T["BORDER_ERROR"]};
                color: {T["DANGER_SOFT"]};
            }}

            /* Стилизованный QSpinBox — чистые кнопки */
            QSpinBox#tinySpin {{
                background: {T["BG"]};
                color: {T["ACCENT_SOFT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 5px;
                padding: 4px 4px 4px 8px;
                font-size: 12pt;
                font-weight: 900;
                selection-background-color: {T["ACCENT"]};
                selection-color: #ffffff;
            }}
            QSpinBox#tinySpin:focus {{
                border: 2px solid {T["ACCENT"]};
            }}
            QSpinBox#tinySpin::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 22px;
                background: {T["CARD_SOFT"]};
                border-left: 1px solid {T["BORDER"]};
                border-top-right-radius: 3px;
            }}
            QSpinBox#tinySpin::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 22px;
                background: {T["CARD_SOFT"]};
                border-left: 1px solid {T["BORDER"]};
                border-bottom-right-radius: 3px;
            }}
            QSpinBox#tinySpin::up-button:hover,
            QSpinBox#tinySpin::down-button:hover {{
                background: {T["ACCENT"]};
            }}
            QSpinBox#tinySpin::up-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid {T["TEXT"]};
            }}
            QSpinBox#tinySpin::down-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {T["TEXT"]};
            }}

            QCheckBox#toolbarCheck, QCheckBox#checkInline {{
                font-size: 10pt;
                font-weight: bold;
                color: {T["TEXT"]};
                spacing: 8px;
            }}
            QCheckBox#toolbarCheck::indicator, QCheckBox#checkInline::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {T["BORDER"]};
                border-radius: 4px;
                background: {T["CARD_SOFT"]};
            }}
            QCheckBox#toolbarCheck::indicator:checked,
            QCheckBox#checkInline::indicator:checked {{
                background: {T["ACCENT"]};
                border: 2px solid {T["ACCENT"]};
            }}

            QGroupBox {{
                background: {T["CARD_BG"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-radius: 8px;
                margin-top: 14px;
                padding: 14px 10px 10px 10px;
                font-weight: 700;
                font-size: 11pt;
                color: {T["TEXT"]};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0 8px;
                color: {T["TEXT"]};
                background: {T["CARD_BG"]};
            }}

            QTabWidget#sideTabs::pane {{
                background: {T["CARD_BG"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-radius: 8px;
                top: -1px;
            }}
            QTabWidget#sideTabs QTabBar::tab {{
                background: {T["CARD_SOFT"]};
                color: {T["TEXT_MUTED"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                padding: 12px 20px;
                font-size: 10pt;
                font-weight: 900;
                letter-spacing: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                min-width: 130px;
            }}
            QTabWidget#sideTabs QTabBar::tab:selected {{
                background: {T["CARD_BG"]};
                color: {T["ACCENT_SOFT"]};
                border-bottom: 2px solid {T["ACCENT"]};
            }}

            QFrame#statRow {{
                background: {T["CARD_SOFT"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-radius: 6px;
            }}
            QFrame#statRowCritical {{
                background: {T["CARD_SOFT"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-left: 4px solid {T["DANGER"]};
                border-radius: 6px;
            }}
            QLabel#statTitle {{
                font-size: 11pt;
                font-weight: bold;
                color: {T["TEXT"]};
            }}
            QLabel#statHint {{
                font-size: 10pt;
                color: {T["TEXT_MUTED"]};
                font-weight: bold;
            }}
            QLabel#statValue {{
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 14pt;
                font-weight: 900;
                color: {T["ACCENT_SOFT"]};
            }}
            QLabel#statValueCritical {{
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 14pt;
                font-weight: 900;
                color: {T["DANGER_SOFT"]};
            }}

            QPushButton {{
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 12pt;
                font-weight: 900;
                letter-spacing: 1px;
            }}
            QPushButton#primaryButton {{
                background: {T["ACCENT"]};
                color: {T["ON_ACCENT"]};
                border: 2px solid {T["ACCENT"]};
                font-size: 12pt;
            }}
            QPushButton#primaryButton:hover {{
                background: {T["ACCENT_HOVER"]};
                border: 2px solid {T["ACCENT_HOVER"]};
            }}
            QPushButton#primaryButton:pressed {{
                background: {T["ACCENT_PRESSED"]};
            }}
            QPushButton#primaryButton:disabled {{
                background: {T["CARD_SOFT"]};
                color: {T["TEXT_MUTED"]};
                border: 2px solid {T["BORDER_SUBTLE"]};
            }}

            QPushButton#iconButton {{
                background: {T["CARD_SOFT"]};
                color: {T["ACCENT_SOFT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 8px;
                font-size: 18pt;
                font-weight: 900;
                padding: 0;
            }}
            QPushButton#iconButton:hover {{
                border: 2px solid {T["ACCENT"]};
                color: {T["ACCENT"]};
            }}
            QPushButton#iconButton:checked {{
                background: {T["ACCENT"]};
                color: {T["ON_ACCENT"]};
                border: 2px solid {T["ACCENT"]};
            }}

            QPushButton#collapseButton {{
                background: {T["CARD_SOFT"]};
                color: {T["ACCENT_SOFT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 6px;
                font-size: 10pt;
                font-weight: bold;
                padding: 6px 12px;
                letter-spacing: 1px;
            }}
            QPushButton#collapseButton:hover {{
                border: 2px solid {T["ACCENT"]};
                color: {T["ACCENT"]};
            }}

            QProgressBar#topProgress {{
                background: {T["CARD_SOFT"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-radius: 3px;
            }}
            QProgressBar#topProgress::chunk {{
                background: {T["ACCENT"]};
                border-radius: 3px;
            }}

            QComboBox#formatCombo {{
                background: {T["CARD_SOFT"]};
                color: {T["ACCENT_SOFT"]};
                border: 2px solid {T["BORDER"]};
                border-radius: 5px;
                padding: 4px 30px 4px 10px;
                font-size: 11pt;
                font-weight: 900;
            }}
            QComboBox#formatCombo:hover {{
                border: 2px solid {T["ACCENT"]};
            }}
            QComboBox#formatCombo::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {T["BORDER"]};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background: {T["CARD_BG"]};
            }}
            QComboBox#formatCombo::down-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {T["TEXT"]};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {T["CARD_SOFT"]};
                color: {T["TEXT"]};
                selection-background-color: {T["ACCENT"]};
                selection-color: #ffffff;
                border: 2px solid {T["BORDER"]};
                font-size: 11pt;
            }}

            QLabel#logView {{
                background: {T["CARD_SOFT"]};
                border: 1px solid {T["BORDER_SUBTLE"]};
                border-radius: 6px;
                padding: 12px 14px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                color: {T["TEXT"]};
            }}

            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {T["CARD_SOFT"]};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {T["BORDER"]};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {T["ACCENT"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                background: none; height: 0;
            }}
            """
        )

    # ============================================================ Handlers ==
    def _mark_invalid(self, field: QLineEdit, invalid: bool) -> None:
        field.setProperty("invalid", "true" if invalid else "false")
        field.style().unpolish(field)
        field.style().polish(field)

    def _validate_int(self, field: QLineEdit) -> Optional[int]:
        text = field.text().strip()
        if not text:
            self._mark_invalid(field, True)
            return None
        try:
            v = int(text)
        except ValueError:
            self._mark_invalid(field, True)
            return None
        self._mark_invalid(field, False)
        return v

    def _on_generate(self) -> None:
        vmin = self._validate_int(self.input_min)
        vmax = self._validate_int(self.input_max)
        if vmin is None or vmax is None:
            QMessageBox.warning(self, "Некорректный ввод",
                                "Диапазон должен содержать целые числа.")
            return
        if vmin >= vmax:
            self._mark_invalid(self.input_min, True)
            self._mark_invalid(self.input_max, True)
            QMessageBox.warning(self, "Некорректный диапазон",
                                "Минимум должен быть строго меньше максимума.")
            return

        count = self.spin_count.value()

        # Блокируем кнопку и показываем загрузку
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("ГЕНЕРАЦИЯ…")
        self.progress.setValue(20)
        QApplication.processEvents()

        t0 = time.perf_counter()
        self._data = DataEngine.generate(count, vmin, vmax)
        elapsed = (time.perf_counter() - t0) * 1000

        self.progress.setValue(70)
        QApplication.processEvents()

        self.plot.set_data(self._data, vmin, vmax)
        self._apply_limits_from_inputs()
        self._refresh_stats()

        self.lbl_subtitle.setText(
            f"Точек: {count} · Диапазон: {vmin}…{vmax} {self._unit}"
        )

        self.progress.setValue(100)
        QTimer.singleShot(400, lambda: self.progress.setValue(0))

        self._log(
            f"Сгенерировано {count} точек [{vmin}…{vmax}] за {elapsed:.2f} мс."
        )
        self._update_export_button_state()
        self._save_settings()

        # Возвращаем кнопку
        QTimer.singleShot(300, lambda: (
            self.btn_generate.setEnabled(True),
            self.btn_generate.setText("СГЕНЕРИРОВАТЬ"),
        ))

    def _on_limits_changed(self) -> None:
        lsl = self._validate_int(self.input_lsl)
        usl = self._validate_int(self.input_usl)
        if lsl is None or usl is None:
            return
        if lsl >= usl:
            self._mark_invalid(self.input_lsl, True)
            self._mark_invalid(self.input_usl, True)
            QMessageBox.warning(self, "Некорректные границы",
                                "LSL должен быть строго меньше USL.")
            return
        self.plot.set_limits(lsl, usl)
        if self._data:
            self._refresh_stats()
        self._log(f"Границы нормы: LSL={lsl}, USL={usl}.")
        self._save_settings()

    def _apply_limits_from_inputs(self) -> None:
        lsl = self._validate_int(self.input_lsl)
        usl = self._validate_int(self.input_usl)
        if lsl is None or usl is None:
            return
        if lsl >= usl:
            return
        self.plot.set_limits(lsl, usl)

    def _on_unit_changed(self, text: str) -> None:
        self._unit = text.strip() or "усл. ед."
        self.plot.set_unit(self._unit)
        self.histogram.set_unit(self._unit)
        if self._data:
            self._refresh_stats()
        self._save_settings()

    def _on_format_changed(self, fmt: str) -> None:
        self._log(f"Формат экспорта: {fmt}.")
        self._save_settings()

    def _on_toggle_hist(self, checked: bool) -> None:
        self.histogram.setVisible(checked)
        if checked and self._data:
            self._refresh_histogram()
        self._log(f"Гистограмма {'включена' if checked else 'выключена'}.")

    def _on_toggle_theme(self) -> None:
        self._current_theme_name = "light" if self._current_theme_name == "dark" else "dark"
        self._theme = THEME_LIGHT if self._current_theme_name == "light" else THEME_DARK
        self.plot.set_theme(self._theme)
        self.histogram.set_theme(self._theme)
        self._apply_styles()
        self.btn_theme.setText("☀" if self._current_theme_name == "light" else "☾")
        self._log(f"Тема: {'светлая' if self._current_theme_name == 'light' else 'тёмная'}.")
        self._save_settings()

    def _on_help(self) -> None:
        dlg = HelpDialog(self)
        dlg.exec()

    def _on_export_settings(self) -> None:
        dlg = ExportSettingsDialog(self, self.combo_format.currentText())
        if dlg.exec():
            self._export_delimiter = dlg.delimiter
            self._export_encoding = dlg.encoding
            self._export_include_stats = dlg.include_stats
            self._log(
                f"Экспорт: разделитель '{self._export_delimiter}', "
                f"кодировка {self._export_encoding}, статистика: "
                f"{'да' if self._export_include_stats else 'нет'}."
            )
            self._save_settings()

    def _toggle_right_panel(self) -> None:
        self._right_panel_visible = not self._right_panel_visible
        self.right_panel.setVisible(self._right_panel_visible)
        self.btn_toggle_panel.setText("▶" if not self._right_panel_visible else "◀")
        self._log(f"Правая панель {'развёрнута' if self._right_panel_visible else 'свёрнута'}.")

    def _update_export_button_state(self) -> None:
        self.btn_export.setEnabled(bool(self._data))

    def _refresh_stats(self) -> None:
        if not self._data:
            return

        vmin, vmax, avg, median, std, cv = DataEngine.stats(self._data)
        skew, kurt = DataEngine.skewness_kurtosis(self._data)
        n = len(self._data)

        self.lbl_stat_count.setText(str(n))
        self.lbl_stat_min.setText(str(vmin))
        self.lbl_stat_max.setText(str(vmax))
        self.lbl_stat_avg.setText(f"{avg:.2f}")
        self.lbl_stat_median.setText(f"{median:.2f}")
        self.lbl_stat_std.setText(f"{std:.2f}")
        self.lbl_stat_cv.setText(f"{cv:.2f} %")
        self.lbl_stat_skew.setText(f"{skew:+.3f}")
        self.lbl_stat_kurt.setText(f"{kurt:+.3f}")

        try:
            lsl = int(self.input_lsl.text().strip())
            usl = int(self.input_usl.text().strip())
        except ValueError:
            lsl, usl = LSL_DEFAULT, USL_DEFAULT

        self.lbl_lsl.setText(str(lsl))
        self.lbl_usl.setText(str(usl))

        defects = sum(1 for v in self._data if v < lsl or v > usl)
        pct = defects / n * 100 if n else 0.0
        self.lbl_defect.setText(str(defects))
        self.lbl_defect_pct.setText(f"{pct:.2f} %")
        self._mark_critical(self.lbl_defect, defects > 0)
        self._mark_critical(self.lbl_defect_pct, pct > 5.0)

        cp, cpk, _ = DataEngine.cp_cpk(self._data, lsl, usl)
        self.lbl_cp.setText(f"{cp:.3f}")
        self.lbl_cpk.setText(f"{cpk:.3f}")
        self._mark_critical(self.lbl_cp, cp < 1.0)
        self._mark_critical(self.lbl_cpk, cpk < 1.0)

        if self.histogram.isVisible():
            self._refresh_histogram()

    def _refresh_histogram(self) -> None:
        if not self._data:
            return
        vmin = min(self._data)
        vmax = max(self._data)
        if vmax <= vmin:
            vmax = vmin + 1
        counts = DataEngine.histogram(self._data, vmin, vmax, bins=20)
        self.histogram.set_data(counts, len(self._data), vmin, vmax)

    def _mark_critical(self, label: QLabel, critical: bool) -> None:
        base = "statValueCritical" if critical else "statValue"
        label.setObjectName(base)
        label.style().unpolish(label)
        label.style().polish(label)

    # ---- Экспорт
    def _on_export(self) -> None:
        if not self._data:
            return

        fmt = self.combo_format.currentText()
        if fmt == "CSV":
            default_name = "scatter_points.csv"
            filter_str = "CSV файлы (*.csv);;Все файлы (*)"
        else:
            default_name = "scatter_points.json"
            filter_str = "JSON файлы (*.json);;Все файлы (*)"

        path, _ = QFileDialog.getSaveFileName(
            self, f"Сохранить в {fmt}", default_name, filter_str
        )
        if not path:
            return

        try:
            if fmt == "CSV":
                self._export_csv(path)
            else:
                self._export_json(path)
        except (OSError, UnicodeEncodeError) as exc:
            QMessageBox.critical(self, "Ошибка сохранения",
                                 f"Не удалось сохранить файл:\n{exc}")
            return

        self.statusBar().showMessage(f"Экспортировано ({fmt}): {path}", 5000)
        self._log(f"Экспорт ({fmt}) → {os.path.basename(path)}")
        self._save_settings()

    def _export_csv(self, path: str) -> None:
        delim = self._export_delimiter
        with open(path, "w", encoding=self._export_encoding, newline="") as f:
            writer = csv.writer(f, delimiter=delim)
            writer.writerow(["Индекс", f"Значение ({self._unit})"])
            for i, v in enumerate(self._data):
                writer.writerow([i, v])
            if self._export_include_stats:
                writer.writerow([])
                writer.writerow(["--- СТАТИСТИКА ---"])
                vmin, vmax, avg, median, std, cv = DataEngine.stats(self._data)
                skew, kurt = DataEngine.skewness_kurtosis(self._data)
                try:
                    lsl = int(self.input_lsl.text().strip())
                    usl = int(self.input_usl.text().strip())
                except ValueError:
                    lsl, usl = LSL_DEFAULT, USL_DEFAULT
                cp, cpk, _ = DataEngine.cp_cpk(self._data, lsl, usl)
                for k, v in [
                    ("Объём", len(self._data)),
                    ("Минимум", vmin), ("Максимум", vmax),
                    ("Среднее", f"{avg:.4f}"),
                    ("Медиана", f"{median:.4f}"),
                    ("Ст. откл.", f"{std:.4f}"),
                    ("Коэф. вариации, %", f"{cv:.4f}"),
                    ("Асимметрия", f"{skew:.4f}"),
                    ("Эксцесс", f"{kurt:.4f}"),
                    ("LSL", lsl), ("USL", usl),
                    ("Cp", f"{cp:.4f}"), ("Cpk", f"{cpk:.4f}"),
                ]:
                    writer.writerow([k, v])

    def _export_json(self, path: str) -> None:
        try:
            lsl = int(self.input_lsl.text().strip())
            usl = int(self.input_usl.text().strip())
        except ValueError:
            lsl, usl = LSL_DEFAULT, USL_DEFAULT

        vmin, vmax, avg, median, std, cv = DataEngine.stats(self._data)
        skew, kurt = DataEngine.skewness_kurtosis(self._data)
        cp, cpk, _ = DataEngine.cp_cpk(self._data, lsl, usl)

        payload = {
            "unit": self._unit,
            "count": len(self._data),
            "limits": {"lsl": lsl, "usl": usl},
            "stats": {
                "min": vmin, "max": vmax,
                "avg": round(avg, 4), "median": round(median, 4),
                "stddev": round(std, 4), "cv_percent": round(cv, 4),
                "skewness": round(skew, 4), "kurtosis": round(kurt, 4),
                "cp": round(cp, 4), "cpk": round(cpk, 4),
            },
            "values": self._data,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ---- Журнал
    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}]  {message}"

        current = self.log_label.text()
        if current == "— журнал пуст —":
            lines = []
        else:
            lines = current.splitlines()
        lines.insert(0, line)
        if len(lines) > LOG_MAX_LINES:
            lines = lines[:LOG_MAX_LINES]
        self.log_label.setText("\n".join(lines))

    def _clear_log(self) -> None:
        self.log_label.setText("— журнал пуст —")
        self._log("Журнал очищен.")

    # ---- Настройки
    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("theme", self._current_theme_name)
        s.setValue("unit", self._unit)
        s.setValue("count", self.spin_count.value())
        s.setValue("min", self.input_min.text())
        s.setValue("max", self.input_max.text())
        s.setValue("lsl", self.input_lsl.text())
        s.setValue("usl", self.input_usl.text())
        s.setValue("export_format", self.combo_format.currentText())
        s.setValue("export_delimiter", self._export_delimiter)
        s.setValue("export_encoding", self._export_encoding)
        s.setValue("export_include_stats", self._export_include_stats)
        s.setValue("right_panel_visible", self._right_panel_visible)

    def _load_settings(self) -> None:
        s = self._settings

        theme = s.value("theme", "dark")
        if theme == "light":
            self._current_theme_name = "dark"
            self._on_toggle_theme()

        unit = s.value("unit", "усл. ед.")
        idx = self.combo_unit.findText(unit)
        if idx >= 0:
            self.combo_unit.setCurrentIndex(idx)
        else:
            self.combo_unit.setEditText(unit)
        self._unit = unit

        try:
            self.spin_count.setValue(int(s.value("count", COUNT_DEFAULT)))
        except (TypeError, ValueError):
            pass

        for key, field in (("min", self.input_min),
                           ("max", self.input_max),
                           ("lsl", self.input_lsl),
                           ("usl", self.input_usl)):
            val = s.value(key)
            if val is not None:
                field.setText(str(val))

        fmt = s.value("export_format", "CSV")
        idx = self.combo_format.findText(fmt)
        if idx >= 0:
            self.combo_format.setCurrentIndex(idx)

        self._export_delimiter = s.value("export_delimiter", ",")
        self._export_encoding = s.value("export_encoding", "utf-8")
        self._export_include_stats = s.value("export_include_stats", False)
        if isinstance(self._export_include_stats, str):
            self._export_include_stats = self._export_include_stats.lower() == "true"

        # Правая панель — состояние
        rp = s.value("right_panel_visible", True)
        if isinstance(rp, str):
            rp = rp.lower() == "true"
        self._right_panel_visible = bool(rp)
        if not self._right_panel_visible:
            self.right_panel.setVisible(False)
            self.btn_toggle_panel.setText("▶")

        self._log("Настройки восстановлены.")

    # ---- Lifecycle
    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)


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
    window = ScatterViewerApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())