"""
Industrial Sensor Simulator — v1.2 (Final Polish)
=================================================
Промышленный симулятор телеметрии и имитатор датчиков.

Назначение: генерация, визуализация и логирование потока случайных чисел
в реальном времени. Соответствует ISO 9241 / ГОСТ Р ИСО 9241-110.

Изменения v1.2 (по результатам финального аудита эргономики):
  - Лента событий: ширина 300px, компактный формат, моноширинный шрифт.
  - Слайдеры Min/Max: жёсткая взаимная валидация — «упираются» друг в друга
    вместо автоматического подтягивания (предсказуемо для оператора).
  - Осциллограф: сетка приглушена, линия тренда — главный элемент.
  - Метаданные дисплея: контрастный тёмно-графитовый цвет #333333.

Стек: Python 3.10+, PySide6. Сторонние зависимости отсутствуют.
"""

from __future__ import annotations

import random
import sys
import time
from collections import deque
from typing import Deque, Optional

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Бизнес-параметры
# ---------------------------------------------------------------------------
DEFAULT_MIN = 0
DEFAULT_MAX = 100

INTERVAL_MIN_MS = 100
INTERVAL_MAX_MS = 2000
INTERVAL_DEFAULT_MS = 500

RANGE_SLIDER_MAX = 200

HISTORY_SIZE = 80
LOG_MAX_ITEMS = 20
CRITICAL_TOP_FRACTION = 0.10

# Профили генерации
PROFILE_UNIFORM = "uniform"
PROFILE_GAUSS = "gauss"
PROFILE_LABELS = {
    PROFILE_UNIFORM: "Равномерный (Хаос)",
    PROFILE_GAUSS: "Нормальный (Гаусс)",
}
# Короткие метки для компактной ленты событий
PROFILE_SHORT = {
    PROFILE_UNIFORM: "Хаос",
    PROFILE_GAUSS: "Гаусс",
}


# ---------------------------------------------------------------------------
# Промышленная палитра HMI
# ---------------------------------------------------------------------------
COLOR_BG = "#f4f5f7"
COLOR_TEXT = "#000000"
COLOR_TEXT_MUTED = "#4a5058"
COLOR_BORDER = "#959da5"
COLOR_BORDER_FOCUS = "#2b579a"
COLOR_BORDER_SUBTLE = "#c8ccd2"

COLOR_DISPLAY_NORMAL = "#0f1e33"
COLOR_DISPLAY_WARNING = "#b32424"
COLOR_DISPLAY_BG = "#ffffff"
COLOR_DISPLAY_META = "#333333"       # контрастные метаданные (было #4a5058)

COLOR_START = "#2f7d32"
COLOR_START_HOVER = "#256428"
COLOR_START_PRESSED = "#1c4d1f"

COLOR_PAUSE = "#b35a00"
COLOR_PAUSE_HOVER = "#8f4800"
COLOR_PAUSE_PRESSED = "#6d3600"

COLOR_STEP_BG = "#2b579a"
COLOR_STEP_HOVER = "#1e3f7a"
COLOR_STEP_PRESSED = "#15305e"
COLOR_ON_ACCENT = "#ffffff"

COLOR_GRAPH_BG = "#0f1e33"
COLOR_GRAPH_GRID = "#253a4e"          # приглушённая сетка (было #1f3352)
COLOR_GRAPH_LINE = "#4fc3f7"
COLOR_GRAPH_FILL = QColor(79, 195, 247, 45)


# ---------------------------------------------------------------------------
# Бизнес-логика: генератор значений по профилю
# ---------------------------------------------------------------------------
class ValueGenerator:
    """
    Генератор случайных чисел по заданному профилю распределения.
    Не зависит от UI — принимает параметры, возвращает число.
    """

    @staticmethod
    def uniform(vmin: int, vmax: int) -> int:
        """Равномерное распределение — стандартный хаос."""
        return random.randint(vmin, vmax)

    @staticmethod
    def gaussian(vmin: int, vmax: int) -> int:
        """
        Нормальное распределение с центром в середине диапазона и
        разбросом ~15% от диапазона. Значения обрезаются границами.

        Имитирует поведение реального физического датчика с шумом.
        """
        center = (vmin + vmax) / 2.0
        sigma = max((vmax - vmin) * 0.15, 1.0)

        # До 20 попыток — если диапазон очень узкий, возвращаем центр.
        for _ in range(20):
            value = random.gauss(center, sigma)
            if vmin <= value <= vmax:
                return int(round(value))
        return int(round(center))

    @classmethod
    def generate(cls, profile: str, vmin: int, vmax: int) -> int:
        if profile == PROFILE_GAUSS:
            return cls.gaussian(vmin, vmax)
        return cls.uniform(vmin, vmax)


