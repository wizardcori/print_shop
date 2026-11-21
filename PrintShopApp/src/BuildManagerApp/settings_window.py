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

from build_manager_config_tab import BuildManagerConfig, ConfigTab
from build_target_config_tab import BuildTargetConfigTab
from build_target_general_tab import BuildTargetGeneralTab
from Common.log_settings_tab import LogSettingsTab


class SettingsWindow(QDialog):
    """General / Log Settings / Config / Build Targets 탭을 제공하는 세팅 윈도우."""

    settings_applied = Signal()

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
        app_config_manager: BuildManagerConfig | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Build Manager 설정")
        self.resize(880, 740)

        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path).resolve() if config_path else None
        if app_config_manager is not None:
            self.app_config_manager = app_config_manager
        else:
            mgr = BuildManagerConfig()
            mgr.file_dir = str(self.project_root)
            if hasattr(mgr, "_load_and_inject") and callable(mgr._load_and_inject):
                try:
                    mgr._load_and_inject()
                except Exception:
                    pass
            self.app_config_manager = mgr

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)

        # 0. General 탭 (경로 및 설정 파일 / 전역 빌드 디렉터리 dirs)
        self.general_tab = BuildTargetGeneralTab(
            project_root=self.project_root,
            config_path=self.config_path,
            parent=self,
        )

        # 1. Log Settings 탭
        self.log_settings_tab = LogSettingsTab(self)

        # 2. Config 탭 (config.py의 FileConfigManager 상속 자체 설정 파일)
        self.config_tab = ConfigTab(config_manager=self.app_config_manager, parent=self)

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
        self.config_tab.config_changed.connect(self._on_child_config_changed)

    def _on_general_paths_changed(self, project_root: Path, config_path: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path).resolve()

    def _on_save_build_targets_requested(self) -> None:
        saved = self.build_target_config_tab.save_to_json(silent=False)
        if saved is not None:
            self.project_root = self.build_target_config_tab.project_root
            self.config_path = self.build_target_config_tab.config_path
            self.settings_applied.emit()

    def _on_child_config_changed(self, _payload: dict[str, Any]) -> None:
        pass

    def _on_save_all(self) -> None:
        if hasattr(self, "general_tab"):
            self.project_root = self.general_tab.project_root
            self.config_path = self.general_tab.get_config_path_from_input()
            self.build_target_config_tab.set_paths(self.project_root, self.config_path)

        ok_cfg = self.config_tab.save_to_manager(silent=True)
        saved_json = self.build_target_config_tab.save_to_json(silent=True)
        if hasattr(self.log_settings_tab, "save_settings") and callable(self.log_settings_tab.save_settings):
            try:
                self.log_settings_tab.save_settings()
            except Exception:
                pass
        elif hasattr(self.log_settings_tab, "config") and hasattr(self.log_settings_tab.config, "save"):
            try:
                self.log_settings_tab.config.save()
            except Exception:
                pass

        self.project_root = self.build_target_config_tab.project_root
        self.config_path = self.build_target_config_tab.config_path

        if ok_cfg or saved_json is not None:
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