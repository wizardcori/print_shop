"""
BuildTargets 세부 설정 위젯 모듈 (build_target_config_tab.py)
- 인스톨러 조합 설정(installer) 및 앱별 세부 빌드 설정(apps, 개별 버전 증가 포함) 조회/편집/JSON 저장 제공
- 경로 및 전역 디렉터리(dirs) 설정은 BuildTargetGeneralTab과 연동
- 별도 위젯 창으로 열릴 때 닫기 버튼 클릭 시 hide()로 숨김 처리
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from build_script.build_targets import (
    APP_OVERRIDE_FIELDS,
    BuildTargets,
    DEFAULT_CONFIG_FILENAME,
)
from build_script.target_config_io import (
    InstallerBuildConfig,
    normalize_target_id_list,
    write_build_config_json,
)
from build_target_general_tab import BuildTargetGeneralTab

BUMP_UNIT_OPTIONS: list[tuple[str, str | None]] = [
    ("변경 없음 (none)", None),
    ("patch", "patch"),
    ("minor", "minor"),
    ("major", "major"),
]


def _normalize_bump_unit(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s in ("none", "null", "false", "0", "변경 없음"):
        return None
    if s in ("patch", "minor", "major"):
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


class BuildTargetConfigTab(QWidget):
    config_changed = Signal(dict)
    paths_changed = Signal(Path, Path)  # (project_root, config_path)
    save_requested = Signal()

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
        auto_save: bool = False,
        parent: QWidget | None = None,
        general_tab: BuildTargetGeneralTab | None = None,
        as_window: bool = True,
    ) -> None:
        super().__init__(parent)
        self._allow_close: bool = False
        if as_window:
            self.setWindowFlags(Qt.WindowType.Window)
            self.setWindowTitle("BuildTarget 설정")
            self.resize(680, 620)

        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / DEFAULT_CONFIG_FILENAME)
        )
        self.auto_save = auto_save
        self.general_tab: BuildTargetGeneralTab | None = general_tab

        self._app_overrides: dict[str, dict[str, Any]] = {}
        self._app_bump_units: dict[str, str | None] = {}
        self._installer_config: InstallerBuildConfig = InstallerBuildConfig()
        self._app_inputs: dict[str, QWidget] = {}
        self._installer_inputs: dict[str, QWidget] = {}

        self._build_ui()
        if self.general_tab is not None:
            self.bind_general_tab(self.general_tab)
        self.sync_path_fields()
        self.load_from_json(self.config_path, show_error=False)

    def force_close_window(self) -> None:
        """프로그램 종료 시 실제로 창을 닫습니다."""
        self._allow_close = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close or not self.isWindow():
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()

    def bind_general_tab(self, general_tab: BuildTargetGeneralTab) -> None:
        """외부 General 탭 위젯과 경로·디렉터리·불러오기/저장 시그널을 연결."""
        self.general_tab = general_tab
        general_tab.set_paths(self.project_root, self.config_path)
        general_tab.paths_changed.connect(self._on_general_paths_changed)
        general_tab.load_requested.connect(self._on_general_load_requested)
        general_tab.save_requested.connect(self._on_general_save_requested)
        general_tab.dir_config_changed.connect(self._on_general_dirs_changed)

    def _on_general_paths_changed(self, project_root: Path, config_path: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path).resolve()
        self.paths_changed.emit(self.project_root, self.config_path)

    def _on_general_load_requested(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.load_from_json(self.config_path, show_error=True)

    def _on_general_save_requested(self, config_path: Path) -> None:
        self.config_path = Path(config_path).resolve()
        self.save_to_json(self.config_path)
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
            else (self.project_root / DEFAULT_CONFIG_FILENAME)
        )
        self.sync_path_fields()

    def _load_installer_form(self, cfg: InstallerBuildConfig) -> None:
        if not self._installer_inputs:
            return
        self._installer_inputs["targets"].setText(_join_list_field(cfg.targets))
        self._installer_inputs["name"].setText(str(cfg.name or ""))
        self._installer_inputs["version_source_id"].setText(str(cfg.version_source_id or ""))

    def _collect_installer_config(self) -> InstallerBuildConfig:
        raw_targets = self._installer_inputs["targets"].text().strip()
        parsed_targets = normalize_target_id_list(raw_targets) if raw_targets else None
        raw_name = self._installer_inputs["name"].text().strip() or None
        raw_ver_src = self._installer_inputs["version_source_id"].text().strip() or None

        return InstallerBuildConfig(
            targets=parsed_targets,
            installer_only=bool(self._installer_config.installer_only),
            skip_installer=bool(self._installer_config.skip_installer),
            name=raw_name,
            version_source_id=raw_ver_src,
            extra=dict(self._installer_config.extra),
        )

    def _sync_bump_units_from_overrides(self) -> None:
        updated: dict[str, str | None] = {}
        for key in BuildTargets.ordered_keys():
            ov = self._app_overrides.get(key, {})
            if "bump_unit" in ov:
                updated[key] = _normalize_bump_unit(ov.get("bump_unit"))
            else:
                updated[key] = self._app_bump_units.get(key)
        self._app_bump_units = updated

    def set_app_bump_units(self, bump_units: dict[str, Any] | None) -> None:
        """외부(BuildManagerWindow 등)에서 앱별 버전 증가 설정을 동기화."""
        src = bump_units or {}
        for key in BuildTargets.ordered_keys():
            if key in src:
                self._app_bump_units[key] = _normalize_bump_unit(src.get(key))
            elif key not in self._app_bump_units:
                self._app_bump_units[key] = None
        self._load_app_form(self._current_target_key())

    def get_app_bump_units(self) -> dict[str, str | None]:
        """현재 확인된 모든 앱의 개별 버전 증가 설정 반환."""
        result: dict[str, str | None] = {}
        for key in BuildTargets.ordered_keys():
            result[key] = _normalize_bump_unit(self._app_bump_units.get(key))
        return result

    def load_from_json(
        self,
        json_path: str | Path | None = None,
        *,
        show_error: bool = True,
    ) -> bool:
        target_file = Path(json_path).resolve() if json_path else self.config_path
        self.config_path = target_file
        self.sync_path_fields()
        try:
            json_arg = str(target_file) if target_file.is_file() else None
            if json_arg:
                BuildTargets.configure(
                    project_root=self.project_root,
                    json_path=target_file,
                )
            else:
                BuildTargets.configure(project_root=self.project_root)

            dcfg = BuildTargets.get_dir_config(self.project_root)
            if self.general_tab is not None:
                self.general_tab.set_dir_values(dcfg)

            self._app_overrides = BuildTargets.get_app_overrides()
            self._sync_bump_units_from_overrides()

            self._installer_config = InstallerBuildConfig.resolve(
                project_root=self.project_root,
                json_path=json_arg,
            )
            self._load_installer_form(self._installer_config)

            self._populate_app_combo()
            self._load_app_form(self._current_target_key())
            self.config_changed.emit(self.get_current_config_payload())
            return True
        except Exception as exc:
            if show_error:
                QMessageBox.critical(
                    self,
                    "설정 불러오기 실패",
                    f"설정을 불러오는 중 오류가 발생했습니다:\n{exc}",
                )
            return False

    def save_to_json(
        self,
        json_path: str | Path | None = None,
        *,
        silent: bool = False,
        emit_signal: bool | None = None,
    ) -> Path | None:
        if self.general_tab is not None:
            self.config_path = self.general_tab.get_config_path_from_input()
        target_file = Path(json_path).resolve() if json_path else self.config_path
        should_emit = (not self.auto_save) if emit_signal is None else emit_signal
        self._apply_all_to_targets(emit_signal=should_emit)
        try:
            dcfg = BuildTargets.get_dir_config(self.project_root)
            if hasattr(BuildTargets, "save_config_json"):
                saved = BuildTargets.save_config_json(
                    target_file,
                    dir_config=dcfg,
                    app_overrides=self._app_overrides,
                    installer_config=self._installer_config,
                )
            else:
                saved = write_build_config_json(
                    target_file,
                    dir_config=dcfg,
                    app_overrides=self._app_overrides,
                    installer_config=self._installer_config,
                )
            if not silent:
                QMessageBox.information(self, "설정 저장", f"설정을 저장했습니다:\n{saved}")
            return Path(saved)
        except Exception as exc:
            if not silent:
                QMessageBox.critical(
                    self,
                    "설정 저장 실패",
                    f"설정을 저장하는 중 오류가 발생했습니다:\n{exc}",
                )
            return None

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(8)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        # 1. 인스톨러 조합 설정 그룹
        inst_group = QGroupBox("인스톨러 조합 설정 (installer)")
        inst_form = QFormLayout(inst_group)

        edit_inst_targets = QLineEdit()
        edit_inst_targets.setPlaceholderText("비우면 선택/전체 대상, 예: 1,3,5 또는 1,2 (ID 오름차순 자동 정렬)")
        edit_inst_name = QLineEdit()
        edit_inst_name.setPlaceholderText("기본값: <PREFIX>Setup (예: PrintShopSetup)")
        edit_inst_ver_src = QLineEdit()
        edit_inst_ver_src.setPlaceholderText("버전 기준 대상 키/ID (선택)")

        self._installer_inputs = {
            "targets": edit_inst_targets,
            "name": edit_inst_name,
            "version_source_id": edit_inst_ver_src,
        }

        inst_form.addRow("포함 대상 (targets)", edit_inst_targets)
        inst_form.addRow("기본 파일명 (name)", edit_inst_name)
        inst_form.addRow("버전 기준 (version_source_id)", edit_inst_ver_src)

        layout.addWidget(inst_group)

        # 2. 앱별 세부설정 그룹
        app_group = QGroupBox("앱별 세부 빌드 설정 (apps)")
        app_vbox = QVBoxLayout(app_group)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("대상 앱:"))
        self.app_combo = QComboBox()
        self.app_combo.currentIndexChanged.connect(self._on_app_selection_changed)
        selector_row.addWidget(self.app_combo, stretch=1)

        self.btn_reset_app = QPushButton("선택 앱 초기화")
        self.btn_reset_app.clicked.connect(self._on_reset_selected_app)
        selector_row.addWidget(self.btn_reset_app)
        app_vbox.addLayout(selector_row)

        self.spec_summary_label = QLabel("현재 스펙: -")
        self.spec_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.spec_summary_label.setStyleSheet("color: #444; padding: 4px 0;")
        app_vbox.addWidget(self.spec_summary_label)

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

        self._app_inputs = {
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
        }

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

        app_vbox.addLayout(app_form)

        app_btn_row = QHBoxLayout()
        app_btn_row.addStretch(1)
        self.btn_apply_app = QPushButton("현재 앱 설정 반영")
        self.btn_apply_app.clicked.connect(self._on_apply_current_app)
        app_btn_row.addWidget(self.btn_apply_app)
        app_vbox.addLayout(app_btn_row)

        layout.addWidget(app_group)

        # 3. 하단 액션 버튼 (설정탭과 저장 동선 중복 방지를 위해 저장 버튼 제외)
        action_row = QHBoxLayout()
        self.btn_reload = QPushButton("다시 불러오기")
        self.btn_reload.clicked.connect(self.reload_from_targets)

        self.btn_reset_all = QPushButton("전체 기본값 복원")
        self.btn_reset_all.clicked.connect(self.reset_all_defaults)

        action_row.addWidget(self.btn_reload)
        action_row.addWidget(self.btn_reset_all)
        action_row.addStretch(1)

        layout.addLayout(action_row)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def _populate_app_combo(self) -> None:
        current_key = self.app_combo.currentData()
        self.app_combo.blockSignals(True)
        self.app_combo.clear()
        for key in BuildTargets.ordered_keys():
            spec = BuildTargets.get_spec(key)
            bump_val = _normalize_bump_unit(self._app_bump_units.get(key))
            bump_suffix = f" | bump={bump_val}" if bump_val else ""
            title = f"{key} ({spec.label}){bump_suffix}" if spec else f"{key}{bump_suffix}"
            self.app_combo.addItem(title, userData=key)
        if current_key:
            idx = self.app_combo.findData(current_key)
            if idx >= 0:
                self.app_combo.setCurrentIndex(idx)
        self.app_combo.blockSignals(False)

    def _current_target_key(self) -> str | None:
        data = self.app_combo.currentData()
        return str(data) if data else None

    def _load_app_form(self, target_key: str | None) -> None:
        if not target_key:
            return
        spec = BuildTargets.get_spec(target_key)
        ov = self._app_overrides.get(target_key, {})

        bump_combo = self._app_inputs.get("bump_unit")
        if isinstance(bump_combo, QComboBox):
            current_bump = _normalize_bump_unit(
                self._app_bump_units.get(target_key, ov.get("bump_unit"))
            )
            b_idx = bump_combo.findData(current_bump)
            bump_combo.setCurrentIndex(b_idx if b_idx >= 0 else 0)

        if spec:
            self.spec_summary_label.setText(
                f"현재 스펙: order={spec.order}, label={spec.label}, exe={spec.exe_name}, "
                f"console={spec.console}, dirs={_join_list_field(spec.dir_hints)}"
            )
            self._app_inputs["label"].setText(str(ov.get("label") or spec.label))
            self._app_inputs["exe_name"].setText(str(ov.get("exe_name") or spec.exe_name))
            console_val = ov["console"] if isinstance(ov.get("console"), bool) else spec.console
            self._app_inputs["console"].setChecked(bool(console_val))
            self._app_inputs["entry_file"].setText(str(ov.get("entry_file") or ""))
            self._app_inputs["version_file"].setText(str(ov.get("version_file") or ""))
            self._app_inputs["dir_hints"].setText(
                _join_list_field(ov.get("dir_hints") if "dir_hints" in ov else spec.dir_hints)
            )
            self._app_inputs["spec_hints"].setText(
                _join_list_field(ov.get("spec_hints") if "spec_hints" in ov else spec.spec_hints)
            )
            self._app_inputs["entry_hints"].setText(
                _join_list_field(ov.get("entry_hints") if "entry_hints" in ov else spec.entry_hints)
            )
            self._app_inputs["version_rel_paths"].setText(
                _join_list_field(
                    ov.get("version_rel_paths") if "version_rel_paths" in ov else spec.version_rel_paths
                )
            )

    def _on_app_selection_changed(self, _index: int) -> None:
        self._load_app_form(self._current_target_key())

    def _collect_dir_overrides(self) -> dict[str, str]:
        if self.general_tab is not None:
            return self.general_tab.collect_dir_overrides()
        return {}

    def _collect_current_app_bump_unit(self, target_key: str) -> str | None:
        bump_combo = self._app_inputs.get("bump_unit")
        if isinstance(bump_combo, QComboBox):
            return _normalize_bump_unit(bump_combo.currentData())
        return _normalize_bump_unit(self._app_bump_units.get(target_key))

    def _collect_current_app_patch(self, target_key: str) -> dict[str, Any]:
        spec = BuildTargets.get_spec(target_key)
        patch: dict[str, Any] = {}

        label_txt = self._app_inputs["label"].text().strip()
        if label_txt and (not spec or label_txt != spec.label):
            patch["label"] = label_txt
        elif not label_txt:
            patch["label"] = None

        exe_txt = self._app_inputs["exe_name"].text().strip()
        if exe_txt and (not spec or exe_txt != spec.exe_name):
            patch["exe_name"] = exe_txt
        elif not exe_txt:
            patch["exe_name"] = None

        checked_console = bool(self._app_inputs["console"].isChecked())
        if spec and checked_console != spec.console:
            patch["console"] = checked_console
        elif "console" in self._app_overrides.get(target_key, {}):
            patch["console"] = checked_console

        entry_file_txt = self._app_inputs["entry_file"].text().strip()
        patch["entry_file"] = entry_file_txt if entry_file_txt else None

        version_file_txt = self._app_inputs["version_file"].text().strip()
        patch["version_file"] = version_file_txt if version_file_txt else None

        for list_field in ("dir_hints", "spec_hints", "entry_hints", "version_rel_paths"):
            items = _split_list_field(self._app_inputs[list_field].text())
            default_tuple = getattr(spec, list_field, ()) if spec else ()
            if items and tuple(items) != tuple(default_tuple):
                patch[list_field] = items
            elif not items and list_field in self._app_overrides.get(target_key, {}):
                patch[list_field] = None

        return {k: v for k, v in patch.items() if k in APP_OVERRIDE_FIELDS}

    def _apply_all_to_targets(self, *, emit_signal: bool = True) -> None:
        dir_ov = self._collect_dir_overrides()
        self._installer_config = self._collect_installer_config()
        BuildTargets.configure(
            project_root=self.project_root,
            code_overrides=dir_ov,
            app_overrides=self._app_overrides,
        )
        self._sync_bump_units_from_overrides()
        self._populate_app_combo()
        self._load_app_form(self._current_target_key())
        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def _on_apply_current_app(self) -> None:
        target_key = self._current_target_key()
        if not target_key:
            return
        bump_unit = self._collect_current_app_bump_unit(target_key)
        self._app_bump_units[target_key] = bump_unit

        patch = self._collect_current_app_patch(target_key)
        bucket = dict(self._app_overrides.get(target_key, {}))
        for k, v in patch.items():
            if v is None:
                bucket.pop(k, None)
            else:
                bucket[k] = v
        if bump_unit is not None:
            bucket["bump_unit"] = bump_unit
        else:
            bucket.pop("bump_unit", None)

        if bucket:
            self._app_overrides[target_key] = bucket
        else:
            self._app_overrides.pop(target_key, None)
        self._apply_all_to_targets()

    def _on_reset_selected_app(self) -> None:
        target_key = self._current_target_key()
        if not target_key:
            return
        self._app_overrides.pop(target_key, None)
        self._app_bump_units[target_key] = None
        self._apply_all_to_targets()

    def reload_from_targets(self) -> None:
        BuildTargets.configure(project_root=self.project_root)
        dcfg = BuildTargets.get_dir_config(self.project_root)
        if self.general_tab is not None:
            self.general_tab.set_dir_values(dcfg)

        self._app_overrides = BuildTargets.get_app_overrides()
        self._sync_bump_units_from_overrides()
        json_arg = str(self.config_path) if self.config_path.is_file() else None
        self._installer_config = InstallerBuildConfig.resolve(
            project_root=self.project_root,
            json_path=json_arg,
        )
        self._load_installer_form(self._installer_config)
        self._populate_app_combo()
        self._load_app_form(self._current_target_key())
        self.config_changed.emit(self.get_current_config_payload())

    def reset_all_defaults(self) -> None:
        self._app_overrides = {}
        self._app_bump_units = {key: None for key in BuildTargets.ordered_keys()}
        self._installer_config = InstallerBuildConfig()
        BuildTargets.configure(project_root=self.project_root, reset=True)
        dcfg = BuildTargets.get_dir_config(self.project_root)
        if self.general_tab is not None:
            self.general_tab.set_dir_values(dcfg)
        self._load_installer_form(self._installer_config)
        self._populate_app_combo()
        self._load_app_form(self._current_target_key())
        self.config_changed.emit(self.get_current_config_payload())

    def get_current_config_payload(self) -> dict[str, Any]:
        return {
            "dir_overrides": self._collect_dir_overrides(),
            "app_overrides": {k: dict(v) for k, v in self._app_overrides.items()},
            "app_bump_units": self.get_app_bump_units(),
            "installer_config": self._collect_installer_config().to_dict(),
        }