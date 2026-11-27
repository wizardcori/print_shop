from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from BuildManagerApp.build_manager_config import (
    BUILD_MANAGER_INI_NAME,
    BuildManagerIniStore,
    KEY_EXCLUDE_LIBS,
    KEY_SCANNED_LIBS,
)
from Common.prio_worker_queue import TaskListenerBase, TaskManager, TaskPriority
from Common.python_app_library_scan import AppLibraryScanner
from build_script.target_config import (
    APP_OVERRIDE_FIELDS,
    TargetConfig,
)
from build_script.target_config_io import (
    InstallerBuildConfig,
    normalize_target_id_list,
)

WINDOW_TITLE_TARGET_CONFIG: str = "BuildTarget 설정"
WINDOW_DEFAULT_WIDTH: int = 760
WINDOW_DEFAULT_HEIGHT: int = 680

SRC_DIR_NAME: str = "src"
ENTRY_FILE_NAME: str = "main_app.py"
VERSION_FILE_NAME: str = "version.txt"
VERSION_FILE_ENCODING: str = "utf-8-sig"
LEGACY_SETUP_NAME: str = "PrintShopSetup"
SETUP_NAME_SUFFIX: str = "Setup"
DEFAULT_BUMP_FALLBACK: str = "patch"

DEFAULT_INSTALLER_KEYS: tuple[str, ...] = (
    "PrintShopApp",
    "PrintShopUpdateService",
)

DEFAULT_INSTALLER_SEARCH_TOKENS: tuple[str, ...] = (
    "printshopapp",
    "updateservice",
)

BUMP_UNIT_OPTIONS: list[tuple[str, str | None]] = [
    ("변경 없음 (none)", None),
    ("patch", "patch"),
    ("minor", "minor"),
    ("major", "major"),
]

VALID_BUMP_UNITS: tuple[str, ...] = ("patch", "minor", "major")
NONE_BUMP_TOKENS: frozenset[str] = frozenset({"none", "null", "false", "0", "변경 없음"})

CLEAN_OPTION_FIELDS: tuple[str, ...] = (
    "clean_work",
    "clean_dist",
    "clean_spec",
)

TEST_OPTION_FIELD: str = "run_test"
EXCLUDE_LIBS_FIELD: str = KEY_EXCLUDE_LIBS
SCANNED_LIBS_FIELD: str = KEY_SCANNED_LIBS

LIST_FIELDS: tuple[str, ...] = (
    "dir_hints",
    "spec_hints",
    "entry_hints",
    "version_rel_paths",
)

SEMVER_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\.(\d+)\.(\d+)\b")


