"""
BuildTargets 세부 설정 위젯 모듈 (build_target_config_tab.py)
- 인스톨러 조합 설정(installer) 및 앱별 세부 빌드 설정(apps, 개별 버전 증가/정리 옵션 포함)을
  전용 탭(개별 앱 탭 -> 마지막 인스톨러 탭)으로 구성하여 조회/편집/JSON 저장 제공
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
    QTabWidget,
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

CLEAN_OPTION_FIELDS: tuple[str, ...] = (
    "clean_work",
    "clean_dist",
    "clean_spec",
)


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


import re

def _parse_semver(raw_version: str) -> tuple[int, int, int] | None:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", (raw_version or "").strip())
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
            self.resize(760, 680)

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
        self._app_clean_options: dict[str, dict[str, bool]] = {}
        self._installer_config: InstallerBuildConfig = InstallerBuildConfig()

        # target_key -> {field_name: input_widget}
        self._app_tab_inputs: dict[str, dict[str, QWidget]] = {}
        self._app_spec_labels: dict[str, QLabel] = {}
        self._app_tab_index_to_key: dict[int, str] = {}
        self._app_key_to_tab_index: dict[str, int] = {}
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

    def _resolve_selected_installer_keys(self, raw_targets: Any) -> set[str]:
        ordered = list(BuildTargets.ordered_keys())
        if not raw_targets:
            return set(ordered)

        if isinstance(raw_targets, (list, tuple, set)):
            tokens = [str(x).strip() for x in raw_targets if str(x).strip()]
        else:
            tokens = [t.strip() for t in str(raw_targets).replace(";", ",").split(",") if t.strip()]

        if not tokens:
            return set(ordered)

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
                spec = BuildTargets.get_spec(key)
                spec_id = getattr(spec, "id", None) if spec else None
                if spec_id is not None and str(spec_id).strip() == tok:
                    resolved.add(key)
                    break

        return resolved or set(ordered)

    def _compute_auto_installer_fields(self, selected_keys: list[str]) -> tuple[str, str]:
        """선택된 포함 대상 목록으로부터 기본 파일명(name)과 버전 기준(version_source_id)을 계산합니다."""
        if not selected_keys:
            return "", ""

        first_key = selected_keys[0].strip()
        spec = BuildTargets.get_spec(first_key)
        auto_name = f"{first_key}Setup" if first_key else ""

        spec_id = getattr(spec, "id", None) if spec else None
        auto_ver_src = str(spec_id).strip() if spec_id is not None and str(spec_id).strip() else first_key
        return auto_name, auto_ver_src

    def _sync_installer_modes_when_empty(self) -> None:
        """포함 대상이 하나도 선택되지 않았을 때 단독 모드 및 건너뛰기를 모두 체크 해제합니다."""
        if not self._installer_inputs:
            return
        ordered = list(BuildTargets.ordered_keys())
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
        """포함 대상 체크박스 선택 상태에 맞춰 name 및 version_source_id를 자동 생성합니다."""
        if not self._installer_inputs:
            return

        ordered = list(BuildTargets.ordered_keys())
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
        if force or not cur_name or cur_name == self._auto_generated_name or cur_name == "PrintShopSetup":
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

        ordered = list(BuildTargets.ordered_keys())
        selected_keys = self._resolve_selected_installer_keys(selected_raw)

        for idx, key in enumerate(ordered, start=1):
            spec = BuildTargets.get_spec(key)
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
        checked_cnt = sum(1 for chk in self._installer_target_checkboxes.values() if chk.isChecked())
        self._installer_all_checkbox.blockSignals(True)
        self._installer_all_checkbox.setChecked(total > 0 and checked_cnt == total)
        self._installer_all_checkbox.blockSignals(False)

    def _on_installer_all_targets_clicked(self) -> None:
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
        self._sync_installer_all_checkbox()
        self._sync_installer_modes_when_empty()
        self._sync_installer_auto_fields()

    def _get_checked_installer_targets(self) -> list[str] | None:
        if not self._installer_target_checkboxes:
            return None
        ordered = list(BuildTargets.ordered_keys())
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
            for key in BuildTargets.ordered_keys()
            if key in self._installer_target_checkboxes
            and self._installer_target_checkboxes[key].isChecked()
        ]
        auto_name, auto_ver_src = self._compute_auto_installer_fields(selected_ordered)
        self._auto_generated_name = auto_name
        self._auto_generated_ver_src = auto_ver_src

        raw_cfg_name = str(cfg.name or "").strip()
        resolved_name = auto_name if (not raw_cfg_name or raw_cfg_name == "PrintShopSetup") else raw_cfg_name
        self._installer_inputs["name"].setText(resolved_name)
        self._installer_inputs["version_source_id"].setText(str(cfg.version_source_id or auto_ver_src))
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
        for key in BuildTargets.ordered_keys():
            ov = self._app_overrides.get(key, {})
            if "bump_unit" in ov:
                updated[key] = _normalize_bump_unit(ov.get("bump_unit"))
            else:
                updated[key] = self._app_bump_units.get(key)
        self._app_bump_units = updated

    def _sync_clean_options_from_overrides(self) -> None:
        updated: dict[str, dict[str, bool]] = {}
        for key in BuildTargets.ordered_keys():
            spec = BuildTargets.get_spec(key)
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

    def set_app_bump_units(self, bump_units: dict[str, Any] | None) -> None:
        """외부(BuildManagerWindow 등)에서 앱별 버전 증가 설정을 동기화."""
        src = bump_units or {}
        for key in BuildTargets.ordered_keys():
            if key in src:
                self._app_bump_units[key] = _normalize_bump_unit(src.get(key))
            elif key not in self._app_bump_units:
                self._app_bump_units[key] = None
        self._refresh_app_tab_titles()
        for key in BuildTargets.ordered_keys():
            self._load_app_form(key)

    def get_app_bump_units(self) -> dict[str, str | None]:
        """현재 확인된 모든 앱의 개별 버전 증가 설정 반환."""
        result: dict[str, str | None] = {}
        for key in BuildTargets.ordered_keys():
            result[key] = _normalize_bump_unit(self._app_bump_units.get(key))
        return result

    def set_app_clean_options(self, clean_options: dict[str, dict[str, Any]] | None) -> None:
        """외부에서 앱별 정리 옵션(--clean-work, --clean-dist, --clean-spec) 동기화."""
        src = clean_options or {}
        for key in BuildTargets.ordered_keys():
            current = dict(
                self._app_clean_options.get(
                    key, {field: False for field in CLEAN_OPTION_FIELDS}
                )
            )
            incoming = src.get(key)
            if isinstance(incoming, dict):
                for field in CLEAN_OPTION_FIELDS:
                    if field in incoming:
                        current[field] = bool(incoming[field])
            self._app_clean_options[key] = current
            self._load_app_form(key)

    def get_app_clean_options(self) -> dict[str, dict[str, bool]]:
        """현재 앱별 정리 옵션 반환."""
        result: dict[str, dict[str, bool]] = {}
        for key in BuildTargets.ordered_keys():
            current = self._app_clean_options.get(key, {})
            result[key] = {
                field: bool(current.get(field, False)) for field in CLEAN_OPTION_FIELDS
            }
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
            self._sync_clean_options_from_overrides()

            self._installer_config = InstallerBuildConfig.resolve(
                project_root=self.project_root,
                json_path=json_arg,
            )

            self._rebuild_app_tabs()
            self._load_installer_form(self._installer_config)
            for key in BuildTargets.ordered_keys():
                self._load_app_form(key)
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

        self.sub_tabs = QTabWidget(self)
        self.sub_tabs.currentChanged.connect(self._on_sub_tab_changed)

        self._installer_tab_widget = self._create_installer_tab()

        # build_targets 순서대로 개별 앱 탭 생성 후 인스톨러 탭을 마지막에 배치
        self._rebuild_app_tabs()

        outer_layout.addWidget(self.sub_tabs, stretch=1)

        # 하단 공통 액션 버튼 (설정탭과 저장 동선 중복 방지를 위해 저장 버튼 제외)
        action_row = QHBoxLayout()
        self.btn_apply_all = QPushButton("전체 탭 변경사항 반영")
        self.btn_apply_all.clicked.connect(self._on_apply_all_tabs)

        self.btn_reload = QPushButton("다시 불러오기")
        self.btn_reload.clicked.connect(self.reload_from_targets)

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

        inst_group = QGroupBox("인스톨러 조합 설정 (installer)")
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
        btn_apply_inst = QPushButton("인스톨러 설정 반영")
        btn_apply_inst.clicked.connect(self._on_apply_installer)
        btn_row.addWidget(btn_apply_inst)
        layout.addLayout(btn_row)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    # def _format_app_tab_title(self, target_key: str) -> str:
    #     bump_val = _normalize_bump_unit(self._app_bump_units.get(target_key))
    #     bump_suffix = f" [+{bump_val}]" if bump_val else ""
    #     return f"{target_key}{bump_suffix}"

    def _create_single_app_tab(self, target_key: str) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        spec = BuildTargets.get_spec(target_key)
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
        app_form.addRow("산출물 정리", clean_row)

        app_vbox.addLayout(app_form)

        btn_row = QHBoxLayout()
        btn_reset = QPushButton("이 앱 기본값 초기화")
        btn_reset.clicked.connect(lambda _checked=False, k=target_key: self._on_reset_app(k))

        btn_apply = QPushButton("이 앱 설정 반영")
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

        # 1. build_targets 순서대로 개별 앱 탭 추가
        for key in BuildTargets.ordered_keys():
            tab_widget = self._create_single_app_tab(key)
            idx = self.sub_tabs.addTab(tab_widget, self._format_app_tab_title(key))
            self._app_tab_index_to_key[idx] = key
            self._app_key_to_tab_index[key] = idx

        # 2. 인스톨러 탭을 제일 마지막에 추가
        if self._installer_tab_widget is None:
            self._installer_tab_widget = self._create_installer_tab()
        self._installer_tab_index = self.sub_tabs.addTab(
            self._installer_tab_widget,
            self._format_installer_tab_title(),
        )

        if self._installer_target_checkboxes:
            self._rebuild_installer_target_checkboxes(
                prev_inst_targets if prev_inst_targets is not None else self._installer_config.targets
            )

        if prev_key and prev_key in self._app_key_to_tab_index:
            self.sub_tabs.setCurrentIndex(self._app_key_to_tab_index[prev_key])
        elif was_installer_selected:
            self.sub_tabs.setCurrentIndex(self._installer_tab_index)
        elif self.sub_tabs.count() > 0:
            self.sub_tabs.setCurrentIndex(0)
        self.sub_tabs.blockSignals(False)

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

        spec = BuildTargets.get_spec(target_key)
        ov = self._app_overrides.get(target_key, {})

        bump_combo = inputs.get("bump_unit")
        if isinstance(bump_combo, QComboBox):
            current_bump = _normalize_bump_unit(
                self._app_bump_units.get(target_key, ov.get("bump_unit"))
            )
            b_idx = bump_combo.findData(current_bump)
            bump_combo.setCurrentIndex(b_idx if b_idx >= 0 else 0)

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
                    f"현재 스펙: order={spec.order}, label={spec.label}, exe={spec.exe_name}, "
                    f"console={spec.console}, dirs={_join_list_field(spec.dir_hints)}"
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
        spec = BuildTargets.get_spec(target_key)
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

        for list_field in ("dir_hints", "spec_hints", "entry_hints", "version_rel_paths"):
            items = _split_list_field(inputs[list_field].text())
            default_tuple = getattr(spec, list_field, ()) if spec else ()
            if items and tuple(items) != tuple(default_tuple):
                patch[list_field] = items
            elif not items and list_field in self._app_overrides.get(target_key, {}):
                patch[list_field] = None

        allowed = set(APP_OVERRIDE_FIELDS) | set(CLEAN_OPTION_FIELDS)
        filtered = {k: v for k, v in patch.items() if k in allowed}

        clean_opts = self._collect_app_clean_options(target_key)
        for field in CLEAN_OPTION_FIELDS:
            default_clean = bool(getattr(spec, field, False)) if spec else False
            val = bool(clean_opts.get(field, False))
            if val != default_clean or field in self._app_overrides.get(target_key, {}):
                filtered[field] = val

        return filtered

    def _stage_app_state(self, target_key: str) -> None:
        bump_unit = self._collect_app_bump_unit(target_key)
        self._app_bump_units[target_key] = bump_unit

        clean_opts = self._collect_app_clean_options(target_key)
        self._app_clean_options[target_key] = clean_opts

        patch = self._collect_app_patch(target_key)
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

    def _stage_all_tabs_state(self) -> None:
        if self._installer_inputs:
            self._installer_config = self._collect_installer_config()
        for key in BuildTargets.ordered_keys():
            if key in self._app_tab_inputs:
                self._stage_app_state(key)

    def _apply_all_to_targets(self, *, emit_signal: bool = True) -> None:
        dir_ov = self._collect_dir_overrides()
        self._stage_all_tabs_state()
        BuildTargets.configure(
            project_root=self.project_root,
            code_overrides=dir_ov,
            app_overrides=self._app_overrides,
        )
        self._sync_bump_units_from_overrides()
        self._sync_clean_options_from_overrides()
        self._refresh_app_tab_titles()
        for key in BuildTargets.ordered_keys():
            self._load_app_form(key)
        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def _on_sub_tab_changed(self, _index: int) -> None:
        self._stage_all_tabs_state()
        self._refresh_app_tab_titles()

    def _on_apply_installer(self) -> None:
        self._installer_config = self._collect_installer_config()
        self._apply_all_to_targets()

    def _on_apply_app(self, target_key: str) -> None:
        self._stage_app_state(target_key)
        self._apply_all_to_targets()

    def _on_apply_all_tabs(self) -> None:
        self._apply_all_to_targets()

    def _on_reset_app(self, target_key: str) -> None:
        self._app_overrides.pop(target_key, None)
        self._app_bump_units[target_key] = None
        self._app_clean_options[target_key] = {
            field: False for field in CLEAN_OPTION_FIELDS
        }
        self._apply_all_to_targets()

    def reload_from_targets(self) -> None:
        BuildTargets.configure(project_root=self.project_root)
        dcfg = BuildTargets.get_dir_config(self.project_root)
        if self.general_tab is not None:
            self.general_tab.set_dir_values(dcfg)

        self._app_overrides = BuildTargets.get_app_overrides()
        self._sync_bump_units_from_overrides()
        self._sync_clean_options_from_overrides()
        json_arg = str(self.config_path) if self.config_path.is_file() else None
        self._installer_config = InstallerBuildConfig.resolve(
            project_root=self.project_root,
            json_path=json_arg,
        )
        self._rebuild_app_tabs()
        self._load_installer_form(self._installer_config)
        for key in BuildTargets.ordered_keys():
            self._load_app_form(key)
        self.config_changed.emit(self.get_current_config_payload())

    def reset_all_defaults(self) -> None:
        self._app_overrides = {}
        self._app_bump_units = {key: None for key in BuildTargets.ordered_keys()}
        self._app_clean_options = {
            key: {field: False for field in CLEAN_OPTION_FIELDS}
            for key in BuildTargets.ordered_keys()
        }
        self._installer_config = InstallerBuildConfig()
        BuildTargets.configure(project_root=self.project_root, reset=True)
        dcfg = BuildTargets.get_dir_config(self.project_root)
        if self.general_tab is not None:
            self.general_tab.set_dir_values(dcfg)
        self._rebuild_app_tabs()
        self._load_installer_form(self._installer_config)
        for key in BuildTargets.ordered_keys():
            self._load_app_form(key)
        self.config_changed.emit(self.get_current_config_payload())

    def get_current_config_payload(self) -> dict[str, Any]:
        self._stage_all_tabs_state()
        return {
            "dir_overrides": self._collect_dir_overrides(),
            "app_overrides": {k: dict(v) for k, v in self._app_overrides.items()},
            "app_bump_units": self.get_app_bump_units(),
            "app_clean_options": self.get_app_clean_options(),
            "installer_config": self._collect_installer_config().to_dict(),
        }

    def apply_clean_options_to_targets(
        self,
        target_keys: list[str],
        clean_patch: dict[str, bool],
        *,
        persist_json: bool = False,
        emit_signal: bool = True,
    ) -> None:
        """메인 앱에서 변경된 정리 옵션을 현재 선택된 개별 앱들에 일괄 적용."""
        if not target_keys or not clean_patch:
            return

        normalized_patch: dict[str, bool] = {
            k: bool(v) for k, v in clean_patch.items() if k in CLEAN_OPTION_FIELDS
        }
        if not normalized_patch:
            return

        for key in target_keys:
            if key not in self._app_tab_inputs and key not in BuildTargets.BY_KEY:
                continue

            cur_clean = dict(
                self._app_clean_options.get(key, {f: False for f in CLEAN_OPTION_FIELDS})
            )
            cur_clean.update(normalized_patch)
            self._app_clean_options[key] = cur_clean

            bucket = dict(self._app_overrides.get(key, {}))
            bucket.update(normalized_patch)
            self._app_overrides[key] = bucket

            # 해당 앱 탭의 체크박스도 즉시 동기화
            inputs = self._app_tab_inputs.get(key)
            if inputs:
                for field_name, val in normalized_patch.items():
                    chk = inputs.get(field_name)
                    if isinstance(chk, QCheckBox):
                        chk.blockSignals(True)
                        chk.setChecked(bool(val))
                        chk.blockSignals(False)

        BuildTargets.configure(
            project_root=self.project_root,
            code_overrides=self._collect_dir_overrides(),
            app_overrides=self._app_overrides,
        )

        if persist_json:
            self.save_to_json(self.config_path, silent=True, emit_signal=False)

        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def apply_app_fields_to_targets(
        self,
        target_keys: list[str],
        field_patch: dict[str, Any],
        *,
        persist_json: bool = False,
        emit_signal: bool = True,
    ) -> None:
        """메인 앱에서 변경된 필드(mode, bump_unit 등)를 현재 선택된 개별 앱들에 일괄 적용."""
        if not target_keys or not field_patch:
            return

        allowed = {"mode", "bump_unit"}
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
            else:
                normalized_patch[k] = v

        if not normalized_patch:
            return

        for key in target_keys:
            if key not in self._app_tab_inputs and key not in BuildTargets.BY_KEY:
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
                if "mode" in normalized_patch:
                    mode_widget = inputs.get("mode")
                    if isinstance(mode_widget, QComboBox):
                        idx = mode_widget.findText(str(normalized_patch["mode"]))
                        if idx >= 0:
                            mode_widget.blockSignals(True)
                            mode_widget.setCurrentIndex(idx)
                            mode_widget.blockSignals(False)

        BuildTargets.configure(
            project_root=self.project_root,
            code_overrides=self._collect_dir_overrides(),
            app_overrides=self._app_overrides,
        )

        if persist_json:
            self.save_to_json(self.config_path, silent=True, emit_signal=False)

        if emit_signal:
            self.config_changed.emit(self.get_current_config_payload())

    def _resolve_app_current_version(self, target_key: str) -> str | None:
        spec = BuildTargets.get_spec(target_key)
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

        candidates.extend([
            self.project_root / "src" / target_key / "version.txt",
            self.project_root / target_key / "version.txt",
        ])

        seen: set[Path] = set()
        for cand in candidates:
            resolved = cand.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_file():
                try:
                    content = resolved.read_text(encoding="utf-8-sig").strip()
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
            return f"{target_key} {next_ver}]"
            #return f"{target_key} [+{bump_val}: {cur_ver} -> {next_ver}]"        
        if next_ver:
            return f"{target_key} {next_ver}]"
            #return f"{target_key} [+{bump_val} -> {next_ver}]"
            
        return f"{target_key} [+{bump_val}]"            