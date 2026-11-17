import os
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QCheckBox, QGroupBox, QLabel, 
    QHBoxLayout, QComboBox, QSpinBox, QPlainTextEdit, QGridLayout
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from PySide6.QtCore import Qt

from Common.log import FileTagManager
from Common.log_config import LogConfig
from Common.log_config import log_config_instance
from Common.settings_registry import register_settings_tab
from Common.logger_service import update_all_feature_loggers_format

class LogSettingsTab(QWidget):
    """PySide6 설정 탭 UI"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = log_config_instance
        
        self.level_checkboxes = {}
        self.module_checkboxes = {}
        self._block_signals = False
        self._last_module_cols = 0  # 모듈 그리드 열 개수 캐싱용
        
        self.init_ui()

    def init_ui(self):
        # 1. 메인 레이아웃 생성 및 위젯에 적용
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("<h3>Log Display & Alignment Settings</h3>"))

        # 2. 로그 포맷 표시 요소 설정 그룹 (그림 1: 한 줄에 3개씩 배치)
        format_group = QGroupBox("Log Format Elements (포맷 표시 요소)")
        format_layout = QGridLayout()

        self.cb_show_time = QCheckBox("Show Time (시간 표시)")
        self.cb_show_time.setChecked(bool(self.config.get('show_time')))
        self.cb_show_time.stateChanged.connect(lambda: self.on_setting_changed('show_time', self.cb_show_time.isChecked()))

        self.cb_show_level = QCheckBox("Show Level (로그 레벨 표시)")
        self.cb_show_level.setChecked(bool(self.config.get('show_level')))
        self.cb_show_level.stateChanged.connect(lambda: self.on_setting_changed('show_level', self.cb_show_level.isChecked()))

        self.cb_show_dir = QCheckBox("Show Directory (디렉토리 경로 표시)")
        self.cb_show_dir.setChecked(bool(self.config.get('show_dir')))
        self.cb_show_dir.stateChanged.connect(lambda: self.on_setting_changed('show_dir', self.cb_show_dir.isChecked()))

        self.cb_show_file = QCheckBox("Show File Name (파일명 표시)")
        self.cb_show_file.setChecked(bool(self.config.get('show_file')))
        self.cb_show_file.stateChanged.connect(lambda: self.on_setting_changed('show_file', self.cb_show_file.isChecked()))

        self.cb_show_line = QCheckBox("Show Line Number (라인 번호 표시)")
        self.cb_show_line.setChecked(bool(self.config.get('show_line')))
        self.cb_show_line.stateChanged.connect(lambda: self.on_setting_changed('show_line', self.cb_show_line.isChecked()))

        self.cb_show_tag = QCheckBox("Show Tag (태그 표시)")
        self.cb_show_tag.setChecked(bool(self.config.get('show_tag')))
        self.cb_show_tag.stateChanged.connect(lambda: self.on_setting_changed('show_tag', self.cb_show_tag.isChecked()))

        format_checkboxes = [
            self.cb_show_time, self.cb_show_level, self.cb_show_dir,
            self.cb_show_file, self.cb_show_line, self.cb_show_tag
        ]
        for idx, cb in enumerate(format_checkboxes):
            format_layout.addWidget(cb, idx // 3, idx % 3)

        format_group.setLayout(format_layout)
        main_layout.addWidget(format_group)

        # 3. 레벨별 로그 출력 제어 그룹
        level_group = QGroupBox("Log Level Filter (레벨별 로그 출력 선택)")
        level_layout = QVBoxLayout()

        self.cb_all_levels = QCheckBox("All Check (전체 선택/해제)")
        self.cb_all_levels.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.cb_all_levels.stateChanged.connect(self.toggle_all_levels)
        level_layout.addWidget(self.cb_all_levels)

        level_grid = QGridLayout()
        
        saved_level_cfg = LogConfig.str_to_dict(self.config.get('level_enabled'))
        if not isinstance(saved_level_cfg, dict) or not saved_level_cfg:
            saved_level_cfg = FileTagManager.get_level_enabled()
            self.config.set('level_enabled', saved_level_cfg)
            
        saved_module_cfg = LogConfig.str_to_dict(self.config.get('module_enabled'))
        if not isinstance(saved_module_cfg, dict) or not saved_module_cfg:
            saved_module_cfg = FileTagManager.get_module_enabled()
            self.config.set('module_enabled', saved_module_cfg)

        for idx, (lvl, is_checked) in enumerate(saved_level_cfg.items()):
            cb = QCheckBox(lvl)
            cb.setChecked(bool(is_checked))
            cb.stateChanged.connect(lambda state, c=cb, l=lvl: self.on_level_toggle(l, c.isChecked()))
            self.level_checkboxes[lvl] = cb
            level_grid.addWidget(cb, 0, idx)

        level_layout.addLayout(level_grid)
        level_group.setLayout(level_layout)
        main_layout.addWidget(level_group)

        # 4. 모듈별 로그 출력 제어 그룹 (그림 3: 전체 모듈명 길이 측정 후 최대 개수 자동 배치)
        self.module_group = QGroupBox("Module / Tag Filter (모듈별 로그 출력 선택)")
        module_layout = QVBoxLayout()

        self.cb_all_modules = QCheckBox("All Check (전체 선택/해제)")
        self.cb_all_modules.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.cb_all_modules.stateChanged.connect(self.toggle_all_modules)
        module_layout.addWidget(self.cb_all_modules)

        self.module_grid = QGridLayout()

        # 체크박스 생성 및 최대 텍스트/위젯 너비 측정
        max_cb_width = 0
        for mod, is_checked in saved_module_cfg.items():
            cb = QCheckBox(mod)
            cb.setChecked(bool(is_checked))
            cb.stateChanged.connect(lambda state, c=cb, m=mod: self.on_module_toggle(m, c.isChecked()))
            self.module_checkboxes[mod] = cb
            
            # 체크박스 아이콘 + 폰트 렌더링 기반 실제 필요 너비 계산 (여유 여백 16px 포함)
            cb_width = cb.sizeHint().width() + 16
            if cb_width > max_cb_width:
                max_cb_width = cb_width

        # 모든 모듈 체크박스에 동일한 기준 너비 적용
        self.module_item_width = max(max_cb_width, 80)
        for cb in self.module_checkboxes.values():
            cb.setMinimumWidth(self.module_item_width)

        # 초기 배치 실행
        self.relayout_modules()

        module_layout.addLayout(self.module_grid)
        self.module_group.setLayout(module_layout)
        main_layout.addWidget(self.module_group)

        # 5. 출력 동작 설정 그룹 (그림 2: 한 줄에 배치)
        behavior_group = QGroupBox("Log Output Options (출력 대상 설정)")
        behavior_layout = QHBoxLayout()

        self.cb_color_file = QCheckBox("Enable Color File Output (개별 컬러 파일 출력)")
        self.cb_color_file.setChecked(bool(self.config.get('enable_color_file')))
        self.cb_color_file.stateChanged.connect(lambda: self.on_setting_changed('enable_color_file', self.cb_color_file.isChecked()))
        behavior_layout.addWidget(self.cb_color_file)

        self.cb_global_log = QCheckBox("Enable Global Log Output (전체 통합 로그 log_all 출력)")
        self.cb_global_log.setChecked(bool(self.config.get('enable_global_log')))
        self.cb_global_log.stateChanged.connect(lambda: self.on_setting_changed('enable_global_log', self.cb_global_log.isChecked()))
        behavior_layout.addWidget(self.cb_global_log)

        self.cb_global_color_file = QCheckBox("Enable Global Color File Output (전체 통합 컬러 파일 출력)")
        self.cb_global_color_file.setChecked(bool(self.config.get('enable_global_color_file')))
        self.cb_global_color_file.stateChanged.connect(lambda: self.on_setting_changed('enable_global_color_file', self.cb_global_color_file.isChecked()))
        behavior_layout.addWidget(self.cb_global_color_file)

        behavior_group.setLayout(behavior_layout)
        main_layout.addWidget(behavior_group)

        # 6. 경로 정렬 및 표출 방식 그룹
        align_group = QGroupBox("Path Alignment & Style Options (경로 정렬 및 표출 방식)")
        align_layout = QVBoxLayout()

        path_style_layout = QHBoxLayout()
        path_style_layout.addWidget(QLabel("Path Style (경로 표시 방식):"))
        self.combo_path_style = QComboBox()
        self.combo_path_style.addItem("Relative Path (상대 경로)", "relative")
        self.combo_path_style.addItem("Absolute Path (절대 경로)", "absolute")
        self.combo_path_style.addItem("Fixed-Width Truncated (고정폭 엘리시스)", "fixed")
        
        current_style = self.config.get('path_style') or "relative"
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
        self.spin_width.setValue(int(self.config.get('fixed_width_size') or 48))
        self.spin_width.valueChanged.connect(lambda: self.on_setting_changed('fixed_width_size', self.spin_width.value()))
        width_layout.addWidget(self.spin_width)
        align_layout.addLayout(width_layout)

        self.cb_tabular = QCheckBox("Enable Tabular Vertical Alignment (구분자 일직선 정렬)")
        self.cb_tabular.setChecked(bool(self.config.get('enable_tabular_alignment')))
        self.cb_tabular.stateChanged.connect(lambda: self.on_setting_changed('enable_tabular_alignment', self.cb_tabular.isChecked()))
        align_layout.addWidget(self.cb_tabular)

        align_group.setLayout(align_layout)
        main_layout.addWidget(align_group)

        # 7. 로그 출력 미리보기 그룹
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
        main_layout.addWidget(preview_group)

        self.update_all_checks_state()
        self.update_preview()
        main_layout.addStretch()

    def relayout_modules(self):
        """현재 위젯 폭과 계산된 모듈 기준 너비를 바탕으로 한 줄에 최대한 많이 배치"""
        if not self.module_checkboxes:
            return

        # 그룹박스 좌우 패딩/마진을 제외한 실제 사용 가능 너비 계산
        available_width = self.width() - 50 if self.width() > 100 else 800
        spacing = self.module_grid.horizontalSpacing()
        if spacing < 0:
            spacing = 10

        # 한 줄에 들어갈 수 있는 최대 열(Column) 수 계산
        max_cols = max(1, (available_width + spacing) // (self.module_item_width + spacing))

        # 열 개수가 이전과 동일하면 불필요한 재배치 생략
        if max_cols == self._last_module_cols:
            return
        self._last_module_cols = max_cols

        # 기존 그리드에서 위젯 제거 (삭제하지 않고 레이아웃에서만 분리)
        while self.module_grid.count():
            item = self.module_grid.takeAt(0)
            if item.widget():
                self.module_grid.removeWidget(item.widget())

        # 계산된 최대 열 수 기준으로 재배치
        for idx, cb in enumerate(self.module_checkboxes.values()):
            row = idx // max_cols
            col = idx % max_cols
            self.module_grid.addWidget(cb, row, col)

    def showEvent(self, event):
        super().showEvent(event)
        self.relayout_modules()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout_modules()

    def toggle_all_levels(self, state):
        if self._block_signals:
            return
        is_checked = (state == Qt.Checked or state == 2 or state is True)
        self._block_signals = True
        level_cfg = {}
        for lvl, cb in self.level_checkboxes.items():
            if cb:
                cb.setChecked(is_checked)
            level_cfg[lvl] = is_checked
        self._block_signals = False
        self.on_setting_changed('level_enabled', level_cfg)

    def on_level_toggle(self, level: str, is_checked: bool):
        if self._block_signals:
            return
        lvl_cfg = self.config.get('level_enabled')
        lvl_cfg = LogConfig.str_to_dict(lvl_cfg)

        if not isinstance(lvl_cfg, dict):
            lvl_cfg = FileTagManager.get_level_enabled()

        lvl_cfg[level] = is_checked
        self.on_setting_changed('level_enabled', lvl_cfg)
        self.update_all_checks_state()

    def on_module_toggle(self, module: str, is_checked: bool):
        if self._block_signals:
            return
        mod_cfg = self.config.get('module_enabled')
        mod_cfg = LogConfig.str_to_dict(mod_cfg)

        if not isinstance(mod_cfg, dict):
            mod_cfg = FileTagManager.get_module_enabled()
        mod_cfg[module] = is_checked
        self.on_setting_changed('module_enabled', mod_cfg)
        self.update_all_checks_state()

    def toggle_all_modules(self, state):
        if self._block_signals:
            return
        is_checked = (state == Qt.Checked or state == 2 or state is True)
        self._block_signals = True
        mod_cfg = {}
        for mod, cb in self.module_checkboxes.items():
            cb.setChecked(is_checked)
            mod_cfg[mod] = is_checked
        self._block_signals = False
        self.on_setting_changed('module_enabled', mod_cfg)

    def update_all_checks_state(self):
        self._block_signals = True
        all_lvl_checked = all(cb.isChecked() for cb in self.level_checkboxes.values())
        self.cb_all_levels.setChecked(all_lvl_checked)
        all_mod_checked = all(cb.isChecked() for cb in self.module_checkboxes.values())
        self.cb_all_modules.setChecked(all_mod_checked)
        self._block_signals = False

    def on_setting_changed(self, key, value):
        if hasattr(self.config, 'set'):
            self.config.set(key, value)

        if hasattr(self.config, 'save'):
            try:
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

    def update_preview(self):
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
        if show_dir: raw_path_parts.append(dir_part)
        if show_file: raw_path_parts.append(file_part)
        if show_line: raw_path_parts.append(line_part)

        combined_path = "".join(raw_path_parts)
        if combined_path:
            if path_style == "fixed":
                formatted_path = ("..." + combined_path[-(width-3):]) if len(combined_path) > width else combined_path.ljust(width)
            else:
                formatted_path = combined_path
        else:
            formatted_path = ""

        level_colors = {
            "DEBUG": QColor("#569CD6"), "INFO": QColor("#4EC9B0"),
            "WARNING": QColor("#CE9178"), "ERROR": QColor("#F44747"), "CRITICAL": QColor("#FF00FF")
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

        level_cfg = self.config.get('level_enabled')
        if not isinstance(level_cfg, dict):
            level_cfg = {}

        self.preview_edit.clear()
        cursor = self.preview_edit.textCursor()
        filtered_samples = [(lvl, msg) for lvl, msg in log_samples if level_cfg.get(lvl, True)]

        for i, (level, message) in enumerate(filtered_samples):
            if show_time:
                cursor.insertText("2026-06-07 14:30:00", time_format)
                cursor.insertText(" ", default_format)
                if is_tabular: cursor.insertText("| ", delimiter_format)

            if show_level:
                level_fmt = QTextCharFormat()
                level_fmt.setForeground(level_colors.get(level, QColor("#D4D4D4")))
                level_fmt.setFontWeight(QFont.Bold)
                cursor.insertText(f"{level:<8}", level_fmt)
                cursor.insertText(" | " if is_tabular else " ", delimiter_format if is_tabular else default_format)

            if formatted_path:
                cursor.insertText(formatted_path, path_format)
                cursor.insertText(" | " if is_tabular else " ", delimiter_format if is_tabular else default_format)

            if show_tag:
                cursor.insertText("[Settings]", tag_format)
                cursor.insertText(" | " if is_tabular else " ", delimiter_format if is_tabular else default_format)

            cursor.insertText(message, default_format)
            if i < len(filtered_samples) - 1:
                cursor.insertBlock()

register_settings_tab('log-settings', 'Log Settings', LogSettingsTab, order=90)