def _normalize_bump_unit(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s in NONE_BUMP_TOKENS:
        return None
    if s in VALID_BUMP_UNITS:
        return s
    return None


def _join_list_field(values: Any) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return ", ".join(str(v).strip() for v in values if str(v).strip())


def _split_list_field(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    sep = "|" if "|" in raw and "," not in raw else ","
    return [part.strip() for part in raw.split(sep) if part.strip()]


def _parse_semver(raw_version: str) -> tuple[int, int, int] | None:
    match = SEMVER_PATTERN.search((raw_version or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _compute_next_version_str(current_ver: str | None, bump_unit: str | None) -> str | None:
    if not current_ver or not bump_unit:
        return None
    parsed = _parse_semver(current_ver)
    if not parsed:
        return None
    major, minor, patch = parsed
    unit = bump_unit.strip().lower()
    if unit == "major":
        return f"{major + 1}.0.0"
    if unit == "minor":
        return f"{major}.{minor + 1}.0"
    if unit == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return None


class _AppScanQueueListener(TaskListenerBase):
    """BuildTargetConfigTab의 앱별 라이브러리 지연 스캔 결과를 수신하는 리스너."""

    def __init__(self, tab_widget: "BuildTargetConfigTab") -> None:
        super().__init__(owner_widget=tab_widget)
        self._tab = tab_widget

    def on_task_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
        if not self.is_owner_alive():
            return
        self._tab._handle_queued_scan_finished(task_key, status, data)


class BuildTargetConfigTab(QWidget):
    config_changed = Signal(dict)
    paths_changed = Signal(Path, Path)  # (project_root, ini_path)
    save_requested = Signal()

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
        auto_save: bool = False,
        parent: QWidget | None = None,
        general_tab: Any | None = None,
        as_window: bool = True,
    ) -> None:
        super().__init__(parent)
        self._allow_close: bool = False
        self._installer_user_configured: bool = False
        if as_window:
            self.setWindowFlags(Qt.WindowType.Window)
            self.setWindowTitle(WINDOW_TITLE_TARGET_CONFIG)
            self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / BUILD_MANAGER_INI_NAME)
        )
        self.auto_save = auto_save
        self.general_tab: Any | None = general_tab
        self._ini_store = BuildManagerIniStore(self.config_path.parent)

        # _app_overrides 단일 원본
        self._app_overrides: dict[str, dict[str, Any]] = {}
        self._app_bump_units: dict[str, str | None] = {}
        self._app_clean_options: dict[str, dict[str, bool]] = {}
        self._app_test_options: dict[str, bool] = {}
        self._installer_config: InstallerBuildConfig = InstallerBuildConfig()

        self._app_tab_inputs: dict[str, dict[str, QWidget]] = {}
        self._app_spec_labels: dict[str, QLabel] = {}
        self._app_tab_index_to_key: dict[int, str] = {}
        self._app_key_to_tab_index: dict[str, int] = {}

        # 개별 앱 탭별 exclude 헤더 체크박스/컨테이너 및 라이브러리 체크박스 상태
        self._app_exclude_groups: dict[str, QWidget] = {}
        self._app_exclude_enable_checks: dict[str, QCheckBox] = {}
        self._app_exclude_body_containers: dict[str, QWidget] = {}
        self._app_exclude_layouts: dict[str, QGridLayout] = {}
        self._app_exclude_all_checkboxes: dict[str, QCheckBox] = {}
        self._app_exclude_checkboxes: dict[str, dict[str, QCheckBox]] = {}
        self._app_scanned_libs: dict[str, list[str]] = {}
        self._app_checked_exclude_libs: dict[str, set[str]] = {}

        # prio_worker_queue 지연 스캔 상태 관리
        self._scan_listener = _AppScanQueueListener(self)
        self._app_scan_in_progress: set[str] = set()
        self._scan_task_to_app: dict[str, str] = {}
        self.destroyed.connect(lambda *_: TaskManager().on_window_closing(self._scan_listener))

        self._installer_tab_widget: QWidget | None = None
        self._installer_tab_index: int = -1
        self._installer_inputs: dict[str, Any] = {}
        self._installer_targets_layout: QHBoxLayout | None = None
        self._installer_all_checkbox: QCheckBox | None = None
        self._installer_target_checkboxes: dict[str, QCheckBox] = {}
        self._auto_generated_name: str = ""
        self._auto_generated_ver_src: str = ""

        self._build_ui()
        if self.general_tab is not None:
            self.bind_general_tab(self.general_tab)
        self.sync_path_fields()
        self.load_from_ini(self.config_path, show_error=False)

    def mark_installer_configured(self) -> None:
        self._installer_user_configured = True

    def get_installer_overrides_dict(self) -> dict[str, Any]:
        cfg = self._collect_installer_config()
        return {
            "targets": list(cfg.targets) if cfg.targets is not None else [],
            "name": cfg.name,
            "version_source_id": cfg.version_source_id,
            "installer_only": bool(cfg.installer_only),
            "skip_installer": bool(cfg.skip_installer),
            "extra": dict(cfg.extra),
        }

    def force_close_window(self) -> None:
        self._allow_close = True
        self.close()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        active_idx = self.sub_tabs.currentIndex()
        active_key = self._app_tab_index_to_key.get(active_idx)
        if active_key and not self._has_saved_exclude_data(active_key):
            self.request_lazy_app_scan(active_key, priority=TaskPriority.LOW, show_warning=False)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stage_all_tabs_state()
        TaskManager().on_window_closing(
            self._scan_listener,
            reason="BuildTarget 설정 창 종료로 앱 스캔이 취소되었습니다.",
        )
        if self._allow_close or not self.isWindow():
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()

    def bind_general_tab(self, general_tab: Any) -> None:
        self.general_tab = general_tab
        general_tab.set_paths(self.project_root, self.config_path)
        general_tab.paths_changed.connect(self._on_general_paths_changed)
        general_tab.load_requested.connect(self._on_general_load_requested)
        general_tab.save_requested.connect(self._on_general_save_requested)
        general_tab.dir_config_changed.connect(self._on_general_dirs_changed)

    def _on_general_paths_changed(self, project_root: Path, config_path: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path).resolve()
        self._ini_store.reload_all(self.config_path.parent)
        self.paths_changed.emit(self.project_root, self.config_path)

    def _on_general_load_requested(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.load_from_ini(self.config_path, show_error=True)

    def _on_general_save_requested(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.save_to_ini(self.config_path)
        self.save_requested.emit()

    def _on_general_dirs_changed(self, _dir_overrides: dict[str, str]) -> None:
        self._apply_all_to_targets()

    def sync_path_fields(self) -> None:
        if self.general_tab is not None:
            self.general_tab.set_paths(self.project_root, self.config_path)

    def set_paths(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / BUILD_MANAGER_INI_NAME)
        )
        self._ini_store.reload_all(self.config_path.parent)
        self.sync_path_fields()

    def _get_default_installer_keys(self, ordered: list[str]) -> set[str]:
        matched: set[str] = set()
        for key in DEFAULT_INSTALLER_KEYS:
            if key in ordered:
                matched.add(key)
        if not matched:
            for key in ordered:
                lower = key.lower()
                if any(tok in lower for tok in DEFAULT_INSTALLER_SEARCH_TOKENS):
                    matched.add(key)
        return matched or set(ordered[:2])

    def _resolve_selected_installer_keys(self, raw_targets: Any) -> set[str]:
        ordered = list(TargetConfig.ordered_keys())
        default_keys = self._get_default_installer_keys(ordered)
        if not raw_targets:
            return default_keys

        if isinstance(raw_targets, (list, tuple, set)):
            tokens = [str(x).strip() for x in raw_targets if str(x).strip()]
        else:
            tokens = [t.strip() for t in str(raw_targets).replace(";", ",").split(",") if t.strip()]

        if not tokens:
            return default_keys

        resolved: set[str] = set()
        for tok in tokens:
            if tok in ordered:
                resolved.add(tok)
                continue
            if tok.isdigit():
                pos = int(tok) - 1
                if 0 <= pos < len(ordered):
                    resolved.add(ordered[pos])
                    continue
            for key in ordered:
                spec = TargetConfig.get_spec(key)
                spec_id = getattr(spec, "id", None) if spec else None
                if spec_id is not None and str(spec_id).strip() == tok:
                    resolved.add(key)
                    break

        return resolved or default_keys

    def _compute_auto_installer_fields(self, selected_keys: list[str]) -> tuple[str, str]:
        if not selected_keys:
            return "", ""

        first_key = selected_keys[0].strip()
        spec = TargetConfig.get_spec(first_key)
        auto_name = f"{first_key}{SETUP_NAME_SUFFIX}" if first_key else ""

        spec_id = getattr(spec, "id", None) if spec else None
        auto_ver_src = (
            str(spec_id).strip() if spec_id is not None and str(spec_id).strip() else first_key
        )
        return auto_name, auto_ver_src

    def _sync_installer_modes_when_empty(self) -> None:
        if not self._installer_inputs:
            return
        ordered = list(TargetConfig.ordered_keys())
        has_selected = any(
            key in self._installer_target_checkboxes
            and self._installer_target_checkboxes[key].isChecked()
            for key in ordered
        )
        if not has_selected:
            chk_only = self._installer_inputs.get("installer_only")
            chk_skip = self._installer_inputs.get("skip_installer")
            if isinstance(chk_only, QCheckBox):
                chk_only.blockSignals(True)
                chk_only.setChecked(False)
                chk_only.blockSignals(False)
            if isinstance(chk_skip, QCheckBox):
                chk_skip.blockSignals(True)
                chk_skip.setChecked(False)
                chk_skip.blockSignals(False)

    def _sync_installer_auto_fields(self, *, force: bool = False) -> None:
        if not self._installer_inputs:
            return

        ordered = list(TargetConfig.ordered_keys())
        selected = [
            key
            for key in ordered
            if key in self._installer_target_checkboxes
            and self._installer_target_checkboxes[key].isChecked()
        ]
        auto_name, auto_ver_src = self._compute_auto_installer_fields(selected)

        edit_name: QLineEdit = self._installer_inputs["name"]
        edit_ver_src: QLineEdit = self._installer_inputs["version_source_id"]

        cur_name = edit_name.text().strip()
        if (
            force
            or not cur_name
            or cur_name == self._auto_generated_name
            or cur_name == LEGACY_SETUP_NAME
        ):
            edit_name.setText(auto_name)
        self._auto_generated_name = auto_name

        cur_ver = edit_ver_src.text().strip()
        if force or not cur_ver or cur_ver == self._auto_generated_ver_src:
            edit_ver_src.setText(auto_ver_src)
        self._auto_generated_ver_src = auto_ver_src

    def _rebuild_installer_target_checkboxes(self, selected_raw: Any = None) -> None:
        if self._installer_targets_layout is None:
            return

        while self._installer_targets_layout.count() > 0:
            item = self._installer_targets_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._installer_target_checkboxes.clear()

        chk_all = QCheckBox("전체")
        chk_all.setToolTip("인스톨러 포함 타겟 앱 전체 선택 / 해제")
        chk_all.clicked.connect(self._on_installer_all_targets_clicked)
        self._installer_all_checkbox = chk_all
        self._installer_targets_layout.addWidget(chk_all)

        ordered = list(TargetConfig.ordered_keys())
        selected_keys = self._resolve_selected_installer_keys(selected_raw)

        for idx, key in enumerate(ordered, start=1):
            spec = TargetConfig.get_spec(key)
            label = f"{idx}. {key}"
            chk = QCheckBox(label)
            tip_detail = f" ({spec.label})" if spec and getattr(spec, "label", None) else ""
            chk.setToolTip(f"인스톨러 포함 대상: {key}{tip_detail}")
            chk.setChecked(key in selected_keys)
            chk.stateChanged.connect(self._on_installer_target_checkbox_changed)
            self._installer_target_checkboxes[key] = chk
            self._installer_targets_layout.addWidget(chk)

        self._installer_targets_layout.addStretch(1)
        self._sync_installer_all_checkbox()
        self._sync_installer_modes_when_empty()
        self._sync_installer_auto_fields()

    def _sync_installer_all_checkbox(self) -> None:
        if self._installer_all_checkbox is None:
            return
        total = len(self._installer_target_checkboxes)
        checked_cnt = sum(
            1 for chk in self._installer_target_checkboxes.values() if chk.isChecked()
        )
        self._installer_all_checkbox.blockSignals(True)
        self._installer_all_checkbox.setChecked(total > 0 and checked_cnt == total)
        self._installer_all_checkbox.blockSignals(False)

    def _on_installer_all_targets_clicked(self) -> None:
        self.mark_installer_configured()
        if self._installer_all_checkbox is None:
            return
        checked = self._installer_all_checkbox.isChecked()
        for chk in self._installer_target_checkboxes.values():
            chk.blockSignals(True)
            chk.setChecked(checked)
            chk.blockSignals(False)
        self._sync_installer_all_checkbox()
        self._sync_installer_modes_when_empty()
        self._sync_installer_auto_fields()

    def _on_installer_target_checkbox_changed(self, _state: int) -> None:
        self.mark_installer_configured()
        self._sync_installer_all_checkbox()
        self._sync_installer_modes_when_empty()
        self._sync_installer_auto_fields()

    def _get_checked_installer_targets(self) -> list[str] | None:
        if not self._installer_target_checkboxes:
            return None
        ordered = list(TargetConfig.ordered_keys())
        selected = [
            key
            for key in ordered
            if key in self._installer_target_checkboxes
            and self._installer_target_checkboxes[key].isChecked()
        ]
        if not selected:
            return []
        if len(selected) == len(ordered):
            return None
        return selected

    def _load_installer_form(self, cfg: InstallerBuildConfig) -> None:
        if not self._installer_inputs:
            return
        self._auto_generated_name = ""
        self._auto_generated_ver_src = ""
        self._rebuild_installer_target_checkboxes(cfg.targets)

        selected_ordered = [
            key
            for key in TargetConfig.ordered_keys()
            if key in self._installer_target_checkboxes
            and self._installer_target_checkboxes[key].isChecked()
        ]
        auto_name, auto_ver_src = self._compute_auto_installer_fields(selected_ordered)
        self._auto_generated_name = auto_name
        self._auto_generated_ver_src = auto_ver_src

        raw_cfg_name = str(cfg.name or "").strip()
        resolved_name = (
            auto_name if (not raw_cfg_name or raw_cfg_name == LEGACY_SETUP_NAME) else raw_cfg_name
        )
        self._installer_inputs["name"].setText(resolved_name)
        self._installer_inputs["version_source_id"].setText(
            str(cfg.version_source_id or auto_ver_src)
        )
        if not selected_ordered:
            self._installer_inputs["installer_only"].setChecked(False)
            self._installer_inputs["skip_installer"].setChecked(False)
        else:
            self._installer_inputs["installer_only"].setChecked(bool(cfg.installer_only))
            self._installer_inputs["skip_installer"].setChecked(bool(cfg.skip_installer))

    def _collect_installer_config(self) -> InstallerBuildConfig:
        raw_targets = self._get_checked_installer_targets()
        parsed_targets = normalize_target_id_list(raw_targets) if raw_targets else None
        raw_name = self._installer_inputs["name"].text().strip() or None
        raw_ver_src = self._installer_inputs["version_source_id"].text().strip() or None
        installer_only = bool(self._installer_inputs["installer_only"].isChecked())
        skip_installer = bool(self._installer_inputs["skip_installer"].isChecked())

        return InstallerBuildConfig(
            targets=parsed_targets,
            installer_only=installer_only,
            skip_installer=skip_installer,
            name=raw_name,
            version_source_id=raw_ver_src,
            extra=dict(self._installer_config.extra),
        )

    def _sync_bump_units_from_overrides(self) -> None:
        updated: dict[str, str | None] = {}
        for key in TargetConfig.ordered_keys():
            ov = self._app_overrides.get(key, {})
            if "bump_unit" in ov:
                updated[key] = _normalize_bump_unit(ov.get("bump_unit"))
            else:
                updated[key] = self._app_bump_units.get(key)
        self._app_bump_units = updated

    def _sync_clean_options_from_overrides(self) -> None:
        updated: dict[str, dict[str, bool]] = {}
        for key in TargetConfig.ordered_keys():
            spec = TargetConfig.get_spec(key)
            ov = self._app_overrides.get(key, {})
            prev = self._app_clean_options.get(key, {})
            app_clean: dict[str, bool] = {}
            for field in CLEAN_OPTION_FIELDS:
                if field in ov and isinstance(ov[field], bool):
                    app_clean[field] = bool(ov[field])
                elif field in prev:
                    app_clean[field] = bool(prev[field])
                else:
                    app_clean[field] = bool(getattr(spec, field, False)) if spec else False
            updated[key] = app_clean
        self._app_clean_options = updated

    def _sync_test_options_from_overrides(self) -> None:
        updated: dict[str, bool] = {}
        for key in TargetConfig.ordered_keys():
            spec = TargetConfig.get_spec(key)
            ov = self._app_overrides.get(key, {})
            if TEST_OPTION_FIELD in ov and isinstance(ov[TEST_OPTION_FIELD], bool):
                updated[key] = bool(ov[TEST_OPTION_FIELD])
            elif key in self._app_test_options:
                updated[key] = bool(self._app_test_options[key])
            else:
                updated[key] = bool(getattr(spec, TEST_OPTION_FIELD, False)) if spec else False
        self._app_test_options = updated

    @staticmethod
    def _extract_str_list(raw_val: Any) -> list[str]:
        if isinstance(raw_val, (list, tuple, set)):
            return sorted({str(x).strip() for x in raw_val if str(x).strip()})
        if isinstance(raw_val, str) and raw_val.strip():
            return sorted(set(_split_list_field(raw_val)))
        return []

    def _get_saved_scanned_libs(self, target_key: str) -> list[str]:
        ov = self._app_overrides.get(target_key, {})
        return self._extract_str_list(ov.get(SCANNED_LIBS_FIELD))

    def _get_saved_exclude_libs(self, target_key: str) -> list[str]:
        ov = self._app_overrides.get(target_key, {})
        return self._extract_str_list(ov.get(EXCLUDE_LIBS_FIELD))

    def _has_saved_exclude_data(self, target_key: str) -> bool:
        return bool(
            self._get_saved_scanned_libs(target_key)
            or self._get_saved_exclude_libs(target_key)
            or self._app_scanned_libs.get(target_key)
            or self._app_checked_exclude_libs.get(target_key)
        )

    def _sync_exclude_libs_from_overrides(self) -> None:
        for key in TargetConfig.ordered_keys():
            saved_scanned = self._get_saved_scanned_libs(key)
            saved_excluded = self._get_saved_exclude_libs(key)
            checked_set = set(saved_excluded)
            self._app_checked_exclude_libs[key] = checked_set

            merged_libs = sorted(
                set(saved_scanned) | set(self._app_scanned_libs.get(key, [])) | checked_set
            )
            if merged_libs:
                self._app_scanned_libs[key] = merged_libs

            has_saved_data = bool(merged_libs or checked_set)
            has_checked = len(checked_set) > 0
            if key in self._app_exclude_enable_checks:
                chk = self._app_exclude_enable_checks[key]
                chk.blockSignals(True)
                chk.setChecked(has_checked)
                chk.blockSignals(False)
                self._refresh_exclude_header_state(key, has_checked)

            if has_saved_data and key in self._app_exclude_layouts:
                self._populate_exclude_checkboxes(key, merged_libs)

    def set_app_bump_units(self, bump_units: dict[str, Any] | None) -> None:
        src = bump_units or {}
        for key in TargetConfig.ordered_keys():
            if key in src:
                self._app_bump_units[key] = _normalize_bump_unit(src.get(key))
            elif key not in self._app_bump_units:
                self._app_bump_units[key] = None
        self._refresh_app_tab_titles()
        for key in TargetConfig.ordered_keys():
            self._load_app_form(key)

    def get_app_bump_units(self) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for key in TargetConfig.ordered_keys():
            result[key] = _normalize_bump_unit(self._app_bump_units.get(key))
        return result

    def set_app_clean_options(self, clean_options: dict[str, dict[str, Any]] | None) -> None:
        src = clean_options or {}
        for key in TargetConfig.ordered_keys():
            current = dict(
                self._app_clean_options.get(key, {field: False for field in CLEAN_OPTION_FIELDS})
            )
            incoming = src.get(key)
            if isinstance(incoming, dict):
                for field in CLEAN_OPTION_FIELDS:
                    if field in incoming:
                        current[field] = bool(incoming[field])
            self._app_clean_options[key] = current
            self._load_app_form(key)

    def get_app_clean_options(self) -> dict[str, dict[str, bool]]:
        result: dict[str, dict[str, bool]] = {}
        for key in TargetConfig.ordered_keys():
            current = self._app_clean_options.get(key, {})
            result[key] = {field: bool(current.get(field, False)) for field in CLEAN_OPTION_FIELDS}
        return result

    def set_app_test_options(self, test_options: dict[str, Any] | None) -> None:
        src = test_options or {}
        for key in TargetConfig.ordered_keys():
            if key in src:
                self._app_test_options[key] = bool(src[key])
            elif key not in self._app_test_options:
                self._app_test_options[key] = False
            self._load_app_form(key)

    def get_app_test_options(self) -> dict[str, bool]:
        return {
            key: bool(self._app_test_options.get(key, False)) for key in TargetConfig.ordered_keys()
        }

    # ------------------------------------------------------------------
    # 개별 앱 탭 exclude 영역, prio_worker_queue 지연 스캔 및 체크박스 관리
    # ------------------------------------------------------------------
    @staticmethod
    def _format_exclude_header_text(checked: bool) -> str:
        state_str = "ENABLE" if checked else "DISABLE"
        return f"exclude [{state_str}]"

    def _refresh_exclude_header_state(self, target_key: str, checked: bool) -> None:
        chk = self._app_exclude_enable_checks.get(target_key)
        if chk is not None:
            chk.setText(self._format_exclude_header_text(checked))
        body = self._app_exclude_body_containers.get(target_key)
        if body is not None:
            body.setEnabled(checked)

    def _resolve_source_root(self) -> Path:
        src_dir = self.project_root / SRC_DIR_NAME
        return src_dir.resolve() if src_dir.is_dir() else self.project_root

    def _resolve_app_entry_point(self, target_key: str) -> Path | None:
        spec = TargetConfig.get_spec(target_key)
        ov = self._app_overrides.get(target_key, {})
        src_root = self._resolve_source_root()

        candidates: list[Path] = []
        raw_entry = ov.get("entry_file")
        if raw_entry:
            p = Path(str(raw_entry))
            candidates.append(p if p.is_absolute() else (self.project_root / p))

        raw_hints = ov.get("entry_hints")
        if not raw_hints and spec:
            raw_hints = getattr(spec, "entry_hints", None)

        if isinstance(raw_hints, (list, tuple)):
            for hint in raw_hints:
                if hint:
                    p = Path(str(hint))
                    candidates.append(p if p.is_absolute() else (self.project_root / p))
        elif isinstance(raw_hints, str) and raw_hints.strip():
            for hint in _split_list_field(raw_hints):
                p = Path(hint)
                candidates.append(p if p.is_absolute() else (self.project_root / p))

        dir_hints: list[str] = []
        raw_dirs = ov.get("dir_hints")
        if isinstance(raw_dirs, (list, tuple)):
            dir_hints.extend(str(d).strip() for d in raw_dirs if str(d).strip())
        elif isinstance(raw_dirs, str) and raw_dirs.strip():
            dir_hints.extend(_split_list_field(raw_dirs))
        elif spec and getattr(spec, "dir_hints", None):
            dir_hints.extend(str(d).strip() for d in spec.dir_hints if str(d).strip())

        for d_name in dir_hints:
            candidates.append(src_root / d_name / ENTRY_FILE_NAME)
            candidates.append(self.project_root / d_name / ENTRY_FILE_NAME)

        candidates.extend(
            [
                src_root / target_key / ENTRY_FILE_NAME,
                self.project_root / target_key / ENTRY_FILE_NAME,
                src_root / ENTRY_FILE_NAME,
            ]
        )

        seen: set[Path] = set()
        for cand in candidates:
            resolved = cand.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_file():
                return resolved
        return None

    def _run_scanner_for_app(self, target_key: str, *, only_used: bool = True) -> list[str]:
        entry_point = self._resolve_app_entry_point(target_key)
        if entry_point is None:
            return []

        src_root = self._resolve_source_root()
        scanner = AppLibraryScanner.create(
            app_name=target_key,
            source_root=src_root,
            entry_point=entry_point,
            only_used=only_used,
        )
        entries = scanner.get_library_by_appname(target_key)
        return sorted(
            {
                entry.get_library_name().strip()
                for entry in entries
                if entry.get_library_name().strip()
            }
        )

    def _fetch_scanner_libraries(self, target_key: str, *, auto_scan: bool = False) -> list[str]:
        try:
            scanner = AppLibraryScanner(source_root=self._resolve_source_root())
            entries = scanner.get_library_by_appname(target_key)
            libs = sorted(
                {
                    entry.get_library_name().strip()
                    for entry in entries
                    if entry.get_library_name().strip()
                }
            )
            if libs or not auto_scan:
                return libs
            return self._run_scanner_for_app(target_key)
        except Exception:
            return []

    def _build_scan_task_key(self, target_key: str) -> str:
        return f"app_lib_scan::{id(self)}::{target_key}"

    @staticmethod
    def _run_scanner_job_in_worker(
        target_key: str,
        entry_point_str: str,
        source_root_str: str,
        only_used: bool,
        progress_cb: Any = None,
        cancel_event: Any = None,
        cancel_token: Any = None,
    ) -> list[str]:
        """prio_worker_queue 워커 스레드에서 실행되는 앱별 라이브러리 스캔 작업."""
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("앱 라이브러리 스캔이 취소되었습니다.")
        if callable(progress_cb):
            progress_cb(20, f"{target_key} 스캔 준비 중")

        scanner = AppLibraryScanner.create(
            app_name=target_key,
            source_root=source_root_str,
            entry_point=entry_point_str,
            only_used=only_used,
        )

        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("앱 라이브러리 스캔이 취소되었습니다.")
        if callable(progress_cb):
            progress_cb(85, f"{target_key} 라이브러리 목록 정리 중")

        entries = scanner.get_library_by_appname(target_key)
        libs = sorted(
            {
                entry.get_library_name().strip()
                for entry in entries
                if entry.get_library_name().strip()
            }
        )
        if callable(progress_cb):
            progress_cb(100, f"{target_key} 스캔 완료")
        return libs

    def request_lazy_app_scan(
        self,
        target_key: str,
        *,
        only_used: bool = True,
        columns: int = 3,
        force: bool = False,
        priority: int = TaskPriority.LOW,
        show_warning: bool = False,
    ) -> bool:
        """
        Config 탭에서 해당 앱에 저장된 exclude/scan 목록이 없을 때만 스캔을 실행합니다.
        저장된 목록이 있으면 자동 스캔을 하지 않고 저장된 목록만 표시합니다.
        """
        if not target_key:
            return False

        saved_scanned = self._get_saved_scanned_libs(target_key)
        saved_excluded = self._get_saved_exclude_libs(target_key)
        saved_checked = set(saved_excluded) | set(
            self._app_checked_exclude_libs.get(target_key, set())
        )
        if saved_checked:
            self._app_checked_exclude_libs[target_key] = saved_checked

        cached_libs = list(self._app_scanned_libs.get(target_key) or [])
        known_libs = sorted(set(saved_scanned) | set(cached_libs) | saved_checked)

        if not force and (saved_scanned or saved_excluded or cached_libs):
            self._app_scanned_libs[target_key] = known_libs
            self._populate_exclude_checkboxes(target_key, known_libs, columns=columns)
            return False

        if target_key in self._app_scan_in_progress:
            return False

        entry_point = self._resolve_app_entry_point(target_key)
        if entry_point is None:
            self.on_app_scan_finished(target_key, list(saved_checked), columns=columns)
            if show_warning:
                QMessageBox.warning(
                    self,
                    "진입점 없음",
                    f"'{target_key}' 앱의 진입점 파일({ENTRY_FILE_NAME})을 찾을 수 없습니다.",
                )
            return False

        src_root = self._resolve_source_root()
        task_key = self._build_scan_task_key(target_key)
        self._app_scan_in_progress.add(target_key)
        self._scan_task_to_app[task_key] = target_key

        try:
            TaskManager().submit(
                self._scan_listener,
                priority,
                task_key,
                f"앱 라이브러리 스캔 ({target_key})",
                self._run_scanner_job_in_worker,
                target_key,
                str(entry_point),
                str(src_root),
                only_used,
                cancel_on_close=True,
            )
            return True
        except Exception:
            self._app_scan_in_progress.discard(target_key)
            self._scan_task_to_app.pop(task_key, None)
            libs = self._run_scanner_for_app(target_key, only_used=only_used)
            self.on_app_scan_finished(target_key, libs, columns=columns)
            return False

    def _handle_queued_scan_finished(self, task_key: str, status: str, data: Any) -> None:
        target_key = self._scan_task_to_app.pop(task_key, None)
        if not target_key and "::" in task_key:
            target_key = task_key.split("::", 2)[-1]
        if not target_key:
            return

        self._app_scan_in_progress.discard(target_key)
        if status == "SUCCESS" and isinstance(data, list):
            libs = sorted({str(x).strip() for x in data if str(x).strip()})
            self.on_app_scan_finished(target_key, libs)

    def scan_app_libraries(
        self,
        target_key: str,
        *,
        only_used: bool = True,
        columns: int = 3,
        show_warning: bool = True,
    ) -> list[str]:
        """RESCAN 버튼이나 명시적 호출 시 우선순위를 높여 스캔 큐에 제출합니다."""
        submitted = self.request_lazy_app_scan(
            target_key,
            only_used=only_used,
            columns=columns,
            force=True,
            priority=TaskPriority.NORMAL,
            show_warning=show_warning,
        )
        if not submitted and target_key in self._app_scanned_libs:
            return list(self._app_scanned_libs[target_key])
        return list(self._app_scanned_libs.get(target_key, []))

    def is_exclude_enabled(self, target_key: str) -> bool:
        """상단 exclude 체크박스 체크 여부(exclude 기능 사용 여부)."""
        chk = self._app_exclude_enable_checks.get(target_key)
        return bool(chk.isChecked()) if chk is not None else False

    def _clear_exclude_checkboxes(self, target_key: str, *, keep_checked: bool = True) -> None:
        if keep_checked:
            prev = self._get_checked_names_from_widgets(target_key)
            if prev:
                self._app_checked_exclude_libs[target_key] = set(prev)

        grid = self._app_exclude_layouts.get(target_key)
        chk_map = self._app_exclude_checkboxes.get(target_key)
        if grid is not None:
            while grid.count():
                item = grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._app_exclude_all_checkboxes.pop(target_key, None)
        if chk_map is not None:
            chk_map.clear()

    def _get_checked_names_from_widgets(self, target_key: str) -> set[str]:
        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        return {name for name, chk in chk_map.items() if chk.isChecked()}

    def _sync_exclude_all_checkbox(self, target_key: str) -> None:
        chk_all = self._app_exclude_all_checkboxes.get(target_key)
        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        if chk_all is None:
            return
        total = len(chk_map)
        checked_cnt = sum(1 for chk in chk_map.values() if chk.isChecked())
        chk_all.blockSignals(True)
        chk_all.setChecked(total > 0 and checked_cnt == total)
        chk_all.blockSignals(False)

    def _on_exclude_all_toggled(self, target_key: str, checked: bool) -> None:
        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        for chk in chk_map.values():
            chk.blockSignals(True)
            chk.setChecked(checked)
            chk.blockSignals(False)
        if checked:
            self._app_checked_exclude_libs[target_key] = set(chk_map.keys())
        else:
            self._app_checked_exclude_libs[target_key] = set()
        self._sync_exclude_all_checkbox(target_key)

    def _populate_exclude_checkboxes(
        self,
        target_key: str,
        lib_names: list[str],
        *,
        columns: int = 3,
    ) -> None:
        """하단 exclude 영역 제일 앞에 All 체크박스를 두고 스캔된 라이브러리 체크박스들을 채웁니다."""
        checked_set = set(self._app_checked_exclude_libs.get(target_key, set()))
        self._clear_exclude_checkboxes(target_key, keep_checked=False)

        parent_widget = self._app_exclude_body_containers.get(target_key)
        grid = self._app_exclude_layouts.get(target_key)
        chk_map = self._app_exclude_checkboxes.get(target_key)
        if parent_widget is None or grid is None or chk_map is None:
            return

        cols = max(1, int(columns))

        chk_all = QCheckBox("All", parent_widget)
        chk_all.setToolTip("제외 라이브러리 전체 선택 / 해제")
        chk_all.toggled.connect(
            lambda checked, k=target_key: self._on_exclude_all_toggled(k, checked)
        )
        grid.addWidget(chk_all, 0, 0)
        self._app_exclude_all_checkboxes[target_key] = chk_all

        ordered_names = sorted({str(x).strip() for x in lib_names if str(x).strip()})
        for idx, lib_name in enumerate(ordered_names, start=1):
            chk = QCheckBox(lib_name, parent_widget)
            chk.setChecked(lib_name in checked_set)
            chk.stateChanged.connect(
                lambda _state, k=target_key, name=lib_name: self._on_exclude_lib_toggled(k, name)
            )
            row, col = divmod(idx, cols)
            grid.addWidget(chk, row, col)
            chk_map[lib_name] = chk

        self._sync_exclude_all_checkbox(target_key)

    def _on_exclude_lib_toggled(self, target_key: str, lib_name: str) -> None:
        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        chk = chk_map.get(lib_name)
        if chk is None:
            return
        bucket = self._app_checked_exclude_libs.setdefault(target_key, set())
        if chk.isChecked():
            bucket.add(lib_name)
        else:
            bucket.discard(lib_name)
        self._sync_exclude_all_checkbox(target_key)

    def on_app_scan_finished(
        self,
        target_key: str,
        libraries: list[str] | None = None,
        *,
        columns: int = 3,
    ) -> None:
        """해당 앱(target_key)의 scan 완료 시 호출. 하단 exclude 영역에 라이브러리 체크박스를 채웁니다."""
        if libraries is not None:
            scanned = {str(x).strip() for x in libraries if str(x).strip()}
        else:
            scanned = set(self._fetch_scanner_libraries(target_key, auto_scan=False))

        saved_checked = set(self._app_checked_exclude_libs.get(target_key, set()))
        lib_names = sorted(scanned | saved_checked)

        self._app_scanned_libs[target_key] = lib_names
        bucket = dict(self._app_overrides.get(target_key, {}))
        if lib_names:
            bucket[SCANNED_LIBS_FIELD] = lib_names
            self._app_overrides[target_key] = bucket

        if target_key in self._app_exclude_layouts:
            self._populate_exclude_checkboxes(target_key, lib_names, columns=columns)

    def _on_exclude_group_toggled(self, target_key: str, checked: bool) -> None:
        """상단 exclude 체크박스는 ENABLE/DISABLE 표시 및 exclude 기능 사용 여부만 결정."""
        self._refresh_exclude_header_state(target_key, checked)
        if not checked:
            self._app_checked_exclude_libs[target_key] = self._get_checked_names_from_widgets(
                target_key
            )
            return

        libs = self._app_scanned_libs.get(target_key) or self._get_saved_scanned_libs(target_key)
        if libs:
            self._app_scanned_libs[target_key] = libs
            self._populate_exclude_checkboxes(target_key, libs)
        elif not self._has_saved_exclude_data(target_key):
            self.request_lazy_app_scan(
                target_key,
                force=True,
                priority=TaskPriority.LOW,
                show_warning=False,
            )

    def get_excluded_libraries(self, target_key: str) -> list[str]:
        """상단 exclude 체크박스가 켜져 있을 때만 선택된 제외 라이브러리 목록을 반환."""
        if not self.is_exclude_enabled(target_key):
            return []
        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        if chk_map:
            return sorted([name for name, chk in chk_map.items() if chk.isChecked()])
        return sorted(self._app_checked_exclude_libs.get(target_key, set()))

    def load_from_ini(
        self,
        ini_path: str | Path | None = None,
        *,
        show_error: bool = True,
    ) -> bool:
        target_file = Path(ini_path).resolve() if ini_path else self.config_path
        self.config_path = target_file
        self._ini_store.reload_all(target_file.parent)
        self.sync_path_fields()
        try:
            sections = self._ini_store.load_target_sections()
            dir_ov = {k: v for k, v in sections["dirs"].items() if v}
            app_ov = sections["app_overrides"]
            inst_dict = sections["installer"]

            TargetConfig.configure(
                project_root=self.project_root,
                code_overrides=dir_ov or None,
                app_overrides=app_ov or None,
            )

            dcfg = TargetConfig.get_dir_config(self.project_root)
            if self.general_tab is not None:
                self.general_tab.set_dir_values(dcfg)

            merged_apps: dict[str, dict[str, Any]] = {
                k: dict(v) for k, v in TargetConfig.get_app_overrides().items()
            }
            if isinstance(app_ov, dict):
                for k, raw_ov in app_ov.items():
                    if isinstance(raw_ov, dict):
                        bucket = dict(merged_apps.get(k, {}))
                        for extra_key in (SCANNED_LIBS_FIELD, EXCLUDE_LIBS_FIELD):
                            if extra_key in raw_ov:
                                bucket[extra_key] = list(raw_ov[extra_key])
                        merged_apps[k] = bucket

            self._app_overrides = merged_apps
            self._sync_bump_units_from_overrides()
            self._sync_clean_options_from_overrides()
            self._sync_test_options_from_overrides()

            self._installer_config = InstallerBuildConfig(
                targets=(
                    normalize_target_id_list(inst_dict.get("targets"))
                    if inst_dict.get("targets")
                    else None
                ),
                installer_only=bool(inst_dict.get("installer_only", False)),
                skip_installer=bool(inst_dict.get("skip_installer", False)),
                name=inst_dict.get("name"),
                version_source_id=inst_dict.get("version_source_id"),
                extra=dict(inst_dict.get("extra") or {}),
            )

            self._rebuild_app_tabs()
            self._sync_exclude_libs_from_overrides()
            self._load_installer_form(self._installer_config)
            for key in TargetConfig.ordered_keys():
                self._load_app_form(key)
            self.config_changed.emit(self.get_current_config_payload())
            return True
        except Exception as exc:
            if show_error:
                QMessageBox.critical(
                    self,
                    "설정 불러오기 실패",
                    f"INI 설정을 불러오는 중 오류가 발생했습니다:\n{exc}",
                )
            return False

    def save_to_ini(
        self,
        ini_path: str | Path | None = None,
        *,
        silent: bool = False,
        emit_signal: bool | None = None,
    ) -> Path | None:
        if self.general_tab is not None:
            self.config_path = self.general_tab.get_config_path_from_input()
        target_file = Path(ini_path).resolve() if ini_path else self.config_path
        self._ini_store.reload_all(target_file.parent)

        should_emit = (not self.auto_save) if emit_signal is None else emit_signal
        self._apply_all_to_targets(emit_signal=should_emit)
        try:
            dcfg = TargetConfig.get_dir_config(self.project_root)
            dir_dict = {
                "work_dir_name": dcfg.work_dir_name,
                "dist_dir_name": dcfg.dist_dir_name,
                "release_dir_name": dcfg.release_dir_name,
                "install_dir_name": dcfg.install_dir_name,
            }
            saved = self._ini_store.save_target_sections(
                dir_values=dir_dict,
                app_overrides=self._app_overrides,
                installer_values=self._installer_config.to_dict(),
            )
            if not silent:
                QMessageBox.information(self, "설정 저장", f"설정을 저장했습니다:\n{saved}")
            return Path(saved)
        except Exception as exc:
            if not silent:
                QMessageBox.critical(
                    self,
                    "설정 저장 실패",
                    f"INI 설정을 저장하는 중 오류가 발생했습니다:\n{exc}",
                )
            return None

    # 하위 호환 별칭
    def load_from_json(
        self, json_path: str | Path | None = None, *, show_error: bool = True
    ) -> bool:
        return self.load_from_ini(json_path, show_error=show_error)

    def save_to_json(
        self,
        json_path: str | Path | None = None,
        *,
        silent: bool = False,
        emit_signal: bool | None = None,
    ) -> Path | None:
        return self.save_to_ini(json_path, silent=silent, emit_signal=emit_signal)

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(8)

        self.sub_tabs = QTabWidget(self)
        self.sub_tabs.currentChanged.connect(self._on_sub_tab_changed)

        self._installer_tab_widget = self._create_installer_tab()
        self._rebuild_app_tabs()

        outer_layout.addWidget(self.sub_tabs, stretch=1)

        action_row = QHBoxLayout()
        self.btn_apply_all = QPushButton("전체 탭 변경사항 반영 및 저장")
        self.btn_apply_all.clicked.connect(self._on_apply_all_tabs)

        self.btn_reload = QPushButton("다시 불러오기")
        self.btn_reload.clicked.connect(
            lambda: self.load_from_ini(self.config_path, show_error=True)
        )

        self.btn_reset_all = QPushButton("전체 기본값 복원")
        self.btn_reset_all.clicked.connect(self.reset_all_defaults)

        action_row.addWidget(self.btn_apply_all)
        action_row.addWidget(self.btn_reload)
        action_row.addWidget(self.btn_reset_all)
        action_row.addStretch(1)

        outer_layout.addLayout(action_row)

    def _format_installer_tab_title(self) -> str:
        flags: list[str] = []
        if self._installer_config.installer_only:
            flags.append("only")
        if self._installer_config.skip_installer:
            flags.append("skip")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        return f"installer{suffix}"

    def _create_installer_tab(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        inst_group = QGroupBox("인스톨러 조합 설정 ([BuildInstallerConfig])")
        inst_form = QFormLayout(inst_group)

        targets_container = QWidget()
        targets_row = QHBoxLayout(targets_container)
        targets_row.setContentsMargins(0, 0, 0, 0)
        targets_row.setSpacing(12)
        self._installer_targets_layout = targets_row

        edit_inst_name = QLineEdit()
        edit_inst_name.setPlaceholderText("기본값: <TARGET>Setup (예: PrintShopAppSetup)")
        edit_inst_ver_src = QLineEdit()
        edit_inst_ver_src.setPlaceholderText("버전 기준 대상 키/ID (선택)")
        chk_installer_only = QCheckBox("인스톨러 단독 빌드 모드 (installer_only)")
        chk_skip_installer = QCheckBox("인스톨러 빌드 건너뛰기 (skip_installer)")

        self._installer_inputs = {
            "targets": self._installer_target_checkboxes,
            "name": edit_inst_name,
            "version_source_id": edit_inst_ver_src,
            "installer_only": chk_installer_only,
            "skip_installer": chk_skip_installer,
        }

        inst_form.addRow("포함 대상 (targets)", targets_container)
        inst_form.addRow("기본 파일명 (name)", edit_inst_name)
        inst_form.addRow("버전 기준 (version_source_id)", edit_inst_ver_src)
        inst_form.addRow("단독 모드", chk_installer_only)
        inst_form.addRow("건너뛰기", chk_skip_installer)

        self._rebuild_installer_target_checkboxes(self._installer_config.targets)

        layout.addWidget(inst_group)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_apply_inst = QPushButton("인스톨러 설정 반영 및 저장")
        btn_apply_inst.clicked.connect(self._on_apply_installer)
        btn_row.addWidget(btn_apply_inst)
        layout.addLayout(btn_row)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _create_single_app_tab(self, target_key: str) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        spec = TargetConfig.get_spec(target_key)
        header_title = (
            f"{spec.label} ({target_key}) 세부 빌드 설정"
            if spec and spec.label
            else f"{target_key} 세부 빌드 설정"
        )
        app_group = QGroupBox(header_title)
        app_vbox = QVBoxLayout(app_group)

        summary_label = QLabel("현재 스펙: -")
        summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_label.setStyleSheet("color: #444; padding: 4px 0;")
        app_vbox.addWidget(summary_label)
        self._app_spec_labels[target_key] = summary_label

        app_form = QFormLayout()

        combo_bump_unit = QComboBox()
        for text, unit in BUMP_UNIT_OPTIONS:
            combo_bump_unit.addItem(text, userData=unit)

        edit_label = QLineEdit()
        edit_exe = QLineEdit()
        chk_console = QCheckBox("콘솔 창 사용 (console)")
        edit_entry_file = QLineEdit()
        edit_version_file = QLineEdit()
        edit_dir_hints = QLineEdit()
        edit_spec_hints = QLineEdit()
        edit_entry_hints = QLineEdit()
        edit_version_rel_paths = QLineEdit()

        edit_dir_hints.setPlaceholderText("예: PrintShopApp, App")
        edit_spec_hints.setPlaceholderText("예: PrintShopApp.spec")
        edit_entry_hints.setPlaceholderText("예: src/PrintShopApp/main_app.py")
        edit_version_rel_paths.setPlaceholderText("예: src/PrintShopApp/version.txt")

        chk_run_test = QCheckBox("테스트 실행 (run_test)")
        chk_clean_work = QCheckBox("work 폴더 정리 (--clean-work)")
        chk_clean_dist = QCheckBox("dist 폴더 정리 (--clean-dist)")
        chk_clean_spec = QCheckBox(".spec 파일 정리 (--clean-spec)")

        clean_row = QHBoxLayout()
        clean_row.setSpacing(16)
        clean_row.addWidget(chk_clean_work)
        clean_row.addWidget(chk_clean_dist)
        clean_row.addWidget(chk_clean_spec)
        clean_row.addStretch(1)

        inputs: dict[str, QWidget] = {
            "bump_unit": combo_bump_unit,
            "label": edit_label,
            "exe_name": edit_exe,
            "console": chk_console,
            "entry_file": edit_entry_file,
            "version_file": edit_version_file,
            "dir_hints": edit_dir_hints,
            "spec_hints": edit_spec_hints,
            "entry_hints": edit_entry_hints,
            "version_rel_paths": edit_version_rel_paths,
            TEST_OPTION_FIELD: chk_run_test,
            "clean_work": chk_clean_work,
            "clean_dist": chk_clean_dist,
            "clean_spec": chk_clean_spec,
        }
        self._app_tab_inputs[target_key] = inputs

        app_form.addRow("개별 버전 증가 (bump_unit)", combo_bump_unit)
        app_form.addRow("빌드 라벨 (label)", edit_label)
        app_form.addRow("실행 파일명 (exe_name)", edit_exe)
        app_form.addRow("콘솔 모드", chk_console)
        app_form.addRow("진입 파일 (entry_file)", edit_entry_file)
        app_form.addRow("버전 파일 (version_file)", edit_version_file)
        app_form.addRow("폴더 힌트 (dir_hints)", edit_dir_hints)
        app_form.addRow("Spec 힌트 (spec_hints)", edit_spec_hints)
        app_form.addRow("Entry 경로 (entry_hints)", edit_entry_hints)
        app_form.addRow("버전 경로 목록 (version_rel_paths)", edit_version_rel_paths)

        saved_scanned = self._get_saved_scanned_libs(target_key)
        saved_excluded = self._get_saved_exclude_libs(target_key)
        initial_checked = bool(saved_excluded) or bool(
            self._app_checked_exclude_libs.get(target_key)
        )
        exclude_container = QWidget()
        exclude_main_layout = QVBoxLayout(exclude_container)
        exclude_main_layout.setContentsMargins(0, 4, 0, 4)
        exclude_main_layout.setSpacing(6)

        exclude_header_row = QHBoxLayout()
        exclude_header_row.setContentsMargins(0, 0, 0, 0)
        exclude_header_row.setSpacing(8)

        chk_exclude_enable = QCheckBox(self._format_exclude_header_text(initial_checked))
        chk_exclude_enable.setChecked(initial_checked)
        chk_exclude_enable.setToolTip("제외 라이브러리 기능 활성화 여부 (ENABLE / DISABLE)")

        btn_rescan = QPushButton("RESCAN")
        btn_rescan.setToolTip("앱 사용 라이브러리를 다시 스캔합니다.")
        btn_rescan.clicked.connect(
            lambda _checked=False, k=target_key: self.scan_app_libraries(k, show_warning=True)
        )

        header_line = QFrame()
        header_line.setFrameShape(QFrame.Shape.HLine)
        header_line.setFrameShadow(QFrame.Shadow.Sunken)

        exclude_header_row.addWidget(chk_exclude_enable)
        exclude_header_row.addWidget(btn_rescan)
        exclude_header_row.addWidget(header_line, stretch=1)

        exclude_body = QWidget()
        exclude_body.setEnabled(initial_checked)
        exclude_grid = QGridLayout(exclude_body)
        exclude_grid.setContentsMargins(16, 4, 2, 2)
        exclude_grid.setHorizontalSpacing(14)
        exclude_grid.setVerticalSpacing(6)

        exclude_main_layout.addLayout(exclude_header_row)
        exclude_main_layout.addWidget(exclude_body)

        app_form.addRow(exclude_container)

        self._app_exclude_groups[target_key] = exclude_container
        self._app_exclude_enable_checks[target_key] = chk_exclude_enable
        self._app_exclude_body_containers[target_key] = exclude_body
        self._app_exclude_layouts[target_key] = exclude_grid
        self._app_exclude_checkboxes[target_key] = {}
        self._app_scanned_libs.setdefault(target_key, [])
        self._app_checked_exclude_libs.setdefault(target_key, set(saved_excluded))

        chk_exclude_enable.toggled.connect(
            lambda checked, k=target_key: self._on_exclude_group_toggled(k, checked)
        )

        merged_initial = sorted(
            set(self._app_scanned_libs.get(target_key, []))
            | set(saved_scanned)
            | set(saved_excluded)
            | set(self._app_checked_exclude_libs.get(target_key, set()))
        )
        if merged_initial:
            self._app_scanned_libs[target_key] = merged_initial
            self._populate_exclude_checkboxes(target_key, merged_initial)

        app_form.addRow("빌드 테스트", chk_run_test)
        app_form.addRow("산출물 정리", clean_row)

        app_vbox.addLayout(app_form)

        btn_row = QHBoxLayout()
        btn_reset = QPushButton("이 앱 기본값 초기화")
        btn_reset.clicked.connect(lambda _checked=False, k=target_key: self._on_reset_app(k))

        btn_apply = QPushButton("이 앱 설정 반영 및 저장")
        btn_apply.clicked.connect(lambda _checked=False, k=target_key: self._on_apply_app(k))

        btn_row.addWidget(btn_reset)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_apply)
        app_vbox.addLayout(btn_row)

        layout.addWidget(app_group)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _rebuild_app_tabs(self) -> None:
        current_tab_idx = self.sub_tabs.currentIndex()
        prev_key = self._app_tab_index_to_key.get(current_tab_idx)
        was_installer_selected = (
            self._installer_tab_index >= 0 and current_tab_idx == self._installer_tab_index
        )
        prev_inst_targets = self._get_checked_installer_targets()

        prev_group_checked: dict[str, bool] = {
            k: chk.isChecked() for k, chk in self._app_exclude_enable_checks.items()
        }
        for k in list(self._app_exclude_checkboxes.keys()):
            cur_checked = self._get_checked_names_from_widgets(k)
            if cur_checked:
                self._app_checked_exclude_libs[k] = cur_checked

        self.sub_tabs.blockSignals(True)
        while self.sub_tabs.count() > 0:
            widget = self.sub_tabs.widget(self.sub_tabs.count() - 1)
            self.sub_tabs.removeTab(self.sub_tabs.count() - 1)
            if widget is not None and widget is not self._installer_tab_widget:
                widget.deleteLater()

        self._app_tab_inputs.clear()
        self._app_spec_labels.clear()
        self._app_tab_index_to_key.clear()
        self._app_key_to_tab_index.clear()
        self._app_exclude_groups.clear()
        self._app_exclude_enable_checks.clear()
        self._app_exclude_body_containers.clear()
        self._app_exclude_layouts.clear()
        self._app_exclude_all_checkboxes.clear()
        self._app_exclude_checkboxes.clear()

        for key in TargetConfig.ordered_keys():
            tab_widget = self._create_single_app_tab(key)
            if key in prev_group_checked and key in self._app_exclude_enable_checks:
                chk = self._app_exclude_enable_checks[key]
                is_checked = prev_group_checked[key]
                chk.blockSignals(True)
                chk.setChecked(is_checked)
                chk.blockSignals(False)
                self._refresh_exclude_header_state(key, is_checked)
            idx = self.sub_tabs.addTab(tab_widget, self._format_app_tab_title(key))
            self._app_tab_index_to_key[idx] = key
            self._app_key_to_tab_index[key] = idx

        if self._installer_tab_widget is None:
            self._installer_tab_widget = self._create_installer_tab()
        self._installer_tab_index = self.sub_tabs.addTab(
            self._installer_tab_widget,
            self._format_installer_tab_title(),
        )

        if self._installer_target_checkboxes:
            self._rebuild_installer_target_checkboxes(
                prev_inst_targets
                if prev_inst_targets is not None
                else self._installer_config.targets
            )

        if prev_key and prev_key in self._app_key_to_tab_index:
            self.sub_tabs.setCurrentIndex(self._app_key_to_tab_index[prev_key])
        elif was_installer_selected:
            self.sub_tabs.setCurrentIndex(self._installer_tab_index)
        elif self.sub_tabs.count() > 0:
            self.sub_tabs.setCurrentIndex(0)
        self.sub_tabs.blockSignals(False)

        if self.isVisible():
            active_idx = self.sub_tabs.currentIndex()
            active_key = self._app_tab_index_to_key.get(active_idx)
            if active_key and not self._has_saved_exclude_data(active_key):
                self.request_lazy_app_scan(
                    active_key, priority=TaskPriority.LOW, show_warning=False
                )

    def _refresh_app_tab_titles(self) -> None:
        for idx, key in self._app_tab_index_to_key.items():
            self.sub_tabs.setTabText(idx, self._format_app_tab_title(key))
        if self._installer_tab_index >= 0:
            self.sub_tabs.setTabText(
                self._installer_tab_index,
                self._format_installer_tab_title(),
            )

    def _load_app_form(self, target_key: str | None) -> None:
        if not target_key:
            return
        inputs = self._app_tab_inputs.get(target_key)
        if not inputs:
            return

        spec = TargetConfig.get_spec(target_key)
        ov = self._app_overrides.get(target_key, {})

        bump_combo = inputs.get("bump_unit")
        if isinstance(bump_combo, QComboBox):
            current_bump = _normalize_bump_unit(
                self._app_bump_units.get(target_key, ov.get("bump_unit"))
            )
            b_idx = bump_combo.findData(current_bump)
            bump_combo.setCurrentIndex(b_idx if b_idx >= 0 else 0)

        chk_test = inputs.get(TEST_OPTION_FIELD)
        if isinstance(chk_test, QCheckBox):
            if TEST_OPTION_FIELD in ov and isinstance(ov[TEST_OPTION_FIELD], bool):
                test_val = bool(ov[TEST_OPTION_FIELD])
            elif target_key in self._app_test_options:
                test_val = bool(self._app_test_options[target_key])
            else:
                test_val = bool(getattr(spec, TEST_OPTION_FIELD, False)) if spec else False
            chk_test.setChecked(test_val)

        clean_state = self._app_clean_options.get(target_key, {})
        for field in CLEAN_OPTION_FIELDS:
            chk = inputs.get(field)
            if isinstance(chk, QCheckBox):
                if field in ov and isinstance(ov[field], bool):
                    val = bool(ov[field])
                elif field in clean_state:
                    val = bool(clean_state[field])
                else:
                    val = bool(getattr(spec, field, False)) if spec else False
                chk.setChecked(val)

        summary_label = self._app_spec_labels.get(target_key)
        if spec:
            if summary_label is not None:
                summary_label.setText(
                    f"현재 스펙: order={spec.order}, label={spec.label},"
                    f" exe={spec.exe_name}, console={spec.console},"
                    f" dirs={_join_list_field(spec.dir_hints)}"
                )
            inputs["label"].setText(str(ov.get("label") or spec.label))
            inputs["exe_name"].setText(str(ov.get("exe_name") or spec.exe_name))
            console_val = ov["console"] if isinstance(ov.get("console"), bool) else spec.console
            inputs["console"].setChecked(bool(console_val))
            inputs["entry_file"].setText(str(ov.get("entry_file") or ""))
            inputs["version_file"].setText(str(ov.get("version_file") or ""))
            inputs["dir_hints"].setText(
                _join_list_field(ov.get("dir_hints") if "dir_hints" in ov else spec.dir_hints)
            )
            inputs["spec_hints"].setText(
                _join_list_field(ov.get("spec_hints") if "spec_hints" in ov else spec.spec_hints)
            )
            inputs["entry_hints"].setText(
                _join_list_field(ov.get("entry_hints") if "entry_hints" in ov else spec.entry_hints)
            )
            inputs["version_rel_paths"].setText(
                _join_list_field(
                    ov.get("version_rel_paths")
                    if "version_rel_paths" in ov
                    else spec.version_rel_paths
                )
            )

    def _collect_dir_overrides(self) -> dict[str, str]:
        if self.general_tab is not None:
            return self.general_tab.collect_dir_overrides()
        return {}

    def _collect_app_bump_unit(self, target_key: str) -> str | None:
        inputs = self._app_tab_inputs.get(target_key) or {}
        bump_combo = inputs.get("bump_unit")
        if isinstance(bump_combo, QComboBox):
            return _normalize_bump_unit(bump_combo.currentData())
        return _normalize_bump_unit(self._app_bump_units.get(target_key))

    def _collect_app_test_option(self, target_key: str) -> bool:
        inputs = self._app_tab_inputs.get(target_key) or {}
        chk_test = inputs.get(TEST_OPTION_FIELD)
        if isinstance(chk_test, QCheckBox):
            return bool(chk_test.isChecked())
        return bool(self._app_test_options.get(target_key, False))

    def _collect_app_clean_options(self, target_key: str) -> dict[str, bool]:
        inputs = self._app_tab_inputs.get(target_key) or {}
        prev = self._app_clean_options.get(target_key, {})
        result: dict[str, bool] = {}
        for field in CLEAN_OPTION_FIELDS:
            chk = inputs.get(field)
            if isinstance(chk, QCheckBox):
                result[field] = bool(chk.isChecked())
            else:
                result[field] = bool(prev.get(field, False))
        return result

    def _collect_app_patch(self, target_key: str) -> dict[str, Any]:
        inputs = self._app_tab_inputs.get(target_key)
        if not inputs:
            return {}
        spec = TargetConfig.get_spec(target_key)
        patch: dict[str, Any] = {}

        label_txt = inputs["label"].text().strip()
        if label_txt and (not spec or label_txt != spec.label):
            patch["label"] = label_txt
        elif not label_txt:
            patch["label"] = None

        exe_txt = inputs["exe_name"].text().strip()
        if exe_txt and (not spec or exe_txt != spec.exe_name):
            patch["exe_name"] = exe_txt
        elif not exe_txt:
            patch["exe_name"] = None

        checked_console = bool(inputs["console"].isChecked())
        if spec and checked_console != spec.console:
            patch["console"] = checked_console
        elif "console" in self._app_overrides.get(target_key, {}):
            patch["console"] = checked_console

        entry_file_txt = inputs["entry_file"].text().strip()
        patch["entry_file"] = entry_file_txt if entry_file_txt else None

        version_file_txt = inputs["version_file"].text().strip()
        patch["version_file"] = version_file_txt if version_file_txt else None

        for list_field in LIST_FIELDS:
            items = _split_list_field(inputs[list_field].text())
            default_tuple = getattr(spec, list_field, ()) if spec else ()
            if items and tuple(items) != tuple(default_tuple):
                patch[list_field] = items
            elif not items and list_field in self._app_overrides.get(target_key, {}):
                patch[list_field] = None

        allowed = (
            set(APP_OVERRIDE_FIELDS)
            | set(CLEAN_OPTION_FIELDS)
            | {TEST_OPTION_FIELD, EXCLUDE_LIBS_FIELD, SCANNED_LIBS_FIELD}
        )
        filtered = {k: v for k, v in patch.items() if k in allowed}

        default_test = bool(getattr(spec, TEST_OPTION_FIELD, False)) if spec else False
        test_val = self._collect_app_test_option(target_key)
        if test_val != default_test or TEST_OPTION_FIELD in self._app_overrides.get(target_key, {}):
            filtered[TEST_OPTION_FIELD] = test_val

        clean_opts = self._collect_app_clean_options(target_key)
        for field in CLEAN_OPTION_FIELDS:
            default_clean = bool(getattr(spec, field, False)) if spec else False
            val = bool(clean_opts.get(field, False))
            if val != default_clean or field in self._app_overrides.get(target_key, {}):
                filtered[field] = val

        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        if chk_map:
            excluded = self.get_excluded_libraries(target_key)
            scanned = sorted(
                set(chk_map.keys())
                | set(self._app_scanned_libs.get(target_key, []))
                | set(excluded)
            )
        else:
            excluded = (
                sorted(self._app_checked_exclude_libs.get(target_key, set()))
                if self.is_exclude_enabled(target_key)
                else []
            )
            scanned = sorted(set(self._app_scanned_libs.get(target_key, [])) | set(excluded))

        if scanned:
            filtered[SCANNED_LIBS_FIELD] = scanned
        elif SCANNED_LIBS_FIELD in self._app_overrides.get(target_key, {}):
            filtered[SCANNED_LIBS_FIELD] = []

        if excluded:
            filtered[EXCLUDE_LIBS_FIELD] = excluded
        elif EXCLUDE_LIBS_FIELD in self._app_overrides.get(target_key, {}):
            filtered[EXCLUDE_LIBS_FIELD] = []

        return filtered

    def _stage_app_state(self, target_key: str) -> None:
        bump_unit = self._collect_app_bump_unit(target_key)
        self._app_bump_units[target_key] = bump_unit

        test_val = self._collect_app_test_option(target_key)
        self._app_test_options[target_key] = test_val

        clean_opts = self._collect_app_clean_options(target_key)
        self._app_clean_options[target_key] = clean_opts

        chk_map = self._app_exclude_checkboxes.get(target_key) or {}
        if chk_map:
            self._app_checked_exclude_libs[target_key] = self._get_checked_names_from_widgets(
                target_key
            )
            merged_scanned = sorted(
                set(chk_map.keys())
                | set(self._app_scanned_libs.get(target_key, []))
                | set(self._app_checked_exclude_libs.get(target_key, set()))
            )
            self._app_scanned_libs[target_key] = merged_scanned
        else:
            merged_scanned = sorted(
                set(self._app_scanned_libs.get(target_key, []))
                | set(self._app_checked_exclude_libs.get(target_key, set()))
            )

        excluded = (
            sorted(self._app_checked_exclude_libs.get(target_key, set()))
            if self.is_exclude_enabled(target_key)
            else []
        )

        patch = self._collect_app_patch(target_key)
        bucket = dict(self._app_overrides.get(target_key, {}))
        for k, v in patch.items():
            if v is None:
                bucket.pop(k, None)
            else:
                bucket[k] = v

        if merged_scanned:
            bucket[SCANNED_LIBS_FIELD] = merged_scanned
        else:
            bucket.pop(SCANNED_LIBS_FIELD, None)

        if excluded:
            bucket[EXCLUDE_LIBS_FIELD] = excluded
        else:
            bucket.pop(EXCLUDE_LIBS_FIELD, None)

        if bump_unit is not None:
            bucket["bump_unit"] = bump_unit
        else:
            bucket.pop("bump_unit", None)
        bucket[TEST_OPTION_FIELD] = test_val

        if bucket:
            self._app_overrides[target_key] = bucket
        else:
            self._app_overrides.pop(target_key, None)

    def _stage_all_tabs_state(self) -> None:
        if self._installer_inputs:
            self._installer_config = self._collect_installer_config()
        for key in TargetConfig.ordered_keys():
            if key in self._app_tab_inputs:
                self._stage_app_state(key)

    def _apply_all_to_targets(self, *, emit_signal: bool = True) -> None:
        dir_ov = self._collect_dir_overrides()
        self._stage_all_tabs_state()
        TargetConfig.configure(
            project_root=self.project_root,
            code_overrides=dir_ov,
            app_overrides=self._app_overrides,
        )
        self._sync_bump_units_from_overrides()
        self._sync_clean_options_from_overrides()
        self._sync_test_options_from_overrides()
        self._refresh_app_tab_titles()
        for key in TargetConfig.ordered_keys():
            self._load_app_form(key)
        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def _on_sub_tab_changed(self, index: int) -> None:
        self._stage_all_tabs_state()
        self._refresh_app_tab_titles()
        target_key = self._app_tab_index_to_key.get(index)
        if target_key and not self._has_saved_exclude_data(target_key):
            self.request_lazy_app_scan(target_key, priority=TaskPriority.LOW, show_warning=False)

    def _on_apply_installer(self) -> None:
        self.mark_installer_configured()
        self._installer_config = self._collect_installer_config()
        self.save_to_ini(self.config_path, silent=True, emit_signal=True)

    def _on_apply_app(self, target_key: str) -> None:
        self._stage_app_state(target_key)
        self.save_to_ini(self.config_path, silent=True, emit_signal=True)

    def _on_apply_all_tabs(self) -> None:
        self.save_to_ini(self.config_path, silent=True, emit_signal=True)

    def _on_reset_app(self, target_key: str) -> None:
        self._app_overrides.pop(target_key, None)
        self._app_bump_units[target_key] = None
        self._app_test_options[target_key] = False
        self._app_clean_options[target_key] = {field: False for field in CLEAN_OPTION_FIELDS}
        self._app_checked_exclude_libs[target_key] = set()
        if target_key in self._app_exclude_enable_checks:
            chk = self._app_exclude_enable_checks[target_key]
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
            self._refresh_exclude_header_state(target_key, False)
        if target_key in self._app_scanned_libs:
            self._populate_exclude_checkboxes(target_key, self._app_scanned_libs[target_key])
        self.save_to_ini(self.config_path, silent=True, emit_signal=True)

    def reload_from_targets(self) -> None:
        self.load_from_ini(self.config_path, show_error=False)

    def reset_all_defaults(self) -> None:
        self._installer_user_configured = False
        self._app_overrides = {}
        self._app_bump_units = {key: None for key in TargetConfig.ordered_keys()}
        self._app_test_options = {key: False for key in TargetConfig.ordered_keys()}
        self._app_clean_options = {
            key: {field: False for field in CLEAN_OPTION_FIELDS}
            for key in TargetConfig.ordered_keys()
        }
        self._app_scanned_libs = {key: [] for key in TargetConfig.ordered_keys()}
        self._app_checked_exclude_libs = {key: set() for key in TargetConfig.ordered_keys()}
        self._installer_config = InstallerBuildConfig()
        TargetConfig.configure(project_root=self.project_root, reset=True)
        dcfg = TargetConfig.get_dir_config(self.project_root)
        if self.general_tab is not None:
            self.general_tab.set_dir_values(dcfg)
        self._rebuild_app_tabs()
        self._load_installer_form(self._installer_config)
        for key in TargetConfig.ordered_keys():
            self._load_app_form(key)
        self.save_to_ini(self.config_path, silent=True, emit_signal=True)

    def get_current_config_payload(self) -> dict[str, Any]:
        self._stage_all_tabs_state()
        return {
            "dir_overrides": self._collect_dir_overrides(),
            "app_overrides": {k: dict(v) for k, v in self._app_overrides.items()},
            "app_bump_units": self.get_app_bump_units(),
            "app_test_options": self.get_app_test_options(),
            "app_clean_options": self.get_app_clean_options(),
            "app_scanned_libs": {
                k: list(self._app_scanned_libs.get(k, [])) for k in TargetConfig.ordered_keys()
            },
            "app_excluded_libs": {
                k: self.get_excluded_libraries(k) for k in TargetConfig.ordered_keys()
            },
            "installer_config": self._collect_installer_config().to_dict(),
        }

    def apply_clean_options_to_targets(
        self,
        target_keys: list[str],
        clean_patch: dict[str, bool],
        *,
        persist_ini: bool = False,
        persist_json: bool = False,
        emit_signal: bool = True,
    ) -> None:
        if not target_keys or not clean_patch:
            return

        normalized_patch: dict[str, bool] = {
            k: bool(v) for k, v in clean_patch.items() if k in CLEAN_OPTION_FIELDS
        }
        if not normalized_patch:
            return

        for key in target_keys:
            if key not in self._app_tab_inputs and key not in TargetConfig.BY_KEY:
                continue

            cur_clean = dict(
                self._app_clean_options.get(key, {f: False for f in CLEAN_OPTION_FIELDS})
            )
            cur_clean.update(normalized_patch)
            self._app_clean_options[key] = cur_clean

            bucket = dict(self._app_overrides.get(key, {}))
            bucket.update(normalized_patch)
            self._app_overrides[key] = bucket

            inputs = self._app_tab_inputs.get(key)
            if inputs:
                for field_name, val in normalized_patch.items():
                    chk = inputs.get(field_name)
                    if isinstance(chk, QCheckBox):
                        chk.blockSignals(True)
                        chk.setChecked(bool(val))
                        chk.blockSignals(False)

        TargetConfig.configure(
            project_root=self.project_root,
            code_overrides=self._collect_dir_overrides(),
            app_overrides=self._app_overrides,
        )

        if persist_ini or persist_json:
            self.save_to_ini(self.config_path, silent=True, emit_signal=False)

        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def apply_app_fields_to_targets(
        self,
        target_keys: list[str],
        field_patch: dict[str, Any],
        *,
        persist_ini: bool = False,
        persist_json: bool = False,
        emit_signal: bool = True,
    ) -> None:
        if not target_keys or not field_patch:
            return

        allowed = {"mode", "bump_unit", TEST_OPTION_FIELD}
        normalized_patch: dict[str, Any] = {}
        for k, v in field_patch.items():
            if k not in allowed:
                continue
            if k == "bump_unit":
                normalized_patch[k] = _normalize_bump_unit(v)
            elif k == "mode":
                m = str(v or "").strip()
                if m:
                    normalized_patch[k] = m
            elif k == TEST_OPTION_FIELD:
                normalized_patch[k] = bool(v)
            else:
                normalized_patch[k] = v

        if not normalized_patch:
            return

        for key in target_keys:
            if key not in self._app_tab_inputs and key not in TargetConfig.BY_KEY:
                continue

            bucket = dict(self._app_overrides.get(key, {}))
            for k, v in normalized_patch.items():
                if v is None:
                    bucket.pop(k, None)
                else:
                    bucket[k] = v
            self._app_overrides[key] = bucket

            if "bump_unit" in normalized_patch:
                self._app_bump_units[key] = normalized_patch["bump_unit"]
            if TEST_OPTION_FIELD in normalized_patch:
                self._app_test_options[key] = bool(normalized_patch[TEST_OPTION_FIELD])

            inputs = self._app_tab_inputs.get(key)
            if inputs:
                if "bump_unit" in normalized_patch:
                    combo = inputs.get("bump_unit")
                    if isinstance(combo, QComboBox):
                        idx = combo.findData(normalized_patch["bump_unit"])
                        if idx >= 0:
                            combo.blockSignals(True)
                            combo.setCurrentIndex(idx)
                            combo.blockSignals(False)
                if TEST_OPTION_FIELD in normalized_patch:
                    chk_test = inputs.get(TEST_OPTION_FIELD)
                    if isinstance(chk_test, QCheckBox):
                        chk_test.blockSignals(True)
                        chk_test.setChecked(bool(normalized_patch[TEST_OPTION_FIELD]))
                        chk_test.blockSignals(False)
                if "mode" in normalized_patch:
                    mode_widget = inputs.get("mode")
                    if isinstance(mode_widget, QComboBox):
                        idx = mode_widget.findText(str(normalized_patch["mode"]))
                        if idx >= 0:
                            mode_widget.blockSignals(True)
                            mode_widget.setCurrentIndex(idx)
                            mode_widget.blockSignals(False)

        TargetConfig.configure(
            project_root=self.project_root,
            code_overrides=self._collect_dir_overrides(),
            app_overrides=self._app_overrides,
        )

        if persist_ini or persist_json:
            self.save_to_ini(self.config_path, silent=True, emit_signal=False)

        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def _resolve_app_current_version(self, target_key: str) -> str | None:
        spec = TargetConfig.get_spec(target_key)
        ov = self._app_overrides.get(target_key, {})

        candidates: list[Path] = []
        raw_vf = ov.get("version_file")
        if raw_vf:
            p = Path(str(raw_vf))
            candidates.append(p if p.is_absolute() else (self.project_root / p))

        rel_list: list[Any] = []
        if isinstance(ov.get("version_rel_paths"), (list, tuple)):
            rel_list.extend(ov["version_rel_paths"])
        if spec and getattr(spec, "version_rel_paths", None):
            rel_list.extend(spec.version_rel_paths)

        for rel in rel_list:
            if rel:
                p = Path(str(rel))
                candidates.append(p if p.is_absolute() else (self.project_root / p))

        candidates.extend(
            [
                self.project_root / SRC_DIR_NAME / target_key / VERSION_FILE_NAME,
                self.project_root / target_key / VERSION_FILE_NAME,
            ]
        )

        seen: set[Path] = set()
        for cand in candidates:
            resolved = cand.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_file():
                try:
                    content = resolved.read_text(encoding=VERSION_FILE_ENCODING).strip()
                except OSError:
                    continue
                parsed = _parse_semver(content)
                if parsed:
                    return f"{parsed[0]}.{parsed[1]}.{parsed[2]}"
                first_line = content.splitlines()[0].strip() if content else ""
                if first_line:
                    return first_line
        return None

    def _format_app_tab_title(self, target_key: str) -> str:
        bump_val = _normalize_bump_unit(self._app_bump_units.get(target_key))
        if not bump_val:
            return target_key

        cur_ver = self._resolve_app_current_version(target_key)
        next_ver = _compute_next_version_str(cur_ver, bump_val)
        if cur_ver and next_ver:
            return f"{target_key} [{next_ver}]"
        if next_ver:
            return f"{target_key} [{next_ver}]"

        return f"{target_key} [+{bump_val}]"