# ---------------------------------------------------------------------------
# Кастомный виджет осциллографа (QPainter, без сторонних библиотек)
# ---------------------------------------------------------------------------
class OscilloscopeWidget(QWidget):
    """
    Мини-осциллограф: рисует историю значений плавной линией тренда
    (слева-направо, самое новое значение — у правого края).

    Оптимизирован под real-time: WA_OpaquePaintEvent, отсутствие лишних
    аллокаций в paintEvent. Сетка приглушена, чтобы не конкурировать
    с яркой линией тренда.
    """

    def __init__(self, history_size: int = HISTORY_SIZE, parent=None) -> None:
        super().__init__(parent)
        self._history: Deque[int] = deque(maxlen=history_size)
        self._vmin = DEFAULT_MIN
        self._vmax = DEFAULT_MAX

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(240)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_range(self, vmin: int, vmax: int) -> None:
        self._vmin = vmin
        self._vmax = vmax
        self.update()

    def push_value(self, value: int) -> None:
        self._history.append(value)
        self.update()

    def clear(self) -> None:
        self._history.clear()
        self.update()

    # ----------------------------------------------------- paint -----------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        # 1) Фон
        painter.fillRect(rect, QColor(COLOR_GRAPH_BG))

        # 2) Приглушённая сетка — тонкая (1px), тёмный полупрозрачный цвет.
        #    Главная цель: не конкурировать с яркой линией тренда.
        grid_pen = QPen(QColor(COLOR_GRAPH_GRID))
        grid_pen.setWidth(1)
        grid_pen.setStyle(Qt.SolidLine)
        painter.setPen(grid_pen)
        for i in range(1, 4):
            y = h * i / 4
            painter.drawLine(0, int(y), w, int(y))
        for i in range(1, 8):
            x = w * i / 8
            painter.drawLine(int(x), 0, int(x), h)

        # 3) Заглушка при отсутствии данных
        if len(self._history) < 2:
            painter.setPen(QColor("#5a6f8c"))
            f = painter.font()
            f.setPointSize(12)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignCenter, "Ожидание данных...")
            return

        # 4) Нормализация значений [vmin..vmax] → [h..0]
        vmin = self._vmin
        vmax = self._vmax
        span = max(vmax - vmin, 1)

        values = list(self._history)
        n = len(values)
        step_x = w / max(n - 1, 1)

        # 5) Линия тренда
        path = QPainterPath()
        first_x = 0.0
        for i, v in enumerate(values):
            x = i * step_x
            norm = max(0.0, min(1.0, (v - vmin) / span))
            y = h - norm * h
            point = QPointF(x, y)
            if i == 0:
                path.moveTo(point)
                first_x = x
            else:
                path.lineTo(point)

        # 6) Полупрозрачная заливка под линией
        fill_path = QPainterPath(path)
        fill_path.lineTo(w, h)
        fill_path.lineTo(first_x, h)
        fill_path.closeSubpath()
        painter.fillPath(fill_path, COLOR_GRAPH_FILL)

        # 7) Сама линия — главный акцентный элемент
        line_pen = QPen(QColor(COLOR_GRAPH_LINE))
        line_pen.setWidth(2)
        line_pen.setJoinStyle(Qt.RoundJoin)
        line_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(line_pen)
        painter.drawPath(path)

        # 8) Маркер текущего значения — точка у правого края
        last_v = values[-1]
        norm = max(0.0, min(1.0, (last_v - vmin) / span))
        last_y = h - norm * h
        painter.setBrush(QColor(COLOR_GRAPH_LINE))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(w - 3, last_y), 4, 4)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class SensorSimulatorApp(QMainWindow):
    """АРМ оператора имитатора датчика: управление, дисплей, график, лог."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Industrial Sensor Simulator v1.2")
        self.resize(1500, 840)

        # --- Состояние бизнес-логики ---
        self._profile: str = PROFILE_UNIFORM
        self._running: bool = False
        self._current_value: Optional[int] = None

        # --- Таймер генерации ---
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)
        self._timer.setInterval(INTERVAL_DEFAULT_MS)

        self._build_ui()
        self._apply_styles()
        self._sync_controls_from_state()
        self._update_range_labels()
        self._update_interval_label()

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
        panel.setFixedWidth(280)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_range_group())
        layout.addWidget(self._build_timer_group())
        layout.addWidget(self._build_profile_group())
        layout.addWidget(self._build_control_group())
        layout.addStretch(1)

        return panel

    def _build_range_group(self) -> QGroupBox:
        group = QGroupBox("Границы диапазона")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 14, 10, 10)

        # --- Min ---
        self.lbl_min_title = QLabel("Минимум:")
        self.lbl_min_value = QLabel(str(DEFAULT_MIN))
        self.lbl_min_value.setObjectName("valueBadge")
        self.lbl_min_value.setAlignment(Qt.AlignCenter)

        self.slider_min = QSlider(Qt.Horizontal)
        self.slider_min.setRange(0, RANGE_SLIDER_MAX)
        self.slider_min.setValue(DEFAULT_MIN)
        self.slider_min.setMinimumHeight(36)
        self.slider_min.valueChanged.connect(self._on_min_slider_changed)

        # --- Max ---
        self.lbl_max_title = QLabel("Максимум:")
        self.lbl_max_value = QLabel(str(DEFAULT_MAX))
        self.lbl_max_value.setObjectName("valueBadge")
        self.lbl_max_value.setAlignment(Qt.AlignCenter)

        self.slider_max = QSlider(Qt.Horizontal)
        self.slider_max.setRange(0, RANGE_SLIDER_MAX)
        self.slider_max.setValue(DEFAULT_MAX)
        self.slider_max.setMinimumHeight(36)
        self.slider_max.valueChanged.connect(self._on_max_slider_changed)

        layout.addWidget(self.lbl_min_title)
        layout.addWidget(self.lbl_min_value)
        layout.addWidget(self.slider_min)
        layout.addSpacing(4)
        layout.addWidget(self.lbl_max_title)
        layout.addWidget(self.lbl_max_value)
        layout.addWidget(self.slider_max)

        return group

    def _build_timer_group(self) -> QGroupBox:
        group = QGroupBox("Таймер и частота")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 14, 10, 10)

        self.lbl_interval_title = QLabel("Интервал генерации:")
        self.lbl_interval_value = QLabel(f"{INTERVAL_DEFAULT_MS} мс")
        self.lbl_interval_value.setObjectName("valueBadge")
        self.lbl_interval_value.setAlignment(Qt.AlignCenter)

        self.slider_interval = QSlider(Qt.Horizontal)
        self.slider_interval.setRange(INTERVAL_MIN_MS, INTERVAL_MAX_MS)
        self.slider_interval.setValue(INTERVAL_DEFAULT_MS)
        self.slider_interval.setSingleStep(50)
        self.slider_interval.setPageStep(100)
        self.slider_interval.setMinimumHeight(36)
        self.slider_interval.valueChanged.connect(self._on_interval_changed)

        layout.addWidget(self.lbl_interval_title)
        layout.addWidget(self.lbl_interval_value)
        layout.addWidget(self.slider_interval)

        return group

    def _build_profile_group(self) -> QGroupBox:
        group = QGroupBox("Профиль распределения")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 14, 10, 10)

        self.combo_profile = QComboBox()
        self.combo_profile.setMinimumHeight(44)
        self.combo_profile.addItem(PROFILE_LABELS[PROFILE_UNIFORM], PROFILE_UNIFORM)
        self.combo_profile.addItem(PROFILE_LABELS[PROFILE_GAUSS], PROFILE_GAUSS)
        self.combo_profile.currentIndexChanged.connect(self._on_profile_changed)

        layout.addWidget(self.combo_profile)
        return group

    def _build_control_group(self) -> QGroupBox:
        group = QGroupBox("Управление")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 14, 10, 10)

        self.btn_start = QPushButton("СТАРТ")
        self.btn_start.setObjectName("startButton")
        self.btn_start.setMinimumHeight(52)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self._on_start_pause)

        self.btn_step = QPushButton("РУЧНОЙ ШАГ")
        self.btn_step.setObjectName("stepButton")
        self.btn_step.setMinimumHeight(52)
        self.btn_step.setCursor(Qt.PointingHandCursor)
        self.btn_step.clicked.connect(self._on_manual_step)

        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_step)

        return group

    # ---- Центральная панель -------------------------------------------------
    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_display(), 0)
        layout.addWidget(self._build_oscilloscope(), 1)

        return panel

    def _build_display(self) -> QWidget:
        card = QFrame()
        card.setObjectName("displayCard")
        card.setFrameShape(QFrame.NoFrame)
        card.setMinimumHeight(160)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(4)

        title = QLabel("ТЕКУЩЕЕ ЗНАЧЕНИЕ ДАТЧИКА")
        title.setObjectName("displayTitle")
        title.setAlignment(Qt.AlignCenter)

        self.lbl_display = QLabel("— — —")
        self.lbl_display.setObjectName("displayValue")
        self.lbl_display.setAlignment(Qt.AlignCenter)

        self.lbl_display_meta = QLabel("Профиль: —   |   Диапазон: 0..100")
        self.lbl_display_meta.setObjectName("displayMeta")
        self.lbl_display_meta.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(self.lbl_display, 1)
        layout.addWidget(self.lbl_display_meta)

        self.display_card = card
        return card

    def _build_oscilloscope(self) -> QGroupBox:
        group = QGroupBox("Осциллограф (история последних значений)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)

        self.oscilloscope = OscilloscopeWidget(HISTORY_SIZE)
        self.oscilloscope.set_range(DEFAULT_MIN, DEFAULT_MAX)
        layout.addWidget(self.oscilloscope)

        return group

    # ---- Правая панель ------------------------------------------------------
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        # Ширина 300px — гарантирует размещение строк лога без гор. скролла
        panel.setFixedWidth(300)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Лента событий")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(10, 14, 10, 10)

        self.log_list = QListWidget()
        self.log_list.setObjectName("eventLog")
        self.log_list.setAlternatingRowColors(True)
        self.log_list.setSelectionMode(QListWidget.NoSelection)
        self.log_list.setFocusPolicy(Qt.NoFocus)
        # Отключаем горизонтальный скролл — строки гарантированно помещаются
        self.log_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_list.setTextElideMode(Qt.ElideRight)
        group_layout.addWidget(self.log_list)

        layout.addWidget(group)
        return panel

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
                width: 18px;
                margin: -8px 0;
                border-radius: 10px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #eef5ff;
            }}

            /* ================== QComboBox ================== */
            QComboBox {{
                background: #ffffff;
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 12pt;
                font-weight: 600;
                min-height: 26px;
            }}
            QComboBox:hover {{ border: 2px solid {COLOR_BORDER_FOCUS}; }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
            }}
            QComboBox QAbstractItemView {{
                background: #ffffff;
                color: {COLOR_TEXT};
                selection-background-color: {COLOR_BORDER_FOCUS};
                selection-color: #ffffff;
                font-size: 12pt;
                padding: 4px;
                border: 2px solid {COLOR_BORDER};
            }}

            /* ================== Кнопки ================== */
            QPushButton {{
                border-radius: 5px;
                padding: 10px 14px;
                font-size: 13pt;
                font-weight: bold;
            }}

            QPushButton#startButton[state="start"] {{
                background: {COLOR_START};
                color: {COLOR_ON_ACCENT};
                border: 2px solid {COLOR_START};
            }}
            QPushButton#startButton[state="start"]:hover {{
                background: {COLOR_START_HOVER};
                border: 2px solid {COLOR_START_HOVER};
            }}
            QPushButton#startButton[state="start"]:pressed {{
                background: {COLOR_START_PRESSED};
            }}

            QPushButton#startButton[state="pause"] {{
                background: {COLOR_PAUSE};
                color: {COLOR_ON_ACCENT};
                border: 2px solid {COLOR_PAUSE};
            }}
            QPushButton#startButton[state="pause"]:hover {{
                background: {COLOR_PAUSE_HOVER};
                border: 2px solid {COLOR_PAUSE_HOVER};
            }}
            QPushButton#startButton[state="pause"]:pressed {{
                background: {COLOR_PAUSE_PRESSED};
            }}

            QPushButton#stepButton {{
                background: {COLOR_STEP_BG};
                color: {COLOR_ON_ACCENT};
                border: 2px solid {COLOR_STEP_BG};
            }}
            QPushButton#stepButton:hover {{
                background: {COLOR_STEP_HOVER};
                border: 2px solid {COLOR_STEP_HOVER};
            }}
            QPushButton#stepButton:pressed {{
                background: {COLOR_STEP_PRESSED};
            }}
            QPushButton#stepButton:disabled {{
                background: #d5d9de;
                color: #8a919b;
                border: 2px solid #b6bcc4;
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
                min-height: 28px;
            }}

            /* ================== Центральный дисплей ================== */
            QFrame#displayCard {{
                background: {COLOR_DISPLAY_BG};
                border: 2px solid {COLOR_BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QLabel#displayTitle {{
                font-size: 11pt;
                font-weight: bold;
                color: {COLOR_TEXT_MUTED};
                letter-spacing: 2px;
            }}
            QLabel#displayValue {{
                font-size: 72pt;
                font-weight: 900;
                color: {COLOR_DISPLAY_NORMAL};
                padding: 4px 0;
            }}
            QLabel#displayValue[level="warning"] {{
                color: {COLOR_DISPLAY_WARNING};
            }}
            QLabel#displayMeta {{
                font-size: 11pt;
                font-weight: 600;
                color: {COLOR_DISPLAY_META};
            }}

            /* ================== Лента событий ================== */
            QListWidget#eventLog {{
                background: #ffffff;
                alternate-background-color: #f2f4f6;
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 6px;
                color: {COLOR_TEXT};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                padding: 4px;
            }}
            QListWidget#eventLog::item {{
                padding: 4px 6px;
                border-bottom: 1px solid #eceef1;
            }}
            """
        )
        self.btn_start.setProperty("state", "start")

    # ==================================================== Синхронизация UI
    def _sync_controls_from_state(self) -> None:
        """Актуализирует тексты, доступность и свойства элементов под режим."""
        if self._running:
            self.btn_start.setText("ПАУЗА")
            self.btn_start.setProperty("state", "pause")
            self.btn_step.setEnabled(False)
        else:
            self.btn_start.setText("СТАРТ")
            self.btn_start.setProperty("state", "start")
            self.btn_step.setEnabled(True)

        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)

    def _update_range_labels(self) -> None:
        self.lbl_min_value.setText(str(self.slider_min.value()))
        self.lbl_max_value.setText(str(self.slider_max.value()))
        self.lbl_display_meta.setText(
            f"Профиль: {PROFILE_LABELS[self._profile]}   |   "
            f"Диапазон: {self.slider_min.value()}..{self.slider_max.value()}"
        )

    def _update_interval_label(self) -> None:
        self.lbl_interval_value.setText(f"{self.slider_interval.value()} мс")

    # =========================================================== Обработчики
    def _on_min_slider_changed(self, value: int) -> None:
        """
        Взаимная валидация Min ↔ Max: Min «упирается» в Max.
        Оператор не может двигать Min выше Max — слайдер останавливается
        на (Max - 1). Это предсказуемое и безопасное поведение по ГОСТ.

        Особенность: QSlider не умеет сам ограничивать значение ниже
        собственного максимума, поэтому мы принудительно возвращаем
        значение обратно и блокируем повторный сигнал.
        """
        max_val = self.slider_max.value()
        if value >= max_val:
            # Возвращаем Min на границу (Max - 1), не трогая Max
            self.slider_min.blockSignals(True)
            self.slider_min.setValue(max(max_val - 1, self.slider_min.minimum()))
            self.slider_min.blockSignals(False)

        self._update_range_labels()
        self.oscilloscope.set_range(
            self.slider_min.value(), self.slider_max.value()
        )

    def _on_max_slider_changed(self, value: int) -> None:
        """
        Взаимная валидация Max ↔ Min: Max «упирается» в Min.
        Оператор не может двигать Max ниже Min — слайдер останавливается
        на (Min + 1).
        """
        min_val = self.slider_min.value()
        if value <= min_val:
            self.slider_max.blockSignals(True)
            self.slider_max.setValue(min(min_val + 1, self.slider_max.maximum()))
            self.slider_max.blockSignals(False)

        self._update_range_labels()
        self.oscilloscope.set_range(
            self.slider_min.value(), self.slider_max.value()
        )

    def _on_interval_changed(self, value: int) -> None:
        self._update_interval_label()
        if self._running:
            self._timer.setInterval(value)

    def _on_profile_changed(self) -> None:
        self._profile = self.combo_profile.currentData()
        self._update_range_labels()

    def _on_start_pause(self) -> None:
        if self._running:
            self._pause()
        else:
            self._start()

    def _start(self) -> None:
        self._running = True
        self._timer.setInterval(self.slider_interval.value())
        self._timer.start()
        self._sync_controls_from_state()

    def _pause(self) -> None:
        self._running = False
        self._timer.stop()
        self._sync_controls_from_state()

    def _on_manual_step(self) -> None:
        """Ручной шаг доступен только на паузе (кнопка disabled иначе)."""
        if self._running:
            return
        self._generate_once()

    def _on_tick(self) -> None:
        """Обработчик QTimer — генерация нового значения в реальном времени."""
        self._generate_once()

    # ================================================== Генерация значения ==
    def _generate_once(self) -> None:
        vmin = self.slider_min.value()
        vmax = self.slider_max.value()

        # Страховка от рассинхрона (взаимная валидация слайдеров не даёт
        # этому случиться, но подстраховываемся на уровне бизнес-логики)
        if vmin >= vmax:
            vmin = max(vmax - 1, self.slider_min.minimum())

        try:
            value = ValueGenerator.generate(self._profile, vmin, vmax)
        except Exception as exc:  # noqa: BLE001 — защитная сетка для продуктива
            self._append_error_log(f"Ошибка генерации: {exc}")
            return

        self._current_value = value
        now = time.time()

        self._update_display(value, vmin, vmax)
        self.oscilloscope.push_value(value)
        self._append_value_log(now, value)

    def _update_display(self, value: int, vmin: int, vmax: int) -> None:
        """Обновляет главный дисплей; подсвечивает критическую зону."""
        span = max(vmax - vmin, 1)
        threshold = vmax - span * CRITICAL_TOP_FRACTION

        self.lbl_display.setText(str(value))

        is_warning = value >= threshold
        self.lbl_display.setProperty(
            "level", "warning" if is_warning else "normal"
        )
        self.lbl_display.style().unpolish(self.lbl_display)
        self.lbl_display.style().polish(self.lbl_display)

    # ============================================================ Лента ===
    @staticmethod
    def _format_timestamp(ts: float) -> str:
        """
        Единая точка форматирования времени для ленты событий.
        Возвращает строку 'ЧЧ:ММ:СС.ммм' в локальном времени.
        """
        tm = time.localtime(ts)
        ms = int((ts - int(ts)) * 1000)
        return time.strftime("%H:%M:%S", tm) + f".{ms:03d}"

    def _prepend_log_item(self, text: str, is_error: bool) -> None:
        """
        Единая точка добавления записи в ленту.
        Новые записи идут сверху, длина ограничена LOG_MAX_ITEMS.
        """
        item = QListWidgetItem(text)
        item.setForeground(
            QColor(COLOR_DISPLAY_WARNING if is_error else COLOR_TEXT)
        )
        self.log_list.insertItem(0, item)

        while self.log_list.count() > LOG_MAX_ITEMS:
            self.log_list.takeItem(self.log_list.count() - 1)

    def _append_value_log(self, ts: float, value: int) -> None:
        """
        Компактный индустриальный формат лога:
            [ЧЧ:ММ:СС.ммм]  VAL: X  |  Профиль

        Фиксированная ширина поля значения (VAL: %-4d) выравнивает
        колонки цифр по моноширинному шрифту — удобно сканировать глазами.
        """
        stamp = self._format_timestamp(ts)
        profile_short = PROFILE_SHORT[self._profile]
        text = f"[{stamp}]  VAL: {value:<4d} |  {profile_short}"
        self._prepend_log_item(text, is_error=False)

    def _append_error_log(self, message: str) -> None:
        """Запись ошибки генерации — выделяется предупреждающим цветом."""
        self._prepend_log_item(f"[!] {message}", is_error=True)

    # ============================================================ Lifecycle
    def closeEvent(self, event) -> None:  # noqa: N802
        """Корректно останавливаем таймер при закрытии окна."""
        self._timer.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = SensorSimulatorApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())