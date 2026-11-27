from operator import index
import sys
import os
import threading
import configparser
import ctypes
import shutil
import logging
from dotenv import load_dotenv

from Common.log import logd, loge
from Common.log import set_file_tag

set_file_tag("MAIN")

from PrintShopApp.print_shop_log_setting_tab import PrintShopLogSettingsTab

from setting import env_settings, general_settings, operator_settings

# 사용하지 않는 경고를 숨기기 위한 더미 참조
_ = (env_settings, general_settings, operator_settings)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Common.globals import CONFIG_ENCODING
from Common.config import FileConfigManager
from Common.log import LogManagerRegistry

# 설정 Config 클래스들 임포트
from setting.general_settings import *
from setting.env_settings import *
from setting.operator_settings import *

general_config = GeneralConfig()
env_config = EnvConfig()

project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from create_admin_shortcut import set_startup_registration
from PrintShopApp.settings_dialog import SettingsDialog
from Common.geometry_manager import GeometryManager

# [추가] LinkShare 내부의 설정들도 레지스트리에 등록될 수 있도록 임포트
# [추가] 각 설정 모듈들을 직접 임포트

from LinkBox.linkbox import LinkBoxManager
from LinkShare.linkshare import LinkShareManager

# from Common.order_service import OrderService
from Common.order_ui_controller import OrderUiController
from LinkBox.print_log_writer import (
    play_notification_sound,
    stop_notification_sound,
)

try:
    import winsound
except ImportError:
    winsound = None

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QMessageBox,
    QWidget,
    QVBoxLayout,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QFile
from PySide6.QtGui import QAction
from PySide6.QtUiTools import QUiLoader

from ui.print_shop_app_ui import Ui_PrintShopApp

# 각 탭 모듈 임포트
# from LinkBox.linkbox import create_tab as create_linkbox_tab
# from LinkShare.linkshare import create_tab as create_linkshare_tab

current_dir = os.path.dirname(os.path.abspath(__file__))
application_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else project_dir
resource_dir = getattr(sys, "_MEIPASS", current_dir)

data_dir = (
    os.path.join(project_root, "data")
    if not getattr(sys, "frozen", False)
    else os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "PrintShopApp",
        "data",
    )
)
os.makedirs(data_dir, exist_ok=True)
os.chdir(project_dir if not getattr(sys, "frozen", False) else application_dir)


class PrintShopAppGeometryConfig(GeometryManager):
    schema: Dict[str, Dict[str, Any]] = {
        "window_geometry": {"type": ConfigType.LIST, "default": [200, 200, 800, 600]}
    }


