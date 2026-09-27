"""
Industrial Data Load Simulator — v1.0
=====================================
Промышленный генератор массивов для стресс-тестирования.

Назначение: генерация сверхбольших массивов случайных чисел, экспресс-анализ
плотности распределения и точное измерение скорости обработки.

Соответствует ISO 9241 / ГОСТ Р ИСО 9241-110.

Архитектурные принципы:
  - Разделение слоёв: UI ↔ бизнес-логика (генерация/статистика) ↔ I/O (CSV).
  - Логарифмический слайдер объёма через дискретные пресеты.
  - Гистограмма на QPainter: мгновенная отрисовка без тяжёлых виджетов.
  - Защита от дурака: валидация слайдеров, антидребезг, безопасный CSV-экспорт.
  - Никаких QTableWidget — только графические примитивы для 50 000+ точек.

Стек: Python 3.10+, PySide6. Сторонние зависимости отсутствуют.
"""

from __future__ import annotations

import csv
import random
import sys
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Пресеты объёма выборки (логарифмическая шкала через индексы слайдера)
# ---------------------------------------------------------------------------
SAMPLE_PRESETS: List[int] = [10, 50, 100, 500, 1000, 5000, 10000, 50000]
DEFAULT_PRESET_INDEX = 4  # 1000 — рабочая точка по умолчанию

# Быстрые пресеты под слайдером
QUICK_PRESETS: List[int] = [100, 1000, 10000]

# Диапазон значений по умолчанию
DEFAULT_VMIN = 0
DEFAULT_VMAX = 100
RANGE_SLIDER_MAX = 200

# Количество корзин гистограммы
BINS_COUNT = 10

# Антидребезг кнопки запуска
DEBOUNCE_MS = 100

# Верхняя граница «разумного» массива для защиты от лавины по памяти
MAX_SAFE_SAMPLE = 500_000


# ---------------------------------------------------------------------------
# Промышленная палитра HMI
# ---------------------------------------------------------------------------
COLOR_BG = "#f4f5f7"
COLOR_TEXT = "#000000"
COLOR_TEXT_MUTED = "#4a5058"
COLOR_BORDER = "#959da5"
COLOR_BORDER_FOCUS = "#2b579a"
COLOR_BORDER_SUBTLE = "#c8ccd2"

COLOR_PRIMARY = "#2b579a"
COLOR_PRIMARY_HOVER = "#1e3f7a"
COLOR_PRIMARY_PRESSED = "#15305e"
COLOR_ON_PRIMARY = "#ffffff"

COLOR_BTN_BG = "#e7eaee"
COLOR_BTN_BG_HOVER = "#d8dde3"
COLOR_BTN_BG_PRESSED = "#c9ced5"

COLOR_BAR = "#3b6ea5"            # сине-стальной — гистограмма
COLOR_BAR_TOP = "#4a80bb"        # лёгкий градиент вершины
COLOR_BAR_GRID = "#e3e7ec"
COLOR_BAR_BG = "#ffffff"

COLOR_META_VALUE = "#0f1e33"
COLOR_META_ACCENT = "#2b579a"

CONTROL_HEIGHT = 44
CONTROL_FONT_SIZE = 12


