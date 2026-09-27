from __future__ import annotations

import math
import sys
import time
from enum import Enum
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Параметры
# ---------------------------------------------------------------------------
APP_TITLE = "ГАЛЕРЕЯ ПРОМЫШЛЕННЫХ КНОПОК"
APP_VERSION = "v 1.6"

SP_4 = 4
SP_8 = 8
SP_10 = 10
SP_12 = 12
SP_16 = 16
SP_20 = 20
SP_24 = 24

RADIUS = 2
LOG_MAX_ITEMS = 500
DUPLICATE_WINDOW_MS = 500
ACTIVE_HIGHLIGHT_MS = 1000
HOLD_DURATION_MS = 1000
BLINK_PERIOD_MS = 500

BUTTON_MIN_W = 140
BUTTON_MIN_H = 140
BUTTON_MAX_H = 160
ESTOP_SIZE = 180

# Высота панели = header(36) + divider(1..2) + content margins (16+16) + высота кнопки
PANEL_HEADER_H = 36
PANEL_CONTENT_MARGIN = SP_16


# ---------------------------------------------------------------------------
# Палитра ISA-101
# ---------------------------------------------------------------------------
COLOR_BG = "#2b2b2b"
COLOR_CARD = "#333333"
COLOR_ELEMENT = "#3a3a3a"

COLOR_BTN_BG = "#4a4a4a"
COLOR_BTN_BG_HOVER = "#5a5a5a"
COLOR_BTN_BORDER = "#707070"
COLOR_BTN_ICON = "#e0e0e0"
COLOR_BTN_ICON_HOVER = "#ffffff"

COLOR_BTN_DISABLED_BG = "#3a3a3a"
COLOR_BTN_DISABLED_BORDER = "#4a4a4a"
COLOR_BTN_DISABLED_ICON = "#6a6a6a"

COLOR_BORDER = "#5a5a5a"
COLOR_DIVIDER = "#454545"

COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_MUTED = "#a0a0a0"
COLOR_TEXT_DIM = "#707070"

COLOR_ACCENT_START = "#22c55e"
COLOR_ACCENT_STOP = "#dc2626"
COLOR_ACCENT_ALARM = "#f59e0b"
COLOR_ACCENT_SERVICE = "#3b82f6"

# E-STOP всегда красный
COLOR_ESTOP_BG = "#c1170e"
COLOR_ESTOP_BG_HOVER = "#dc2626"
COLOR_ESTOP_BG_PRESSED = "#991b1b"
COLOR_ESTOP_BORDER = "#7f1d1d"
COLOR_ESTOP_ICON = "#ffffff"

COLOR_LOG_INFO = "#e0e0e0"
COLOR_LOG_WARNING = "#f59e0b"
COLOR_LOG_ERROR = "#ef4444"
COLOR_LOG_CRITICAL = "#ff3b3b"

COLOR_STATUS_READY = "#22c55e"
COLOR_STATUS_RUN = "#22c55e"
COLOR_STATUS_PAUSE = "#f59e0b"
COLOR_STATUS_ALARM = "#dc2626"
COLOR_STATUS_STOP = "#a0a0a0"

COLOR_ESTOP_ZONE_BG = "#3a1a1a"
COLOR_ESTOP_ZONE_BORDER = "#dc2626"

COLOR_STATUS_BG = "#1a1a1a"


# ---------------------------------------------------------------------------
# Перечисления
# ---------------------------------------------------------------------------
class ButtonShape(Enum):
    CIRCLE = "circle"
    TRIANGLE = "triangle"
    WARNING_TRIANGLE = "warning_triangle"
    HEXAGON = "hexagon"
    OCTAGON = "octagon"
    OVAL_PAIR = "oval_pair"


class ButtonState(Enum):
    NORMAL = "normal"
    HOVER = "hover"
    PRESSED = "pressed"
    ACTIVE = "active"
    DISABLED = "disabled"


class SymbolType(Enum):
    PLAY = "play"
    STOP = "stop"
    WARNING = "warning"
    GEAR = "gear"
    NONE = "none"


class LogLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


BUTTON_META = {
    ButtonShape.CIRCLE: {
        "name": "ПУСК",
        "symbol": SymbolType.PLAY,
        "accent": COLOR_ACCENT_START,
        "group": "work",
        "critical": False,
    },
    ButtonShape.TRIANGLE: {
        "name": "ВОСПР.",
        "symbol": SymbolType.PLAY,
        "accent": COLOR_ACCENT_SERVICE,
        "group": "work",
        "critical": False,
    },
    ButtonShape.WARNING_TRIANGLE: {
        "name": "АВАРИЯ",
        "symbol": SymbolType.WARNING,
        "accent": COLOR_ACCENT_ALARM,
        "group": "alarm",
        "critical": True,
    },
    ButtonShape.HEXAGON: {
        "name": "НАСТРОЙКИ",
        "symbol": SymbolType.GEAR,
        "accent": COLOR_ACCENT_SERVICE,
        "group": "service",
        "critical": False,
    },
    ButtonShape.OCTAGON: {
        "name": "СТОП",
        "symbol": SymbolType.STOP,
        "accent": COLOR_ESTOP_BG,
        "group": "estop",
        "critical": True,
    },
    ButtonShape.OVAL_PAIR: {
        "name": "ПУСК / ПАУЗА",
        "symbol": SymbolType.NONE,
        "accent": COLOR_ACCENT_START,
        "group": "work",
        "critical": False,
    },
}


# Коды и описания событий для панели "Последнее событие"
EVENT_DETAILS = {
    "ПУСК": ("OK-001", "Пуск оборудования выполнен"),
    "ВОСПР.": ("OK-002", "Воспроизведение запущено"),
    "АВАРИЯ": ("AL-101", "Сработала аварийная сигнализация"),
    "СТОП": ("EM-001", "Аварийный останов оборудования"),
    "ПАУЗА": ("PS-001", "Оборудование в паузе"),
    "НАСТРОЙКИ": ("SV-001", "Открыт режим настроек"),
    "СБРОС": ("RS-001", "Сброс состояний кнопок"),
    "СНИМОК ЭКРАНА": ("SC-001", "Снимок интерфейса сохранён"),
    "ЭКСПОРТ ЖУРНАЛА": ("EX-001", "Журнал экспортирован в файл"),
    "СИСТЕМА": ("SY-000", "Системное сообщение"),
}


