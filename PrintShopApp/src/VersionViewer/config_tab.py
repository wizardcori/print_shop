import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QFileDialog, QLabel
)
from viewer_config import VersionViewerConfig, viewer_config_instance
from Common.log import logd, loge


class ConfigTab(QWidget):
    """VersionViewerConfig 설정을 편집하는 탭 위젯"""

    def __init__(self, config: VersionViewerConfig = None, parent=None):
        super().__init__(parent)
        self.config = config or viewer_config_instance
        self._init_ui()
        self.load_from_config()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 경로 및 검색 깊이 설정 그룹
        path_group = QGroupBox("스캔 경로 및 폴더 깊이 설정 (Scan Path & Dir Depth)")
        path_form_layout = QFormLayout(path_group)

        path_row_layout = QHBoxLayout()
        self.edit_last_path = QLineEdit()
        self.edit_last_path.setPlaceholderText("기본 스캔 폴더 또는 실행 파일(.exe, .zip) 경로")
        self.edit_last_path.editingFinished.connect(self._on_last_path_changed)

        btn_browse_dir = QPushButton("폴더 선택")
        btn_browse_dir.clicked.connect(self._browse_directory)

        btn_browse_file = QPushButton("파일 선택")
        btn_browse_file.clicked.connect(self._browse_file)

        path_row_layout.addWidget(self.edit_last_path, 1)
        path_row_layout.addWidget(btn_browse_dir)
        path_row_layout.addWidget(btn_browse_file)

        self.spin_dir_depth = QSpinBox()
        self.spin_dir_depth.setRange(0, 10)
        self.spin_dir_depth.setToolTip("폴더 검색 하위 깊이 (최소 0 ~ 최대 10)")
        self.spin_dir_depth.valueChanged.connect(lambda val: self._save_value("dir_depth", val))

        path_form_layout.addRow("기본 경로:", path_row_layout)
        path_form_layout.addRow("폴더 서치 깊이 (0~10):", self.spin_dir_depth)
        main_layout.addWidget(path_group)

        # 윈도우 크기 설정 그룹
        win_group = QGroupBox("창 크기 설정 (Window Size)")
        form_layout = QFormLayout(win_group)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(400, 3840)
        self.spin_width.valueChanged.connect(lambda val: self._save_value("window_width", val))

        self.spin_height = QSpinBox()
        self.spin_height.setRange(300, 2160)
        self.spin_height.valueChanged.connect(lambda val: self._save_value("window_height", val))

        form_layout.addRow("너비 (Width, px):", self.spin_width)
        form_layout.addRow("높이 (Height, px):", self.spin_height)
        main_layout.addWidget(win_group)

        # 설정 파일 정보 표시
        info_label = QLabel(f"설정 파일: {self.config.filepath}")
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        main_layout.addWidget(info_label)

        main_layout.addStretch()

    def load_from_config(self):
        """Config 현재 값을 UI에 반영"""
        self.edit_last_path.blockSignals(True)
        self.spin_dir_depth.blockSignals(True)
        self.spin_width.blockSignals(True)
        self.spin_height.blockSignals(True)

        self.edit_last_path.setText(str(self.config.get("last_path") or ""))

        raw_depth = self.config.get("dir_depth")
        depth_val = int(raw_depth if raw_depth is not None else 3)
        depth_val = max(0, min(10, depth_val))
        self.spin_dir_depth.setValue(depth_val)

        self.spin_width.setValue(int(self.config.get("window_width") or 1350))
        self.spin_height.setValue(int(self.config.get("window_height") or 600))

        self.edit_last_path.blockSignals(False)
        self.spin_dir_depth.blockSignals(False)
        self.spin_width.blockSignals(False)
        self.spin_height.blockSignals(False)

    def _browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "기본 폴더 선택", self.edit_last_path.text())
        if dir_path:
            abs_path = os.path.abspath(dir_path)
            self.edit_last_path.setText(abs_path)
            self._save_value("last_path", abs_path)

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "기본 실행 또는 압축 파일 선택",
            self.edit_last_path.text(),
            "Executable & Zip Files (*.exe *.zip);;Executable Files (*.exe);;Zip Archives (*.zip)",
        )
        if file_path:
            abs_path = os.path.abspath(file_path)
            self.edit_last_path.setText(abs_path)
            self._save_value("last_path", abs_path)

    def _on_last_path_changed(self):
        path_val = self.edit_last_path.text().strip()
        if path_val:
            path_val = os.path.abspath(path_val)
            self.edit_last_path.setText(path_val)
        self._save_value("last_path", path_val)

    def _save_value(self, key: str, value):
        try:
            self.config.set(key, value)
            if hasattr(self.config, "save"):
                self.config.save()
            logd(f"ConfigTab updated '{key}' = {value}")
        except Exception as e:
            loge(f"ConfigTab failed to save '{key}': {e}")