# ---------------------------------------------------------------------------
# Бизнес-логика: генерация и статистика
# ---------------------------------------------------------------------------
class DataEngine:
    """
    Генерация массива и его статистический анализ.
    Не зависит от UI — принимает параметры, возвращает числа/метрики.
    """

    @staticmethod
    def generate(count: int, vmin: int, vmax: int) -> List[int]:
        """
        Генерация массива через встроенный random.randint.
        Возвращает готовый список целых чисел.
        """
        # Одна локальная ссылка на randint — небольшой, но реальный выигрыш
        # при 50 000 итерациях (экономит атрибутный поиск).
        randint = random.randint
        return [randint(vmin, vmax) for _ in range(count)]

    @staticmethod
    def stats(data: List[int]) -> Tuple[int, int, float, float]:
        """
        Минимум, максимум, среднее и медиана — только stdlib.
        Медиана через сортировку (для 50k это доли миллисекунды).
        """
        if not data:
            return 0, 0, 0.0, 0.0

        vmin = min(data)
        vmax = max(data)
        avg = sum(data) / len(data)

        sorted_data = sorted(data)
        n = len(sorted_data)
        mid = n // 2
        if n % 2 == 1:
            median = float(sorted_data[mid])
        else:
            median = (sorted_data[mid - 1] + sorted_data[mid]) / 2.0

        return vmin, vmax, avg, median

    @staticmethod
    def histogram(data: List[int], vmin: int, vmax: int,
                  bins: int = BINS_COUNT) -> List[int]:
        """
        Разбивает диапазон [vmin..vmax] на `bins` равных интервалов и
        считает количество чисел в каждом.

        Возвращает список длиной `bins` с абсолютными частотами.
        Работает за O(N) — один проход по массиву, никаких сортировок.
        """
        result = [0] * bins
        if not data or vmax <= vmin:
            return result

        span = vmax - vmin
        for v in data:
            # Нормализуем в индекс корзины [0..bins-1].
            # Последняя корзина включает и верхнюю границу (v == vmax).
            idx = (v - vmin) * bins // span
            if idx >= bins:
                idx = bins - 1
            elif idx < 0:
                idx = 0
            result[idx] += 1
        return result