# ---------------------------------------------------------------------------
# Кнопка
# ---------------------------------------------------------------------------
class IndustrialButton(QWidget):
    clicked = Signal(str, str)
    critical_triggered = Signal(str, str)

    def __init__(self, shape: ButtonShape, parent=None) -> None:
        super().__init__(parent)
        self.shape = shape
        self.meta = BUTTON_META[shape]

        self._state = ButtonState.NORMAL
        self._accent = QColor(self.meta["accent"])
        self._holding = False
        self._pressed_side: Optional[str] = None

        self._active_timer = QTimer(self)
        self._active_timer.setSingleShot(True)
        self._active_timer.timeout.connect(self._on_active_timeout)

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_complete)

        self._hold_progress = 0.0
        self._hold_anim = QTimer(self)
        self._hold_anim.setInterval(30)
        self._hold_anim.timeout.connect(self._on_hold_tick)

        if shape == ButtonShape.OCTAGON:
            self.setMinimumSize(ESTOP_SIZE, ESTOP_SIZE)
        elif shape == ButtonShape.OVAL_PAIR:
            self.setMinimumSize(300, BUTTON_MIN_H)
        else:
            self.setMinimumSize(BUTTON_MIN_W, BUTTON_MIN_H)

        # Фиксированная вертикальная политика + отсутствие maximumHeight,
        # чтобы layout корректно считал минимальные размеры панели.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def _is_critical(self) -> bool:
        return self.meta["critical"]

    def _is_estop(self) -> bool:
        return self.shape == ButtonShape.OCTAGON

    def set_button_state(self, state: ButtonState) -> None:
        if self._state != state:
            self._state = state
            self.update()

    def reset_state(self) -> None:
        self._active_timer.stop()
        self._hold_timer.stop()
        self._hold_anim.stop()
        self._holding = False
        self._hold_progress = 0.0
        self._pressed_side = None
        self._state = ButtonState.NORMAL
        self.update()

    def flash_active(self) -> None:
        self._state = ButtonState.ACTIVE
        self._active_timer.start(ACTIVE_HIGHLIGHT_MS)
        self.update()

    def _on_active_timeout(self) -> None:
        self._state = ButtonState.NORMAL
        self.update()

    # -------------------------------------------------- События
    def enterEvent(self, event) -> None:  # noqa: N802
        if self._state == ButtonState.NORMAL:
            self._state = ButtonState.HOVER
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._state in (ButtonState.HOVER, ButtonState.PRESSED):
            self._state = ButtonState.NORMAL
            self._pressed_side = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        self._state = ButtonState.PRESSED

        if self.shape == ButtonShape.OVAL_PAIR:
            half = self.width() / 2
            self._pressed_side = "left" if event.position().x() < half else "right"
        else:
            self._pressed_side = None

        self.update()

        if self._is_critical():
            self._holding = True
            self._hold_progress = 0.0
            self._hold_anim.start()
            self._hold_timer.start(HOLD_DURATION_MS)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return

        was_pressed = self._state == ButtonState.PRESSED

        if self._is_critical() and self._holding:
            self._holding = False
            self._hold_timer.stop()
            self._hold_anim.stop()
            self._hold_progress = 0.0
            self._state = ButtonState.HOVER
            self._pressed_side = None
            self.update()
            return

        if was_pressed and self.rect().contains(event.position().toPoint()):
            self._emit_click(event.position())

        self._state = ButtonState.HOVER
        self._pressed_side = None
        self.update()

    def _on_hold_tick(self) -> None:
        self._hold_progress = min(1.0, self._hold_progress + 30.0 / HOLD_DURATION_MS)
        self.update()

    def _on_hold_complete(self) -> None:
        if not self._holding:
            return
        self._holding = False
        self._hold_anim.stop()
        self._hold_progress = 0.0
        self._state = ButtonState.ACTIVE
        self._active_timer.start(ACTIVE_HIGHLIGHT_MS)
        self.update()
        self.critical_triggered.emit(self.shape.value, self.meta["name"])

    def _emit_click(self, pos) -> None:
        if self.shape == ButtonShape.OVAL_PAIR:
            half = self.width() / 2
            if pos.x() < half:
                self.clicked.emit("oval_pair_start", "ПУСК")
            else:
                self.clicked.emit("oval_pair_pause", "ПАУЗА")
        else:
            self.clicked.emit(self.shape.value, self.meta["name"])

    # -------------------------------------------------- Paint
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.shape == ButtonShape.OVAL_PAIR:
            self._draw_oval_pair(painter)
        else:
            self._draw_single_button(painter)

        if self._holding and self._hold_progress > 0:
            self._draw_hold_progress(painter)

    def _draw_single_button(self, painter: QPainter) -> None:
        w = self.width()
        h = self.height()

        size = min(w, h) - SP_16 * 2
        if size < 40:
            return

        cx = w / 2.0
        cy = h / 2.0

        path = self._build_shape_path(cx, cy, size)
        bg_color, border_color, icon_color = self._colors_for_state()

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawPath(path)

        pen = QPen(border_color)
        pen.setWidth(3 if self._is_estop() else 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        self._draw_symbol(painter, cx, cy, size, icon_color)

    def _colors_for_state(self) -> Tuple[QColor, QColor, QColor]:
        state = self._state

        # ============ E-STOP: ВСЕГДА КРАСНЫЙ ============
        if self._is_estop():
            if state == ButtonState.HOVER:
                return (QColor(COLOR_ESTOP_BG_HOVER),
                        QColor(COLOR_ESTOP_BORDER),
                        QColor(COLOR_ESTOP_ICON))
            if state == ButtonState.PRESSED or state == ButtonState.ACTIVE:
                return (QColor(COLOR_ESTOP_BG_PRESSED),
                        QColor("#000000"),
                        QColor(COLOR_ESTOP_ICON))
            return (QColor(COLOR_ESTOP_BG),
                    QColor(COLOR_ESTOP_BORDER),
                    QColor(COLOR_ESTOP_ICON))

        # ============ Остальные кнопки ============
        accent = self._accent

        if state == ButtonState.NORMAL:
            return (QColor(COLOR_BTN_BG),
                    QColor(COLOR_BTN_BORDER),
                    QColor(COLOR_BTN_ICON))
        if state == ButtonState.HOVER:
            return (QColor(COLOR_BTN_BG_HOVER),
                    accent,
                    QColor(COLOR_BTN_ICON_HOVER))
        if state == ButtonState.PRESSED:
            return (accent, accent, QColor("#ffffff"))
        if state == ButtonState.ACTIVE:
            return (accent, accent, QColor("#ffffff"))
        return (QColor(COLOR_BTN_DISABLED_BG),
                QColor(COLOR_BTN_DISABLED_BORDER),
                QColor(COLOR_BTN_DISABLED_ICON))

    def _draw_oval_pair(self, painter: QPainter) -> None:
        w = self.width()
        h = self.height()
        margin = SP_16
        body_w = w - margin * 2
        body_h = h - margin * 2
        if body_w <= 0 or body_h <= 0:
            return

        full_path = QPainterPath()
        full_path.addRoundedRect(
            QRectF(margin, margin, body_w, body_h),
            body_h / 2, body_h / 2,
        )

        left_path = QPainterPath()
        left_path.moveTo(margin + body_w / 2, margin)
        left_path.lineTo(margin + body_h / 2, margin)
        left_path.arcTo(QRectF(margin, margin, body_h, body_h), 90, 180)
        left_path.lineTo(margin + body_w / 2, margin + body_h)
        left_path.closeSubpath()

        right_path = QPainterPath()
        right_path.moveTo(margin + body_w / 2, margin)
        right_path.lineTo(margin + body_w - body_h / 2, margin)
        right_path.arcTo(
            QRectF(margin + body_w - body_h, margin, body_h, body_h),
            90, -180,
        )
        right_path.lineTo(margin + body_w / 2, margin + body_h)
        right_path.closeSubpath()

        press_side = self._pressed_side

        bg_l = QColor(COLOR_BTN_BG)
        bg_r = QColor(COLOR_BTN_BG)
        border_l = QColor(COLOR_BTN_BORDER)
        border_r = QColor(COLOR_BTN_BORDER)

        if self._state == ButtonState.HOVER:
            bg_l = QColor(COLOR_BTN_BG_HOVER)
            bg_r = QColor(COLOR_BTN_BG_HOVER)
            border_l = QColor(COLOR_ACCENT_START)
            border_r = QColor(COLOR_ACCENT_ALARM)

        if self._state == ButtonState.PRESSED:
            if press_side == "left":
                bg_l = QColor(COLOR_ACCENT_START)
                border_l = QColor(COLOR_ACCENT_START)
            elif press_side == "right":
                bg_r = QColor(COLOR_ACCENT_ALARM)
                border_r = QColor(COLOR_ACCENT_ALARM)
            else:
                bg_l = QColor(COLOR_ACCENT_START)
                border_l = QColor(COLOR_ACCENT_START)
                bg_r = QColor(COLOR_ACCENT_ALARM)
                border_r = QColor(COLOR_ACCENT_ALARM)

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_l)
        painter.drawPath(left_path)
        painter.setBrush(bg_r)
        painter.drawPath(right_path)

        painter.setPen(QPen(QColor("#1a1a1a"), 2))
        painter.drawLine(
            QPointF(margin + body_w / 2, margin + 4),
            QPointF(margin + body_w / 2, margin + body_h - 4),
        )

        pen = QPen(QColor(COLOR_BTN_BORDER))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(full_path)

        f = painter.font()
        f.setFamily("Consolas")
        f.setPointSize(13)
        f.setBold(True)
        painter.setFont(f)

        text_l = QColor("#ffffff") if press_side == "left" else QColor(COLOR_BTN_ICON)
        text_r = QColor("#ffffff") if press_side == "right" else QColor(COLOR_BTN_ICON)

        half_w = body_w / 2
        painter.setPen(text_l)
        painter.drawText(QRectF(margin, margin, half_w, body_h),
                         Qt.AlignCenter, "ПУСК")
        painter.setPen(text_r)
        painter.drawText(QRectF(margin + half_w, margin, half_w, body_h),
                         Qt.AlignCenter, "ПАУЗА")

    def _draw_symbol(self, painter: QPainter, cx: float, cy: float,
                     size: float, color: QColor) -> None:
        symbol = self.meta["symbol"]
        if symbol == SymbolType.NONE:
            return

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        s = size * 0.28

        if symbol == SymbolType.PLAY:
            path = QPainterPath()
            path.moveTo(cx - s * 0.4, cy - s * 0.6)
            path.lineTo(cx + s * 0.6, cy)
            path.lineTo(cx - s * 0.4, cy + s * 0.6)
            path.closeSubpath()
            painter.drawPath(path)

        elif symbol == SymbolType.STOP:
            path = QPainterPath()
            path.addRect(QRectF(cx - s * 0.55, cy - s * 0.55,
                                s * 1.1, s * 1.1))
            painter.drawPath(path)

        elif symbol == SymbolType.WARNING:
            self._symbol_warning(painter, cx, cy, s, color)

        elif symbol == SymbolType.GEAR:
            outer = QPainterPath()
            n_teeth = 8
            r_out = s * 1.05
            r_in = s * 0.82
            for i in range(n_teeth * 2):
                angle = (math.pi * i / n_teeth) - math.pi / 2
                r = r_out if i % 2 == 0 else r_in
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                if i == 0:
                    outer.moveTo(x, y)
                else:
                    outer.lineTo(x, y)
            outer.closeSubpath()

            hole = QPainterPath()
            hole.addEllipse(QPointF(cx, cy), s * 0.4, s * 0.4)
            outer = outer.subtracted(hole)
            painter.drawPath(outer)

    def _symbol_warning(self, painter: QPainter, cx: float, cy: float,
                        s: float, color: QColor) -> None:
        """Треугольник с восклицательным знаком — стандарт тревоги."""
        triangle = QPainterPath()
        triangle.moveTo(cx, cy - s * 0.95)
        triangle.lineTo(cx + s * 0.95, cy + s * 0.65)
        triangle.lineTo(cx - s * 0.95, cy + s * 0.65)
        triangle.closeSubpath()
        painter.drawPath(triangle)

        cut = QPainterPath()
        cut.addRect(QRectF(cx - s * 0.09, cy - s * 0.55,
                           s * 0.18, s * 0.75))
        cut.addEllipse(QPointF(cx, cy + s * 0.4), s * 0.11, s * 0.11)

        final = triangle.subtracted(cut)
        bg = QColor(COLOR_CARD if self._state == ButtonState.NORMAL
                    else COLOR_BTN_BG_HOVER if self._state == ButtonState.HOVER
                    else self._accent)
        painter.setBrush(bg)
        painter.drawPath(final)

    def _draw_hold_progress(self, painter: QPainter) -> None:
        cx = self.width() / 2
        cy = self.height() / 2
        r = min(self.width(), self.height()) / 2 - 8

        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        pen = QPen(QColor(self._accent), 5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        span = int(-360 * self._hold_progress * 16)
        painter.drawArc(rect, 90 * 16, span)

    @staticmethod
    def _star_points(cx: float, cy: float, r_outer: float,
                     r_inner: float, n: int) -> List[QPointF]:
        pts = []
        for i in range(n * 2):
            angle = (math.pi * i / n) - math.pi / 2
            r = r_outer if i % 2 == 0 else r_inner
            pts.append(QPointF(cx + r * math.cos(angle),
                               cy + r * math.sin(angle)))
        return pts

    def _build_shape_path(self, cx: float, cy: float,
                          size: float) -> QPainterPath:
        path = QPainterPath()
        r = size / 2

        if self.shape == ButtonShape.CIRCLE:
            path.addEllipse(QPointF(cx, cy), r, r)

        elif self.shape in (ButtonShape.TRIANGLE,
                            ButtonShape.WARNING_TRIANGLE):
            h = size * math.sqrt(3) / 2
            path.moveTo(QPointF(cx, cy - h * 0.55))
            path.lineTo(QPointF(cx + r, cy + h * 0.45))
            path.lineTo(QPointF(cx - r, cy + h * 0.45))
            path.closeSubpath()

        elif self.shape == ButtonShape.HEXAGON:
            pts = self._polygon_points(cx, cy, r, 6, rotation=-math.pi / 2)
            path.moveTo(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            path.closeSubpath()

        elif self.shape == ButtonShape.OCTAGON:
            pts = self._polygon_points(cx, cy, r, 8, rotation=math.pi / 8)
            path.moveTo(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            path.closeSubpath()

        else:
            path.addEllipse(QPointF(cx, cy), r, r)

        return path

    @staticmethod
    def _polygon_points(cx: float, cy: float, r: float,
                        n: int, rotation: float = 0.0) -> List[QPointF]:
        pts = []
        for i in range(n):
            angle = rotation + (2 * math.pi * i / n) - math.pi / 2
            pts.append(QPointF(cx + r * math.cos(angle),
                               cy + r * math.sin(angle)))
        return pts


# ---------------------------------------------------------------------------
# Мигающий индикатор
# ---------------------------------------------------------------------------
class BlinkingIndicator(QWidget):
    """Круглый индикатор с миганием для статуса АВАРИЯ."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(COLOR_TEXT_MUTED)
        self._on = True
        self._blinking = False

        self.setFixedSize(28, 28)

        self._timer = QTimer(self)
        self._timer.setInterval(BLINK_PERIOD_MS)
        self._timer.timeout.connect(self._toggle)

    def set_color(self, color: str, blinking: bool = False) -> None:
        self._color = QColor(color)
        self._blinking = blinking
        self._on = True
        if blinking:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _toggle(self) -> None:
        self._on = not self._on
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        color = QColor(self._color)
        if self._blinking and not self._on:
            color.setAlpha(60)

        painter.setBrush(color)
        painter.setPen(QPen(color.darker(150), 2))
        painter.drawEllipse(QPointF(14, 14), 11, 11)

        if self._on or not self._blinking:
            highlight = QColor("#ffffff")
            highlight.setAlpha(80)
            painter.setPen(Qt.NoPen)
            painter.setBrush(highlight)
            painter.drawEllipse(QPointF(11, 11), 3, 3)


# ---------------------------------------------------------------------------
# Панель группы
# ---------------------------------------------------------------------------
class ButtonGroupPanel(QFrame):
    def __init__(self, title: str, buttons: List[IndustrialButton],
                 emergency: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._emergency = emergency
        self.setObjectName("estopPanel" if emergency else "groupPanel")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("estopHeader" if emergency else "groupHeader")
        header.setFixedHeight(PANEL_HEADER_H)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(SP_12, 0, SP_12, 0)

        lbl = QLabel(title)
        lbl.setObjectName("estopTitle" if emergency else "groupTitle")
        hl.addWidget(lbl)
        hl.addStretch(1)

        layout.addWidget(header)

        div = QFrame()
        div.setObjectName("estopDivider" if emergency else "groupDivider")
        div.setFixedHeight(2 if emergency else 1)
        layout.addWidget(div)

        content = QWidget()
        content.setObjectName("estopContent" if emergency else "groupContent")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(
            PANEL_CONTENT_MARGIN, PANEL_CONTENT_MARGIN,
            PANEL_CONTENT_MARGIN, PANEL_CONTENT_MARGIN,
        )
        content_layout.setSpacing(SP_16)

        max_btn_h = 0
        for btn in buttons:
            content_layout.addWidget(btn)
            max_btn_h = max(max_btn_h, btn.minimumHeight())
        content_layout.addStretch(1)

        layout.addWidget(content, 1)

        # Явно сообщаем layout минимальную высоту панели,
        # чтобы она не сжималась и не перекрывала соседей.
        divider_h = 2 if emergency else 1
        panel_min_h = (
            PANEL_HEADER_H
            + divider_h
            + PANEL_CONTENT_MARGIN * 2
            + max_btn_h
        )
        self.setMinimumHeight(panel_min_h)


# ---------------------------------------------------------------------------
# Диалог защищённого сброса
# ---------------------------------------------------------------------------
class ConfirmResetDialog(QDialog):
    CONFIRM_WORD = "ПОДТВЕРЖДАЮ"

    def __init__(self, is_alarm: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Подтверждение сброса")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet("")

        self._is_alarm = is_alarm

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP_24, SP_24, SP_24, SP_24)
        layout.setSpacing(SP_16)

        if is_alarm:
            header_text = "СБРОС В СОСТОЯНИИ АВАРИИ"
            warn_text = (
                "⚠ ВНИМАНИЕ: система находится в состоянии АВАРИЯ.\n\n"
                "Перед сбросом убедитесь, что:\n"
                "  • Причина аварии устранена\n"
                "  • Оборудование безопасно\n"
                "  • Персонал не подвергается риску\n\n"
                f"Для подтверждения введите слово <b>{self.CONFIRM_WORD}</b>:"
            )
        else:
            header_text = "ОПАСНОЕ ДЕЙСТВИЕ"
            warn_text = (
                "Сброс состояний вернёт все кнопки в исходное положение.\n"
                "Журнал событий сохранён.\n\n"
                f"Для подтверждения введите слово <b>{self.CONFIRM_WORD}</b>:"
            )

        header = QLabel(header_text)
        header.setStyleSheet(
            f"color: {COLOR_ACCENT_STOP}; font-family: Consolas; "
            f"font-size: 14pt; font-weight: 900; letter-spacing: 4px; "
            f"background: transparent;"
        )

        text = QLabel(warn_text)
        text.setWordWrap(True)
        text.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 11pt; background: transparent;"
        )

        self.input_field = QLineEdit()
        self.input_field.setObjectName("confirmInput")
        self.input_field.setPlaceholderText(self.CONFIRM_WORD)
        self.input_field.setMinimumHeight(46)
        self.input_field.setAlignment(Qt.AlignCenter)
        self.input_field.textChanged.connect(self._on_text_changed)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SP_8)
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("ОТМЕНИТЬ")
        self.btn_cancel.setMinimumHeight(42)
        self.btn_cancel.setMinimumWidth(130)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_BTN_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: {RADIUS}px;
                font-family: Consolas;
                font-size: 11pt;
                font-weight: 900;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: {COLOR_BTN_BG_HOVER};
                border: 2px solid {COLOR_BTN_BORDER};
            }}
        """)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("ПОДТВЕРДИТЬ СБРОС")
        self.btn_ok.setMinimumHeight(42)
        self.btn_ok.setMinimumWidth(200)
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.setEnabled(False)
        self.btn_ok.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_ACCENT_STOP};
                color: #ffffff;
                border: 2px solid {COLOR_ACCENT_STOP};
                border-radius: {RADIUS}px;
                font-family: Consolas;
                font-size: 11pt;
                font-weight: 900;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background: #b91c1c;
            }}
            QPushButton:disabled {{
                background: {COLOR_BTN_DISABLED_BG};
                color: {COLOR_TEXT_DIM};
                border: 2px solid {COLOR_BTN_DISABLED_BORDER};
            }}
        """)
        self.btn_ok.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)

        layout.addWidget(header)
        layout.addWidget(text)
        layout.addWidget(self.input_field)
        layout.addStretch(1)
        layout.addLayout(btn_row)

        self.setStyleSheet(f"""
            QDialog {{
                background: {COLOR_CARD};
                border: 2px solid {COLOR_ACCENT_STOP};
            }}
            QLineEdit#confirmInput {{
                background: {COLOR_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: {RADIUS}px;
                font-family: Consolas;
                font-size: 14pt;
                font-weight: 900;
                letter-spacing: 4px;
                padding: 6px 12px;
            }}
            QLineEdit#confirmInput:focus {{
                border: 2px solid {COLOR_ACCENT_STOP};
            }}
        """)

    def _on_text_changed(self, text: str) -> None:
        valid = text.strip().upper() == self.CONFIRM_WORD
        self.btn_ok.setEnabled(valid)


# ---------------------------------------------------------------------------
# Диалог справки
# ---------------------------------------------------------------------------
class HelpDialog(QDialog):
    HELP_HTML = f"""
    <html><body style="color: {COLOR_TEXT}; font-family: Segoe UI; font-size: 11pt;">
    <h2 style="color: {COLOR_ACCENT_START}; font-family: Consolas;">
      СПРАВКА — ГАЛЕРЕЯ ПРОМЫШЛЕННЫХ КНОПОК v1.6
    </h2>

    <h3 style="color: {COLOR_ACCENT_START}; font-family: Consolas;">БЕЗОПАСНОСТЬ</h3>
    <ul>
      <li><b>E-STOP</b> (красный) — всегда активен, работает в любом состоянии</li>
      <li><b>E-STOP / АВАРИЯ</b> — требуют удержания 1 сек</li>
      <li><b>СБРОС</b> — требует ввода слова ПОДТВЕРЖДАЮ</li>
      <li><b>В АВАРИИ сброс заблокирован</b> до устранения причины</li>
    </ul>

    <h3 style="color: {COLOR_ACCENT_START}; font-family: Consolas;">СОСТОЯНИЯ СИСТЕМЫ</h3>
    <ul>
      <li><span style="color: {COLOR_STATUS_READY};">● ГОТОВ</span> — система в норме</li>
      <li><span style="color: {COLOR_STATUS_RUN};">● РАБОТА</span> — оборудование работает</li>
      <li><span style="color: {COLOR_STATUS_PAUSE};">● ПАУЗА</span> — временная остановка</li>
      <li><span style="color: {COLOR_STATUS_ALARM};">● АВАРИЯ</span> — критическое событие (мигает)</li>
      <li><span style="color: {COLOR_STATUS_STOP};">● ОСТАНОВ</span> — после аварийного останова</li>
    </ul>

    <h3 style="color: {COLOR_ACCENT_START}; font-family: Consolas;">ГОРЯЧИЕ КЛАВИШИ</h3>
    <ul>
      <li><b>1</b>…<b>6</b> — нажать кнопку</li>
      <li><b>Esc</b> — сброс состояний</li>
      <li><b>F1</b> — справка</li>
    </ul>
    </body></html>
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Справка")
        self.resize(680, 640)
        self.setStyleSheet("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP_24, SP_24, SP_24, SP_24)
        layout.setSpacing(SP_16)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(self.HELP_HTML)
        text.setStyleSheet(f"""
            QTextEdit {{
                background: {COLOR_CARD};
                color: {COLOR_TEXT};
                border: 1px solid {COLOR_BORDER};
                border-radius: {RADIUS}px;
                padding: {SP_16}px;
            }}
        """)
        layout.addWidget(text, 1)

        btn = QPushButton("ЗАКРЫТЬ")
        btn.setMinimumHeight(44)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_ACCENT_START};
                color: #0a1f10;
                border: 2px solid {COLOR_ACCENT_START};
                border-radius: {RADIUS}px;
                font-family: Consolas;
                font-size: 11pt;
                font-weight: 900;
                letter-spacing: 2px;
            }}
        """)
        layout.addWidget(btn)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class ButtonGalleryApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.resize(1280, 980)
        # Минимум ниже — чтобы окно можно было уменьшить и проверить скролл
        self.setMinimumSize(900, 600)

        self._buttons: List[IndustrialButton] = []
        self._log_entries: List[Tuple[float, LogLevel, str, str, str, str]] = []
        self._system_state = "ГОТОВ"

        self._build_ui()
        self._apply_styles()
        self._bind_shortcuts()

        self._update_active_card(None)
        self._refresh_log()
        self._update_system_indicator()
        self._update_reset_button_state()

        self._append_log(LogLevel.INFO, "СИСТЕМА", "запущена", "SY-000")
        self._refresh_log()
        self._log_status("СИСТЕМА ГОТОВА")

    # ==================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_toolbar())

        # Оборачиваем контент в QScrollArea, чтобы при нехватке места
        # появлялась прокрутка, а не перекрытие элементов.
        scroll = QScrollArea()
        scroll.setObjectName("contentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(self._build_content())
        root.addWidget(scroll, 1)

        root.addWidget(self._build_status_bar())

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(60)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SP_24, 0, SP_24, 0)
        layout.setSpacing(SP_12)

        title = QLabel(APP_TITLE)
        title.setObjectName("topBarTitle")

        version = QLabel(APP_VERSION)
        version.setObjectName("topBarVersion")

        self.indicator = BlinkingIndicator()

        self.lbl_system = QLabel("● ГОТОВ")
        self.lbl_system.setObjectName("systemStatus")
        self.lbl_system.setMinimumWidth(180)
        self.lbl_system.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addStretch(1)
        layout.addWidget(self.indicator)
        layout.addWidget(self.lbl_system)

        return bar

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(60)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SP_24, SP_10, SP_24, SP_10)
        layout.setSpacing(SP_8)

        self.btn_export = QPushButton("ЭКСПОРТ ЖУРНАЛА")
        self.btn_export.setObjectName("toolbarButton")
        self.btn_export.setMinimumHeight(40)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export_log)

        self.btn_snapshot = QPushButton("СНИМОК ЭКРАНА")
        self.btn_snapshot.setObjectName("toolbarButton")
        self.btn_snapshot.setMinimumHeight(40)
        self.btn_snapshot.setCursor(Qt.PointingHandCursor)
        self.btn_snapshot.clicked.connect(self._on_snapshot)

        self.btn_help = QPushButton("СПРАВКА")
        self.btn_help.setObjectName("toolbarButton")
        self.btn_help.setMinimumHeight(40)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._on_help)

        self.btn_reset = QPushButton("СБРОСИТЬ СОСТОЯНИЕ")
        self.btn_reset.setObjectName("dangerToolbarButton")
        self.btn_reset.setMinimumHeight(40)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._on_reset)

        layout.addWidget(self.btn_export)
        layout.addWidget(self.btn_snapshot)
        layout.addWidget(self.btn_help)
        layout.addStretch(1)
        layout.addWidget(self.btn_reset)

        return bar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("contentRoot")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(SP_24, SP_20, SP_24, SP_20)
        layout.setSpacing(SP_12)

        # === E-STOP ЗОНА ===
        estop_btn = IndustrialButton(ButtonShape.OCTAGON)
        estop_btn.clicked.connect(self._on_button_clicked)
        estop_btn.critical_triggered.connect(self._on_button_critical)
        self._buttons.append(estop_btn)

        estop_panel = ButtonGroupPanel(
            "АВАРИЙНЫЙ ОСТАНОВ (E-STOP) — удержание 1 сек",
            [estop_btn], emergency=True,
        )

        # === АВАРИЙНЫЕ ===
        alarm_buttons = []
        btn_alarm = IndustrialButton(ButtonShape.WARNING_TRIANGLE)
        btn_alarm.clicked.connect(self._on_button_clicked)
        btn_alarm.critical_triggered.connect(self._on_button_critical)
        alarm_buttons.append(btn_alarm)
        self._buttons.append(btn_alarm)

        alarm_panel = ButtonGroupPanel(
            "АВАРИЙНЫЕ (требуют удержания 1 сек)", alarm_buttons,
        )

        # === РАБОЧИЕ ===
        work_buttons = []
        for shape in (ButtonShape.CIRCLE, ButtonShape.TRIANGLE,
                      ButtonShape.OVAL_PAIR):
            btn = IndustrialButton(shape)
            btn.clicked.connect(self._on_button_clicked)
            btn.critical_triggered.connect(self._on_button_critical)
            work_buttons.append(btn)
            self._buttons.append(btn)

        work_panel = ButtonGroupPanel("РАБОЧИЕ", work_buttons)

        # === СЕРВИСНЫЕ ===
        service_buttons = []
        btn_hex = IndustrialButton(ButtonShape.HEXAGON)
        btn_hex.clicked.connect(self._on_button_clicked)
        btn_hex.critical_triggered.connect(self._on_button_critical)
        service_buttons.append(btn_hex)
        self._buttons.append(btn_hex)

        service_panel = ButtonGroupPanel("СЕРВИСНЫЕ", service_buttons)

        # Без stretch-коэффициентов — панели растут строго по содержимому.
        layout.addWidget(estop_panel)
        layout.addWidget(alarm_panel)
        layout.addWidget(work_panel)
        layout.addWidget(service_panel)

        # === Нижняя часть ===
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(SP_12)

        # Последнее событие
        active_frame = QFrame()
        active_frame.setObjectName("groupPanel")
        al = QVBoxLayout(active_frame)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)

        ah = QFrame()
        ah.setObjectName("groupHeader")
        ah.setFixedHeight(36)
        ahl = QHBoxLayout(ah)
        ahl.setContentsMargins(SP_12, 0, SP_12, 0)
        ahl.addWidget(self._make_group_title("ПОСЛЕДНЕЕ СОБЫТИЕ"))
        ahl.addStretch(1)
        al.addWidget(ah)

        adiv = QFrame()
        adiv.setObjectName("groupDivider")
        adiv.setFixedHeight(1)
        al.addWidget(adiv)

        ac = QWidget()
        ac.setObjectName("groupContent")
        acl = QVBoxLayout(ac)
        acl.setContentsMargins(SP_16, SP_16, SP_16, SP_16)
        acl.setSpacing(SP_8)

        self.lbl_active_name = QLabel("—")
        self.lbl_active_name.setObjectName("activeName")

        self.lbl_active_time = QLabel("Время: —")
        self.lbl_active_time.setObjectName("activeTime")

        self.lbl_active_code = QLabel("Код: —")
        self.lbl_active_code.setObjectName("activeCode")

        self.lbl_active_desc = QLabel("—")
        self.lbl_active_desc.setObjectName("activeDesc")
        self.lbl_active_desc.setWordWrap(True)

        self.lbl_active_status = QLabel("Статус: —")
        self.lbl_active_status.setObjectName("activeStatus")

        acl.addWidget(self.lbl_active_name)
        acl.addWidget(self.lbl_active_time)
        acl.addWidget(self.lbl_active_code)
        acl.addWidget(self.lbl_active_desc)
        acl.addWidget(self.lbl_active_status)
        acl.addStretch(1)
        al.addWidget(ac, 1)

        # Журнал
        log_frame = QFrame()
        log_frame.setObjectName("groupPanel")
        ll = QVBoxLayout(log_frame)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        lh = QFrame()
        lh.setObjectName("groupHeader")
        lh.setFixedHeight(36)
        lhl = QHBoxLayout(lh)
        lhl.setContentsMargins(SP_12, 0, SP_12, 0)
        lhl.addWidget(self._make_group_title("ЖУРНАЛ СОБЫТИЙ"))
        lhl.addStretch(1)
        ll.addWidget(lh)

        ldiv = QFrame()
        ldiv.setObjectName("groupDivider")
        ldiv.setFixedHeight(1)
        ll.addWidget(ldiv)

        lc = QWidget()
        lc.setObjectName("groupContent")
        lcl = QVBoxLayout(lc)
        lcl.setContentsMargins(SP_12, SP_12, SP_12, SP_12)
        lcl.setSpacing(SP_8)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(SP_8)

        filter_lbl = QLabel("ФИЛЬТР:")
        filter_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: Consolas; "
            f"font-size: 11pt; font-weight: 900; letter-spacing: 2px; "
            f"background: transparent;"
        )

        self.combo_filter = QComboBox()
        self.combo_filter.setObjectName("filterCombo")
        self.combo_filter.addItems(["ВСЕ", "INFO", "WARNING", "ERROR"])
        self.combo_filter.setFixedWidth(150)
        self.combo_filter.setMinimumHeight(34)
        self.combo_filter.currentTextChanged.connect(lambda _: self._refresh_log())

        filter_row.addWidget(filter_lbl)
        filter_row.addWidget(self.combo_filter)
        filter_row.addStretch(1)

        lcl.addLayout(filter_row)

        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("logView")
        self.log_edit.setReadOnly(True)
        self.log_edit.setFrameShape(QFrame.NoFrame)
        self.log_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.log_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        self.log_edit.setMinimumHeight(160)
        self.log_edit.setHtml(
            f'<div style="color: {COLOR_TEXT_DIM}; '
            f'font-family: Consolas; font-size: 12pt; '
            f'font-style: italic;">НЕТ СОБЫТИЙ</div>'
        )
        lcl.addWidget(self.log_edit, 1)

        ll.addWidget(lc, 1)

        bottom_row.addWidget(active_frame, 1)
        bottom_row.addWidget(log_frame, 2)

        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_row)
        bottom_widget.setMinimumHeight(240)
        bottom_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(bottom_widget)

        return content

    def _make_group_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("groupTitle")
        return lbl

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(30)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SP_24, 0, SP_24, 0)

        self.lbl_status = QLabel("СИСТЕМА ГОТОВА")
        self.lbl_status.setObjectName("statusText")

        self.lbl_hints = QLabel(
            "1..6 — НАЖАТЬ  ·  ESC — СБРОС  ·  F1 — СПРАВКА"
        )
        self.lbl_hints.setObjectName("statusHints")

        layout.addWidget(self.lbl_status, 1)
        layout.addWidget(self.lbl_hints, 0)

        return bar

    # ============================================================ Handlers ==
    def _on_button_clicked(self, shape_key: str, caption: str) -> None:
        self._flash_button(shape_key)

        level = LogLevel.INFO
        action = "НАЖАТА"
        if shape_key == "oval_pair_pause":
            level = LogLevel.WARNING
            action = "ПАУЗА"

        code, _ = EVENT_DETAILS.get(caption, ("--", "—"))
        self._append_log(level, caption, action, code)
        self._update_active_card((caption, self._now_ms_str(), action, code))
        self._update_system_state_from_event(caption, level)
        self._log_status(f"{caption}: {action}")

    def _on_button_critical(self, shape_key: str, caption: str) -> None:
        self._flash_button(shape_key)

        if caption == "АВАРИЯ":
            level = LogLevel.CRITICAL
        else:
            level = LogLevel.ERROR

        code, _ = EVENT_DETAILS.get(caption, ("--", "—"))
        self._append_log(level, caption, "СРАБОТАЛА", code)
        self._update_active_card((caption, self._now_ms_str(),
                                   "СРАБОТАЛА", code))
        self._update_system_state_from_event(caption, level)
        self._log_status(f"{caption}: СРАБОТАЛА")

    def _flash_button(self, shape_key: str) -> None:
        for btn in self._buttons:
            if btn.shape.value == shape_key:
                btn.flash_active()
                break

    def _append_log(self, level: LogLevel, caption: str,
                    action: str, code: str = "--") -> None:
        now = time.time()

        if self._log_entries:
            last_ts, last_lvl, last_cap, _, last_code, _ = self._log_entries[0]
            if (last_lvl == level
                    and last_cap == caption
                    and (now - last_ts) * 1000 < DUPLICATE_WINDOW_MS):
                self._log_entries[0] = (now, level, caption,
                                         action + " ×2", last_code, code)
                return

        self._log_entries.insert(0, (now, level, caption, action, code, ""))
        if len(self._log_entries) > LOG_MAX_ITEMS:
            self._log_entries = self._log_entries[:LOG_MAX_ITEMS]

    def _update_active_card(self, data: Optional[Tuple[str, str, str, str]]) -> None:
        if data is None:
            self.lbl_active_name.setText("—")
            self.lbl_active_time.setText("Время: —")
            self.lbl_active_code.setText("Код: —")
            self.lbl_active_desc.setText("—")
            self.lbl_active_status.setText("Статус: —")
            return

        caption, ts, status, code = data
        _, desc = EVENT_DETAILS.get(caption, ("--", "—"))

        self.lbl_active_name.setText(caption.upper())
        self.lbl_active_time.setText(f"Время: {ts}")
        self.lbl_active_code.setText(f"Код: {code}")
        self.lbl_active_desc.setText(f"Описание: {desc}")
        self.lbl_active_status.setText(f"Статус: {status}")

    def _refresh_log(self) -> None:
        filter_value = self.combo_filter.currentText() if hasattr(
            self, "combo_filter") else "ВСЕ"

        if not self._log_entries:
            self.log_edit.setHtml(
                f'<div style="color: {COLOR_TEXT_DIM}; '
                f'font-family: Consolas; font-size: 12pt; '
                f'font-style: italic;">НЕТ СОБЫТИЙ</div>'
            )
            return

        html_lines = ['<div style="font-family: Consolas; font-size: 12pt;">']
        has_content = False
        for ts, level, caption, action, code, _ in self._log_entries[:80]:
            if filter_value != "ВСЕ" and level.value != filter_value:
                continue
            has_content = True
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts))
            ms = int((ts - int(ts)) * 1000)
            full_ts = f"{ts_str}.{ms:03d}"

            color = self._color_for_level(level)
            bold = "font-weight: 900;" if level in (LogLevel.ERROR,
                                                     LogLevel.CRITICAL) else ""

            html_lines.append(
                f'<div style="color: {color}; {bold} margin-bottom: 3px;">'
                f'[{full_ts}] &nbsp; [{level.value:<8}] &nbsp; '
                f'[{code:<6}] &nbsp; {caption:<16} &nbsp; {action}'
                f'</div>'
            )

        if not has_content:
            self.log_edit.setHtml(
                f'<div style="color: {COLOR_TEXT_DIM}; '
                f'font-family: Consolas; font-size: 12pt; '
                f'font-style: italic;">НЕТ СОБЫТИЙ ВЫБРАННОГО УРОВНЯ</div>'
            )
            return

        html_lines.append('</div>')
        self.log_edit.setHtml("".join(html_lines))

    @staticmethod
    def _color_for_level(level: LogLevel) -> str:
        return {
            LogLevel.INFO: COLOR_LOG_INFO,
            LogLevel.WARNING: COLOR_LOG_WARNING,
            LogLevel.ERROR: COLOR_LOG_ERROR,
            LogLevel.CRITICAL: COLOR_LOG_CRITICAL,
        }.get(level, COLOR_LOG_INFO)

    def _update_system_state_from_event(self, caption: str,
                                         level: LogLevel) -> None:
        if caption == "СТОП":
            self._system_state = "ОСТАНОВ"
        elif caption == "АВАРИЯ":
            self._system_state = "АВАРИЯ"
        elif level == LogLevel.ERROR:
            self._system_state = "АВАРИЯ"
        elif caption in ("ПУСК", "ВОСПР."):
            self._system_state = "РАБОТА"
        elif caption == "ПАУЗА":
            self._system_state = "ПАУЗА"
        else:
            return

        self._update_system_indicator()
        self._update_reset_button_state()

        if self._system_state == "АВАРИЯ":
            QApplication.beep()

    def _update_system_indicator(self) -> None:
        state = self._system_state

        color_map = {
            "ГОТОВ": COLOR_STATUS_READY,
            "РАБОТА": COLOR_STATUS_RUN,
            "ПАУЗА": COLOR_STATUS_PAUSE,
            "АВАРИЯ": COLOR_STATUS_ALARM,
            "ОСТАНОВ": COLOR_STATUS_STOP,
        }
        color = color_map.get(state, COLOR_TEXT_MUTED)

        blinking = (state == "АВАРИЯ")

        self.indicator.set_color(color, blinking)

        if state == "АВАРИЯ":
            bg = COLOR_ACCENT_STOP
            text_color = "#ffffff"
        elif state == "ПАУЗА":
            bg = COLOR_ACCENT_ALARM
            text_color = "#1a1400"
        elif state == "РАБОТА":
            bg = COLOR_ACCENT_START
            text_color = "#0a1f10"
        elif state == "ОСТАНОВ":
            bg = COLOR_BTN_BG
            text_color = COLOR_TEXT
        else:
            bg = COLOR_BTN_BG
            text_color = COLOR_TEXT

        self.lbl_system.setText(f"● {state}")
        self.lbl_system.setStyleSheet(
            f"QLabel#systemStatus {{ "
            f"color: {text_color}; "
            f"background: {bg}; "
            f"border: 2px solid {color}; "
            f"border-radius: {RADIUS}px; "
            f"padding: 6px 20px; "
            f"font-family: Consolas; "
            f"font-size: 11pt; "
            f"font-weight: 900; "
            f"letter-spacing: 3px; "
            f"}}"
        )

    def _update_reset_button_state(self) -> None:
        if self._system_state == "АВАРИЯ":
            self.btn_reset.setEnabled(False)
            self.btn_reset.setToolTip(
                "Сброс заблокирован в состоянии АВАРИЯ.\n"
                "Устраните причину и нажмите E-STOP для подтверждения."
            )
        else:
            self.btn_reset.setEnabled(True)
            self.btn_reset.setToolTip("Сброс состояний (требует подтверждения)")

    @staticmethod
    def _now_ms_str() -> str:
        t = time.time()
        return time.strftime("%H:%M:%S", time.localtime(t)) + \
            f".{int((t - int(t)) * 1000):03d}"

    def _on_reset(self) -> None:
        if not self.btn_reset.isEnabled():
            return

        is_alarm = (self._system_state == "АВАРИЯ")
        dlg = ConfirmResetDialog(is_alarm=is_alarm, parent=self)
        if dlg.exec() != QDialog.Accepted:
            self._append_log(LogLevel.WARNING, "СБРОС", "ОТМЕНЁН", "RS-000")
            self._refresh_log()
            self._log_status("СБРОС ОТМЕНЁН")
            return

        for btn in self._buttons:
            btn.reset_state()
        self._update_active_card(None)
        self._append_log(LogLevel.WARNING, "СБРОС", "выполнен", "RS-001")
        self._refresh_log()
        self._system_state = "ГОТОВ"
        self._update_system_indicator()
        self._update_reset_button_state()
        self._log_status("СОСТОЯНИЯ СБРОШЕНЫ")

    def _on_help(self) -> None:
        dlg = HelpDialog(self)
        dlg.exec()

    def _on_snapshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить снимок экрана", "button_gallery.png",
            "PNG изображения (*.png);;Все файлы (*)"
        )
        if not path:
            return
        pixmap = self.grab()
        if pixmap.save(path, "PNG"):
            self._append_log(LogLevel.INFO, "СНИМОК ЭКРАНА",
                             "сохранён", "SC-001")
            self._refresh_log()
            self._log_status(f"СНИМОК: {path}")

    def _on_export_log(self) -> None:
        if not self._log_entries:
            self._log_status("ЖУРНАЛ ПУСТ")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт журнала событий", "event_log.txt",
            "Текстовые файлы (*.txt);;Все файлы (*)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("ЖУРНАЛ СОБЫТИЙ — ГАЛЕРЕЯ ПРОМЫШЛЕННЫХ КНОПОК\n")
                f.write("=" * 78 + "\n\n")
                for ts, level, caption, action, code, _ in self._log_entries:
                    ts_str = time.strftime("%H:%M:%S", time.localtime(ts))
                    ms = int((ts - int(ts)) * 1000)
                    f.write(f"[{ts_str}.{ms:03d}] "
                            f"[{level.value:<8}] [{code:<6}] "
                            f"{caption:<16} {action}\n")
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return

        self._append_log(LogLevel.INFO, "ЭКСПОРТ ЖУРНАЛА",
                         "выполнен", "EX-001")
        self._refresh_log()
        self._log_status(f"ЭКСПОРТ: {path}")

    def _activate_button_by_index(self, idx: int) -> None:
        if not (0 <= idx < len(self._buttons)):
            return
        btn = self._buttons[idx]
        caption = btn.meta["name"]

        if btn.meta["critical"]:
            self._log_status(f"{caption}: ТРЕБУЕТ УДЕРЖАНИЯ 1 СЕК")
            return

        btn.flash_active()
        self._on_button_clicked(btn.shape.value, caption)

    def _bind_shortcuts(self) -> None:
        for i in range(1, 7):
            QShortcut(QKeySequence(str(i)), self,
                      activated=lambda n=i - 1: self._activate_button_by_index(n))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._on_reset)
        QShortcut(QKeySequence(Qt.Key_F1), self, activated=self._on_help)

    # ================================================================ Стили
    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget#root, QWidget#contentRoot {{
                background: {COLOR_BG};
            }}
            QWidget {{
                color: {COLOR_TEXT};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QLabel {{
                background: transparent;
                color: {COLOR_TEXT};
                font-size: 10pt;
            }}

            QScrollArea#contentScroll {{
                background: {COLOR_BG};
                border: none;
            }}
            QScrollArea#contentScroll > QWidget > QWidget {{
                background: {COLOR_BG};
            }}

            QFrame#topBar {{
                background: {COLOR_CARD};
                border-bottom: 2px solid {COLOR_BORDER};
            }}
            QLabel#topBarTitle {{
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13pt;
                font-weight: 900;
                color: {COLOR_TEXT};
                letter-spacing: 4px;
            }}
            QLabel#topBarVersion {{
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                color: {COLOR_TEXT_MUTED};
            }}

            QFrame#toolbar {{
                background: {COLOR_BG};
                border-bottom: 1px solid {COLOR_DIVIDER};
            }}
            QPushButton#toolbarButton {{
                background: {COLOR_CARD};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: {RADIUS}px;
                padding: 6px 16px;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                font-weight: 900;
                letter-spacing: 1px;
            }}
            QPushButton#toolbarButton:hover {{
                border: 2px solid {COLOR_BTN_BORDER};
                background: {COLOR_BTN_BG_HOVER};
            }}

            QPushButton#dangerToolbarButton {{
                background: {COLOR_CARD};
                color: {COLOR_ACCENT_STOP};
                border: 2px solid {COLOR_ACCENT_STOP};
                border-radius: {RADIUS}px;
                padding: 6px 16px;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                font-weight: 900;
                letter-spacing: 1px;
            }}
            QPushButton#dangerToolbarButton:hover {{
                background: {COLOR_ACCENT_STOP};
                color: #ffffff;
            }}
            QPushButton#dangerToolbarButton:disabled {{
                background: {COLOR_BTN_DISABLED_BG};
                color: {COLOR_TEXT_DIM};
                border: 2px solid {COLOR_BTN_DISABLED_BORDER};
            }}

            QFrame#groupPanel {{
                background: {COLOR_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: {RADIUS}px;
            }}
            QFrame#groupHeader {{
                background: {COLOR_BG};
                border-top-left-radius: {RADIUS}px;
                border-top-right-radius: {RADIUS}px;
            }}
            QLabel#groupTitle {{
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                font-weight: 900;
                color: {COLOR_TEXT_MUTED};
                letter-spacing: 3px;
                background: transparent;
            }}
            QFrame#groupDivider {{
                background: {COLOR_DIVIDER};
                border: none;
            }}
            QWidget#groupContent {{
                background: {COLOR_CARD};
            }}

            QFrame#estopPanel {{
                background: {COLOR_ESTOP_ZONE_BG};
                border: 2px solid {COLOR_ESTOP_ZONE_BORDER};
                border-radius: {RADIUS}px;
            }}
            QFrame#estopHeader {{
                background: {COLOR_ACCENT_STOP};
                border-top-left-radius: {RADIUS}px;
                border-top-right-radius: {RADIUS}px;
            }}
            QLabel#estopTitle {{
                font-family: 'Consolas', monospace;
                font-size: 11pt;
                font-weight: 900;
                color: #ffffff;
                letter-spacing: 3px;
                background: transparent;
            }}
            QFrame#estopDivider {{
                background: {COLOR_ACCENT_STOP};
                border: none;
            }}
            QWidget#estopContent {{
                background: {COLOR_ESTOP_ZONE_BG};
            }}

            QLabel#activeName {{
                font-family: 'Consolas', monospace;
                font-size: 16pt;
                font-weight: 900;
                color: {COLOR_TEXT};
                letter-spacing: 3px;
                background: transparent;
            }}
            QLabel#activeTime {{
                font-family: 'Consolas', monospace;
                font-size: 12pt;
                color: {COLOR_TEXT_MUTED};
                background: transparent;
            }}
            QLabel#activeCode {{
                font-family: 'Consolas', monospace;
                font-size: 12pt;
                font-weight: 900;
                color: {COLOR_ACCENT_ALARM};
                background: transparent;
            }}
            QLabel#activeDesc {{
                font-family: 'Segoe UI', sans-serif;
                font-size: 11pt;
                color: {COLOR_TEXT};
                background: transparent;
            }}
            QLabel#activeStatus {{
                font-family: 'Consolas', monospace;
                font-size: 12pt;
                color: {COLOR_TEXT};
                background: transparent;
            }}

            QTextEdit#logView {{
                background: {COLOR_BG};
                border: 1px solid {COLOR_DIVIDER};
                border-radius: {RADIUS}px;
                padding: {SP_8}px;
                color: {COLOR_TEXT};
                font-family: 'Consolas', monospace;
                font-size: 12pt;
            }}

            QComboBox#filterCombo {{
                background: {COLOR_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: {RADIUS}px;
                padding: 4px 10px;
                font-family: 'Consolas', monospace;
                font-size: 11pt;
                font-weight: 900;
            }}
            QComboBox#filterCombo:hover {{
                border: 2px solid {COLOR_BTN_BORDER};
            }}
            QComboBox#filterCombo::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLOR_CARD};
                color: {COLOR_TEXT};
                selection-background-color: {COLOR_BTN_BG_HOVER};
                selection-color: #ffffff;
                border: 2px solid {COLOR_BORDER};
                font-family: 'Consolas', monospace;
                font-size: 11pt;
            }}

            QFrame#statusBar {{
                background: {COLOR_STATUS_BG};
                border-top: 1px solid {COLOR_DIVIDER};
            }}
            QLabel#statusText {{
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                font-weight: 900;
                color: {COLOR_TEXT};
                letter-spacing: 1px;
            }}
            QLabel#statusHints {{
                font-family: 'Consolas', monospace;
                font-size: 9pt;
                color: {COLOR_TEXT_DIM};
                letter-spacing: 1px;
            }}

            QScrollBar:vertical {{
                background: {COLOR_BG};
                width: 12px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_BORDER};
                min-height: 24px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLOR_BTN_BORDER};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                background: none; height: 0;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: none;
            }}

            QToolTip {{
                background: {COLOR_CARD};
                color: {COLOR_TEXT};
                border: 1px solid {COLOR_BORDER};
                padding: 4px;
            }}
        """)

    def _log_status(self, message: str) -> None:
        self.lbl_status.setText(message.upper())
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] {message}")


# ---------------------------------------------------------------------------
def main() -> int:
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(msg, file=sys.stderr)

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = ButtonGalleryApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())