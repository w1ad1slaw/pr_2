"""
Industrial Random Data Analyzer — v3.0 (Industrial HMI Edition)
================================================================
АРМ оператора: генерация, контроль брака, инженерный анализ массивов
случайных чисел. Соответствует ISO 9241 / ГОСТ Р ИСО 9241-110.

История версий:
  v2.0 — компактная 4-блочная сетка.
  v2.1 — раскладка сверху вниз, центрирование, полировка UI.
  v2.2 — кастомный QStyledItemDelegate для разделителей блоков.
  v3.0 — промышленный HMI: крупные элементы (42-45px), высококонтрастная
         палитра, акцентная кнопка «Сгенерировать», адаптация под цех
         (яркое освещение, блики, работа в перчатках).

Стек: Python 3.10+, PySide6. Сторонние зависимости отсутствуют.
"""

from __future__ import annotations

import csv
import random
import re
import sys
from typing import List, Optional, Tuple

from PySide6.QtCore import QModelIndex, QRect, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Константы — базовые параметры приложения
# ---------------------------------------------------------------------------
DEFAULT_COUNT = 1000
DEFAULT_MIN = 0
DEFAULT_MAX = 100
DEFAULT_LSL = 20
DEFAULT_USL = 80

LEFT_PANEL_MIN_WIDTH = 320
LEFT_PANEL_MAX_WIDTH = 340

DATA_FONT_SIZE = 10
LABEL_FONT_SIZE = 11
ROW_HEIGHT = 22
BLOCKS = 4
COLS_PER_BLOCK = 2

DEBOUNCE_MS = 250

# --- Промышленная палитра HMI (для работы при ярком свете и бликах) ---
COLOR_BG = "#f4f5f7"
COLOR_TEXT = "#000000"                 # максимальный контраст
COLOR_TEXT_MUTED = "#4a5058"
COLOR_BORDER = "#959da5"               # контрастные рамки полей
COLOR_BORDER_FOCUS = "#2b579a"
COLOR_BORDER_SUBTLE = "#c8ccd2"        # для GroupBox и второстепенных

COLOR_PRIMARY = "#2b579a"              # акцент — «Сгенерировать»
COLOR_PRIMARY_HOVER = "#1e3f7a"
COLOR_PRIMARY_PRESSED = "#15305e"
COLOR_ON_PRIMARY = "#ffffff"

COLOR_BTN_BG = "#e7eaee"               # второстепенные кнопки
COLOR_BTN_BG_HOVER = "#d8dde3"
COLOR_BTN_BG_PRESSED = "#c9ced5"

# Мягкая, не ядовитая подсветка брака
COLOR_BELOW_LSL = QColor("#eef5ff")    # ниже нормы — светло-синий
COLOR_ABOVE_USL = QColor("#ffeef0")    # выше нормы — светло-красный

# Сдержанный промышленный цвет главного индикатора "Брак"
COLOR_DEFECT_TEXT = "#b32424"

# Жирный разделитель между блоками колонок
COLOR_BLOCK_DIVIDER = QColor("#a1a8b3")
BLOCK_DIVIDER_WIDTH = 2

# Колонки, ПОСЛЕ которых рисуется жирный разделитель
DIVIDER_COLUMNS = {1, 3, 5}

# Геометрия промышленного HMI
CONTROL_HEIGHT = 44                    # единая высота для кнопок и полей ввода
CONTROL_FONT_SIZE = 12
CONTROL_PADDING_V = 10
CONTROL_PADDING_H = 14

FILTER_HEIGHT = 46                     # поле фильтра — чуть выше остальных


# ---------------------------------------------------------------------------
# Парсер фильтра: >N, <N, >=N, <=N, =N, N, пусто
# ---------------------------------------------------------------------------
_FILTER_RE = re.compile(r"^\s*(>=|<=|>|<|=)?\s*(-?\d+)\s*$")


