from operator import index
import sys
import os
import threading
import configparser
import ctypes
import shutil
import logging
from dotenv import load_dotenv


from setting import env_settings, general_settings, operator_settings
# 사용하지 않는 경고를 숨기기 위한 더미 참조
_ = (env_settings, general_settings, operator_settings)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Common.globals import CONFIG_ENCODING
from Common.config import FileConfigManager

# 설정 Config 클래스들 임포트
from setting.general_settings import *
from setting.env_settings import *
from setting.operator_settings import *

general_config = GeneralSettingsConfig()
env_config = EnvSettingsConfig()

project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from create_admin_shortcut import set_startup_registration
from Common.paths import get_ui_file_path
#from Common.db import BaseDb
from Common.settings_dialog import SettingsDialog

# [추가] LinkShare 내부의 설정들도 레지스트리에 등록될 수 있도록 임포트
# [추가] 각 설정 모듈들을 직접 임포트
from LinkBox.setting import zone_settings, sound_settings, color_settings, print_fare_settings
# 사용하지 않는 경고를 숨기기 위한 더미 참조
_ = (zone_settings, sound_settings, color_settings, print_fare_settings)

from LinkShare.setting import hotspot_settings, storage_settings, internet_rates_settings
# 사용하지 않는 경고를 숨기기 위한 더미 참조
_ = (hotspot_settings, storage_settings, internet_rates_settings)

from LinkBox.linkbox import LinkBoxManager

from LinkShare.linkshare import LinkShareManager

#from Common.order_service import OrderService
from Common.order_ui_controller import OrderUiController
from LinkBox.print_log_writer import (
    play_notification_sound, stop_notification_sound,
)
try:
    import winsound
except ImportError:
    winsound = None

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QMessageBox, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QFile
from PySide6.QtGui import QAction
from PySide6.QtUiTools import QUiLoader

# 각 탭 모듈 임포트
#from LinkBox.linkbox import create_tab as create_linkbox_tab
#from LinkShare.linkshare import create_tab as create_linkshare_tab

current_dir = os.path.dirname(os.path.abspath(__file__))
application_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else project_dir
resource_dir = getattr(sys, '_MEIPASS', current_dir)

data_dir = os.path.join(project_root, 'data') if not getattr(sys, 'frozen', False) else os.path.join(
    os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
    'PrintShopApp',
    'data',
)
os.makedirs(data_dir, exist_ok=True)
os.chdir(project_dir if not getattr(sys, 'frozen', False) else application_dir)

# 데이터베이스 설정
# database_dir = os.path.join(data_dir, "db")
# wifi_approval_db_path = os.path.join(database_dir, "wifi_approval.db")
# os.makedirs(database_dir, exist_ok=True)
# app_database = BaseDb(wifi_approval_db_path)
#order_service = OrderService(app_database)


