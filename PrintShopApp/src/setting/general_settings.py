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
# 현재 파일 기준으로 프로젝트 루트 경로(C:\1print_shop\PrintShopApp) 찾기
# (폴더 구조에 맞춰 parents 인덱스는 조정이 필요할 수 있습니다)
grandparent_dir = Path(__file__).resolve().parents[2]

# 문자열로 변환하여 sys.path에 추가
grandparent_path_str = str(grandparent_dir)
if grandparent_path_str not in sys.path:
    sys.path.append(grandparent_path_str)


from Common import globals as app_globals  # 전역 변수 모듈 임포트
from Common.config import FileConfigManager, ConfigType
from Common.settings_dialog import register_settings_tab
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox

class GeneralSettingsConfig(FileConfigManager):
    section = "GeneralSettings"
    section_order = 10
    schema = {

        'login_user_name': {"default": "", "type": ConfigType.STRING},        
        'login_user_password': {"default": "", "type": ConfigType.STRING},                
        'auto_login': {"default": False, "type": ConfigType.BOOLEAN},                

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
        # 초기화 시점에 파일에서 읽어온 값을 전역 변수에 동기화
        self._sync_to_globals()

    _original_set = FileConfigManager.set

    def set(self, key: str, value: Any):
        """설정값이 변경될 때 전역 변수도 함께 업데이트"""
        super().set(key, value)
        if key in ['login_user_name']:
            self._sync_to_globals()

    def _sync_to_globals(self):
        """현재 설정 파일의 값을 전역 변수(app_globals)에 반영"""
        try:
            app_globals.GLOBAL_LOGIN_USER_NAME = self.get('login_user_name')
        except Exception as e:
            print(f"[Global Sync Error] {e}")    

# 필요한 경우 설정 화면 탭 컴포넌트도 함께 구성할 수 있습니다.
class GeneralAppSettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = GeneralSettingsConfig()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>General Application Settings</h3>"))
        
        self.mode_title_cb = QCheckBox("Show mode in window title")
        #self.mode_title_cb.setChecked(self.config.get('show_mode_in_title'))
        layout.addWidget(self.mode_title_cb)
        
        layout.addStretch()

    def save_to_config(self):
        self.config.set('show_mode_in_title', self.mode_title_cb.isChecked())

register_settings_tab('general-app-settings', 'General', GeneralAppSettingsTab, order=10)