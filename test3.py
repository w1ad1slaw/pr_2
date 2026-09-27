from __future__ import annotations

import json
import sys
import time
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import (
    QColor, QFont, QKeySequence, QPainter, QPen, QBrush,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Параметры продукта
# ---------------------------------------------------------------------------
SETTINGS_ORG = "IndustrialControl"
SETTINGS_APP = "PanelConfigurator"

MODES = [
    ("auto",    "АВТОМАТИЧЕСКИЙ",     "Полный цикл без участия оператора"),
    ("semi",    "ПОЛУАВТОМАТИЧЕСКИЙ", "Оператор запускает цикл"),
    ("manual",  "РУЧНОЙ",             "Все действия выполняет оператор"),
    ("service", "СЕРВИСНЫЙ",          "Диагностика, без производства"),
]

OPTIONS = [
    ("logging",   "Логирование в файл"),
    ("alarm",     "Звуковой сигнал при аварии"),
    ("autosave",  "Автосохранение параметров"),
    ("highlight", "Подсветка аварийных зон"),
    ("remote",    "Удалённый доступ"),
    ("telemetry", "Отправка статистики"),
]

DISABLED_IN_MODE: Dict[str, List[str]] = {
    "auto": [],
    "semi": [],
    "manual": ["autosave"],
    "service": ["remote", "telemetry"],
}


# ---------------------------------------------------------------------------
# Палитра: строгий промышленный графит + зелёный акцент
# ---------------------------------------------------------------------------
COLOR_BG = "#2b2b2b"
COLOR_PANEL = "#383838"
COLOR_PANEL_DARK = "#242424"
COLOR_BORDER = "#5a5a5a"
COLOR_BORDER_LIGHT = "#707070"
COLOR_DIVIDER = "#4a4a4a"

COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_MUTED = "#a0a0a0"
COLOR_TEXT_DIM = "#6a6a6a"

COLOR_ACCENT = "#22c55e"
COLOR_ACCENT_DARK = "#16a34a"
COLOR_ACCENT_TEXT = "#0a1f10"

COLOR_WARNING = "#f59e0b"
COLOR_DANGER = "#ef4444"

COLOR_STATUS_BG = "#1a1a1a"


# ---------------------------------------------------------------------------
# Бизнес-логика
# ---------------------------------------------------------------------------
class ConfigState:
    def __init__(self) -> None:
        self.mode: str = "auto"
        self.options: Dict[str, bool] = {k: False for k, _ in OPTIONS}

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_option(self, key: str, value: bool) -> None:
        if key in self.options:
            self.options[key] = value

    def is_option_available(self, key: str) -> bool:
        return key not in DISABLED_IN_MODE.get(self.mode, [])

    def enabled_options(self) -> List[str]:
        return [k for k, v in self.options.items() if v]

    def enabled_count(self) -> int:
        return sum(1 for v in self.options.values() if v)

    def mode_label(self) -> str:
        return next((m[1] for m in MODES if m[0] == self.mode), self.mode)

    def mode_description(self) -> str:
        return next((m[2] for m in MODES if m[0] == self.mode), "")

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "mode_label": self.mode_label(),
            "options": dict(self.options),
            "options_enabled": self.enabled_options(),
        }


# ---------------------------------------------------------------------------
# Заголовок секции
# ---------------------------------------------------------------------------
class SectionHeader(QFrame):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionHeader")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)

        lbl = QLabel(text)
        lbl.setObjectName("sectionHeaderText")

        layout.addWidget(lbl)
        layout.addStretch(1)


# ---------------------------------------------------------------------------
# Строка режима
# ---------------------------------------------------------------------------
class ModeRow(QWidget):
    def __init__(self, key: str, label: str, description: str,
                 parent=None) -> None:
        super().__init__(parent)
        self.key = key

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(14)

        self.radio = QRadioButton(label)
        self.radio.setObjectName("modeRadio")
        self.radio.setMinimumWidth(240)
        self.radio.setCursor(Qt.PointingHandCursor)

        self.lbl_desc = QLabel(description)
        self.lbl_desc.setObjectName("modeDesc")
        self.lbl_desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(self.radio)
        layout.addWidget(self.lbl_desc, 1)


