"""
TargetConfig 일반 설정 탭 위젯 모듈 (build_target_general_tab.py)
- 프로젝트 루트 / 통합 설정 파일(BuildManager.ini) 경로 관리 및 불러오기·저장 요청
- 전역 빌드 디렉터리 설정 ([BuildDirsConfig]) 입력 및 수집/동기화 제공
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from build_manager_config import BUILD_MANAGER_INI_NAME

DIR_FIELD_SPECS: list[tuple[str, str]] = [
    ("work_dir_name", "작업 폴더 (work)"),
    ("dist_dir_name", "배포 폴더 (dist)"),
    ("release_dir_name", "릴리스 폴더 (release)"),
    ("install_dir_name", "인스톨러 폴더 (installer)"),
]


class BuildTargetGeneralTab(QWidget):
    paths_changed = Signal(Path, Path)  # (project_root, ini_path)
    load_requested = Signal(Path)
    save_requested = Signal(Path)
    dir_config_changed = Signal(dict)

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / BUILD_MANAGER_INI_NAME)
        )
        self._dir_inputs: dict[str, QLineEdit] = {}

        self._build_ui()
        self.sync_path_fields()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        path_group = QGroupBox("경로 및 통합 설정 파일")
        path_form = QFormLayout(path_group)

        root_row = QHBoxLayout()
        self.edit_project_root = QLineEdit(str(self.project_root))
        self.edit_project_root.setReadOnly(True)
        self.btn_browse_root = QPushButton("프로젝트 선택...")
        self.btn_browse_root.clicked.connect(self._on_browse_project_root_clicked)
        root_row.addWidget(self.edit_project_root, stretch=1)
        root_row.addWidget(self.btn_browse_root)
        path_form.addRow("프로젝트 루트", root_row)

        cfg_row = QHBoxLayout()
        self.edit_config_path = QLineEdit(str(self.config_path))
        self.btn_browse_cfg = QPushButton("설정 INI 선택...")
        self.btn_browse_cfg.clicked.connect(self._on_browse_config_path_clicked)
        self.btn_load_cfg = QPushButton("불러오기")
        self.btn_load_cfg.clicked.connect(self._on_load_path_clicked)
        self.btn_save_cfg = QPushButton("저장")
        self.btn_save_cfg.clicked.connect(self._on_save_path_clicked)
        cfg_row.addWidget(self.edit_config_path, stretch=1)
        cfg_row.addWidget(self.btn_browse_cfg)
        cfg_row.addWidget(self.btn_load_cfg)
        cfg_row.addWidget(self.btn_save_cfg)
        path_form.addRow("설정 파일 (INI)", cfg_row)

        layout.addWidget(path_group)

        dir_group = QGroupBox("전역 빌드 디렉터리 설정 ([BuildDirsConfig])")
        dir_form = QFormLayout(dir_group)

        for key, label_text in DIR_FIELD_SPECS:
            edit = QLineEdit()
            edit.setPlaceholderText(key)
            edit.editingFinished.connect(self._on_dir_input_changed)
            self._dir_inputs[key] = edit
            dir_form.addRow(label_text, edit)

        layout.addWidget(dir_group)

    def sync_path_fields(self) -> None:
        if hasattr(self, "edit_project_root"):
            self.edit_project_root.setText(str(self.project_root))
        if hasattr(self, "edit_config_path"):
            self.edit_config_path.setText(str(self.config_path))

    def set_paths(
        self,
        project_root: str | Path,
        config_path: str | Path | None = None,
        *,
        emit_signal: bool = False,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / BUILD_MANAGER_INI_NAME)
        )
        self.sync_path_fields()
        if emit_signal:
            self.paths_changed.emit(self.project_root, self.config_path)

    def get_config_path_from_input(self) -> Path:
        typed_cfg = self.edit_config_path.text().strip()
        if typed_cfg:
            self.config_path = Path(typed_cfg).resolve()
        self.sync_path_fields()
        return self.config_path

    def set_dir_values(self, values: dict[str, object] | object) -> None:
        for key, edit in self._dir_inputs.items():
            if isinstance(values, dict):
                raw = values.get(key, "")
            else:
                raw = getattr(values, key, "")
            edit.setText("" if raw is None else str(raw))

    def collect_dir_overrides(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, edit in self._dir_inputs.items():
            val = edit.text().strip()
            if val:
                result[key] = val
        return result

    def _on_dir_input_changed(self) -> None:
        self.dir_config_changed.emit(self.collect_dir_overrides())

    def _on_browse_project_root_clicked(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "프로젝트 루트 폴더 선택",
            str(self.project_root),
        )
        if not chosen:
            return
        self.project_root = Path(chosen).resolve()
        self.config_path = self.project_root / BUILD_MANAGER_INI_NAME
        self.sync_path_fields()
        self.paths_changed.emit(self.project_root, self.config_path)

    def _on_browse_config_path_clicked(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "빌드 설정 INI 파일 선택",
            str(self.config_path.parent),
            "INI Files (*.ini);;All Files (*.*)",
        )
        if not chosen:
            return
        self.config_path = Path(chosen).resolve()
        self.sync_path_fields()
        self.paths_changed.emit(self.project_root, self.config_path)
        self.load_requested.emit(self.config_path)

    def _on_load_path_clicked(self) -> None:
        target = self.get_config_path_from_input()
        self.paths_changed.emit(self.project_root, self.config_path)
        self.load_requested.emit(target)

    def _on_save_path_clicked(self) -> None:
        target = self.get_config_path_from_input()
        self.paths_changed.emit(self.project_root, self.config_path)
        self.save_requested.emit(target)