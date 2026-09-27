from __future__ import annotations

import math
import os
import sys
import time
from typing import Optional

from PySide6.QtCore import (
    Qt, QTimer, QPointF, QRectF, QEasingCurve,
    QPropertyAnimation, Property, Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QDial,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Параметры
# ---------------------------------------------------------------------------
DIAL_MIN = 0
DIAL_MAX = 100
DIAL_DEFAULT = 0

# Границы хода метки по белому полю (доли от размера картинки)
PIXELS_PAD_LEFT = 0.135
PIXELS_PAD_RIGHT = 0.13
PIXELS_PAD_TOP = 0.4
PIXELS_PAD_BOTTOM = 0.575

ANIM_DURATION_MS = 400
NUDGE_STEP = 3

SCALE_IMAGE_NAME = "iskra.jpg"


# ---------------------------------------------------------------------------
# Палитра "Bakelite"
# ---------------------------------------------------------------------------
COLOR_BG_OUTER = "#1a1008"
COLOR_CASE = "#2b1d0e"
COLOR_PANEL = "#e8dcc4"
COLOR_PANEL_DARK = "#d4c4a3"
COLOR_PANEL_LIGHT = "#f5ecd8"
COLOR_BRASS = "#c9a961"
COLOR_BRASS_DARK = "#8b7340"
COLOR_BRASS_LIGHT = "#e0c98a"
COLOR_SCALE_BG = "#0f0e0a"
COLOR_NEEDLE = "#dc2626"
COLOR_NEEDLE_GLOW = "#fca5a5"
COLOR_TEXT_DARK = "#2b1d0e"
COLOR_STATUS_BG = "#181008"


# ---------------------------------------------------------------------------
# Поиск картинки
# ---------------------------------------------------------------------------
def find_scale_image() -> Optional[str]:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.getcwd())
    for folder in candidates:
        path = os.path.join(folder, SCALE_IMAGE_NAME)
        if os.path.isfile(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Кастомная ручка-крутилка
# ---------------------------------------------------------------------------
class VintageKnobDial(QDial):
    """Круглая латунная ручка с рифлением и красной меткой."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRange(DIAL_MIN, DIAL_MAX)
        self.setValue(DIAL_DEFAULT)
        self.setNotchesVisible(False)
        self.setWrapping(False)
        self.setSingleStep(1)
        self.setPageStep(5)
        self.setMinimumSize(180, 180)
        self.setMaximumSize(220, 220)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        size = min(w, h)
        cx = w / 2.0
        cy = h / 2.0
        radius = size / 2.0 - 6

        # 1) Тёмная утопленная база
        base_grad = QRadialGradient(cx, cy, radius + 6)
        base_grad.setColorAt(0.0, QColor("#2a1d0e"))
        base_grad.setColorAt(1.0, QColor("#150d05"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(base_grad)
        painter.drawEllipse(QPointF(cx, cy), radius + 4, radius + 4)

        # 2) Латунное кольцо
        ring_grad = QLinearGradient(cx - radius, cy - radius,
                                     cx + radius, cy + radius)
        ring_grad.setColorAt(0.0, QColor(COLOR_BRASS_DARK))
        ring_grad.setColorAt(0.5, QColor(COLOR_BRASS_LIGHT))
        ring_grad.setColorAt(1.0, QColor(COLOR_BRASS_DARK))
        painter.setBrush(ring_grad)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 3) Внутренняя часть ручки
        inner_r = radius - 8
        knob_grad = QRadialGradient(cx - inner_r * 0.4, cy - inner_r * 0.4,
                                     inner_r * 1.5)
        knob_grad.setColorAt(0.0, QColor("#3a2814"))
        knob_grad.setColorAt(0.5, QColor("#1f1408"))
        knob_grad.setColorAt(1.0, QColor("#0d0803"))
        painter.setBrush(knob_grad)
        painter.setPen(QPen(QColor(COLOR_BRASS_DARK), 2))
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # 4) Рифление
        pen = QPen(QColor(COLOR_BRASS_LIGHT))
        pen.setWidth(2)
        painter.setPen(pen)
        n_notches = 30
        for i in range(n_notches):
            angle = (i / n_notches) * 2 * math.pi - math.pi / 2
            r1 = inner_r - 2
            r2 = inner_r - 12
            x1 = cx + r1 * math.cos(angle)
            y1 = cy + r1 * math.sin(angle)
            x2 = cx + r2 * math.cos(angle)
            y2 = cy + r2 * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 5) Красная метка-указатель
        value_t = (self.value() - self.minimum()) / max(
            self.maximum() - self.minimum(), 1
        )
        angle_deg = -135 + value_t * 270
        angle_rad = math.radians(angle_deg - 90)

        tip_x = cx + (inner_r - 4) * math.cos(angle_rad)
        tip_y = cy + (inner_r - 4) * math.sin(angle_rad)

        pen = QPen(QColor(COLOR_NEEDLE))
        pen.setWidth(5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        mark_inner_r = inner_r * 0.35
        x_in = cx + mark_inner_r * math.cos(angle_rad)
        y_in = cy + mark_inner_r * math.sin(angle_rad)
        painter.drawLine(QPointF(x_in, y_in), QPointF(tip_x, tip_y))

        # Свечение у острия
        glow = QColor(COLOR_NEEDLE_GLOW)
        glow.setAlpha(120)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(tip_x, tip_y), 6, 6)
        painter.setBrush(QColor(COLOR_NEEDLE))
        painter.drawEllipse(QPointF(tip_x, tip_y), 3, 3)

        # 6) Центральный латунный болт
        painter.setBrush(QColor(COLOR_BRASS))
        painter.setPen(QPen(QColor(COLOR_BRASS_DARK), 1))
        painter.drawEllipse(QPointF(cx, cy), 10, 10)
        painter.setBrush(QColor(COLOR_BRASS_LIGHT))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx - 2, cy - 2), 3, 3)

        # 7) Точечные деления
        painter.setPen(Qt.NoPen)
        n_dots = 11
        for i in range(n_dots):
            a = -135 + (i / (n_dots - 1)) * 270
            ar = math.radians(a - 90)
            dx = cx + (radius + 2) * math.cos(ar)
            dy = cy + (radius + 2) * math.sin(ar)
            if 0 <= dx <= w and 0 <= dy <= h:
                active = (i / (n_dots - 1)) <= value_t
                painter.setBrush(QColor(COLOR_BRASS_LIGHT) if active
                                 else QColor("#5a4a2a"))
                painter.drawEllipse(QPointF(dx, dy), 3, 3)


# ---------------------------------------------------------------------------
# Шкала с меткой
# ---------------------------------------------------------------------------
class VintageScaleWidget(QWidget):
    """Картинка «Искра» + одна метка, ходящая по белому полю."""

    needle_moved = Signal(int)

    def __init__(self, image_path: Optional[str], parent=None) -> None:
        super().__init__(parent)

        self._needle_value = DIAL_DEFAULT
        self._target_value = self._needle_value

        self._pixmap: Optional[QPixmap] = None
        if image_path:
            pm = QPixmap(image_path)
            if not pm.isNull():
                self._pixmap = pm

        self._anim = QPropertyAnimation(self, b"needle_value")
        self._anim.setDuration(ANIM_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._image_rect = QRectF()

        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    # ---- property
    def get_needle_value(self) -> int:
        return self._needle_value

    def set_needle_value(self, value: int) -> None:
        self._needle_value = max(DIAL_MIN, min(DIAL_MAX, int(value)))
        self.needle_moved.emit(self._needle_value)
        self.update()

    needle_value = Property(int, get_needle_value, set_needle_value)

    # ---- API
    def animate_to(self, value: int, duration_ms: int = ANIM_DURATION_MS) -> None:
        self._target_value = max(DIAL_MIN, min(DIAL_MAX, int(value)))
        self._anim.stop()
        self._anim.setDuration(duration_ms)
        self._anim.setStartValue(self._needle_value)
        self._anim.setEndValue(self._target_value)
        self._anim.start()

    def set_needle_immediately(self, value: int) -> None:
        self._anim.stop()
        self._needle_value = max(DIAL_MIN, min(DIAL_MAX, int(value)))
        self._target_value = self._needle_value
        self.needle_moved.emit(self._needle_value)
        self.update()

    def stop_animation(self) -> None:
        self._anim.stop()

    # ---- геометрия
    def _recompute_image_rect(self) -> None:
        if self._pixmap is None:
            self._image_rect = QRectF()
            return
        w = self.width()
        h = self.height()
        pw = self._pixmap.width()
        ph = self._pixmap.height()
        scale = min(w / pw, h / ph)
        draw_w = pw * scale
        draw_h = ph * scale
        x = (w - draw_w) / 2
        y = (h - draw_h) / 2
        self._image_rect = QRectF(x, y, draw_w, draw_h)

    def _working_x_range(self) -> tuple[float, float]:
        if self._image_rect.isEmpty():
            return 0.0, 0.0
        x_left = self._image_rect.left() + self._image_rect.width() * PIXELS_PAD_LEFT
        x_right = self._image_rect.right() - self._image_rect.width() * PIXELS_PAD_RIGHT
        return x_left, x_right

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recompute_image_rect()

    # ---- мышь
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        x_left, x_right = self._working_x_range()
        if x_right <= x_left:
            return
        x = event.position().x()
        t = (x - x_left) / (x_right - x_left)
        t = max(0.0, min(1.0, t))
        target = int(round(DIAL_MIN + t * (DIAL_MAX - DIAL_MIN)))
        self.animate_to(target, 400)

    # ------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w = self.width()
        h = self.height()

        self._draw_panel(painter, w, h)
        self._draw_frame(painter, w, h)

        if self._pixmap is not None:
            self._recompute_image_rect()
            painter.drawPixmap(self._image_rect, self._pixmap,
                               QRectF(self._pixmap.rect()))
            self._draw_needle(painter)
        else:
            self._draw_missing_image_hint(painter)

    def _draw_panel(self, painter: QPainter, w: int, h: int) -> None:
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(COLOR_PANEL_LIGHT))
        grad.setColorAt(0.5, QColor(COLOR_PANEL))
        grad.setColorAt(1.0, QColor(COLOR_PANEL_DARK))
        painter.fillRect(self.rect(), grad)

    def _draw_frame(self, painter: QPainter, w: int, h: int) -> None:
        pen = QPen(QColor(COLOR_BRASS_DARK))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(1, 1, w - 2, h - 2)

        pen = QPen(QColor(COLOR_BRASS_LIGHT))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(3, 3, w - 6, h - 6)

    def _draw_needle(self, painter: QPainter) -> None:
        if self._image_rect.isEmpty():
            return

        x_left, x_right = self._working_x_range()
        if x_right <= x_left:
            return

        t = (self._needle_value - DIAL_MIN) / (DIAL_MAX - DIAL_MIN)
        t = max(0.0, min(1.0, t))
        x = x_left + t * (x_right - x_left)

        y_top = self._image_rect.top() + self._image_rect.height() * PIXELS_PAD_TOP
        y_bot = self._image_rect.top() + self._image_rect.height() * PIXELS_PAD_BOTTOM

        # Свечение
        glow = QColor(COLOR_NEEDLE_GLOW)
        glow.setAlpha(110)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(
            QRectF(x - 6, y_top - 3, 12, (y_bot - y_top) + 6), 3, 3,
        )

        # Красная метка
        pen = QPen(QColor(COLOR_NEEDLE))
        pen.setWidth(3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, y_top), QPointF(x, y_bot))

        # Латунные точки
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_BRASS))
        r = 3
        painter.drawEllipse(QPointF(x, y_top), r, r)
        painter.drawEllipse(QPointF(x, y_bot), r, r)

    def _draw_missing_image_hint(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(COLOR_SCALE_BG))
        f = painter.font()
        f.setFamily("Consolas")
        f.setPointSize(12)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor("#ef4444"))
        painter.drawText(
            self.rect(), Qt.AlignCenter,
            f"⚠ Файл «{SCALE_IMAGE_NAME}» не найден.\n\n"
            f"Положите картинку рядом с main.py",
        )


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class RadioTunerApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Радиоприёмник «Искра» — Симулятор настройки")
        self.resize(1360, 720)
        self.setMinimumSize(1100, 640)

        self._image_path = find_scale_image()
        self._image_found = self._image_path is not None

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(40)
        self._auto_timer.timeout.connect(self._on_auto_tick)
        self._auto_direction = 1

        self._build_ui()
        self._apply_styles()
        self._bind_shortcuts()

        self._dial.valueChanged.connect(self._on_dial_changed)
        self._scale.needle_moved.connect(self._on_needle_changed)

        self._dial.setValue(DIAL_DEFAULT)
        self._scale.set_needle_immediately(DIAL_DEFAULT)

        if not self._image_found:
            QTimer.singleShot(200, self._warn_missing_image)
        else:
            self._log(f"Картинка загружена: {self._image_path}")

    # ==================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("case")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        root.addWidget(self._build_branding())

        # Центральная зона
        middle = QHBoxLayout()
        middle.setSpacing(16)

        # Ручка
        knob_panel = QFrame()
        knob_panel.setObjectName("knobPanel")
        knob_panel.setFixedWidth(260)

        knob_layout = QVBoxLayout(knob_panel)
        knob_layout.setContentsMargins(20, 20, 20, 20)
        knob_layout.setSpacing(10)

        knob_label = QLabel("НАСТРОЙКА")
        knob_label.setObjectName("controlLabel")
        knob_label.setAlignment(Qt.AlignCenter)

        self._dial = VintageKnobDial()
        knob_layout.addWidget(knob_label)
        knob_layout.addStretch(1)
        knob_layout.addWidget(self._dial, 0, Qt.AlignHCenter)
        knob_layout.addStretch(1)

        # Шкала
        self._scale = VintageScaleWidget(self._image_path)

        middle.addWidget(knob_panel, 0)
        middle.addWidget(self._scale, 1)

        root.addLayout(middle, 1)

        # Нижняя панель — управление
        root.addWidget(self._build_controls())

        # Статус-бар
        self.status = QFrame()
        self.status.setObjectName("statusBar")
        self.status.setFixedHeight(32)

        status_layout = QHBoxLayout(self.status)
        status_layout.setContentsMargins(16, 0, 16, 0)

        self.lbl_status = QLabel("Готово")
        self.lbl_status.setObjectName("statusText")

        self.lbl_hint = QLabel(
            "Крутите ручку мышью · ← / → — точная настройка"
        )
        self.lbl_hint.setObjectName("shortcutHint")

        status_layout.addWidget(self.lbl_status, 1)
        status_layout.addWidget(self.lbl_hint, 0)

        root.addWidget(self.status)

    def _build_branding(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("brandPanel")
        panel.setFixedHeight(72)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(24, 8, 24, 8)

        screw_l = QLabel("●")
        screw_l.setObjectName("screw")

        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)

        brand = QLabel("«ИСКРА»")
        brand.setObjectName("brandTitle")

        subtitle = QLabel("ВИНТАЖНЫЙ СИМУЛЯТОР НАСТРОЙКИ РАДИОПРИЁМНИКА")
        subtitle.setObjectName("brandSubtitle")

        brand_box.addWidget(brand)
        brand_box.addWidget(subtitle)

        screw_r = QLabel("●")
        screw_r.setObjectName("screw")

        layout.addWidget(screw_l)
        layout.addSpacing(12)
        layout.addLayout(brand_box)
        layout.addStretch(1)
        layout.addWidget(screw_r)

        return panel

    def _build_controls(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("controlPanel")

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(18)

        # Кнопки навигации
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self.btn_left = QPushButton("◀")
        self.btn_left.setObjectName("navButton")
        self.btn_left.setMinimumHeight(52)
        self.btn_left.setMinimumWidth(70)
        self.btn_left.setCursor(Qt.PointingHandCursor)
        self.btn_left.clicked.connect(lambda: self._nudge(-NUDGE_STEP))

        self.btn_auto = QPushButton("ДВИЖЕНИЕ")
        self.btn_auto.setObjectName("navButton")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setMinimumHeight(52)
        self.btn_auto.setMinimumWidth(180)
        self.btn_auto.setCursor(Qt.PointingHandCursor)
        self.btn_auto.clicked.connect(self._on_auto_toggle)

        self.btn_right = QPushButton("▶")
        self.btn_right.setObjectName("navButton")
        self.btn_right.setMinimumHeight(52)
        self.btn_right.setMinimumWidth(70)
        self.btn_right.setCursor(Qt.PointingHandCursor)
        self.btn_right.clicked.connect(lambda: self._nudge(NUDGE_STEP))

        nav_row.addStretch(1)
        nav_row.addWidget(self.btn_left)
        nav_row.addWidget(self.btn_auto)
        nav_row.addWidget(self.btn_right)
        nav_row.addStretch(1)

        layout.addLayout(nav_row)
        return panel

    # ---- обработчики
    def _on_dial_changed(self, value: int) -> None:
        if self._scale._needle_value != value:
            self._scale.set_needle_immediately(value)

    def _on_needle_changed(self, value: int) -> None:
        if self._dial.value() != value:
            self._dial.blockSignals(True)
            self._dial.setValue(value)
            self._dial.blockSignals(False)

    def _nudge(self, delta: int) -> None:
        new_value = self._dial.value() + delta
        new_value = max(DIAL_MIN, min(DIAL_MAX, new_value))
        self._scale.animate_to(new_value, 200)

    def _on_auto_toggle(self) -> None:
        if self.btn_auto.isChecked():
            self._auto_direction = 1
            self._auto_timer.start()
            self._log("Автопрокрутка включена.")
        else:
            self._auto_timer.stop()
            self._log("Автопрокрутка выключена.")

    def _on_auto_tick(self) -> None:
        new_value = self._dial.value() + self._auto_direction
        if new_value >= DIAL_MAX:
            new_value = DIAL_MAX
            self._auto_direction = -1
        elif new_value <= DIAL_MIN:
            new_value = DIAL_MIN
            self._auto_direction = 1

        self._dial.blockSignals(True)
        self._dial.setValue(new_value)
        self._dial.blockSignals(False)

        self._scale.set_needle_immediately(new_value)

    def _warn_missing_image(self) -> None:
        QMessageBox.warning(
            self, "Картинка не найдена",
            f"Файл «{SCALE_IMAGE_NAME}» не найден в папке с main.py.\n\n"
            f"Положите PNG-картинку рядом с программой и перезапустите.",
        )

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key_Left), self,
                  activated=lambda: self._nudge(-NUDGE_STEP))
        QShortcut(QKeySequence(Qt.Key_Right), self,
                  activated=lambda: self._nudge(NUDGE_STEP))
        QShortcut(QKeySequence(Qt.Key_Space), self,
                  activated=self._toggle_auto)
        QShortcut(QKeySequence(Qt.Key_Home), self,
                  activated=lambda: self._scale.animate_to(DIAL_MIN, 400))
        QShortcut(QKeySequence(Qt.Key_End), self,
                  activated=lambda: self._scale.animate_to(DIAL_MAX, 400))

    def _toggle_auto(self) -> None:
        self.btn_auto.setChecked(not self.btn_auto.isChecked())
        self._on_auto_toggle()

    # ================================================================ Стили
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow {{ background: {COLOR_BG_OUTER}; }}
            QWidget#case {{ background: {COLOR_CASE}; }}

            QFrame#brandPanel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {COLOR_PANEL_LIGHT},
                    stop:0.5 {COLOR_PANEL},
                    stop:1 {COLOR_PANEL_DARK});
                border: 2px solid {COLOR_BRASS_DARK};
                border-radius: 8px;
            }}
            QLabel#brandTitle {{
                font-family: Georgia, serif;
                font-size: 20pt;
                font-weight: 900;
                font-style: italic;
                color: {COLOR_TEXT_DARK};
                letter-spacing: 6px;
            }}
            QLabel#brandSubtitle {{
                font-family: Georgia, serif;
                font-size: 8pt;
                font-weight: bold;
                color: {COLOR_BRASS_DARK};
                letter-spacing: 4px;
            }}
            QLabel#screw {{
                font-size: 14pt;
                color: {COLOR_BRASS_DARK};
            }}

            QFrame#knobPanel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {COLOR_PANEL_LIGHT},
                    stop:0.5 {COLOR_PANEL},
                    stop:1 {COLOR_PANEL_DARK});
                border: 2px solid {COLOR_BRASS_DARK};
                border-radius: 8px;
            }}

            QFrame#controlPanel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {COLOR_PANEL_LIGHT},
                    stop:0.5 {COLOR_PANEL},
                    stop:1 {COLOR_PANEL_DARK});
                border: 2px solid {COLOR_BRASS_DARK};
                border-radius: 8px;
            }}
            QLabel#controlLabel {{
                font-family: Georgia, serif;
                font-size: 9pt;
                font-weight: bold;
                color: {COLOR_BRASS_DARK};
                letter-spacing: 2px;
            }}

            QPushButton#navButton {{
                font-family: Georgia, serif;
                font-size: 13pt;
                font-weight: 900;
                color: {COLOR_TEXT_DARK};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {COLOR_PANEL_LIGHT},
                    stop:1 {COLOR_PANEL_DARK});
                border: 2px solid {COLOR_BRASS_DARK};
                border-radius: 6px;
                letter-spacing: 2px;
                padding: 4px 10px;
            }}
            QPushButton#navButton:hover {{
                border: 2px solid {COLOR_BRASS};
                color: {COLOR_BRASS_DARK};
            }}
            QPushButton#navButton:pressed {{
                background: {COLOR_PANEL_DARK};
            }}
            QPushButton#navButton:checked {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #d97706,
                    stop:1 #92400e);
                color: {COLOR_PANEL_LIGHT};
                border: 2px solid {COLOR_BRASS};
            }}

            QFrame#statusBar {{
                background: {COLOR_STATUS_BG};
                border-top: 2px solid {COLOR_BRASS_DARK};
            }}
            QLabel#statusText {{
                font-family: Consolas, 'Courier New', monospace;
                font-size: 10pt;
                font-weight: bold;
                color: {COLOR_BRASS_LIGHT};
            }}
            QLabel#shortcutHint {{
                font-size: 9pt;
                color: #8a7a5a;
                letter-spacing: 1px;
            }}
            """
        )

    def _log(self, message: str) -> None:
        self.lbl_status.setText(message)
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] {message}")

    def closeEvent(self, event) -> None:
        self._auto_timer.stop()
        self._scale.stop_animation()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
def main() -> int:
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(msg, file=sys.stderr)

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setFont(QFont("Georgia", 10))
    window = RadioTunerApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())