# ---------------------------------------------------------------------------
# Строка опции
# ---------------------------------------------------------------------------
class OptionRow(QWidget):
    def __init__(self, key: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.key = key

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(14)

        self.checkbox = QCheckBox(label)
        self.checkbox.setObjectName("optionCheckbox")
        self.checkbox.setCursor(Qt.PointingHandCursor)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("optionStatus")
        self.lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self.checkbox, 1)
        layout.addWidget(self.lbl_status, 0)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class PanelConfiguratorApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PANEL CONFIGURATOR")
        self.resize(1200, 760)
        self.setMinimumSize(1050, 680)

        self._state = ConfigState()
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._saved_dict: Optional[dict] = None

        self._mode_rows: Dict[str, ModeRow] = {}
        self._option_rows: Dict[str, OptionRow] = {}
        self._mode_group = QButtonGroup(self)

        self._build_ui()
        self._apply_styles()
        self._bind_shortcuts()

        self._load_settings()
        self._sync_ui_from_state()
        self._refresh_summary()
        self._update_dirty_state()
        self._log("PANEL CONFIGURATOR v2.1 готов.")

    # ==================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header(), 0)
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_status_bar(), 0)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(52)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(20)

        title = QLabel("PANEL CONFIGURATOR")
        title.setObjectName("headerTitle")

        version = QLabel("v 2.1")
        version.setObjectName("headerVersion")

        self.lbl_state = QLabel("● ГОТОВО")
        self.lbl_state.setObjectName("headerState")

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addStretch(1)
        layout.addWidget(self.lbl_state)

        return header

    def _build_body(self) -> QWidget:
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(16)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        left_layout.addWidget(self._build_modes_panel())
        left_layout.addWidget(self._build_options_panel(), 1)

        right = self._build_summary_panel()

        body_layout.addWidget(left, 3)
        body_layout.addWidget(right, 2)

        return body

    def _build_modes_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 8)
        panel_layout.setSpacing(0)

        panel_layout.addWidget(SectionHeader("РЕЖИМ РАБОТЫ"))

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        panel_layout.addWidget(divider)

        for key, label, desc in MODES:
            row = ModeRow(key, label, desc)
            row.radio.toggled.connect(
                lambda checked, k=key: self._on_mode_toggled(k, checked)
            )
            self._mode_group.addButton(row.radio)
            panel_layout.addWidget(row)
            self._mode_rows[key] = row

        return panel

    def _build_options_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 8)
        panel_layout.setSpacing(0)

        panel_layout.addWidget(SectionHeader("ДОПОЛНИТЕЛЬНЫЕ ОПЦИИ"))

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        panel_layout.addWidget(divider)

        scroll = QScrollArea()
        scroll.setObjectName("optionsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("optionsScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 6, 0, 0)
        content_layout.setSpacing(2)

        for key, label in OPTIONS:
            row = OptionRow(key, label)
            row.checkbox.toggled.connect(
                lambda checked, k=key: self._on_option_toggled(k, checked)
            )
            content_layout.addWidget(row)
            self._option_rows[key] = row

        content_layout.addStretch(1)
        scroll.setWidget(content)
        panel_layout.addWidget(scroll, 1)

        return panel

    def _build_summary_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 14)
        panel_layout.setSpacing(0)

        panel_layout.addWidget(SectionHeader("ТЕКУЩАЯ КОНФИГУРАЦИЯ"))

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        panel_layout.addWidget(divider)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(14)

        # Блок режима
        mode_block = QFrame()
        mode_block.setObjectName("summaryBlock")
        mode_layout = QVBoxLayout(mode_block)
        mode_layout.setContentsMargins(14, 12, 14, 14)
        mode_layout.setSpacing(4)

        lbl_mode_key = QLabel("РЕЖИМ РАБОТЫ")
        lbl_mode_key.setObjectName("summaryKey")

        self.lbl_mode_value = QLabel("АВТОМАТИЧЕСКИЙ")
        self.lbl_mode_value.setObjectName("summaryModeValue")

        self.lbl_mode_desc = QLabel("Полный цикл без участия оператора")
        self.lbl_mode_desc.setObjectName("summaryDesc")
        self.lbl_mode_desc.setWordWrap(True)

        mode_layout.addWidget(lbl_mode_key)
        mode_layout.addWidget(self.lbl_mode_value)
        mode_layout.addWidget(self.lbl_mode_desc)

        # Блок опций
        options_block = QFrame()
        options_block.setObjectName("summaryBlock")
        options_layout = QVBoxLayout(options_block)
        options_layout.setContentsMargins(14, 12, 14, 14)
        options_layout.setSpacing(8)

        opts_header = QHBoxLayout()
        lbl_opts_key = QLabel("АКТИВНЫЕ ОПЦИИ")
        lbl_opts_key.setObjectName("summaryKey")

        self.lbl_opts_count = QLabel("0 / 6")
        self.lbl_opts_count.setObjectName("summaryCount")

        opts_header.addWidget(lbl_opts_key)
        opts_header.addStretch(1)
        opts_header.addWidget(self.lbl_opts_count)

        self.lbl_options_list = QLabel("НЕТ АКТИВНЫХ ОПЦИЙ")
        self.lbl_options_list.setObjectName("summaryOptionsList")
        self.lbl_options_list.setWordWrap(True)
        self.lbl_options_list.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_options_list.setTextFormat(Qt.PlainText)

        options_layout.addLayout(opts_header)
        options_layout.addWidget(self.lbl_options_list)

        # Кнопки
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(8)

        self.btn_save = QPushButton("СОХРАНИТЬ")
        self.btn_save.setObjectName("primaryButton")
        self.btn_save.setMinimumHeight(48)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)

        self.btn_export = QPushButton("ЭКСПОРТ В JSON")
        self.btn_export.setObjectName("secondaryButton")
        self.btn_export.setMinimumHeight(42)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export)

        self.btn_reset = QPushButton("СБРОС")
        self.btn_reset.setObjectName("secondaryButton")
        self.btn_reset.setMinimumHeight(42)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._on_reset)

        buttons_layout.addWidget(self.btn_save)
        buttons_layout.addWidget(self.btn_export)
        buttons_layout.addWidget(self.btn_reset)

        content_layout.addWidget(mode_block)
        content_layout.addWidget(options_block, 1)
        content_layout.addLayout(buttons_layout)

        panel_layout.addWidget(content, 1)
        return panel

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(28)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        self.lbl_status = QLabel("ГОТОВО")
        self.lbl_status.setObjectName("statusText")

        self.lbl_hint = QLabel(
            "ALT+1..4 — РЕЖИМ  ·  CTRL+S — СОХРАНИТЬ  ·  CTRL+R — СБРОС"
        )
        self.lbl_hint.setObjectName("statusHint")

        layout.addWidget(self.lbl_status, 1)
        layout.addWidget(self.lbl_hint, 0)

        return bar

    # ============================================================ Handlers ==
    def _on_mode_toggled(self, key: str, checked: bool) -> None:
        if not checked:
            return
        if self._state.mode == key:
            return

        self._state.set_mode(key)
        self._update_option_availability()
        self._refresh_summary()
        self._update_dirty_state()
        self._log(f"РЕЖИМ: {self._state.mode_label()}")

    def _on_option_toggled(self, key: str, checked: bool) -> None:
        if not self._state.is_option_available(key):
            row = self._option_rows[key]
            row.checkbox.blockSignals(True)
            row.checkbox.setChecked(False)
            row.checkbox.blockSignals(False)
            self._log("ОПЦИЯ НЕДОСТУПНА В ЭТОМ РЕЖИМЕ")
            return

        self._state.set_option(key, checked)
        self._refresh_summary()
        self._update_dirty_state()

    def _update_option_availability(self) -> None:
        for key, row in self._option_rows.items():
            available = self._state.is_option_available(key)
            row.checkbox.setEnabled(available)
            if not available:
                row.lbl_status.setText("НЕДОСТУПНО")
                row.lbl_status.setProperty("state", "disabled")
                if self._state.options[key]:
                    self._state.set_option(key, False)
                    row.checkbox.blockSignals(True)
                    row.checkbox.setChecked(False)
                    row.checkbox.blockSignals(False)
            else:
                row.lbl_status.setText("")
                row.lbl_status.setProperty("state", "normal")
            row.lbl_status.style().unpolish(row.lbl_status)
            row.lbl_status.style().polish(row.lbl_status)

    def _refresh_summary(self) -> None:
        self.lbl_mode_value.setText(self._state.mode_label())
        self.lbl_mode_desc.setText(self._state.mode_description())

        enabled = self._state.enabled_options()
        count = len(enabled)
        total = len(OPTIONS)

        self.lbl_opts_count.setText(f"{count} / {total}")

        if not enabled:
            self.lbl_options_list.setText("НЕТ АКТИВНЫХ ОПЦИЙ")
            self.lbl_options_list.setProperty("state", "empty")
        else:
            lines = []
            for k in enabled:
                label = next((o[1] for o in OPTIONS if o[0] == k), k)
                lines.append(f"[✓]  {label.upper()}")
            self.lbl_options_list.setText("\n".join(lines))
            self.lbl_options_list.setProperty("state", "filled")

        self.lbl_options_list.style().unpolish(self.lbl_options_list)
        self.lbl_options_list.style().polish(self.lbl_options_list)

    def _update_dirty_state(self) -> None:
        current = self._state.to_dict()
        if self._saved_dict is None:
            self.lbl_state.setText("● НЕ СОХРАНЕНО")
            self.lbl_state.setProperty("state", "dirty")
        elif current != self._saved_dict:
            self.lbl_state.setText("● ИЗМЕНЕНО")
            self.lbl_state.setProperty("state", "dirty")
        else:
            self.lbl_state.setText("● СОХРАНЕНО")
            self.lbl_state.setProperty("state", "saved")
        self.lbl_state.style().unpolish(self.lbl_state)
        self.lbl_state.style().polish(self.lbl_state)

    def _sync_ui_from_state(self) -> None:
        for key, row in self._mode_rows.items():
            row.radio.blockSignals(True)
            row.radio.setChecked(key == self._state.mode)
            row.radio.blockSignals(False)

        for key, row in self._option_rows.items():
            row.checkbox.blockSignals(True)
            row.checkbox.setChecked(self._state.options[key])
            row.checkbox.blockSignals(False)

        self._update_option_availability()

    def _on_save(self) -> None:
        self._saved_dict = self._state.to_dict()
        self._save_settings()
        self._update_dirty_state()
        self._log(f"КОНФИГУРАЦИЯ СОХРАНЕНА: {self._state.mode_label()}")

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить конфигурацию",
            "panel_config.json",
            "JSON файлы (*.json);;Все файлы (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._state.to_dict(), f,
                          ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self._log(f"ЭКСПОРТ: {path}")

    def _on_reset(self) -> None:
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Сбросить конфигурацию к значениям по умолчанию?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._state = ConfigState()
        self._sync_ui_from_state()
        self._refresh_summary()
        self._update_dirty_state()
        self._log("СБРОС К ЗНАЧЕНИЯМ ПО УМОЛЧАНИЮ.")

    def _bind_shortcuts(self) -> None:
        for i, (key, _, _) in enumerate(MODES, start=1):
            QShortcut(QKeySequence(f"Alt+{i}"), self,
                      activated=lambda k=key: self._set_mode(k))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_reset)

    def _set_mode(self, key: str) -> None:
        if key in self._mode_rows:
            self._mode_rows[key].radio.setChecked(True)

    # ============================================================ Settings
    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("mode", self._state.mode)
        for k in self._state.options:
            s.setValue(f"option/{k}", self._state.options[k])

    def _load_settings(self) -> None:
        s = self._settings
        mode = s.value("mode", "auto")
        if mode in {m[0] for m in MODES}:
            self._state.set_mode(mode)
        for key, _ in OPTIONS:
            val = s.value(f"option/{key}", False)
            if isinstance(val, str):
                val = val.lower() == "true"
            self._state.set_option(key, bool(val))
        self._saved_dict = self._state.to_dict()

    # ================================================================ Стили
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            /* ================== Общие правила ================== */
            QMainWindow, QWidget#root {{
                background: {COLOR_BG};
                color: {COLOR_TEXT};
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

            /* ================== Верхняя строка ================== */
            QFrame#headerBar {{
                background: {COLOR_PANEL};
                border-bottom: 2px solid {COLOR_BORDER};
            }}
            QLabel#headerTitle {{
                font-size: 12pt;
                font-weight: 900;
                color: {COLOR_TEXT};
                letter-spacing: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
            }}
            QLabel#headerVersion {{
                font-size: 10pt;
                color: {COLOR_TEXT_MUTED};
                font-family: 'Consolas', monospace;
            }}
            QLabel#headerState {{
                font-size: 10pt;
                font-weight: 900;
                color: {COLOR_TEXT_MUTED};
                letter-spacing: 2px;
                font-family: 'Consolas', monospace;
            }}
            QLabel#headerState[state="saved"] {{
                color: {COLOR_ACCENT};
            }}
            QLabel#headerState[state="dirty"] {{
                color: {COLOR_WARNING};
            }}

            /* ================== Панели ================== */
            QFrame#panel {{
                background: {COLOR_PANEL};
                border: 1px solid {COLOR_BORDER};
            }}

            QFrame#sectionHeader {{
                background: {COLOR_PANEL_DARK};
                border-bottom: 1px solid {COLOR_BORDER};
            }}
            QLabel#sectionHeaderText {{
                color: {COLOR_ACCENT};
                font-size: 10pt;
                font-weight: 900;
                letter-spacing: 3px;
                font-family: 'Consolas', 'Courier New', monospace;
            }}

            QFrame#divider {{
                background: {COLOR_DIVIDER};
                border: none;
            }}

            /* ================== QScrollArea (без белого фона) ================== */
            QScrollArea, QScrollArea#optionsScroll {{
                background: {COLOR_PANEL};
                border: none;
            }}
            QScrollArea#optionsScroll > QWidget > QWidget {{
                background: {COLOR_PANEL};
            }}
            QWidget#optionsScrollContent {{
                background: {COLOR_PANEL};
            }}

            /* ================== Радиокнопки (режимы) ================== */
            QRadioButton#modeRadio {{
                color: {COLOR_TEXT};
                font-size: 11pt;
                font-weight: bold;
                letter-spacing: 1px;
                spacing: 10px;
                padding: 8px 6px;
                background: transparent;
            }}
            QRadioButton#modeRadio:hover {{
                color: {COLOR_ACCENT};
            }}
            QRadioButton#modeRadio::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {COLOR_BORDER_LIGHT};
                border-radius: 10px;
                background: {COLOR_PANEL_DARK};
            }}
            QRadioButton#modeRadio::indicator:hover {{
                border: 2px solid {COLOR_ACCENT};
            }}
            QRadioButton#modeRadio::indicator:checked {{
                border: 2px solid {COLOR_ACCENT};
                background: {COLOR_ACCENT};
            }}
            QRadioButton#modeRadio::indicator:disabled {{
                background: #1a1a1a;
                border: 2px solid #3a3a3a;
            }}
            QLabel#modeDesc {{
                color: {COLOR_TEXT_MUTED};
                font-size: 10pt;
                background: transparent;
            }}

            /* ================== Чекбоксы (опции) ================== */
            QCheckBox#optionCheckbox {{
                color: {COLOR_TEXT};
                font-size: 11pt;
                spacing: 10px;
                padding: 8px 4px;
                background: transparent;
            }}
            QCheckBox#optionCheckbox:hover {{
                color: {COLOR_ACCENT};
            }}
            QCheckBox#optionCheckbox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {COLOR_BORDER_LIGHT};
                background: {COLOR_PANEL_DARK};
            }}
            QCheckBox#optionCheckbox::indicator:hover {{
                border: 2px solid {COLOR_ACCENT};
            }}
            QCheckBox#optionCheckbox::indicator:checked {{
                background: {COLOR_ACCENT};
                border: 2px solid {COLOR_ACCENT};
            }}
            QCheckBox#optionCheckbox:disabled {{
                color: {COLOR_TEXT_DIM};
            }}
            QCheckBox#optionCheckbox::indicator:disabled {{
                background: #1a1a1a;
                border: 2px solid #3a3a3a;
            }}

            QLabel#optionStatus {{
                color: {COLOR_TEXT_MUTED};
                font-size: 9pt;
                font-family: 'Consolas', monospace;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#optionStatus[state="disabled"] {{
                color: {COLOR_WARNING};
            }}

            /* ================== Сводка ================== */
            QFrame#summaryBlock {{
                background: {COLOR_PANEL_DARK};
                border: 1px solid {COLOR_BORDER};
            }}
            QLabel#summaryKey {{
                color: {COLOR_TEXT_MUTED};
                font-size: 9pt;
                font-weight: bold;
                letter-spacing: 2px;
                font-family: 'Consolas', monospace;
                background: transparent;
            }}
            QLabel#summaryModeValue {{
                color: {COLOR_ACCENT};
                font-size: 16pt;
                font-weight: 900;
                letter-spacing: 2px;
                font-family: 'Consolas', 'Courier New', monospace;
                background: transparent;
            }}
            QLabel#summaryDesc {{
                color: {COLOR_TEXT_MUTED};
                font-size: 9pt;
                background: transparent;
            }}
            QLabel#summaryCount {{
                color: {COLOR_ACCENT};
                font-size: 12pt;
                font-weight: 900;
                font-family: 'Consolas', monospace;
                background: transparent;
            }}
            QLabel#summaryOptionsList {{
                color: {COLOR_TEXT};
                font-size: 10pt;
                font-family: 'Consolas', 'Courier New', monospace;
                background: transparent;
            }}
            QLabel#summaryOptionsList[state="empty"] {{
                color: {COLOR_TEXT_DIM};
                font-style: italic;
            }}

            /* ================== Кнопки ================== */
            QPushButton {{
                border-radius: 2px;
                padding: 8px 16px;
                font-size: 11pt;
                font-weight: 900;
                letter-spacing: 2px;
                font-family: 'Consolas', 'Courier New', monospace;
            }}
            QPushButton#primaryButton {{
                background: {COLOR_ACCENT};
                color: {COLOR_ACCENT_TEXT};
                border: 2px solid {COLOR_ACCENT};
            }}
            QPushButton#primaryButton:hover {{
                background: {COLOR_ACCENT_DARK};
                border: 2px solid {COLOR_ACCENT_DARK};
                color: #ffffff;
            }}
            QPushButton#primaryButton:pressed {{
                background: #15803d;
            }}

            QPushButton#secondaryButton {{
                background: {COLOR_PANEL};
                color: {COLOR_TEXT};
                border: 2px solid {COLOR_BORDER_LIGHT};
            }}
            QPushButton#secondaryButton:hover {{
                border: 2px solid {COLOR_ACCENT};
                color: {COLOR_ACCENT};
            }}
            QPushButton#secondaryButton:pressed {{
                background: {COLOR_PANEL_DARK};
            }}

            /* ================== Статус-бар ================== */
            QFrame#statusBar {{
                background: {COLOR_STATUS_BG};
                border-top: 1px solid {COLOR_BORDER};
            }}
            QLabel#statusText {{
                color: {COLOR_ACCENT};
                font-size: 10pt;
                font-weight: bold;
                font-family: 'Consolas', 'Courier New', monospace;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#statusHint {{
                color: {COLOR_TEXT_DIM};
                font-size: 9pt;
                font-family: 'Consolas', monospace;
                letter-spacing: 1px;
                background: transparent;
            }}

            /* ================== Скроллбар ================== */
            QScrollBar:vertical {{
                background: {COLOR_PANEL_DARK};
                width: 12px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_BORDER};
                min-height: 30px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLOR_BORDER_LIGHT};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                background: none; height: 0;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: none;
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

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = PanelConfiguratorApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())