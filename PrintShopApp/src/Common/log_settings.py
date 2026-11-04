import os
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QCheckBox, QGroupBox, QLabel, 
    QHBoxLayout, QComboBox, QSpinBox, QPlainTextEdit
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from PySide6.QtCore import Qt

from Common.log_config import LogConfig
from Common.settings_registry import register_settings_tab

class LogSettingsTab(QWidget):
    """PySide6 설정 탭 UI"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = LogConfig()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>Log Display & Alignment Settings</h3>"))

        # 1. 로그 포맷 표시 요소 설정 그룹 (LogFormat Elements)
        format_group = QGroupBox("Log Format Elements (포맷 표시 요소)")
        format_layout = QVBoxLayout()

        self.cb_show_time = QCheckBox("Show Time (시간 표시)")
        self.cb_show_time.setChecked(self.config.get('show_time'))
        self.cb_show_time.stateChanged.connect(lambda: self.on_setting_changed('show_time', self.cb_show_time.isChecked()))
        format_layout.addWidget(self.cb_show_time)

        self.cb_show_level = QCheckBox("Show Level (로그 레벨 표시)")
        self.cb_show_level.setChecked(self.config.get('show_level'))
        self.cb_show_level.stateChanged.connect(lambda: self.on_setting_changed('show_level', self.cb_show_level.isChecked()))
        format_layout.addWidget(self.cb_show_level)

        self.cb_show_dir = QCheckBox("Show Directory (디렉토리 경로 표시)")
        self.cb_show_dir.setChecked(self.config.get('show_dir'))
        self.cb_show_dir.stateChanged.connect(lambda: self.on_setting_changed('show_dir', self.cb_show_dir.isChecked()))
        format_layout.addWidget(self.cb_show_dir)

        self.cb_show_file = QCheckBox("Show File Name (파일명 표시)")
        self.cb_show_file.setChecked(self.config.get('show_file'))
        self.cb_show_file.stateChanged.connect(lambda: self.on_setting_changed('show_file', self.cb_show_file.isChecked()))
        format_layout.addWidget(self.cb_show_file)

        self.cb_show_line = QCheckBox("Show Line Number (라인 번호 표시)")
        self.cb_show_line.setChecked(self.config.get('show_line'))
        self.cb_show_line.stateChanged.connect(lambda: self.on_setting_changed('show_line', self.cb_show_line.isChecked()))
        format_layout.addWidget(self.cb_show_line)

        self.cb_show_tag = QCheckBox("Show Tag (태그 표시)")
        self.cb_show_tag.setChecked(self.config.get('show_tag'))
        self.cb_show_tag.stateChanged.connect(lambda: self.on_setting_changed('show_tag', self.cb_show_tag.isChecked()))
        format_layout.addWidget(self.cb_show_tag)

        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # 2. 출력 동작 설정 그룹
        behavior_group = QGroupBox("Log Output Options (출력 대상 설정)")
        behavior_layout = QVBoxLayout()

        self.cb_color_file = QCheckBox("Enable Color File Output (개별 컬러 파일 출력)")
        self.cb_color_file.setChecked(self.config.get('enable_color_file'))
        self.cb_color_file.stateChanged.connect(lambda: self.on_setting_changed('enable_color_file', self.cb_color_file.isChecked()))
        behavior_layout.addWidget(self.cb_color_file)

        self.cb_global_log = QCheckBox("Enable Global Log Output (전체 통합 로그 log_all 출력)")
        self.cb_global_log.setChecked(self.config.get('enable_global_log'))
        self.cb_global_log.stateChanged.connect(lambda: self.on_setting_changed('enable_global_log', self.cb_global_log.isChecked()))
        behavior_layout.addWidget(self.cb_global_log)

        self.cb_global_color_file = QCheckBox("Enable Global Color File Output (전체 통합 컬러 파일 출력)")
        self.cb_global_color_file.setChecked(self.config.get('enable_global_color_file'))
        self.cb_global_color_file.stateChanged.connect(lambda: self.on_setting_changed('enable_global_color_file', self.cb_global_color_file.isChecked()))
        behavior_layout.addWidget(self.cb_global_color_file)

        behavior_group.setLayout(behavior_layout)
        layout.addWidget(behavior_group)

        # 3. 경로 정렬 및 표출 방식 그룹
        align_group = QGroupBox("Path Alignment & Style Options (경로 정렬 및 표출 방식)")
        align_layout = QVBoxLayout()

        path_style_layout = QHBoxLayout()
        path_style_layout.addWidget(QLabel("Path Style (경로 표시 방식):"))
        self.combo_path_style = QComboBox()
        self.combo_path_style.addItem("Relative Path (상대 경로)", "relative")
        self.combo_path_style.addItem("Absolute Path (절대 경로)", "absolute")
        self.combo_path_style.addItem("Fixed-Width Truncated (고정폭 엘리시스)", "fixed")
        
        current_style = self.config.get('path_style')
        index = self.combo_path_style.findData(current_style)
        if index >= 0:
            self.combo_path_style.setCurrentIndex(index)
        self.combo_path_style.currentIndexChanged.connect(lambda: self.on_setting_changed('path_style', self.combo_path_style.currentData()))
        path_style_layout.addWidget(self.combo_path_style)
        align_layout.addLayout(path_style_layout)

        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Fixed Width Size (고정폭 정렬 글자수):"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(20, 100)
        self.spin_width.setValue(self.config.get('fixed_width_size'))
        self.spin_width.valueChanged.connect(lambda: self.on_setting_changed('fixed_width_size', self.spin_width.value()))
        width_layout.addWidget(self.spin_width)
        align_layout.addLayout(width_layout)

        self.cb_tabular = QCheckBox("Enable Tabular Vertical Alignment (구분자 일직선 정렬)")
        self.cb_tabular.setChecked(self.config.get('enable_tabular_alignment'))
        self.cb_tabular.stateChanged.connect(lambda: self.on_setting_changed('enable_tabular_alignment', self.cb_tabular.isChecked()))
        align_layout.addWidget(self.cb_tabular)

        align_group.setLayout(align_layout)
        layout.addWidget(align_group)

        # 4. 로그 출력 미리보기 그룹 (Sample Preview - QPlainTextEdit 사용)
        preview_group = QGroupBox("Log Output Preview (미리보기)")
        preview_layout = QVBoxLayout()
        
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFixedHeight(140)
        self.preview_edit.setStyleSheet(
            "background-color: #1e1e1e; "
            "color: #d4d4d4; "
            "font-family: Consolas, 'Courier New', monospace; "
            "font-size: 11pt;"
        )
        preview_layout.addWidget(self.preview_edit)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # 초기 미리보기 갱신
        self.update_preview()
        layout.addStretch()

    def on_setting_changed(self, key, value):
        """설정값이 변경될 때 Config에 저장하고 프리뷰를 갱신합니다."""
        if hasattr(self.config, 'set'):
            self.config.set(key, value)
        else:
            # set 메서드가 없을 경우 직접 속성/딕셔너리처럼 대입 시도
            try:
                setattr(self.config, key, value)
            except Exception:
                pass
        self.update_preview()

    def update_preview(self):
        """설정 변경 즉시 5가지 로그 레벨 샘플을 컬러와 함께 갱신"""
        show_time = self.cb_show_time.isChecked()
        show_level = self.cb_show_level.isChecked()
        show_dir = self.cb_show_dir.isChecked()
        show_file = self.cb_show_file.isChecked()
        show_line = self.cb_show_line.isChecked()
        show_tag = self.cb_show_tag.isChecked()
        
        path_style = self.combo_path_style.currentData() or "relative"
        width = self.spin_width.value()
        is_tabular = self.cb_tabular.isChecked()

        # 경로 조각 구성 (디렉토리, 파일명, 라인번호 분리)
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
                if len(combined_path) > width:
                    formatted_path = "..." + combined_path[-(width-3):]
                else:
                    formatted_path = combined_path.ljust(width)
            else:
                formatted_path = combined_path
        else:
            formatted_path = ""

        level_colors = {
            "DEBUG": QColor("#569CD6"),
            "INFO": QColor("#4EC9B0"),
            "WARNING": QColor("#CE9178"),
            "ERROR": QColor("#F44747"),
            "CRITICAL": QColor("#FF00FF")
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
            ("CRITICAL", "Critical system error encountered.")
        ]

        self.preview_edit.clear()
        cursor = self.preview_edit.textCursor()

        for i, (level, message) in enumerate(log_samples):
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
                if is_tabular:
                    cursor.insertText(" | ", delimiter_format)
                else:
                    cursor.insertText(" ", default_format)

            if formatted_path:
                cursor.insertText(formatted_path, path_format)
                if is_tabular:
                    cursor.insertText(" | ", delimiter_format)
                else:
                    cursor.insertText(" ", default_format)

            if show_tag:
                cursor.insertText("[Settings]", tag_format)
                if is_tabular:
                    cursor.insertText(" | ", delimiter_format)
                else:
                    cursor.insertText(" ", default_format)

            cursor.insertText(message, default_format)

            if i < len(log_samples) - 1:
                cursor.insertBlock()

# 탭 등록
register_settings_tab('log-settings', 'Log Settings', LogSettingsTab, order=16)