def parse_filter(text: str) -> Optional[Tuple[str, int]]:
    """Возвращает (operator, value) или None, если фильтр пуст/невалиден."""
    text = text.strip()
    if not text:
        return None
    m = _FILTER_RE.match(text)
    if not m:
        return None
    op = m.group(1) or "="
    try:
        val = int(m.group(2))
    except ValueError:
        return None
    return op, val


def matches_filter(value: int, parsed: Tuple[str, int]) -> bool:
    op, target = parsed
    if op == "=":
        return value == target
    if op == ">":
        return value > target
    if op == "<":
        return value < target
    if op == ">=":
        return value >= target
    if op == "<=":
        return value <= target
    return True


# ---------------------------------------------------------------------------
# Кастомный делегат: жирная вертикальная линия между блоками колонок
# ---------------------------------------------------------------------------
class BlockDividerDelegate(QStyledItemDelegate):
    """
    Рисует стандартную ячейку и поверх — акцентный разделитель по правому
    краю для колонок из DIVIDER_COLUMNS. Изолирован, не влияет на другие
    ячейки.
    """

    def __init__(self, divider_columns: set[int], parent=None) -> None:
        super().__init__(parent)
        self._divider_columns = divider_columns

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        super().paint(painter, option, index)
        if index.column() not in self._divider_columns:
            return

        painter.save()
        try:
            pen = QPen(COLOR_BLOCK_DIVIDER)
            pen.setWidth(BLOCK_DIVIDER_WIDTH)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)

            rect: QRect = option.rect
            x = rect.right() - BLOCK_DIVIDER_WIDTH + 1
            painter.drawLine(x, rect.top(), x, rect.bottom())
        finally:
            painter.restore()


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class IndustrialApp(QMainWindow):
    """АРМ оператора: генерация, фильтрация, контроль брака, статистика."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Industrial Random Data Analyzer — АРМ оператора v3.0")
        self.resize(1420, 820)

        self._data: List[int] = []
        self._current_vmin: int = DEFAULT_MIN
        self._current_vmax: int = DEFAULT_MAX
        self._filter_parsed: Optional[Tuple[str, int]] = None
        self._is_generating = False
        self._sort_order: Optional[str] = None

        self._build_ui()
        self._apply_styles()
        self._bind_shortcuts()

        QTimer.singleShot(0, self._on_generate)

    # ================================================================== UI ==
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_left_panel(), 0)
        root.addWidget(self._build_right_panel(), 1)

    # ---- Левая панель -------------------------------------------------------
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(LEFT_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(LEFT_PANEL_MAX_WIDTH)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_settings_group())
        layout.addWidget(self._build_limits_group())
        layout.addWidget(self._build_controls_group())
        layout.addWidget(self._build_stats_group(), 1)

        return panel

    def _build_settings_group(self) -> QGroupBox:
        group = QGroupBox("Настройки генерации")
        form = QVBoxLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(10, 14, 10, 10)

        validator = QIntValidator()

        self.input_count = QLineEdit(str(DEFAULT_COUNT))
        self.input_min = QLineEdit(str(DEFAULT_MIN))
        self.input_max = QLineEdit(str(DEFAULT_MAX))

        for f in (self.input_count, self.input_min, self.input_max):
            f.setValidator(validator)
            f.setMinimumHeight(CONTROL_HEIGHT)
            f.returnPressed.connect(self._on_generate)

        form.addWidget(QLabel("Количество чисел:"))
        form.addWidget(self.input_count)
        form.addWidget(QLabel("Минимум диапазона:"))
        form.addWidget(self.input_min)
        form.addWidget(QLabel("Максимум диапазона:"))
        form.addWidget(self.input_max)

        return group

    def _build_limits_group(self) -> QGroupBox:
        group = QGroupBox("Границы нормы (LSL / USL)")
        form = QVBoxLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(10, 14, 10, 10)

        validator = QIntValidator()

        self.input_lsl = QLineEdit(str(DEFAULT_LSL))
        self.input_usl = QLineEdit(str(DEFAULT_USL))
        for f in (self.input_lsl, self.input_usl):
            f.setValidator(validator)
            f.setMinimumHeight(CONTROL_HEIGHT)

        self.input_lsl.editingFinished.connect(self._on_limits_changed)
        self.input_usl.editingFinished.connect(self._on_limits_changed)

        form.addWidget(QLabel("Нижний лимит (LSL):"))
        form.addWidget(self.input_lsl)
        form.addWidget(QLabel("Верхний лимит (USL):"))
        form.addWidget(self.input_usl)

        return group

    def _build_controls_group(self) -> QGroupBox:
        group = QGroupBox("Управление")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 14, 10, 10)

        self.btn_generate = QPushButton("Сгенерировать")
        self.btn_copy = QPushButton("Скопировать в буфер")
        self.btn_export = QPushButton("Экспорт в CSV")

        # Главная кнопка — акцентный объект, помечаем её свойством для QSS
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setProperty("hmiRole", "primary")

        for btn in (self.btn_generate, self.btn_copy, self.btn_export):
            btn.setMinimumHeight(CONTROL_HEIGHT)
            btn.setCursor(Qt.PointingHandCursor)

        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_export.clicked.connect(self._on_export)

        layout.addWidget(self.btn_generate)
        layout.addWidget(self.btn_copy)
        layout.addWidget(self.btn_export)

        return group

    def _build_stats_group(self) -> QGroupBox:
        group = QGroupBox("Статистика")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 14, 10, 10)

        self.lbl_min = QLabel("Min: —")
        self.lbl_max = QLabel("Max: —")
        self.lbl_avg = QLabel("Avg: —")
        self.lbl_median = QLabel("Median: —")
        self.lbl_defect = QLabel("Брак: —")

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)

        for lbl in (self.lbl_min, self.lbl_max, self.lbl_avg, self.lbl_median):
            f = lbl.font()
            f.setPointSize(LABEL_FONT_SIZE)
            f.setBold(True)
            lbl.setFont(f)
            layout.addWidget(lbl)

        layout.addWidget(separator)

        f = self.lbl_defect.font()
        f.setPointSize(LABEL_FONT_SIZE + 1)
        f.setBold(True)
        self.lbl_defect.setFont(f)
        self.lbl_defect.setStyleSheet(
            f"color: {COLOR_DEFECT_TEXT}; padding-top: 4px;"
        )
        layout.addWidget(self.lbl_defect)

        layout.addStretch(1)
        return group

    # ---- Правая панель ------------------------------------------------------
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_filter_bar())
        layout.addWidget(self._build_table(), 1)

        return panel

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        lbl = QLabel("Фильтр:")
        lbl_font = lbl.font()
        lbl_font.setPointSize(CONTROL_FONT_SIZE)
        lbl_font.setBold(True)
        lbl.setFont(lbl_font)

        self.input_filter = QLineEdit()
        self.input_filter.setObjectName("filterInput")
        self.input_filter.setPlaceholderText("Пример: 50, >50, <20, >=50...")
        self.input_filter.setClearButtonEnabled(True)
        self.input_filter.setMinimumHeight(FILTER_HEIGHT)
        self.input_filter.textChanged.connect(self._on_filter_changed)

        self.lbl_filter_info = QLabel("")
        info_font = self.lbl_filter_info.font()
        info_font.setPointSize(11)
        info_font.setBold(True)
        self.lbl_filter_info.setFont(info_font)
        self.lbl_filter_info.setContentsMargins(8, 0, 4, 0)
        self.lbl_filter_info.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; padding-left: 8px;"
        )

        h.addWidget(lbl, 0)
        h.addWidget(self.input_filter, 1)
        h.addWidget(self.lbl_filter_info, 0)

        return bar

    def _build_table(self) -> QTableWidget:
        headers: List[str] = []
        for b in range(BLOCKS):
            headers.append(f"№{b + 1}")
            headers.append("Значение")

        table = QTableWidget(0, BLOCKS * COLS_PER_BLOCK)
        table.setHorizontalHeaderLabels(headers)

        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setWordWrap(False)

        font = QFont()
        font.setPointSize(DATA_FONT_SIZE)
        table.setFont(font)
        table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)

        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(table.columnCount()):
            if col % 2 == 0:
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
            else:
                header.setSectionResizeMode(col, QHeaderView.Stretch)

        self._divider_delegate = BlockDividerDelegate(DIVIDER_COLUMNS, table)
        table.setItemDelegate(self._divider_delegate)

        self.table = table
        return table

    # ---- Стили (промышленный HMI) -------------------------------------------
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            /* ==================== Общая палитра ==================== */
            QMainWindow, QWidget {{
                background-color: {COLOR_BG};
                color: {COLOR_TEXT};
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }}
            QLabel {{
                font-size: {LABEL_FONT_SIZE}pt;
                color: {COLOR_TEXT};
            }}

            /* ==================== GroupBox ==================== */
            QGroupBox {{
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                font-weight: 600;
                font-size: {LABEL_FONT_SIZE}pt;
                color: {COLOR_TEXT};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: {COLOR_TEXT};
            }}

            /* ==================== QLineEdit (крупные поля) ==================== */
            QLineEdit {{
                background: #ffffff;
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: {CONTROL_PADDING_V}px {CONTROL_PADDING_H}px;
                font-size: {CONTROL_FONT_SIZE}pt;
                font-weight: 600;
                min-height: {CONTROL_HEIGHT - 2 * CONTROL_PADDING_V}px;
                selection-background-color: {COLOR_PRIMARY};
                selection-color: #ffffff;
            }}
            QLineEdit:hover {{
                border: 2px solid {COLOR_BORDER_FOCUS};
            }}
            QLineEdit:focus {{
                border: 2px solid {COLOR_BORDER_FOCUS};
                background: #ffffff;
            }}

            /* ==================== Кнопки (второстепенные) ==================== */
            QPushButton {{
                background: {COLOR_BTN_BG};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: {CONTROL_PADDING_V}px {CONTROL_PADDING_H}px;
                font-size: {CONTROL_FONT_SIZE}pt;
                font-weight: bold;
                min-height: {CONTROL_HEIGHT - 2 * CONTROL_PADDING_V}px;
            }}
            QPushButton:hover {{
                background: {COLOR_BTN_BG_HOVER};
                border: 2px solid {COLOR_BORDER_FOCUS};
            }}
            QPushButton:pressed {{
                background: {COLOR_BTN_BG_PRESSED};
            }}
            QPushButton:disabled {{
                color: #8a919b;
                background: #eceef1;
                border: 2px solid #c8ccd2;
            }}

            /* ==================== Главная акцентная кнопка ==================== */
            QPushButton#primaryButton {{
                background: {COLOR_PRIMARY};
                color: {COLOR_ON_PRIMARY};
                border: 2px solid {COLOR_PRIMARY};
                font-weight: bold;
                font-size: {CONTROL_FONT_SIZE + 1}pt;
            }}
            QPushButton#primaryButton:hover {{
                background: {COLOR_PRIMARY_HOVER};
                border: 2px solid {COLOR_PRIMARY_HOVER};
                color: {COLOR_ON_PRIMARY};
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

            /* ==================== Поле фильтра ==================== */
            QLineEdit#filterInput {{
                border: 2px solid {COLOR_PRIMARY};
                background: #ffffff;
                color: {COLOR_TEXT};
                font-size: {CONTROL_FONT_SIZE}pt;
                font-weight: 600;
                padding: {CONTROL_PADDING_V}px {CONTROL_PADDING_H}px;
                min-height: {FILTER_HEIGHT - 2 * CONTROL_PADDING_V}px;
            }}
            QLineEdit#filterInput:focus {{
                border: 2px solid {COLOR_PRIMARY_HOVER};
            }}
            QLineEdit#filterInput::placeholder {{
                color: #5c6470;
            }}

            /* ==================== Таблица ==================== */
            QTableWidget {{
                background: #ffffff;
                alternate-background-color: #f2f4f6;
                gridline-color: #b6bcc4;
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 6px;
                color: {COLOR_TEXT};
            }}
            QTableWidget::item {{
                padding: 0px;
                border: none;
                color: {COLOR_TEXT};
            }}
            QHeaderView::section {{
                background: #dfe3e8;
                color: {COLOR_TEXT};
                padding: 6px 6px;
                border: none;
                border-right: 1px solid #b6bcc4;
                border-bottom: 1px solid #b6bcc4;
                font-weight: 700;
                font-size: 10pt;
            }}
            """
        )

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._on_generate)
        QShortcut(
            QKeySequence("Ctrl+F"),
            self,
            activated=lambda: self.input_filter.setFocus(),
        )

    # ========================================================== Валидация ==
    def _read_int(self, field: QLineEdit, name: str) -> int:
        text = field.text().strip()
        if not text:
            raise ValueError(f"Поле «{name}» не заполнено.")
        try:
            return int(text)
        except ValueError:
            raise ValueError(f"Поле «{name}» должно содержать целое число.")

    def _validate_inputs(self) -> Tuple[int, int, int]:
        count = self._read_int(self.input_count, "Количество чисел")
        vmin = self._read_int(self.input_min, "Минимум диапазона")
        vmax = self._read_int(self.input_max, "Максимум диапазона")

        if count <= 0:
            raise ValueError("Количество чисел должно быть положительным.")
        if count > 1_000_000:
            raise ValueError("Слишком большое количество чисел (максимум 1 000 000).")
        if vmin >= vmax:
            raise ValueError("Минимум должен быть строго меньше максимума.")

        return count, vmin, vmax

    def _read_limits(self) -> Tuple[int, int]:
        try:
            lsl = int(self.input_lsl.text().strip() or DEFAULT_LSL)
            usl = int(self.input_usl.text().strip() or DEFAULT_USL)
        except ValueError:
            lsl, usl = DEFAULT_LSL, DEFAULT_USL
        return lsl, usl

    # ============================================================ Handlers ==
    def _on_generate(self) -> None:
        if self._is_generating:
            return
        self._is_generating = True
        self.btn_generate.setEnabled(False)

        try:
            count, vmin, vmax = self._validate_inputs()
        except ValueError as exc:
            self._is_generating = False
            self.btn_generate.setEnabled(True)
            QMessageBox.warning(self, "Некорректный ввод", str(exc))
            return

        self._current_vmin = vmin
        self._current_vmax = vmax
        self._sort_order = None

        self._data = [random.randint(vmin, vmax) for _ in range(count)]

        self._refresh_view()
        self._update_stats()

        QTimer.singleShot(DEBOUNCE_MS, self._release_generate_button)

    def _release_generate_button(self) -> None:
        self._is_generating = False
        self.btn_generate.setEnabled(True)

    def _on_limits_changed(self) -> None:
        if self._data:
            self._update_stats()
            self._refresh_view()

    def _on_filter_changed(self, text: str) -> None:
        if not text.strip():
            self._filter_parsed = None
            self._refresh_view()
            return

        parsed = parse_filter(text)
        if parsed is None:
            self.lbl_filter_info.setText("⚠ некорректный фильтр")
            self.lbl_filter_info.setStyleSheet(
                f"color: {COLOR_DEFECT_TEXT}; padding-left: 8px; font-weight: bold;"
            )
            self._filter_parsed = None
            self._refresh_view()
            return

        self._filter_parsed = parsed
        self._refresh_view()

    def _on_header_clicked(self, section: int) -> None:
        if section % 2 == 0:
            return
        if self._sort_order is None:
            self._sort_order = "asc"
        elif self._sort_order == "asc":
            self._sort_order = "desc"
        else:
            self._sort_order = None
        self._refresh_view()

    # ==================================================== Отрисовка вида ==
    def _visible_values(self) -> List[Tuple[int, int]]:
        indexed = list(enumerate(self._data, start=1))

        if self._filter_parsed is not None:
            indexed = [
                (idx, v) for idx, v in indexed
                if matches_filter(v, self._filter_parsed)
            ]

        if self._sort_order == "asc":
            indexed.sort(key=lambda pair: (pair[1], pair[0]))
        elif self._sort_order == "desc":
            indexed.sort(key=lambda pair: (-pair[1], pair[0]))

        return indexed

    def _refresh_view(self) -> None:
        """Раскладка сверху вниз по блокам [№ | Значение] × 4."""
        indexed = self._visible_values()
        total_original = len(self._data)
        lsl, usl = self._read_limits()

        n_rows = (len(indexed) + BLOCKS - 1) // BLOCKS

        table = self.table
        table.setUpdatesEnabled(False)
        table.clearContents()
        table.setRowCount(n_rows)

        for row in range(n_rows):
            for block in range(BLOCKS):
                flat = block * n_rows + row
                idx_col = block * COLS_PER_BLOCK
                val_col = idx_col + 1

                if flat >= len(indexed):
                    idx_item = QTableWidgetItem("")
                    val_item = QTableWidgetItem("")
                    idx_item.setTextAlignment(Qt.AlignCenter)
                    val_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, idx_col, idx_item)
                    table.setItem(row, val_col, val_item)
                    continue

                original_idx, value = indexed[flat]

                idx_item = QTableWidgetItem(str(original_idx))
                idx_item.setTextAlignment(Qt.AlignCenter)
                idx_item.setForeground(QColor("#4a5058"))

                val_item = QTableWidgetItem(str(value))
                val_item.setTextAlignment(Qt.AlignCenter)

                if value < lsl:
                    val_item.setBackground(COLOR_BELOW_LSL)
                elif value > usl:
                    val_item.setBackground(COLOR_ABOVE_USL)

                table.setItem(row, idx_col, idx_item)
                table.setItem(row, val_col, val_item)

        table.setUpdatesEnabled(True)

        if self._filter_parsed is None:
            self.lbl_filter_info.setText(f"Всего: {total_original}")
            self.lbl_filter_info.setStyleSheet(
                f"color: {COLOR_TEXT_MUTED}; padding-left: 8px;"
            )
        else:
            self.lbl_filter_info.setText(
                f"Найдено: {len(indexed)} из {total_original}"
            )
            self.lbl_filter_info.setStyleSheet(
                f"color: {COLOR_PRIMARY}; padding-left: 8px;"
            )

    # ========================================================== Статистика ==
    def _update_stats(self) -> None:
        data = self._data
        if not data:
            self.lbl_min.setText("Min: —")
            self.lbl_max.setText("Max: —")
            self.lbl_avg.setText("Avg: —")
            self.lbl_median.setText("Median: —")
            self.lbl_defect.setText("Брак: —")
            return

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

        lsl, usl = self._read_limits()
        defect_count = sum(1 for v in data if v < lsl or v > usl)
        defect_pct = defect_count / len(data) * 100.0

        self.lbl_min.setText(f"Min: {vmin}")
        self.lbl_max.setText(f"Max: {vmax}")
        self.lbl_avg.setText(f"Avg: {avg:.2f}")
        self.lbl_median.setText(f"Median: {median:.2f}")
        self.lbl_defect.setText(f"Брак: {defect_count} шт ({defect_pct:.1f}%)")

    # ====================================================== Экспорт/буфер ==
    def _on_copy(self) -> None:
        if not self._data:
            QMessageBox.information(self, "Нет данных", "Сначала сгенерируйте массив.")
            return
        csv_line = ",".join(str(v) for v in self._data)
        QApplication.clipboard().setText(csv_line)
        self.statusBar().showMessage(
            f"Скопировано чисел: {len(self._data)} (исходный массив)", 3000
        )

    def _on_export(self) -> None:
        if not self._data:
            QMessageBox.information(self, "Нет данных", "Сначала сгенерируйте массив.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить массив как CSV",
            "random_data.csv",
            "CSV файлы (*.csv);;Все файлы (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Индекс", "Значение"])
                for i, v in enumerate(self._data, start=1):
                    writer.writerow([i, v])
        except OSError as exc:
            QMessageBox.critical(
                self, "Ошибка сохранения", f"Не удалось сохранить файл:\n{exc}"
            )
            return

        self.statusBar().showMessage(f"Экспортировано: {path}", 5000)


# ---------------------------------------------------------------------------
def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = IndustrialApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())