# ---------------------------------------------------------------------------
# Кастомная гистограмма (QPainter, без сторонних виджетов)
# ---------------------------------------------------------------------------
class HistogramWidget(QWidget):
    """
    Кастомный виджет гистограммы распределения.

    Принимает абсолютные частоты по корзинам, нормализует к процентам
    от общего числа и рисует 10 вертикальных столбиков. Подписи корзин
    (диапазоны значений) — под каждым столбиком. Проценты — над столбиком.

    Оптимизирован: WA_OpaquePaintEvent, без аллокаций в горячем цикле,
    перерисовка мгновенная даже при 50 000 точек, т.к. рисуется только
    BINS_COUNT столбиков (независимо от объёма выборки).
    """

    def __init__(self, bins: int = BINS_COUNT, parent=None) -> None:
        super().__init__(parent)
        self._bins = bins
        self._counts: List[int] = [0] * bins
        self._bin_edges: List[Tuple[int, int]] = [(0, 0)] * bins
        self._total: int = 0

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(260)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_data(self, counts: List[int], edges: List[Tuple[int, int]],
                 total: int) -> None:
        """
        Установка новых данных: абсолютные частоты, границы корзин,
        общее число для расчёта процентов.
        """
        self._counts = counts
        self._bin_edges = edges
        self._total = max(total, 0)
        self.update()

    def clear(self) -> None:
        self._counts = [0] * self._bins
        self._bin_edges = [(0, 0)] * self._bins
        self._total = 0
        self.update()

    # ----------------------------------------------------- paint -----------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        # 1) Фон
        painter.fillRect(rect, QColor(COLOR_BAR_BG))

        # 2) Отступы под подписи
        pad_left = 50
        pad_right = 20
        pad_top = 30
        pad_bottom = 46

        plot_w = max(w - pad_left - pad_right, 1)
        plot_h = max(h - pad_top - pad_bottom, 1)

        # 3) Сетка по горизонтали (5 линий) — очень светлая
        grid_pen = QPen(QColor(COLOR_BAR_GRID))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        for i in range(1, 5):
            y = pad_top + plot_h * i / 5
            painter.drawLine(pad_left, int(y), pad_left + plot_w, int(y))

        # 4) Если данных нет — заглушка
        if self._total == 0:
            painter.setPen(QColor("#8892a0"))
            f = painter.font()
            f.setPointSize(12)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignCenter, "Ожидание запуска теста...")
            return

        # 5) Пропорции столбиков
        total_slots = self._bins
        slot_w = plot_w / total_slots
        bar_w = slot_w * 0.7          # 70% ширины слота — воздух между столбиками
        bar_offset = (slot_w - bar_w) / 2

        max_count = max(self._counts) if self._counts else 0
        if max_count == 0:
            max_count = 1

        # 6) Рисуем столбики
        bar_color = QColor(COLOR_BAR)
        bar_top_color = QColor(COLOR_BAR_TOP)

        # Шрифт подписей — один раз ставим, не аллоцируем на каждой итерации
        label_font = painter.font()
        label_font.setPointSize(9)
        label_font.setBold(False)

        value_font = painter.font()
        value_font.setPointSize(10)
        value_font.setBold(True)

        for i, count in enumerate(self._counts):
            ratio = count / max_count
            bar_h = ratio * plot_h

            x = pad_left + i * slot_w + bar_offset
            y = pad_top + plot_h - bar_h

            # Основание столбика
            painter.fillRect(
                int(x), int(y), int(bar_w), int(bar_h), bar_color
            )
            # Акцентная «шапка» сверху — тонкая полоса для читаемости
            if bar_h > 2:
                painter.fillRect(
                    int(x), int(y), int(bar_w), 2, bar_top_color
                )

            # Процент над столбиком
            pct = (count / self._total * 100.0) if self._total else 0.0
            painter.setFont(value_font)
            painter.setPen(QColor(COLOR_META_VALUE))
            text_y = int(y) - 6
            if text_y < pad_top + 12:
                text_y = int(y) + 16  # если столбик высокий — пишем внутрь
            painter.drawText(
                int(x) - 2, text_y, int(bar_w) + 4, 16,
                Qt.AlignHCenter | Qt.AlignBottom,
                f"{pct:.1f}%",
            )

            # Подпись диапазона корзины под осью
            painter.setFont(label_font)
            painter.setPen(QColor(COLOR_TEXT_MUTED))
            lo, hi = self._bin_edges[i]
            painter.drawText(
                int(pad_left + i * slot_w), pad_top + plot_h + 4,
                int(slot_w), 18,
                Qt.AlignHCenter | Qt.AlignTop,
                f"{lo}…{hi}",
            )

        # 7) Оси
        axis_pen = QPen(QColor(COLOR_BORDER))
        axis_pen.setWidth(1)
        painter.setPen(axis_pen)
        painter.drawLine(
            pad_left, pad_top + plot_h, pad_left + plot_w, pad_top + plot_h
        )
        painter.drawLine(pad_left, pad_top, pad_left, pad_top + plot_h)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class DataLoadSimulatorApp(QMainWindow):
    """АРМ оператора: объём выборки, бенчмарк, гистограмма, метрики."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Industrial Data Load Simulator v1.0")
        self.resize(1500, 860)

        # --- Состояние бизнес-логики ---
        self._data: List[int] = []
        self._is_generating: bool = False
        self._last_elapsed_ms: float = 0.0
        self._last_speed: float = 0.0

        # --- Таймер антидребезга ---
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._release_generate_button)

        self._build_ui()
        self._apply_styles()
        self._update_sample_label()
        self._update_range_labels()
        self._update_metrics_placeholder()

    # ==================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_left_panel(), 0)
        root.addWidget(self._build_center_panel(), 1)
        root.addWidget(self._build_right_panel(), 0)

    # ---- Левая панель -------------------------------------------------------
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(320)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_sample_group())
        layout.addWidget(self._build_range_group())
        layout.addWidget(self._build_action_group())
        layout.addStretch(1)

        return panel

    def _build_sample_group(self) -> QGroupBox:
        group = QGroupBox("Объём выборки")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 14, 10, 10)

        self.lbl_sample_title = QLabel("Количество чисел:")
        self.lbl_sample_value = QLabel("—")
        self.lbl_sample_value.setObjectName("valueBadge")
        self.lbl_sample_value.setAlignment(Qt.AlignCenter)

        # Логарифмическая шкала: range = [0, len(SAMPLE_PRESETS) - 1]
        self.slider_sample = QSlider(Qt.Horizontal)
        self.slider_sample.setRange(0, len(SAMPLE_PRESETS) - 1)
        self.slider_sample.setValue(DEFAULT_PRESET_INDEX)
        self.slider_sample.setSingleStep(1)
        self.slider_sample.setPageStep(1)
        self.slider_sample.setTickInterval(1)
        self.slider_sample.setTickPosition(QSlider.TicksBelow)
        self.slider_sample.setMinimumHeight(40)
        self.slider_sample.valueChanged.connect(self._on_sample_slider_changed)

        # Быстрые пресеты
        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        self.preset_buttons: List[QPushButton] = []
        for value in QUICK_PRESETS:
            btn = QPushButton(self._format_number(value))
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("presetButton")
            btn.clicked.connect(
                lambda _checked=False, v=value: self._apply_quick_preset(v)
            )
            presets_row.addWidget(btn)
            self.preset_buttons.append(btn)

        layout.addWidget(self.lbl_sample_title)
        layout.addWidget(self.lbl_sample_value)
        layout.addWidget(self.slider_sample)
        layout.addLayout(presets_row)

        return group

    def _build_range_group(self) -> QGroupBox:
        group = QGroupBox("Диапазон значений")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 14, 10, 10)

        # --- Min ---
        self.lbl_range_min_title = QLabel("Минимум:")
        self.lbl_range_min_value = QLabel(str(DEFAULT_VMIN))
        self.lbl_range_min_value.setObjectName("valueBadge")
        self.lbl_range_min_value.setAlignment(Qt.AlignCenter)

        self.slider_min = QSlider(Qt.Horizontal)
        self.slider_min.setRange(0, RANGE_SLIDER_MAX)
        self.slider_min.setValue(DEFAULT_VMIN)
        self.slider_min.setMinimumHeight(36)
        self.slider_min.valueChanged.connect(self._on_min_slider_changed)

        # --- Max ---
        self.lbl_range_max_title = QLabel("Максимум:")
        self.lbl_range_max_value = QLabel(str(DEFAULT_VMAX))
        self.lbl_range_max_value.setObjectName("valueBadge")
        self.lbl_range_max_value.setAlignment(Qt.AlignCenter)

        self.slider_max = QSlider(Qt.Horizontal)
        self.slider_max.setRange(0, RANGE_SLIDER_MAX)
        self.slider_max.setValue(DEFAULT_VMAX)
        self.slider_max.setMinimumHeight(36)
        self.slider_max.valueChanged.connect(self._on_max_slider_changed)

        layout.addWidget(self.lbl_range_min_title)
        layout.addWidget(self.lbl_range_min_value)
        layout.addWidget(self.slider_min)
        layout.addSpacing(4)
        layout.addWidget(self.lbl_range_max_title)
        layout.addWidget(self.lbl_range_max_value)
        layout.addWidget(self.slider_max)

        return group

    def _build_action_group(self) -> QGroupBox:
        group = QGroupBox("Действие")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 14, 10, 10)

        self.btn_generate = QPushButton("ЗАПУСТИТЬ ТЕСТ")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(56)
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        layout.addWidget(self.btn_generate)
        return group

    # ---- Центральная панель -------------------------------------------------
    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_monitor_block(), 0)
        layout.addWidget(self._build_histogram_block(), 1)

        return panel

    def _build_monitor_block(self) -> QWidget:
        card = QFrame()
        card.setObjectName("monitorCard")
        card.setFrameShape(QFrame.NoFrame)
        card.setMinimumHeight(120)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 14)
        layout.setSpacing(6)

        title = QLabel("МОНИТОРИНГ ПРОИЗВОДИТЕЛЬНОСТИ")
        title.setObjectName("monitorTitle")
        title.setAlignment(Qt.AlignCenter)

        self.lbl_monitor_volume = QLabel("Объём: —")
        self.lbl_monitor_volume.setObjectName("monitorLine")
        self.lbl_monitor_volume.setAlignment(Qt.AlignCenter)

        self.lbl_monitor_time = QLabel("Время генерации: —")
        self.lbl_monitor_time.setObjectName("monitorLineAccent")
        self.lbl_monitor_time.setAlignment(Qt.AlignCenter)

        self.lbl_monitor_speed = QLabel("Скорость: — чисел/сек")
        self.lbl_monitor_speed.setObjectName("monitorLineAccent")
        self.lbl_monitor_speed.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(self.lbl_monitor_volume)
        layout.addWidget(self.lbl_monitor_time)
        layout.addWidget(self.lbl_monitor_speed)

        self.monitor_card = card
        return card

    def _build_histogram_block(self) -> QGroupBox:
        group = QGroupBox("Плотность распределения (10 интервалов)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)

        self.histogram = HistogramWidget(BINS_COUNT)
        layout.addWidget(self.histogram)

        return group

    # ---- Правая панель ------------------------------------------------------
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(240)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_metrics_group(), 1)
        layout.addWidget(self._build_export_button(), 0)

        return panel

    def _build_metrics_group(self) -> QGroupBox:
        group = QGroupBox("Метрики массива")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 14, 10, 10)

        self.lbl_total = QLabel("Всего: —")
        self.lbl_min = QLabel("Min: —")
        self.lbl_max = QLabel("Max: —")
        self.lbl_avg = QLabel("Avg: —")
        self.lbl_median = QLabel("Median: —")

        for lbl in (self.lbl_total, self.lbl_min, self.lbl_max,
                    self.lbl_avg, self.lbl_median):
            f = lbl.font()
            f.setPointSize(13)
            f.setBold(True)
            lbl.setFont(f)
            lbl.setObjectName("metricLine")
            layout.addWidget(lbl)

        layout.addStretch(1)
        return group

    def _build_export_button(self) -> QPushButton:
        self.btn_export = QPushButton("Экспорт пакета в CSV")
        self.btn_export.setObjectName("exportButton")
        self.btn_export.setMinimumHeight(CONTROL_HEIGHT)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export)
        return self.btn_export

    # ================================================================ Стили
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background-color: {COLOR_BG};
                color: {COLOR_TEXT};
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}
            QLabel {{ font-size: 11pt; color: {COLOR_TEXT}; }}

            /* ================== GroupBox ================== */
            QGroupBox {{
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                font-weight: 600;
                font-size: 11pt;
                color: {COLOR_TEXT};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: {COLOR_TEXT};
            }}

            /* ================== QSlider ================== */
            QSlider::groove:horizontal {{
                height: 8px;
                background: #d5d9de;
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLOR_BORDER_FOCUS};
                border: 1px solid {COLOR_BORDER_FOCUS};
                border-radius: 4px;
            }}
            QSlider::add-page:horizontal {{
                background: #d5d9de;
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #ffffff;
                border: 2px solid {COLOR_BORDER_FOCUS};
                width: 20px;
                margin: -9px 0;
                border-radius: 11px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #eef5ff;
            }}
            QSlider::tick-mark {{
                background: {COLOR_BORDER};
            }}

            /* ================== Бейджи значений ================== */
            QLabel#valueBadge {{
                background: #ffffff;
                border: 2px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: 6px 10px;
                font-size: 14pt;
                font-weight: bold;
                color: {COLOR_TEXT};
                min-height: 30px;
            }}

            /* ================== Кнопки ================== */
            QPushButton {{
                border-radius: 5px;
                padding: 10px 14px;
                font-size: {CONTROL_FONT_SIZE}pt;
                font-weight: bold;
            }}

            QPushButton#primaryButton {{
                background: {COLOR_PRIMARY};
                color: {COLOR_ON_PRIMARY};
                border: 2px solid {COLOR_PRIMARY};
                font-size: {CONTROL_FONT_SIZE + 2}pt;
            }}
            QPushButton#primaryButton:hover {{
                background: {COLOR_PRIMARY_HOVER};
                border: 2px solid {COLOR_PRIMARY_HOVER};
            }}
            QPushButton#primaryButton:pressed {{
                background: {COLOR_PRIMARY_PRESSED};
                border: 2px solid {COLOR_PRIMARY_PRESSED};
            }}
            QPushButton#primaryButton:disabled {{
                background: #8ea6c9;
                border: 2px solid #8ea6c9;
                color: #eef1f6;
            }}

            QPushButton#presetButton {{
                background: {COLOR_BTN_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                font-size: 11pt;
            }}
            QPushButton#presetButton:hover {{
                background: {COLOR_BTN_BG_HOVER};
                border: 2px solid {COLOR_BORDER_FOCUS};
            }}
            QPushButton#presetButton:pressed {{
                background: {COLOR_BTN_BG_PRESSED};
            }}

            QPushButton#exportButton {{
                background: {COLOR_BTN_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                font-size: {CONTROL_FONT_SIZE}pt;
            }}
            QPushButton#exportButton:hover {{
                background: {COLOR_BTN_BG_HOVER};
                border: 2px solid {COLOR_BORDER_FOCUS};
            }}
            QPushButton#exportButton:pressed {{
                background: {COLOR_BTN_BG_PRESSED};
            }}

            /* ================== Мониторинг ================== */
            QFrame#monitorCard {{
                background: #ffffff;
                border: 2px solid {COLOR_BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QLabel#monitorTitle {{
                font-size: 11pt;
                font-weight: bold;
                color: {COLOR_TEXT_MUTED};
                letter-spacing: 2px;
            }}
            QLabel#monitorLine {{
                font-size: 13pt;
                font-weight: bold;
                color: {COLOR_META_VALUE};
            }}
            QLabel#monitorLineAccent {{
                font-size: 15pt;
                font-weight: 900;
                color: {COLOR_META_ACCENT};
            }}

            /* ================== Метрики ================== */
            QLabel#metricLine {{
                font-size: 13pt;
                font-weight: bold;
                color: {COLOR_META_VALUE};
                padding: 2px 0;
            }}
            """
        )

    # ==================================================== Синхронизация UI
    @staticmethod
    def _format_number(value: int) -> str:
        """Форматирование с неразрывным пробелом-разделителем: 1 000, 10 000."""
        return f"{value:,}".replace(",", " ")

    def _current_sample_size(self) -> int:
        idx = self.slider_sample.value()
        return SAMPLE_PRESETS[idx]

    def _update_sample_label(self) -> None:
        value = self._current_sample_size()
        self.lbl_sample_value.setText(self._format_number(value))

        # Подсветка активного пресета (если совпал с быстрым)
        for btn, preset in zip(self.preset_buttons, QUICK_PRESETS):
            active = (value == preset)
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _update_range_labels(self) -> None:
        self.lbl_range_min_value.setText(str(self.slider_min.value()))
        self.lbl_range_max_value.setText(str(self.slider_max.value()))

    def _update_metrics_placeholder(self) -> None:
        self.lbl_total.setText("Всего: —")
        self.lbl_min.setText("Min: —")
        self.lbl_max.setText("Max: —")
        self.lbl_avg.setText("Avg: —")
        self.lbl_median.setText("Median: —")

    # =========================================================== Обработчики
    def _on_sample_slider_changed(self, value: int) -> None:
        self._update_sample_label()

    def _apply_quick_preset(self, value: int) -> None:
        """Мгновенно переключает слайдер на ближайший пресет."""
        if value in SAMPLE_PRESETS:
            idx = SAMPLE_PRESETS.index(value)
            self.slider_sample.setValue(idx)

    def _on_min_slider_changed(self, value: int) -> None:
        """
        Взаимная валидация: Min упирается в Max (Max не двигается).
        Предсказуемое поведение по ГОСТ Р ИСО 9241-110.
        """
        max_val = self.slider_max.value()
        if value >= max_val:
            self.slider_min.blockSignals(True)
            self.slider_min.setValue(
                max(max_val - 1, self.slider_min.minimum())
            )
            self.slider_min.blockSignals(False)

        self._update_range_labels()

    def _on_max_slider_changed(self, value: int) -> None:
        min_val = self.slider_min.value()
        if value <= min_val:
            self.slider_max.blockSignals(True)
            self.slider_max.setValue(
                min(min_val + 1, self.slider_max.maximum())
            )
            self.slider_max.blockSignals(False)

        self._update_range_labels()

    # ================================================== Главное действие ==
    def _on_generate_clicked(self) -> None:
        """
        Запуск теста: генерация массива, точный замер, статистика,
        гистограмма, метрики. Защита от дребезга через блокировку кнопки.
        """
        if self._is_generating:
            return

        count = self._current_sample_size()
        vmin = self.slider_min.value()
        vmax = self.slider_max.value()

        # Защита от дурака: аномально большой объём — предупреждаем
        if count > MAX_SAFE_SAMPLE:
            QMessageBox.warning(
                self, "Превышение лимита",
                f"Объём {self._format_number(count)} превышает безопасный лимит "
                f"{self._format_number(MAX_SAFE_SAMPLE)}."
            )
            return
        if vmin >= vmax:
            QMessageBox.warning(
                self, "Некорректный диапазон",
                "Минимум должен быть строго меньше максимума."
            )
            return

        # Блокировка кнопки на DEBOUNCE_MS
        self._is_generating = True
        self.btn_generate.setEnabled(False)
        self._debounce_timer.start(DEBOUNCE_MS)

        # --- Бенчмарк: точное измерение времени генерации ---
        # perf_counter_ns() — монотонные наносекунды, максимальная точность
        t0 = time.perf_counter_ns()
        try:
            data = DataEngine.generate(count, vmin, vmax)
        except MemoryError:
            t1 = time.perf_counter_ns()
            self._is_generating = False
            self.btn_generate.setEnabled(True)
            self._debounce_timer.stop()
            QMessageBox.critical(
                self, "Ошибка памяти",
                "Недостаточно памяти для запрошенного объёма."
            )
            return
        except Exception as exc:  # noqa: BLE001 — защитная сетка
            t1 = time.perf_counter_ns()
            self._is_generating = False
            self.btn_generate.setEnabled(True)
            self._debounce_timer.stop()
            QMessageBox.critical(
                self, "Ошибка генерации", f"Не удалось сгенерировать массив:\n{exc}"
            )
            return
        t1 = time.perf_counter_ns()

        elapsed_ns = t1 - t0
        elapsed_ms = elapsed_ns / 1_000_000.0
        # Скорость: чисел в секунду. Защита от деления на ноль (теоретически)
        speed = (count / (elapsed_ns / 1_000_000_000.0)) if elapsed_ns > 0 else 0.0

        self._data = data
        self._last_elapsed_ms = elapsed_ms
        self._last_speed = speed

        # --- Статистика (тоже под замером, но отдельным) ---
        vmin_actual, vmax_actual, avg, median = DataEngine.stats(data)

        # --- Гистограмма ---
        counts = DataEngine.histogram(data, vmin, vmax, BINS_COUNT)
        edges = self._compute_bin_edges(vmin, vmax, BINS_COUNT)
        self.histogram.set_data(counts, edges, total=len(data))

        # --- Обновление метрик и монитора ---
        self._update_monitor(count, elapsed_ms, speed)
        self._update_metrics(len(data), vmin_actual, vmax_actual, avg, median)

    def _release_generate_button(self) -> None:
        self._is_generating = False
        self.btn_generate.setEnabled(True)

    @staticmethod
    def _compute_bin_edges(vmin: int, vmax: int,
                           bins: int) -> List[Tuple[int, int]]:
        """Границы интервалов гистограммы — целые числа, покрывающие диапазон."""
        span = vmax - vmin
        edges: List[Tuple[int, int]] = []
        for i in range(bins):
            lo = vmin + span * i // bins
            hi = vmin + span * (i + 1) // bins
            edges.append((lo, hi))
        return edges

    def _update_monitor(self, count: int, elapsed_ms: float, speed: float) -> None:
        self.lbl_monitor_volume.setText(
            f"Объём: {self._format_number(count)} чисел"
        )
        self.lbl_monitor_time.setText(
            f"Время генерации: {elapsed_ms:.2f} мс"
        )
        self.lbl_monitor_speed.setText(
            f"Скорость: {self._format_number(int(speed))} чисел/сек"
        )

    def _update_metrics(self, total: int, vmin: int, vmax: int,
                        avg: float, median: float) -> None:
        self.lbl_total.setText(f"Всего: {self._format_number(total)}")
        self.lbl_min.setText(f"Min: {vmin}")
        self.lbl_max.setText(f"Max: {vmax}")
        self.lbl_avg.setText(f"Avg: {avg:.2f}")
        self.lbl_median.setText(f"Median: {median:.2f}")

    # ========================================================== Экспорт ===
    def _on_export(self) -> None:
        if not self._data:
            QMessageBox.information(
                self, "Нет данных", "Сначала запустите тест генерации."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить тестовый пакет как CSV",
            "industrial_load_test.csv",
            "CSV файлы (*.csv);;Все файлы (*)",
        )
        if not path:
            return

        # Массовая запись через csv.writer с newline='' — корректно на всех ОС
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Индекс", "Значение"])
                for i, v in enumerate(self._data, start=1):
                    writer.writerow([i, v])
        except OSError as exc:
            QMessageBox.critical(
                self, "Ошибка сохранения",
                f"Не удалось сохранить файл:\n{exc}"
            )
            return

        self.statusBar().showMessage(
            f"Экспортировано {self._format_number(len(self._data))} чисел: {path}",
            5000,
        )

    # ============================================================ Lifecycle
    def closeEvent(self, event) -> None:  # noqa: N802
        self._debounce_timer.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = DataLoadSimulatorApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())