from __future__ import annotations

import ast
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Common.config import ConfigType, FileConfigManager
from Common.log import FileTagManager, loge
from Common.logger_service import update_all_feature_loggers_format
from Common.path_mgr import PathMgr
from Common.settings_registry import register_settings_tab


class BaseLogConfig(FileConfigManager):
    """로그 포맷, 경로 정렬 및 모듈/레벨 동적 설정 관리 Base 클래스."""

    app_name: Optional[str] = None
    filename: Optional[str] = None
    section = "LogConfig"
    section_order = 21
    schema = {
        "show_time": {"default": True, "type": ConfigType.BOOLEAN},
        "show_level": {"default": True, "type": ConfigType.BOOLEAN},
        "show_dir": {"default": True, "type": ConfigType.BOOLEAN},
        "show_file": {"default": False, "type": ConfigType.BOOLEAN},
        "show_line": {"default": True, "type": ConfigType.BOOLEAN},
        "show_tag": {"default": True, "type": ConfigType.BOOLEAN},
        "enable_color_file": {"default": True, "type": ConfigType.BOOLEAN},
        "enable_global_log": {"default": True, "type": ConfigType.BOOLEAN},
        "enable_global_color_file": {"default": True, "type": ConfigType.BOOLEAN},
        "path_style": {"default": "relative", "type": ConfigType.STRING},
        "fixed_width_size": {"default": 48, "type": ConfigType.INTEGER},
        "enable_tabular_alignment": {"default": True, "type": ConfigType.BOOLEAN},
        "level_enabled": {
            "default": {
                "DEBUG": True,
                "INFO": True,
                "WARNING": True,
                "ERROR": True,
                "CRITICAL": True,
            },
            "type": ConfigType.DICT,
        },
        "module_enabled": {"default": {}, "type": ConfigType.DICT},
        "module_min_level": {"default": {}, "type": ConfigType.DICT},
        "custom_log_levels": {"default": {}, "type": ConfigType.DICT},
    }

    _app_config_classes: dict[tuple[str, str], type["BaseLogConfig"]] = {}

    @staticmethod
    def _ensure_ini_ext(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            cleaned = "app"
        return cleaned if cleaned.lower().endswith(".ini") else f"{cleaned}.ini"

    @classmethod
    def resolve_app_name(cls) -> str:
        resolved = (cls.app_name or getattr(PathMgr, "APP_NAME", "") or "app").strip()
        return resolved or "app"

    @classmethod
    def resolve_ini_filename(cls) -> str:
        if cls.filename and str(cls.filename).strip():
            return cls._ensure_ini_ext(str(cls.filename))
        return cls._ensure_ini_ext(cls.resolve_app_name())

    @classmethod
    def get_config_for_app(
        cls,
        app_name: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> "BaseLogConfig":
        """클래스 속성 app_name / filename 기준으로 싱글톤 설정 인스턴스를 반환합니다."""
        target_app = (
            app_name
            or cls.app_name
            or getattr(PathMgr, "APP_NAME", "")
            or "app"
        ).strip() or "app"

        raw_file = (
            filename
            if (filename is not None and str(filename).strip())
            else (cls.filename if (cls.filename and str(cls.filename).strip()) else "")
        )
        ini_name = (
            cls._ensure_ini_ext(str(raw_file))
            if raw_file
            else cls._ensure_ini_ext(target_app)
        )

        cache_key = (target_app, ini_name)
        sub_cls = cls._app_config_classes.get(cache_key)
        if sub_cls is None:
            safe_suffix = "".join(
                ch if ch.isalnum() or ch == "_" else "_" for ch in f"{target_app}_{ini_name}"
            )
            sub_cls = type(
                f"{cls.__name__}_{safe_suffix}",
                (cls,),
                {
                    "app_name": target_app,
                    "filename": ini_name,
                    "file_name": ini_name,
                },
            )
            cls._app_config_classes[cache_key] = sub_cls

        return sub_cls()

    def __init__(self) -> None:
        resolved_app = self.__class__.resolve_app_name()
        resolved_ini = self.__class__.resolve_ini_filename()
        self.__class__.app_name = resolved_app
        self.__class__.filename = resolved_ini
        self.__class__.file_name = resolved_ini

        super().__init__()
        self.sync_with_file_tag_manager(prune_missing=False)

    def sync_with_file_tag_manager(self, prune_missing: bool = False) -> None:
        """log.py에 등록된 FileTagManager 모듈 목록과 LogConfig 설정을 동기화합니다."""
        try:
            from Common.log import FileTagManager

            file_modules = FileTagManager.get_module_enabled()
            if not isinstance(file_modules, dict):
                return

            current_mod_cfg = self.str_to_dict(self.get("module_enabled"))
            if not isinstance(current_mod_cfg, dict):
                current_mod_cfg = {}

            updated = False

            for mod, is_enabled in file_modules.items():
                tag = str(mod).strip().upper()
                if tag and tag not in current_mod_cfg:
                    current_mod_cfg[tag] = bool(is_enabled)
                    updated = True

            if prune_missing:
                allowed_tags = {str(m).strip().upper() for m in file_modules if str(m).strip()}
                keys_to_remove = [mod for mod in current_mod_cfg if mod not in allowed_tags]
                for mod in keys_to_remove:
                    del current_mod_cfg[mod]
                    updated = True

            if updated:
                self.set("module_enabled", current_mod_cfg)
                if hasattr(self, "save"):
                    try:
                        self.save()
                    except Exception:
                        pass
        except ImportError:
            pass

    def save_runtime_config(self, updates: dict[str, Any] | None = None) -> None:
        """프로그램 실행 중 변경된 설정을 적용하고 INI 파일에 저장합니다."""
        if isinstance(updates, dict):
            for key, value in updates.items():
                self.set(key, value)
        self.save()

    def reload_from_disk(self, prune_missing: bool = False) -> None:
        """저장된 INI 파일에서 LogConfig 값을 다시 로드합니다."""
        self.config = self._create_parser()
        self._load_and_inject()
        self.sync_with_file_tag_manager(prune_missing=prune_missing)

    def build_format_string(self) -> str:
        """설정된 요소들을 조합하여 logging 포맷 스트링 생성."""
        parts = []

        if self.get("show_time"):
            parts.append("%(asctime)s")
        if self.get("show_level"):
            parts.append("%(levelname)-8s")

        show_dir = self.get("show_dir")
        show_file = self.get("show_file")
        show_line = self.get("show_line")

        if show_dir or show_file or show_line:
            parts.append("%(fixed_path)s")

        if self.get("show_tag"):
            parts.append("[%(tag)s]")

        parts.append("%(message)s")

        return " | ".join(parts)

    @classmethod
    def str_to_dict(cls, str_data: Any) -> dict:
        if isinstance(str_data, str):
            try:
                map_data = ast.literal_eval(str_data)
            except (ValueError, SyntaxError):
                map_data = {}
        elif isinstance(str_data, dict):
            map_data = str_data
        else:
            map_data = {}

        return map_data if isinstance(map_data, dict) else {}

    def is_level_enabled(self, level: str) -> bool:
        """로그 레벨이 활성화(True)되어 있는지 확인."""
        saved_lvl_raw = self.get("level_enabled")
        saved_lvl = (
            self.str_to_dict(saved_lvl_raw)
            if isinstance(saved_lvl_raw, str)
            else (saved_lvl_raw or {})
        )
        return bool(saved_lvl.get(level.upper(), False))

    def is_module_enabled(self, current_mods: Any) -> bool:
        """전달된 모듈(태그) 중 단 하나라도 활성화(True)되어 있는지 확인."""
        if isinstance(current_mods, str):
            current_mods = [current_mods]
        elif not isinstance(current_mods, (list, tuple, set)):
            return False

        saved_mod_raw = self.get("module_enabled")
        saved_mod = (
            self.str_to_dict(saved_mod_raw)
            if isinstance(saved_mod_raw, str)
            else (saved_mod_raw or {})
        )
        return any(bool(saved_mod.get(str(m).strip().upper(), False)) for m in current_mods)


def get_log_config(
    app_name: Optional[str] = None,
    filename: Optional[str] = None,
) -> BaseLogConfig:
    """앱 이름 또는 INI 파일명 기준으로 LogConfig 인스턴스를 반환합니다."""
    return BaseLogConfig.get_config_for_app(app_name=app_name, filename=filename)


class BaseLogSettingsTab(QWidget):
    """PySide6 로그 설정 탭 Base 클래스."""

    app_name: Optional[str] = None
    filename: Optional[str] = None
    config_cls: type[BaseLogConfig] = BaseLogConfig

    auto_register: bool = True
    tab_id: Optional[str] = None
    tab_title: str = "Log Settings"
    tab_order: int = 90

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "auto_register", True):
            return

        slug_source = (
            cls.tab_id
            or cls.app_name
            or getattr(PathMgr, "APP_NAME", "")
            or cls.__name__
        )
        slug = "".join(
            ch.lower() if ch.isalnum() or ch == "-" else "-"
            for ch in str(slug_source).strip()
        ).strip("-")
        resolved_id = cls.tab_id or (f"log-settings-{slug}" if slug else "log-settings")
        resolved_title = cls.tab_title or "Log Settings"
        resolved_order = int(getattr(cls, "tab_order", 90))

        try:
            register_settings_tab(resolved_id, resolved_title, cls, order=resolved_order)
        except Exception as e:
            try:
                loge(f"Failed to auto-register settings tab {cls.__name__}: {e}")
            except Exception:
                pass

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = self.get_log_config()

        self.level_checkboxes: dict[str, QCheckBox] = {}
        self.module_checkboxes: dict[str, QCheckBox] = {}
        self.module_item_width = 72
        self._block_signals = False
        self._last_module_cols = 0

        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.init_ui()

    @classmethod
    def get_log_config(cls) -> BaseLogConfig:
        """탭 클래스에 지정된 app_name / filename 기준으로 LogConfig를 반환합니다."""
        resolved_app = (
            cls.app_name
            or cls.config_cls.app_name
            or getattr(PathMgr, "APP_NAME", "")
            or None
        )
        resolved_file = cls.filename or cls.config_cls.filename or None
        if resolved_app or resolved_file:
            return cls.config_cls.get_config_for_app(
                app_name=resolved_app,
                filename=resolved_file,
            )
        return cls.config_cls()

    def _get_merged_module_cfg(self, persist_if_missing: bool = False) -> dict[str, bool]:
        """저장된 module_enabled 설정과 FileTagManager에 등록된 모듈 태그를 병합합니다."""
        saved_module_cfg = BaseLogConfig.str_to_dict(self.config.get("module_enabled"))
        merged: dict[str, bool] = {}

        if isinstance(saved_module_cfg, dict):
            for mod, is_checked in saved_module_cfg.items():
                tag = str(mod).strip().upper()
                if tag:
                    merged[tag] = bool(is_checked)

        mgr_modules = FileTagManager.get_module_enabled()
        added_new = False
        if isinstance(mgr_modules, dict):
            for mod, is_checked in mgr_modules.items():
                tag = str(mod).strip().upper()
                if not tag:
                    continue
                if tag not in merged:
                    merged[tag] = bool(is_checked)
                    added_new = True

        if not merged and isinstance(mgr_modules, dict):
            merged = {
                str(k).strip().upper(): bool(v)
                for k, v in mgr_modules.items()
                if str(k).strip()
            }
            added_new = bool(merged)

        if persist_if_missing and added_new and hasattr(self.config, "set"):
            prev_auto_save = getattr(self.config, "auto_save", True)
            try:
                self.config.auto_save = False
                self.config.set("module_enabled", merged)
                if hasattr(self.config, "save_runtime_config"):
                    self.config.save_runtime_config()
                elif hasattr(self.config, "save"):
                    self.config.save()
            finally:
                self.config.auto_save = prev_auto_save

        return merged

    def _collect_module_cfg_from_ui(self) -> dict[str, bool]:
        """현재 UI 체크박스 상태를 기준으로 module_enabled 딕셔너리를 구성합니다."""
        cfg: dict[str, bool] = {}
        for mod, cb in self.module_checkboxes.items():
            tag = str(mod).strip().upper()
            if tag:
                cfg[tag] = bool(cb.isChecked())
        return cfg

    def _create_module_checkbox(self, mod: str, is_checked: bool) -> QCheckBox:
        cb = QCheckBox(mod)
        cb.setMinimumWidth(0)
        cb.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        cb.blockSignals(True)
        cb.setChecked(bool(is_checked))
        cb.blockSignals(False)
        cb.stateChanged.connect(lambda state, c=cb, m=mod: self.on_module_toggle(m, c.isChecked()))
        return cb

    def _recalc_module_item_width(self) -> None:
        max_cb_width = 0
        for cb in self.module_checkboxes.values():
            cb_width = cb.sizeHint().width() + 10
            if cb_width > max_cb_width:
                max_cb_width = cb_width
        self.module_item_width = max(min(max_cb_width, 130), 68)

    def sync_module_checkboxes(self, force_relayout: bool = False) -> None:
        """새로 등록된 모듈 태그를 반영해 체크박스를 동적으로 생성/동기화합니다."""
        merged_cfg = self._get_merged_module_cfg(persist_if_missing=True)
        if not merged_cfg:
            return

        prev_block = self._block_signals
        self._block_signals = True
        structure_changed = False

        try:
            for mod, is_checked in merged_cfg.items():
                if mod not in self.module_checkboxes:
                    self.module_checkboxes[mod] = self._create_module_checkbox(mod, is_checked)
                    structure_changed = True
                else:
                    cb = self.module_checkboxes[mod]
                    if cb.isChecked() != bool(is_checked):
                        cb.setChecked(bool(is_checked))
        finally:
            self._block_signals = prev_block

        self._recalc_module_item_width()
        if structure_changed or force_relayout:
            self._last_module_cols = 0
            self.relayout_modules()
        self.update_all_checks_state()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        title_lbl = QLabel("<h3>Log Display & Alignment Settings</h3>")
        title_lbl.setMinimumWidth(0)
        main_layout.addWidget(title_lbl)

        format_group = QGroupBox("Log Format Elements (포맷 표시 요소)")
        format_group.setMinimumWidth(0)
        format_layout = QGridLayout()
        format_layout.setHorizontalSpacing(8)
        format_layout.setVerticalSpacing(6)

        self.cb_show_time = QCheckBox("Show Time (시간 표시)")
        self.cb_show_time.setChecked(bool(self.config.get("show_time")))
        self.cb_show_time.stateChanged.connect(
            lambda: self.on_setting_changed("show_time", self.cb_show_time.isChecked())
        )

        self.cb_show_level = QCheckBox("Show Level (로그 레벨 표시)")
        self.cb_show_level.setChecked(bool(self.config.get("show_level")))
        self.cb_show_level.stateChanged.connect(
            lambda: self.on_setting_changed("show_level", self.cb_show_level.isChecked())
        )

        self.cb_show_dir = QCheckBox("Show Directory (디렉토리 경로 표시)")
        self.cb_show_dir.setChecked(bool(self.config.get("show_dir")))
        self.cb_show_dir.stateChanged.connect(
            lambda: self.on_setting_changed("show_dir", self.cb_show_dir.isChecked())
        )

        self.cb_show_file = QCheckBox("Show File Name (파일명 표시)")
        self.cb_show_file.setChecked(bool(self.config.get("show_file")))
        self.cb_show_file.stateChanged.connect(
            lambda: self.on_setting_changed("show_file", self.cb_show_file.isChecked())
        )

        self.cb_show_line = QCheckBox("Show Line Number (라인 번호 표시)")
        self.cb_show_line.setChecked(bool(self.config.get("show_line")))
        self.cb_show_line.stateChanged.connect(
            lambda: self.on_setting_changed("show_line", self.cb_show_line.isChecked())
        )

        self.cb_show_tag = QCheckBox("Show Tag (태그 표시)")
        self.cb_show_tag.setChecked(bool(self.config.get("show_tag")))
        self.cb_show_tag.stateChanged.connect(
            lambda: self.on_setting_changed("show_tag", self.cb_show_tag.isChecked())
        )

        format_checkboxes = [
            self.cb_show_time,
            self.cb_show_level,
            self.cb_show_dir,
            self.cb_show_file,
            self.cb_show_line,
            self.cb_show_tag,
        ]
        for idx, cb in enumerate(format_checkboxes):
            cb.setMinimumWidth(0)
            cb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            format_layout.addWidget(cb, idx // 2, idx % 2)

        format_group.setLayout(format_layout)
        main_layout.addWidget(format_group)

        level_group = QGroupBox("Log Level Filter (레벨별 로그 출력 선택)")
        level_group.setMinimumWidth(0)
        level_layout = QVBoxLayout()
        level_layout.setSpacing(6)

        self.cb_all_levels = QCheckBox("All Check (전체 선택/해제)")
        self.cb_all_levels.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.cb_all_levels.stateChanged.connect(self.toggle_all_levels)
        level_layout.addWidget(self.cb_all_levels)

        level_grid = QGridLayout()
        level_grid.setHorizontalSpacing(8)
        level_grid.setVerticalSpacing(4)

        saved_level_cfg = BaseLogConfig.str_to_dict(self.config.get("level_enabled"))
        if not isinstance(saved_level_cfg, dict) or not saved_level_cfg:
            saved_level_cfg = FileTagManager.get_level_enabled()
            if isinstance(saved_level_cfg, dict) and saved_level_cfg and hasattr(self.config, "set"):
                prev_auto_save = getattr(self.config, "auto_save", True)
                try:
                    self.config.auto_save = False
                    self.config.set("level_enabled", saved_level_cfg)
                    if hasattr(self.config, "save_runtime_config"):
                        self.config.save_runtime_config()
                    elif hasattr(self.config, "save"):
                        self.config.save()
                finally:
                    self.config.auto_save = prev_auto_save

        for idx, (lvl, is_checked) in enumerate(saved_level_cfg.items()):
            cb = QCheckBox(lvl)
            cb.setMinimumWidth(0)
            cb.setChecked(bool(is_checked))
            cb.stateChanged.connect(lambda state, c=cb, l=lvl: self.on_level_toggle(l, c.isChecked()))
            self.level_checkboxes[lvl] = cb
            level_grid.addWidget(cb, idx // 5, idx % 5)

        level_layout.addLayout(level_grid)
        level_group.setLayout(level_layout)
        main_layout.addWidget(level_group)

        self.module_group = QGroupBox("Module / Tag Filter (모듈별 로그 출력 선택)")
        self.module_group.setMinimumWidth(0)
        module_layout = QVBoxLayout()
        module_layout.setSpacing(6)

        self.cb_all_modules = QCheckBox("All Check (전체 선택/해제)")
        self.cb_all_modules.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.cb_all_modules.stateChanged.connect(self.toggle_all_modules)
        module_layout.addWidget(self.cb_all_modules)

        self.module_grid = QGridLayout()
        self.module_grid.setHorizontalSpacing(8)
        self.module_grid.setVerticalSpacing(4)

        merged_module_cfg = self._get_merged_module_cfg(persist_if_missing=True)
        for mod, is_checked in merged_module_cfg.items():
            self.module_checkboxes[mod] = self._create_module_checkbox(mod, is_checked)

        self._recalc_module_item_width()
        self.relayout_modules()

        module_layout.addLayout(self.module_grid)
        self.module_group.setLayout(module_layout)
        main_layout.addWidget(self.module_group)

        behavior_group = QGroupBox("Log Output Options (출력 대상 설정)")
        behavior_group.setMinimumWidth(0)
        behavior_layout = QGridLayout()
        behavior_layout.setHorizontalSpacing(8)
        behavior_layout.setVerticalSpacing(6)

        self.cb_color_file = QCheckBox("Enable Color File Output (개별 컬러 파일 출력)")
        self.cb_color_file.setChecked(bool(self.config.get("enable_color_file")))
        self.cb_color_file.stateChanged.connect(
            lambda: self.on_setting_changed("enable_color_file", self.cb_color_file.isChecked())
        )

        self.cb_global_log = QCheckBox("Enable Global Log Output (전체 통합 로그 log_all 출력)")
        self.cb_global_log.setChecked(bool(self.config.get("enable_global_log")))
        self.cb_global_log.stateChanged.connect(
            lambda: self.on_setting_changed("enable_global_log", self.cb_global_log.isChecked())
        )

        self.cb_global_color_file = QCheckBox(
            "Enable Global Color File Output (전체 통합 컬러 파일 출력)"
        )
        self.cb_global_color_file.setChecked(bool(self.config.get("enable_global_color_file")))
        self.cb_global_color_file.stateChanged.connect(
            lambda: self.on_setting_changed(
                "enable_global_color_file", self.cb_global_color_file.isChecked()
            )
        )

        for idx, cb in enumerate(
            [self.cb_color_file, self.cb_global_log, self.cb_global_color_file]
        ):
            cb.setMinimumWidth(0)
            cb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            behavior_layout.addWidget(cb, idx, 0)

        behavior_group.setLayout(behavior_layout)
        main_layout.addWidget(behavior_group)

        align_group = QGroupBox("Path Alignment & Style Options (경로 정렬 및 표출 방식)")
        align_group.setMinimumWidth(0)
        align_layout = QVBoxLayout()
        align_layout.setSpacing(6)

        path_style_layout = QHBoxLayout()
        path_style_layout.setSpacing(8)
        lbl_style = QLabel("Path Style (경로 표시 방식):")
        lbl_style.setMinimumWidth(0)
        path_style_layout.addWidget(lbl_style, stretch=0)

        self.combo_path_style = QComboBox()
        self.combo_path_style.setMinimumWidth(0)
        self.combo_path_style.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.combo_path_style.addItem("Relative Path (상대 경로)", "relative")
        self.combo_path_style.addItem("Absolute Path (절대 경로)", "absolute")
        self.combo_path_style.addItem("Fixed-Width Truncated (고정폭 엘리시스)", "fixed")

        current_style = self.config.get("path_style") or "relative"
        index = self.combo_path_style.findData(current_style)
        if index >= 0:
            self.combo_path_style.setCurrentIndex(index)
        self.combo_path_style.currentIndexChanged.connect(
            lambda: self.on_setting_changed("path_style", self.combo_path_style.currentData())
        )
        path_style_layout.addWidget(self.combo_path_style, stretch=1)
        align_layout.addLayout(path_style_layout)

        width_layout = QHBoxLayout()
        width_layout.setSpacing(8)
        lbl_width = QLabel("Fixed Width Size (고정폭 정렬 글자수):")
        lbl_width.setMinimumWidth(0)
        width_layout.addWidget(lbl_width, stretch=0)

        self.spin_width = QSpinBox()
        self.spin_width.setMinimumWidth(64)
        self.spin_width.setRange(20, 100)
        self.spin_width.setValue(int(self.config.get("fixed_width_size") or 48))
        self.spin_width.valueChanged.connect(
            lambda: self.on_setting_changed("fixed_width_size", self.spin_width.value())
        )
        width_layout.addWidget(self.spin_width, stretch=0)
        width_layout.addStretch(1)
        align_layout.addLayout(width_layout)

        self.cb_tabular = QCheckBox("Enable Tabular Vertical Alignment (구분자 일직선 정렬)")
        self.cb_tabular.setMinimumWidth(0)
        self.cb_tabular.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.cb_tabular.setChecked(bool(self.config.get("enable_tabular_alignment")))
        self.cb_tabular.stateChanged.connect(
            lambda: self.on_setting_changed(
                "enable_tabular_alignment", self.cb_tabular.isChecked()
            )
        )
        align_layout.addWidget(self.cb_tabular)

        align_group.setLayout(align_layout)
        main_layout.addWidget(align_group)

        preview_group = QGroupBox("Log Output Preview (미리보기)")
        preview_group.setMinimumWidth(0)
        preview_layout = QVBoxLayout()

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMinimumWidth(0)
        self.preview_edit.setFixedHeight(140)
        self.preview_edit.setStyleSheet(
            "background-color: #1e1e1e; "
            "color: #d4d4d4; "
            "font-family: Consolas, 'Courier New', monospace; "
            "font-size: 10pt;"
        )
        preview_layout.addWidget(self.preview_edit)
        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)

        self.update_all_checks_state()
        self.update_preview()
        main_layout.addStretch()

    def save_settings(self) -> None:
        """현재 UI 상태를 config에 반영하고 디스크에 저장합니다."""
        mod_cfg = self._collect_module_cfg_from_ui()
        if mod_cfg:
            FileTagManager.set_module_enabled(mod_cfg)
            self.config.set("module_enabled", mod_cfg)
        if hasattr(self.config, "save_runtime_config"):
            self.config.save_runtime_config()
        elif hasattr(self.config, "save"):
            self.config.save()

    def relayout_modules(self) -> None:
        if not self.module_checkboxes:
            return

        w = self.module_group.width() if self.module_group.width() > 40 else self.width()
        available_width = max(120, w - 36)
        spacing = self.module_grid.horizontalSpacing()
        if spacing < 0:
            spacing = 8

        max_cols = max(1, (available_width + spacing) // (self.module_item_width + spacing))

        if max_cols == self._last_module_cols:
            return
        self._last_module_cols = max_cols

        while self.module_grid.count():
            item = self.module_grid.takeAt(0)
            if item.widget():
                self.module_grid.removeWidget(item.widget())

        for idx, cb in enumerate(self.module_checkboxes.values()):
            row = idx // max_cols
            col = idx % max_cols
            self.module_grid.addWidget(cb, row, col)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.sync_module_checkboxes(force_relayout=True)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.relayout_modules()

    def toggle_all_levels(self, state: Any) -> None:
        if self._block_signals:
            return
        is_checked = state == Qt.Checked or state == 2 or state is True
        self._block_signals = True
        level_cfg = {}
        for lvl, cb in self.level_checkboxes.items():
            if cb:
                cb.setChecked(is_checked)
            level_cfg[lvl] = is_checked
        self._block_signals = False
        self.on_setting_changed("level_enabled", level_cfg)

    def on_level_toggle(self, level: str, is_checked: bool) -> None:
        if self._block_signals:
            return
        lvl_cfg = self.config.get("level_enabled")
        lvl_cfg = BaseLogConfig.str_to_dict(lvl_cfg)

        if not isinstance(lvl_cfg, dict):
            lvl_cfg = FileTagManager.get_level_enabled()

        lvl_cfg[level] = is_checked
        self.on_setting_changed("level_enabled", lvl_cfg)
        self.update_all_checks_state()

    def on_module_toggle(self, module: str, is_checked: bool) -> None:
        if self._block_signals:
            return
        tag = str(module).strip().upper()
        if not tag:
            return
        mod_cfg = self._collect_module_cfg_from_ui()
        mod_cfg[tag] = bool(is_checked)
        FileTagManager.set_module_enabled({tag: bool(is_checked)})
        self.on_setting_changed("module_enabled", mod_cfg)
        self.update_all_checks_state()

    def toggle_all_modules(self, state: Any) -> None:
        if self._block_signals:
            return
        is_checked = state == Qt.Checked or state == 2 or state is True
        self._block_signals = True
        mod_cfg: dict[str, bool] = {}
        for mod, cb in self.module_checkboxes.items():
            cb.setChecked(is_checked)
            tag = str(mod).strip().upper()
            if tag:
                mod_cfg[tag] = bool(is_checked)
        self._block_signals = False
        FileTagManager.set_module_enabled(mod_cfg)
        self.on_setting_changed("module_enabled", mod_cfg)

    def update_all_checks_state(self) -> None:
        self._block_signals = True
        all_lvl_checked = all(cb.isChecked() for cb in self.level_checkboxes.values())
        self.cb_all_levels.setChecked(all_lvl_checked)
        all_mod_checked = bool(self.module_checkboxes) and all(
            cb.isChecked() for cb in self.module_checkboxes.values()
        )
        self.cb_all_modules.setChecked(all_mod_checked)
        self._block_signals = False

    def on_setting_changed(self, key: str, value: Any) -> None:
        if hasattr(self.config, "set"):
            self.config.set(key, value)

        try:
            if hasattr(self.config, "save_runtime_config"):
                self.config.save_runtime_config()
            elif hasattr(self.config, "save"):
                self.config.save()
        except Exception as e:
            loge(f"Failed to save config: {e}")

        try:
            update_all_feature_loggers_format()
        except Exception:
            pass

        try:
            from Common.log import LoggerManager

            LoggerManager.update_all_logger_formats()
        except Exception:
            pass

        self.update_preview()

    def update_preview(self) -> None:
        show_time = self.cb_show_time.isChecked()
        show_level = self.cb_show_level.isChecked()
        show_dir = self.cb_show_dir.isChecked()
        show_file = self.cb_show_file.isChecked()
        show_line = self.cb_show_line.isChecked()
        show_tag = self.cb_show_tag.isChecked()

        path_style = self.combo_path_style.currentData() or "relative"
        width = self.spin_width.value()
        is_tabular = self.cb_tabular.isChecked()

        dir_part = "PrintShopApp/src/Common/"
        file_part = "settings_dialog.py"
        line_part = ":66"
        if path_style == "absolute":
            dir_part = "C:/1print_shop/PrintShopApp/src/Common/"

        raw_path_parts = []
        if show_dir:
            raw_path_parts.append(dir_part)
        if show_file:
            raw_path_parts.append(file_part)
        if show_line:
            raw_path_parts.append(line_part)

        combined_path = "".join(raw_path_parts)
        if combined_path:
            if path_style == "fixed":
                formatted_path = (
                    ("..." + combined_path[-(width - 3) :])
                    if len(combined_path) > width
                    else combined_path.ljust(width)
                )
            else:
                formatted_path = combined_path
        else:
            formatted_path = ""

        level_colors = {
            "DEBUG": QColor("#569CD6"),
            "INFO": QColor("#4EC9B0"),
            "WARNING": QColor("#CE9178"),
            "ERROR": QColor("#F44747"),
            "CRITICAL": QColor("#FF00FF"),
        }

        default_format = QTextCharFormat()
        default_format.setForeground(QColor("#D4D4D4"))
        time_format = QTextCharFormat()
        time_format.setForeground(QColor("#858585"))
        path_format = QTextCharFormat()
        path_format.setForeground(QColor("#9CDCFE"))
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor("#C586C0"))
        delimiter_format = QTextCharFormat()
        delimiter_format.setForeground(QColor("#6A9955"))

        log_samples = [
            ("DEBUG", "Detailed debug information sample."),
            ("INFO", "Log settings updated successfully."),
            ("WARNING", "Configuration warning: deprecated option used."),
            ("ERROR", "Failed to process log formatting."),
            ("CRITICAL", "Critical system error encountered."),
        ]

        level_cfg = self.config.get("level_enabled")
        if not isinstance(level_cfg, dict):
            level_cfg = {}

        self.preview_edit.clear()
        cursor = self.preview_edit.textCursor()
        filtered_samples = [(lvl, msg) for lvl, msg in log_samples if level_cfg.get(lvl, True)]

        for i, (level, message) in enumerate(filtered_samples):
            if show_time:
                cursor.insertText("2026-06-07 14:30:00", time_format)
                cursor.insertText(" ", default_format)
                if is_tabular:
                    cursor.insertText("| ", delimiter_format)

            if show_level:
                level_fmt = QTextCharFormat()
                level_fmt.setForeground(level_colors.get(level, QColor("#D4D4D4")))
                level_fmt.setFontWeight(QFont.Bold)
                cursor.insertText(f"{level:<8}", level_fmt)
                cursor.insertText(
                    " | " if is_tabular else " ",
                    delimiter_format if is_tabular else default_format,
                )

            if formatted_path:
                cursor.insertText(formatted_path, path_format)
                cursor.insertText(
                    " | " if is_tabular else " ",
                    delimiter_format if is_tabular else default_format,
                )

            if show_tag:
                cursor.insertText("[Settings]", tag_format)
                cursor.insertText(
                    " | " if is_tabular else " ",
                    delimiter_format if is_tabular else default_format,
                )

            cursor.insertText(message, default_format)
            if i < len(filtered_samples) - 1:
                cursor.insertBlock()