class PrintShopApp(QMainWindow):
    file_signal = Signal(list, str, str)
    delete_signal = Signal(str, list)
    database_loaded = Signal(object, object, object)
    qr_export_completed = Signal(str, bool, str)

    def update_window_title(self, privilege_label=None):
        privilege_label = privilege_label or (
            "Administrator privileges" if env_config.get('is_admin') else "Standard privileges"
        )
        parts = ["PrintShop Integrated Manager (HTTPS)"]
        if self.show_mode_in_title:
            parts.append("DevMode" if env_config.get('runtime_mode') == 'development' else "OpMode")
        parts.append(privilege_label)
        self.setWindowTitle(" - ".join(parts))

    def __init__(self):
        super().__init__()
        self.show_mode_in_title = env_config.get('show_mode_in_title')
        self.show_feature_in_title = env_config.get('show_feature_in_title')
        privilege_label = "Administrator privileges" if env_config.get('is_admin') else "Standard privileges"
        self.update_window_title(privilege_label)

        # 설정 액션 추가
        self.settings_action = QAction('Open Settings', self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        self.menuBar().addAction(self.settings_action)

        # print_shop_app.ui 파일 로드 (ui 폴더 또는 현재 디렉토리 탐색)
        loader = QUiLoader()

        ui_path = get_ui_file_path(__file__, "ui", "print_shop_app.ui")

        loaded_widget = None
        file = QFile(ui_path)        
        if file.open(QFile.ReadOnly):
            loaded_widget = loader.load(file, self)
            file.close()

        # UI 파일 로드가 성공했는지 확인하고 중앙 위젯 설정
        if loaded_widget:
            if isinstance(loaded_widget, QMainWindow):
                # 만약 UI 최상위가 QMainWindow라면 내부 중앙 위젯 등을 가져와야 할 수 있음
                self.setCentralWidget(loaded_widget.centralWidget())
            else:
                self.setCentralWidget(loaded_widget)
        else:
            # UI 파일 로드 실패 시 폴백(Fallback) 기본 레이아웃 강제 생성
            central_widget = QWidget(self)
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            layout.setContentsMargins(10, 10, 10, 10)
            self.main_tabs = QTabWidget(central_widget)
            layout.addWidget(self.main_tabs)

        # UI 파일 내에 정의된 main_tabs 찾기
        if not hasattr(self, 'main_tabs') or self.main_tabs is None:
            self.main_tabs = self.findChild(QTabWidget, "main_tabs")
            if self.main_tabs is None:
                central_widget = QWidget()
                self.setCentralWidget(central_widget)
                layout = QVBoxLayout(central_widget)
                layout.setContentsMargins(10, 10, 10, 10)
                self.main_tabs = QTabWidget()
                layout.addWidget(self.main_tabs)

        # # 업로드 폴더 경로 설정
        # current_upload_folder = os.path.join(data_dir, "LinkBox_Files")
        # os.makedirs(current_upload_folder, exist_ok=True)

        # LinkBox 및 LinkShare 탭 등록

        self.linkbox_manager = LinkBoxManager(self)

        self.linkshare_manager = LinkShareManager(self)        
        
#        create_linkshare_tab(self)

        # # [추가] 탭이 정상적으로 표시되도록 초기 인덱스를 0으로 강제 설정 및 갱신
        # if hasattr(self, 'main_tabs') and self.main_tabs.count() > 0:
        #     self.main_tabs.setCurrentIndex(0)        

        # [수정] 저장된 active_main_tab 값을 불러와 초기 탭으로 설정
        if hasattr(self, 'main_tabs') and self.main_tabs.count() > 0:
            saved_tab_index = general_config.get('active_main_tab')
            if 0 <= saved_tab_index < self.main_tabs.count():
                self.main_tabs.setCurrentIndex(saved_tab_index)
            else:
                self.main_tabs.setCurrentIndex(0)            

        # 4. 초기 탭 세팅이 모두 끝난 후에 시그널을 연결 (시작할 때 불필요한 0번->1번 변경 이벤트 방지 및 안정적인 연결)
        self.main_tabs.currentChanged.connect(self.on_main_tab_changed)                

        self.resize(1150, 750)

    # ----------------------------------------------------------------------
    # Event Handlers & Helper Methods
    # ----------------------------------------------------------------------
    def open_settings_dialog(self):
        """메뉴에서 세팅 선택 시 세팅 클래스의 모달리스 다이얼로그 호출"""
        logd("[Settings] Open modeless settings dialog requested...")
        # 싱글톤으로 관리되며 hide 상태였다면 다시 화면에 나타나고 상태가 유지됨
        SettingsDialog.show_dialog(self)

    def on_main_tab_changed(self, index):
        logd(f"[UI] Main tab changed to index: {index}")
        if index >= 0:
            general_config.set('active_main_tab', index)

    def set_hotspot_state(self, enable: bool):
        logd(f"[Hotspot] State change requested: {enable}")

    def diagnose_hotspot(self):
        logd("[Hotspot] Running diagnostics...")

    def show_network_qr_print_dialog(self):
        logd("[QR] Print Network QR dialog")

    def show_captive_qr_print_dialog(self):
        logd("[QR] Print Captive Portal QR dialog")

    def handle_linkshare_splitter_moved(self, pos, index):
        if hasattr(self, 'linkshare_splitter_save_timer'):
            self.linkshare_splitter_save_timer.start()

    def persist_settings(self):
        logd("[Settings] Persisting settings...")

    def adjust_linkshare_spacing(self):
        pass

    def bring_to_front(self):
        was_maximized = bool(self.windowState() & Qt.WindowMaximized)
        if was_maximized:
            self.setWindowState(
                (self.windowState() & ~Qt.WindowMinimized) | Qt.WindowMaximized | Qt.WindowActive
            )
        else:
            self.showNormal()
            self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 3 if was_maximized else 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

    def closeEvent(self, event):
        logd("Application closing...")
        # [추가] 앱이 종료될 때 메모리에 남아있는 세팅 다이얼로그가 있다면 완전히 닫고 해제
        if hasattr(SettingsDialog, '_instance') and SettingsDialog._instance is not None:
            SettingsDialog._instance.setAttribute(Qt.WA_DeleteOnClose, True)
            SettingsDialog._instance.close()
            SettingsDialog._instance = None
        event.accept()        


def initialize_all_configurations():
    _config_load_count = 0  # 로드 카운터 초기화            
    for config_cls in FileConfigManager._registry:
        filepath = os.path.join(config_cls.file_dir, config_cls.file_name)
        is_file_exists = os.path.exists(filepath)
        
        instance = config_cls()

        _config_load_count += 1

        if is_file_exists:
            logd(f"{_config_load_count:02d} : [Config Loaded] 파일에서 로드됨 - Section: '{instance.section}' -> File: {filepath}")
        else:
            logd(f"{_config_load_count:02d} : [Config Initialized] 파일이 없어 기본값으로 생성됨 - Section: '{instance.section}' -> File: {filepath}")

