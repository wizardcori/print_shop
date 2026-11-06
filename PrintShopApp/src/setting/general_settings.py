"""General App Settings and Configuration."""
import sys
import os
from typing import Optional, List, Dict, Any

# 현재 파일 기준으로 src 또는 프로젝트 루트 경로를 sys.path에 강제로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir) # 필요에 따라 상위 폴더 조정
if src_dir not in sys.path:
    sys.path.append(src_dir)


from pathlib import Path
grandparent_dir = Path(__file__).resolve().parents[2]

grandparent_path_str = str(grandparent_dir)
if grandparent_path_str not in sys.path:
    sys.path.append(grandparent_path_str)


from Common import globals as app_globals  # 전역 변수 모듈 임포트
from Common.config import FileConfigManager, ConfigType
from Common.geometry_manager import AutoGeometryWidget
from Common.settings_registry import register_settings_tab
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox, QLineEdit, QPushButton, QFileDialog

class GeneralSettingsConfig(FileConfigManager):
    section = "GeneralSettings"
    section_order = 10
    schema = {
        'login_user_name': {"default": "", "type": ConfigType.STRING},        
        'login_user_password': {"default": "", "type": ConfigType.STRING},                
        'auto_login': {"default": False, "type": ConfigType.BOOLEAN},                

        # 핫스팟/윈도우 시작 시 자동 등록 설정 이동
        'startup_enabled': {"default": False, "type": ConfigType.BOOLEAN},

        'log_print_enabled': {"default": True, "type": ConfigType.BOOLEAN},
        'print_detect_enabled': {"default": True, "type": ConfigType.BOOLEAN},
        'transfer_show_completed': {"default": False, "type": ConfigType.BOOLEAN},
        'transfer_period': {"default": "today", "type": ConfigType.STRING},
        'transfer_start_date': {"default": "", "type": ConfigType.STRING},
        'transfer_end_date': {"default": "", "type": ConfigType.STRING},
        'status_poll_interval': {"default": 3, "type": ConfigType.INTEGER},
        'expiration_check_interval': {"default": 10, "type": ConfigType.INTEGER},
        'active_main_tab': {"default": 0, "type": ConfigType.INTEGER},
        'settings_active_tab': {"default": 0, "type": ConfigType.INTEGER},
    }

    def __init__(self):
        super().__init__()
        self._sync_to_globals()

    _original_set = FileConfigManager.set

    def set(self, key: str, value: Any):
        super().set(key, value)
        if key in ['login_user_name']:
            self._sync_to_globals()

    def _sync_to_globals(self):
        try:
            app_globals.GLOBAL_LOGIN_USER_NAME = self.get('login_user_name')
        except Exception as e:
            pass


class GeneralAppSettingsTab(AutoGeometryWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = GeneralSettingsConfig()
        self.widgets = {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        
        layout.addWidget(QLabel("<h3>General Application Settings</h3>"))
        
        for key, meta in self.config.schema.items():
            default_val = meta.get("default")
            config_type = meta.get("type")
            current_val = self.config.get(key)
            
            row_layout = QHBoxLayout()
            
            # 특정 키에 대해 명시적 라벨 지정
            if key == 'startup_enabled':
                label_text = "Register automatically at Windows startup"
            else:
                label_text = key.replace('_', ' ').title()
                
            label = QLabel(label_text)
            row_layout.addWidget(label)
            
            if config_type == ConfigType.BOOLEAN:
                widget = QCheckBox()
                widget.setChecked(bool(current_val if current_val is not None else default_val))
                row_layout.addWidget(widget)
                
            elif config_type == ConfigType.INTEGER:
                widget = QSpinBox()
                widget.setRange(-999999, 999999)
                widget.setValue(int(current_val if current_val is not None else default_val))
                row_layout.addWidget(widget)
                
            else:
                widget = QLineEdit()
                widget.setText(str(current_val if current_val is not None else default_val))
                row_layout.addWidget(widget)
                
            self.widgets[key] = widget
            layout.addLayout(row_layout)
            
        layout.addStretch()
        main_layout.addWidget(scroll_content)

    def save_to_config(self):
        for key, widget in self.widgets.items():
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QLineEdit):
                value = widget.text()
            else:
                continue
                
            self.config.set(key, value)

register_settings_tab('general-app-settings', 'General', GeneralAppSettingsTab, order=10)