class PrintShopApp(QMainWindow):
    file_signal = Signal(list, str, str)
    delete_signal = Signal(str, list)
    database_loaded = Signal(object, object, object)
    qr_export_completed = Signal(str, bool, str)

    def update_window_title(self, privilege_label=None):
        privilege_label = privilege_label or (
            "Administrator privileges" if env_config.get("is_admin") else "Standard privileges"
        )
        parts = ["PrintShop Integrated Manager (HTTPS)"]
        if self.show_mode_in_title:
            parts.append("DevMode" if env_config.get("runtime_mode") == "development" else "OpMode")
        parts.append(privilege_label)
        self.setWindowTitle(" - ".join(parts))

    def __init__(self):
        super().__init__()

        self.show_mode_in_title = env_config.get("show_mode_in_title")
        self.show_feature_in_title = env_config.get("show_feature_in_title")
        privilege_label = (
            "Administrator privileges" if env_config.get("is_admin") else "Standard privileges"
        )
        self.update_window_title(privilege_label)

        # [수정] 1. 변환된 파이썬 UI 모듈(Ui_PrintShopApp)을 메인 윈도우(self)에 먼저 적용
        ui_instance = None
        try:
            ui_instance = Ui_PrintShopApp()
            ui_instance.setupUi(self)
            logd("UI_LOAD (Python Module 성공) : Ui_PrintShopApp setupUi 완료")
        except Exception as e:
            loge(f"[오류] UI setupUi 실행 중 예외 발생: {e}")
            # 폴백: UI 로드 실패 시 기본 탭 위젯 생성
            central_widget = QWidget(self)
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            layout.setContentsMargins(10, 10, 10, 10)
            self.main_tabs = QTabWidget(central_widget)
            layout.addWidget(self.main_tabs)

        # UI 파일에 정의된 actionSetting 버튼 클릭 시 설정 다이얼로그 연결
        if hasattr(self, "actionSetting"):
            self.actionSetting.triggered.connect(self.open_settings_dialog)
        elif hasattr(ui_instance, "actionSetting"):
            ui_instance.actionSetting.triggered.connect(self.open_settings_dialog)

        # # [수정] UI 파일이 만든 드롭다운 메뉴(menusetting)를 제거하고, 바로 클릭되는 단독 버튼 추가
        # menubar = self.menuBar()
        # if menubar is not None:
        #     # 1. UI에 의해 자동 생성된 기존 드롭다운 메뉴가 있다면 메뉴바에서 완전 제거
        #     if hasattr(self, 'menusetting') and self.menusetting is not None:
        #         menubar.removeAction(self.menusetting.menuAction())
        #         self.menusetting.deleteLater()
        #         self.menusetting = None

        #     # 2. 메뉴바에 화살표 없는 직접 실행 버튼(QAction) 생성 및 추가
        #     self.settings_action = QAction('setting', self)
        #     self.settings_action.triggered.connect(self.open_settings_dialog)
        #     menubar.addAction(self.settings_action)

        # 3. UI 파일 내에 정의된 main_tabs 찾기 (setupUi가 성공했으면 이미 존재함)
        if not hasattr(self, "main_tabs") or self.main_tabs is None:
            self.main_tabs = self.findChild(QTabWidget, "main_tabs")
            if self.main_tabs is None:
                central_widget = QWidget(self)
                self.setCentralWidget(central_widget)
                layout = QVBoxLayout(central_widget)
                layout.setContentsMargins(10, 10, 10, 10)
                self.main_tabs = QTabWidget(central_widget)
                layout.addWidget(self.main_tabs)

        # LinkBox 및 LinkShare 탭 등록
        self.linkbox_manager = LinkBoxManager(self)
        self.main_tabs.addTab(self.linkbox_manager, self.linkbox_manager.title)

        self.linkshare_manager = LinkShareManager(self)
        self.main_tabs.addTab(self.linkshare_manager, self.linkshare_manager.title)

        # 저장된 active_main_tab 값을 불러와 초기 탭으로 설정
        if hasattr(self, "main_tabs") and self.main_tabs.count() > 0:
            saved_tab_index = general_config.get("active_main_tab")
            if 0 <= saved_tab_index < self.main_tabs.count():
                self.main_tabs.setCurrentIndex(saved_tab_index)
            else:
                self.main_tabs.setCurrentIndex(0)

        # 초기 탭 세팅이 모두 끝난 후에 시그널을 연결
        self.main_tabs.currentChanged.connect(self.on_main_tab_changed)

        # 윈도우 크기 및 설정 로드
        self.geo_config = PrintShopAppGeometryConfig()
        self.geo_config.load_window_geometry(self)

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
            general_config.set("active_main_tab", index)

    def set_hotspot_state(self, enable: bool):
        logd(f"[Hotspot] State change requested: {enable}")

    def diagnose_hotspot(self):
        logd("[Hotspot] Running diagnostics...")

    def show_network_qr_print_dialog(self):
        logd("[QR] Print Network QR dialog")

    def show_captive_qr_print_dialog(self):
        logd("[QR] Print Captive Portal QR dialog")

    def handle_linkshare_splitter_moved(self, pos, index):
        if hasattr(self, "linkshare_splitter_save_timer"):
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

        # 5. 윈도우 종료 시점 자동 저장
        self.geo_config.save_window_geometry(self)
        # self.geo_config.save_splitters_by_name(self)

        # [추가] 앱이 종료될 때 메모리에 남아있는 세팅 다이얼로그가 있다면 완전히 닫고 해제
        if hasattr(SettingsDialog, "_instance") and SettingsDialog._instance is not None:
            SettingsDialog._instance.setAttribute(Qt.WA_DeleteOnClose, True)
            SettingsDialog._instance.close()
            SettingsDialog._instance = None

        """메인 매니저 창이 닫힐 때 싱글톤 승인 다이얼로그도 함께 닫기"""
        try:
            from LinkShare.ui.internet_share_approval_dialog import InternetShareApprovalDialog

            # 싱글톤 인스턴스가 존재하면 닫기 및 삭제 수행
            if InternetShareApprovalDialog in InternetShareApprovalDialog._instances:
                dialog = InternetShareApprovalDialog._instances[InternetShareApprovalDialog]
                if dialog:
                    dialog.close()
                    dialog.deleteLater()
                InternetShareApprovalDialog._instances[InternetShareApprovalDialog] = None
        except Exception as e:
            loge(f"[LinkShare] 승인 다이얼로그 종료 중 오류 발생: {e}")

        LogManagerRegistry.close_all_logs()
        event.accept()


def initialize_all_configurations():
    _config_load_count = 0  # 로드 카운터 초기화
    for config_cls in FileConfigManager._registry:
        filepath = config_cls._resolve_cls_filepath()
        is_file_exists = os.path.exists(filepath)

        instance = config_cls()
        resolved_filepath = instance.filepath

        _config_load_count += 1

        if is_file_exists:
            logd(
                f"{_config_load_count:02d} : [Config Loaded] 파일에서 로드됨 - Section: '{instance.section}' -> File: {resolved_filepath}"
            )
        else:
            logd(
                f"{_config_load_count:02d} : [Config Initialized] 파일이 없어 기본값으로 생성됨 - Section: '{instance.section}' -> File: {resolved_filepath}"
            )
