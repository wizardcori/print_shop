from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from build_manager_config import BuildManagerConfig
from Common.config import ConfigType, FileConfigManager


class ConfigTab(QWidget):
    """[BuildManagerConfig] 섹션 설정을 표시·편집하는 탭[cite: 1]."""

    config_changed = Signal(dict)

    def __init__(
        self,
        config_manager: FileConfigManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_mgr: FileConfigManager = config_manager or BuildManagerConfig()
        self._editors: dict[str, QWidget] = {}

        self._build_ui()
        self.load_from_manager(show_error=False)

    def set_config_manager(self, config_manager: FileConfigManager) -> None:
        self.config_mgr = config_manager
        self.load_from_manager(show_error=False)

    def _create_editor_for_key(self, key: str, meta: dict[str, Any]) -> QWidget:
        cfg_type = meta.get("type", ConfigType.STRING)
        if cfg_type == ConfigType.BOOLEAN:
            return QCheckBox()
        if cfg_type == ConfigType.INTEGER:
            spin = QSpinBox()
            min_v = meta.get("min")
            max_v = meta.get("max")
            spin.setRange(
                int(min_v) if min_v is not None else -1_000_000,
                int(max_v) if max_v is not None else 1_000_000,
            )
            return spin
        if cfg_type == ConfigType.FLOAT:
            dspin = QDoubleSpinBox()
            min_v = meta.get("min")
            max_v = meta.get("max")
            dspin.setRange(
                float(min_v) if min_v is not None else -1_000_000.0,
                float(max_v) if max_v is not None else 1_000_000.0,
            )
            return dspin
        return QLineEdit()

    def _set_editor_value(self, editor: QWidget, cfg_type: Any, value: Any) -> None:
        if isinstance(editor, QCheckBox):
            editor.setChecked(bool(value))
        elif isinstance(editor, QSpinBox):
            editor.setValue(int(value or 0))
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value or 0.0))
        elif isinstance(editor, QLineEdit):
            if cfg_type in (ConfigType.LIST, ConfigType.DICT) and not isinstance(value, str):
                editor.setText(json.dumps(value, ensure_ascii=False))
            else:
                editor.setText("" if value is None else str(value))

    def _get_editor_value(self, editor: QWidget, cfg_type: Any) -> Any:
        if isinstance(editor, QCheckBox):
            return bool(editor.isChecked())
        if isinstance(editor, QSpinBox):
            return int(editor.value())
        if isinstance(editor, QDoubleSpinBox):
            return float(editor.value())
        if isinstance(editor, QLineEdit):
            txt = editor.text().strip()
            if cfg_type == ConfigType.LIST:
                if not txt:
                    return []
                try:
                    parsed = json.loads(txt)
                    return parsed if isinstance(parsed, list) else [parsed]
                except Exception:
                    return [x.strip() for x in txt.split(",") if x.strip()]
            if cfg_type == ConfigType.DICT:
                if not txt:
                    return {}
                parsed = json.loads(txt)
                if not isinstance(parsed, dict):
                    raise ValueError("DICT 형식(JSON 객체)이어야 합니다.")
                return parsed
            return txt
        return None

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        filepath_text = getattr(self.config_mgr, "filepath", "")
        section_text = getattr(self.config_mgr, "section", "")
        group = QGroupBox(f"Config 설정 ([{section_text}])")
        form = QFormLayout(group)

        self.lbl_filepath = QLineEdit(str(filepath_text))
        self.lbl_filepath.setReadOnly(True)
        form.addRow("설정 파일 경로", self.lbl_filepath)

        schema = getattr(self.config_mgr, "schema", {}) or {}
        for key, meta in schema.items():
            editor = self._create_editor_for_key(key, meta)
            self._editors[key] = editor
            form.addRow(key, editor)

        layout.addWidget(group)

        btn_row = QHBoxLayout()
        btn_reload = QPushButton("다시 불러오기")
        btn_reload.clicked.connect(lambda: self.load_from_manager(show_error=True))

        btn_save = QPushButton("Config 저장")
        btn_save.clicked.connect(lambda: self.save_to_manager(silent=False))

        btn_row.addWidget(btn_reload)
        btn_row.addWidget(btn_save)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addStretch(1)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def get_values(self) -> dict[str, Any]:
        schema = getattr(self.config_mgr, "schema", {}) or {}
        result: dict[str, Any] = {}
        for key, editor in self._editors.items():
            cfg_type = schema.get(key, {}).get("type", ConfigType.STRING)
            result[key] = self._get_editor_value(editor, cfg_type)
        return result

    def load_from_manager(self, *, show_error: bool = True) -> bool:
        try:
            if hasattr(self.config_mgr, "_load_and_inject"):
                self.config_mgr._load_and_inject()
            if hasattr(self, "lbl_filepath"):
                self.lbl_filepath.setText(str(getattr(self.config_mgr, "filepath", "")))

            schema = getattr(self.config_mgr, "schema", {}) or {}
            for key, editor in self._editors.items():
                cfg_type = schema.get(key, {}).get("type", ConfigType.STRING)
                val = self.config_mgr.get(key)
                self._set_editor_value(editor, cfg_type, val)

            self.config_changed.emit(self.get_values())
            return True
        except Exception as exc:
            if show_error:
                QMessageBox.critical(self, "Config 불러오기 실패", f"설정을 불러오지 못했습니다:\n{exc}")
            return False

    def save_to_manager(self, *, silent: bool = False) -> bool:
        try:
            values = self.get_values()
            for key, val in values.items():
                self.config_mgr.set(key, val)
            if hasattr(self.config_mgr, "save"):
                self.config_mgr.save()
            self.config_changed.emit(values)
            if not silent:
                QMessageBox.information(
                    self,
                    "Config 저장",
                    f"설정을 저장했습니다:\n{getattr(self.config_mgr, 'filepath', '')}",
                )
            return True
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Config 저장 실패", f"설정을 저장하지 못했습니다:\n{exc}")
            return False