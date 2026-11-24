from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from build_manager_config import (
    BUILD_MANAGER_INI_NAME,
    BuildManagerConfig,
    BuildManagerIniStore,
)
from build_manager_config_tab import ConfigTab

from build_target_general_tab import BuildTargetGeneralTab
from Common.log_settings_tab import LogSettingsTab


class SettingsWindow(QDialog):
    """General / Config / Log Settings 탭을 제공하는 세팅 윈도우."""

    settings_applied = Signal()

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
        ini_store: BuildManagerIniStore | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Build Manager 설정")
        self.resize(880, 740)

        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / BUILD_MANAGER_INI_NAME)
        )
        self.ini_store = ini_store or BuildManagerIniStore(self.config_path.parent)
        self.app_config_manager: BuildManagerConfig = self.ini_store.manager_cfg

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)

        self.general_tab = BuildTargetGeneralTab(
            project_root=self.project_root,
            config_path=self.config_path,
            parent=self,
        )
        self.config_tab = ConfigTab(config_manager=self.app_config_manager, parent=self)
        self.log_settings_tab = LogSettingsTab(self)

        self.tabs.addTab(self.general_tab, "General")
        self.tabs.addTab(self.config_tab, "Config")
        self.tabs.addTab(self.log_settings_tab, "Log Settings")

        layout.addWidget(self.tabs, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)

        self.btn_save_all = QPushButton("모두 저장 및 적용")
        self.btn_save_all.clicked.connect(self._on_save_all)

        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self._on_close_clicked)

        bottom_row.addWidget(self.btn_save_all)
        bottom_row.addWidget(self.btn_close)
        layout.addLayout(bottom_row)

    def _connect_signals(self) -> None:
        self.general_tab.paths_changed.connect(self._on_general_paths_changed)
        self.general_tab.load_requested.connect(self._on_general_load_requested)
        self.general_tab.save_requested.connect(self._on_general_save_requested)
        self.config_tab.config_changed.connect(self._on_child_config_changed)

    def _on_general_paths_changed(self, project_root: Path, config_path: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path).resolve()
        self.ini_store.reload_all(self.config_path.parent)
        self.app_config_manager = self.ini_store.manager_cfg
        self.config_tab.set_config_manager(self.app_config_manager)

    def _on_general_load_requested(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.ini_store.reload_all(self.config_path.parent)
        self.app_config_manager = self.ini_store.manager_cfg
        self.config_tab.set_config_manager(self.app_config_manager)
        sections = self.ini_store.load_target_sections()
        self.general_tab.set_dir_values(sections["dirs"])
        self.settings_applied.emit()

    def _on_general_save_requested(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.ini_store.reload_all(self.config_path.parent)
        dir_ov = self.general_tab.collect_dir_overrides()
        self.ini_store.save_target_sections(dir_values=dir_ov)
        self.settings_applied.emit()

    def _on_child_config_changed(self, _payload: dict[str, Any]) -> None:
        pass

    def _on_save_all(self) -> None:
        if hasattr(self, "general_tab"):
            self.project_root = Path(self.general_tab.project_root).resolve()
            self.config_path = self.general_tab.get_config_path_from_input()
            self.ini_store.reload_all(self.config_path.parent)
            self.app_config_manager = self.ini_store.manager_cfg
            self.config_tab.config_mgr = self.app_config_manager

        ok_cfg = self.config_tab.save_to_manager(silent=True)

        dir_ov = self.general_tab.collect_dir_overrides()
        self.ini_store.save_target_sections(dir_values=dir_ov)

        ok_log = False
        if hasattr(self.log_settings_tab, "save_settings") and callable(self.log_settings_tab.save_settings):
            try:
                self.log_settings_tab.save_settings()
                ok_log = True
            except Exception:
                pass
        elif hasattr(self.log_settings_tab, "config") and hasattr(self.log_settings_tab.config, "save"):
            try:
                self.log_settings_tab.config.save()
                ok_log = True
            except Exception:
                pass

        if ok_cfg or ok_log or dir_ov:
            self.settings_applied.emit()
        self.accept()
        self.hide()

    def _on_close_clicked(self) -> None:
        self.reject()
        self.hide()

    def closeEvent(self, event: Any) -> None:
        parent = self.parent()
        if parent is not None and getattr(parent, "_is_closing", False):
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()