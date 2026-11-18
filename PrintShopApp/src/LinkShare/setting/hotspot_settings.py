"""Hotspot and Network settings and UI component cleanly separated with .ui file."""
import os
import ipaddress
import secrets
import psutil
import socket
import hashlib
from io import BytesIO
import qrcode

from PySide6.QtWidgets import (
    QWidget, QMessageBox, QDialog, QApplication
)
from PySide6.QtGui import QColor, QPixmap, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtCore import Qt, QTimer, Signal, QFile
from PySide6.QtUiTools import QUiLoader

from Common.path_mgr import PathMgr
from Common.config import FileConfigManager, ConfigType
from Common.geometry_manager import AutoGeometryWidget
from Common.settings_registry import register_settings_tab
from Common.network_utils import normalize_hotspot_network, escape_wifi_qr_field
from LinkShare.qrcode.qr_log import QrcodeLog
from Common.folder_explorer_dialog_component import FolderExplorerDialog

from LinkShare.core.hotspot_service import (
    apply_windows_hotspot_registry_limit,
    run_hotspot_diagnostics,
    set_hotspot_enabled,
    check_hotspot_checkpoints
)
from LinkShare.core.firewall_service import apply_hotspot_firewall_rules
from LinkShare.core.network_adapter_service import (
    ping_ip_address, 
    get_nic_mac_address, 
    get_network_interfaces, 
    choose_optimal_adapters, 
    choose_preferred_interface,
    is_adapter_physical
)

DEFAULT_HOTSPOT_SSID = "hbwifi"
DEFAULT_HOTSPOT_PASSWORD = "hbwifihb"
DEFAULT_HOTSPOT_NETWORK = "192.168.137.0/24"
DEFAULT_HOTSPOT_GATEWAY = "192.168.137.1"
DEFAULT_MAX_CONNECTIONS = 250
DEFAULT_WINDOWS_HOTSPOT_LIMIT = 8
WINDOWS_HOTSPOT_LIMIT_MAX = 128


class HotspotNetworkConfig(FileConfigManager):
    section = "HotspotNetworkConfig"
    section_order = 10
    schema = {
        'ssid': {"default": DEFAULT_HOTSPOT_SSID, "type": ConfigType.STRING},
        'password': {"default": DEFAULT_HOTSPOT_PASSWORD, "type": ConfigType.STRING},
        'hotspot_password_user_set': {"default": False, "type": ConfigType.BOOLEAN},
        'provide_internet_for_file_transfer': {"default": True, "type": ConfigType.BOOLEAN},
        'max_connections': {"default": DEFAULT_MAX_CONNECTIONS, "type": ConfigType.INTEGER},
        'windows_hotspot_limit': {"default": DEFAULT_WINDOWS_HOTSPOT_LIMIT, "type": ConfigType.INTEGER},
        'internet_nic': {"default": "", "type": ConfigType.STRING},
        'internet_ip': {"default": "", "type": ConfigType.STRING},
        'hotspot_nic': {"default": "", "type": ConfigType.STRING},
        'hotspot_ip': {"default": "", "type": ConfigType.STRING},
        'hotspot_gateway': {"default": DEFAULT_HOTSPOT_GATEWAY, "type": ConfigType.STRING},
        'hotspot_network': {"default": DEFAULT_HOTSPOT_NETWORK, "type": ConfigType.STRING},
        'network_qr_output_dir': {"default": PathMgr.NETWORK_QR_OUTPUT_DIR, "type": ConfigType.STRING},
        'captive_qr_output_dir': {"default": PathMgr.CAPTIVE_QR_OUTPUT_DIR, "type": ConfigType.STRING},
        'last_qr_hash': {"default": "", "type": ConfigType.STRING},
    }

from .ui_hotspot_settings import Ui_HotspotSettingsWidget
class HotspotNetworkTab(AutoGeometryWidget):
    qr_export_completed = Signal(str, bool, str)

    def __init__(self, parent=None, interfaces=None):
        super().__init__(parent)
        self.config = HotspotNetworkConfig()
        self.interfaces = interfaces if interfaces is not None else get_network_interfaces()
        
        self._initial_checked = False
        self._auto_retry_done = False
        
        self.qr_output_dirs = {
            'network': self.config.get('network_qr_output_dir') or PathMgr.NETWORK_QR_OUTPUT_DIR,
            'captive': self.config.get('captive_qr_output_dir') or PathMgr.CAPTIVE_QR_OUTPUT_DIR
        }
        
        # 원본 QR 픽스맵 저장용 변수 초기화
        self._raw_net_pixmap = QPixmap()
        self._raw_cap_pixmap = QPixmap()
        
        self.diag_timer = QTimer(self)
        self.diag_timer.setInterval(400)
        self.diag_timer.timeout.connect(self._animate_diagnostic_status)
        self._anim_toggle = False

        # 1. UI 파일 (.ui) 분리 로드
        self.init_ui()

        # 2. 초기값 로드 및 시그널/슬롯 바인딩
        self.setup_initial_values_and_signals()

        # 3. 최초 QR 코드 업데이트
        self.update_qr_codes()
    def init_ui(self):
        # ==========================================
        # 1. 변환된 파이썬 UI 모듈(Ui_HotspotSettingsWidget)을 self에 직접 적용
        # ==========================================
        try:
            ui_instance = Ui_HotspotSettingsWidget()
            ui_instance.setupUi(self)
            logd("UI_LOAD (Python Module 성공) : Ui_HotspotSettingsWidget setupUi 완료")
        except Exception as e:
            loge(f"[오류] UI setupUi 실행 중 예외 발생: {e}")
            # 폴백: UI 로드 실패 시 기본 레이아웃 생성
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_tabs = QTabWidget(self)
            main_layout.addWidget(self.main_tabs)

        # self가 곧 UI가 생성된 위젯이므로 self.ui를 자기 자신으로 지정
        self.ui = self

        # UI 내 위젯 바인딩
        self.hotspot_status_btn = self.ui.findChild(QWidget, "hotspot_status_btn")
        self.hotspot_on_btn = self.ui.findChild(QWidget, "hotspot_on_btn")
        self.hotspot_off_btn = self.ui.findChild(QWidget, "hotspot_off_btn")
        self.hotspot_diagnose_btn = self.ui.findChild(QWidget, "hotspot_diagnose_btn")
        
        self.active_name_label = self.ui.findChild(QWidget, "active_name_label")
        self.active_nic_label = self.ui.findChild(QWidget, "active_nic_label")
        self.active_range_label = self.ui.findChild(QWidget, "active_range_label")

        self.hotspot_network_qr_label = self.ui.findChild(QWidget, "hotspot_network_qr_label")
        self.hotspot_network_info_label = self.ui.findChild(QWidget, "hotspot_network_info_label")
        self.network_print_btn = self.ui.findChild(QWidget, "network_print_btn")
        self.network_folder_btn = self.ui.findChild(QWidget, "network_folder_btn")

        self.hotspot_qr_label = self.ui.findChild(QWidget, "hotspot_qr_label")
        self.qr_caption = self.ui.findChild(QWidget, "qr_caption")
        self.captive_print_btn = self.ui.findChild(QWidget, "captive_print_btn")
        self.captive_folder_btn = self.ui.findChild(QWidget, "captive_folder_btn")

        self.ssid_input = self.ui.findChild(QWidget, "ssid_input")
        self.file_transfer_internet_checkbox = self.ui.findChild(QWidget, "file_transfer_internet_checkbox")
        self.password_input = self.ui.findChild(QWidget, "password_input")
        self.show_password_btn = self.ui.findChild(QWidget, "show_password_btn")
        self.default_password_btn = self.ui.findChild(QWidget, "default_password_btn")
        self.random_password_btn = self.ui.findChild(QWidget, "random_password_btn")

        self.max_connections_input = self.ui.findChild(QWidget, "max_connections_input")
        self.windows_hotspot_limit_input = self.ui.findChild(QWidget, "windows_hotspot_limit_input")
        self.apply_windows_limit_btn = self.ui.findChild(QWidget, "apply_windows_limit_btn")

        self.auto_detect_btn = self.ui.findChild(QWidget, "auto_detect_btn")
        self.internet_nic_combo = self.ui.findChild(QWidget, "internet_nic_combo")
        self.hotspot_nic_combo = self.ui.findChild(QWidget, "hotspot_nic_combo")
        self.hotspot_gateway_input = self.ui.findChild(QWidget, "hotspot_gateway_input")
        self.hotspot_network_input = self.ui.findChild(QWidget, "hotspot_network_input")

        self._apply_custom_styles()

    def _apply_custom_styles(self):
        """고정 크기 제한을 제거하고 최소 크기만 부여하여 실시간 반응형 확대 보장"""
        self.hotspot_status_btn.setStyleSheet(
            "QLabel { background-color: #607d8b; color: white; font-weight: bold; "
            "border: 1px solid #455a64; border-radius: 4px; padding: 5px 10px; }"
        )
        self.hotspot_on_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
            "border: 1px solid #1b5e20; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.hotspot_off_btn.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; font-weight: bold; "
            "border: 1px solid #8e0000; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #d32f2f; }"
        )
        self.hotspot_diagnose_btn.setStyleSheet(
            "QPushButton { background-color: #1565c0; color: white; font-weight: bold; "
            "border: 1px solid #0d47a1; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #1976d2; }"
        )
        
        # [핵심] setFixedSize 대신 최소 크기만 설정하여 창 크기에 따라 QR 이미지가 커지도록 허용
        self.hotspot_network_qr_label.setMinimumSize(100, 100)
        self.hotspot_network_qr_label.setStyleSheet("border: 1px solid #64b5f6; background-color: #ffffff; border-radius: 5px;")
        
        self.hotspot_qr_label.setMinimumSize(100, 100)
        self.hotspot_qr_label.setStyleSheet("border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 5px;")
        
        self.auto_detect_btn.setStyleSheet(
            "QPushButton { background-color: #0277bd; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }"
            "QPushButton:hover { background-color: #01579b; }"
        )
        self.apply_windows_limit_btn.setStyleSheet("background-color: #a15c00; color: white; font-weight: bold;")

    def setup_initial_values_and_signals(self):
        """설정값 동기화 및 버튼/입력 이벤트 시그널 연결"""
        current_ssid = self.config.get('ssid') or DEFAULT_HOTSPOT_SSID
        current_nic = self.config.get('hotspot_nic') or 'Not selected'
        current_net = self.config.get('hotspot_network') or DEFAULT_HOTSPOT_NETWORK
        current_gw = self.config.get('hotspot_gateway') or DEFAULT_HOTSPOT_GATEWAY

        self.active_name_label.setText(f"Active Hotspot Name: <b>{current_ssid}</b> (Stopped)")
        self.active_nic_label.setText(f"Hotspot NIC: <b>{current_nic}</b>")
        self.active_range_label.setText(f"Hotspot IP range: <b>{current_net}</b> / gateway: <b>{current_gw}</b>")

        self.ssid_input.setText(current_ssid)
        self.ssid_input.setMaxLength(32)

        self.file_transfer_internet_checkbox.setChecked(self.config.get('provide_internet_for_file_transfer'))

        self.password_input.setText(self.config.get('password') or DEFAULT_HOTSPOT_PASSWORD)
        self.password_input.setMaxLength(63)

        self.max_connections_input.setRange(1, 250000)
        self.max_connections_input.setValue(self.config.get('max_connections'))
        self.max_connections_input.setSuffix(" devices")

        self.windows_hotspot_limit_input.setRange(1, WINDOWS_HOTSPOT_LIMIT_MAX)
        self.windows_hotspot_limit_input.setValue(self.config.get('windows_hotspot_limit'))
        self.windows_hotspot_limit_input.setSuffix(" devices")

        self.hotspot_gateway_input.setText(current_gw)
        self.hotspot_network_input.setText(current_net)

        saved_internet_display = self.config.get('internet_nic')
        saved_internet_ip = self.config.get('internet_ip')
        saved_hotspot_display = self.config.get('hotspot_nic')
        saved_hotspot_ip = self.config.get('hotspot_ip')

        opt_internet, opt_hotspot = choose_optimal_adapters(
            self.interfaces, 
            saved_internet_display, saved_internet_ip,
            saved_hotspot_display, saved_hotspot_ip
        )

        preferred_internet = choose_preferred_interface(
            self.interfaces, 
            saved_internet_display or opt_internet[0], 
            saved_internet_ip or opt_internet[1], 
            wireless_only=False
        )
        self.populate_internet_nic_combo(preferred_internet[0])

        selected_internet_name = preferred_internet[0]
        valid_hotspot_candidates = [item for item in self.interfaces if item[0] != selected_internet_name]
        opt_hotspot_filtered, _ = choose_optimal_adapters(valid_hotspot_candidates, '', '', '', '')
        
        preferred_hotspot = choose_preferred_interface(
            self.interfaces, 
            saved_hotspot_display or opt_hotspot_filtered[0] or opt_hotspot[0], 
            saved_hotspot_ip or opt_hotspot[1], 
            wireless_only=True
        )
        self.populate_hotspot_nic_combo(preferred_hotspot[0], hotspot_gateway=current_gw)

        # 시그널 연결
        self.hotspot_on_btn.clicked.connect(lambda: self.set_hotspot_state(True))
        self.hotspot_off_btn.clicked.connect(lambda: self.set_hotspot_state(False))
        self.hotspot_diagnose_btn.clicked.connect(self.diagnose_hotspot)
        self.network_print_btn.clicked.connect(lambda: self.print_network_qr_codes(silent=False))
        self.captive_print_btn.clicked.connect(lambda: self.print_captive_qr_codes(silent=False))
        
        if self.network_folder_btn:
            self.network_folder_btn.clicked.connect(lambda: self.select_qr_folder('network'))
        if self.captive_folder_btn:
            self.captive_folder_btn.clicked.connect(lambda: self.select_qr_folder('captive'))

        self.show_password_btn.toggled.connect(self.toggle_password_visibility)
        self.default_password_btn.clicked.connect(lambda: self.password_input.setText(DEFAULT_HOTSPOT_PASSWORD))
        self.random_password_btn.clicked.connect(self.generate_random_password)
        self.apply_windows_limit_btn.clicked.connect(self.apply_windows_hotspot_limit)
        self.auto_detect_btn.clicked.connect(self.run_auto_detection)

        self.ssid_input.textChanged.connect(self.update_qr_codes)
        self.password_input.textChanged.connect(self.update_qr_codes)
        self.hotspot_gateway_input.textChanged.connect(self.update_qr_codes)
        self.hotspot_gateway_input.textChanged.connect(self.on_hotspot_gateway_changed)
        self.internet_nic_combo.currentIndexChanged.connect(self.on_internet_nic_changed)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_checked:
            self._initial_checked = True
            self.diagnose_hotspot()
            self._check_and_auto_print_qr_on_startup()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_qr_images()

    def _update_scaled_qr_images(self):
        """창 크기가 바뀔 때마다 원본 픽스맵을 현재 라벨 크기에 맞춰 비율 유지하며 실시간 스케일링"""
        if not self._raw_net_pixmap.isNull():
            size = self.hotspot_network_qr_label.size()
            min_dim = min(size.width(), size.height())
            if min_dim > 10:
                scaled = self._raw_net_pixmap.scaled(min_dim, min_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.hotspot_network_qr_label.setPixmap(scaled)

        if not self._raw_cap_pixmap.isNull():
            size = self.hotspot_qr_label.size()
            min_dim = min(size.width(), size.height())
            if min_dim > 10:
                scaled = self._raw_cap_pixmap.scaled(min_dim, min_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.hotspot_qr_label.setPixmap(scaled)

    def _check_and_auto_print_qr_on_startup(self):
        current_ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        current_pw = self.password_input.text().strip()
        current_gw = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        
        raw_data = f"{current_ssid}:{current_pw}:{current_gw}:{self.qr_output_dirs['network']}:{self.qr_output_dirs['captive']}"
        current_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
        
        saved_hash = self.config.get('last_qr_hash') or ""
        network_qr_path = os.path.join(self.qr_output_dirs['network'], 'network_connection_qr_1x.jpg')
        captive_qr_path = os.path.join(self.qr_output_dirs['captive'], 'captive_portal_qr_1x.jpg')
        
        if current_hash != saved_hash or not os.path.exists(network_qr_path) or not os.path.exists(captive_qr_path):
            print("[HotspotNetworkTab] 설정 변경 감지 또는 파일 누락: QR 코드를 자동으로 다시 생성하여 출력합니다.")
            self.print_network_qr_codes(silent=True)
            self.print_captive_qr_codes(silent=True)
            self.config.set('last_qr_hash', current_hash)
            self.config.save()

    def select_qr_folder(self, qr_type):
        current_dir = self.qr_output_dirs.get(qr_type, PathMgr.NETWORK_QR_OUTPUT_DIR)
        dialog = FolderExplorerDialog(current_dir, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_path:
            selected_dir = dialog.selected_path
            self.qr_output_dirs[qr_type] = selected_dir
            
            if qr_type == 'network':
                self.config.set('network_qr_output_dir', selected_dir)
                self.print_network_qr_codes(silent=True)
            elif qr_type == 'captive':
                self.config.set('captive_qr_output_dir', selected_dir)
                self.print_captive_qr_codes(silent=True)
                
            self._update_and_save_qr_hash()
                
            QMessageBox.information(
                self, 
                "폴더 변경 및 QR 생성 완료", 
                f"선택된 폴더:\n{selected_dir}\n\n해당 폴더에 1x~4x QR 코드가 자동 생성되었습니다."
            )

    def print_network_qr_codes(self, silent=False):
        wifi_ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        wifi_password = self.password_input.text().strip()
        displayed_pwd = wifi_password if wifi_password else '(not available)'
        guide_text = f"SSID: {wifi_ssid}\nPassword: {displayed_pwd}"
        
        wifi_type = 'WPA' if wifi_password else 'nopass'
        wifi_payload = (
            f"WIFI:T:{wifi_type};S:{escape_wifi_qr_field(wifi_ssid)};"
            f"P:{escape_wifi_qr_field(wifi_password)};H:false;;"
        )
        try:
            wifi_qr = qrcode.QRCode(version=1, box_size=10, border=4)
            wifi_qr.add_data(wifi_payload)
            wifi_qr.make(fit=True)
            wifi_img = wifi_qr.make_image(fill_color="black", back_color="white")
            
            buffer = BytesIO()
            wifi_img.save(buffer, format="PNG")
            net_qimage = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(net_qimage)
            
            for scale in [1, 2, 3, 4]:
                self.export_qr_to_directory_with_scale('network', pixmap, guide_text, scale)
                
            self._update_and_save_qr_hash()
            
            output_dir = self.qr_output_dirs.get('network', PathMgr.NETWORK_QR_OUTPUT_DIR)
            if not silent:
                QMessageBox.information(self, "Network QR Print", f"네트워크 연결 QR 코드 (1x~4x)가\n다음 경로에 저장되었습니다:\n{output_dir}")
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "Error", f"네트워크 QR 출력 실패:\n{e}")

    def print_captive_qr_codes(self, silent=False):
        gateway = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        portal_url = f"http://{gateway}:5000/scan"
        guide_text = f"Internet access request\n{portal_url}"
        
        try:
            portal_qr = qrcode.QRCode(version=1, box_size=10, border=4)
            portal_qr.add_data(portal_url)
            portal_qr.make(fit=True)
            portal_img = portal_qr.make_image(fill_color="black", back_color="white")
            
            buf2 = BytesIO()
            portal_img.save(buf2, format="PNG")
            portal_qimage = QImage.fromData(buf2.getvalue())
            pixmap = QPixmap.fromImage(portal_qimage)
            
            for scale in [1, 2, 3, 4]:
                self.export_qr_to_directory_with_scale('captive', pixmap, guide_text, scale)
                
            self._update_and_save_qr_hash()
            
            output_dir = self.qr_output_dirs.get('captive', PathMgr.CAPTIVE_QR_OUTPUT_DIR)
            if not silent:
                QMessageBox.information(self, "Captive QR Print", f"캡티브 포털 QR 코드 (1x~4x)가\n다음 경로에 저장되었습니다:\n{output_dir}")
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "Error", f"캡티브 포털 QR 출력 실패:\n{e}")

    def _update_and_save_qr_hash(self):
        current_ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        current_pw = self.password_input.text().strip()
        current_gw = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        raw_data = f"{current_ssid}:{current_pw}:{current_gw}:{self.qr_output_dirs['network']}:{self.qr_output_dirs['captive']}"
        current_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
        self.config.set('last_qr_hash', current_hash)
        self.config.save()

    def update_qr_codes(self):
        wifi_ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        wifi_password = self.password_input.text().strip()
        gateway = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY

        wifi_type = 'WPA' if wifi_password else 'nopass'
        wifi_payload = (
            f"WIFI:T:{wifi_type};S:{escape_wifi_qr_field(wifi_ssid)};"
            f"P:{escape_wifi_qr_field(wifi_password)};H:false;;"
        )
        try:
            wifi_qr = qrcode.QRCode(version=1, box_size=10, border=4)
            wifi_qr.add_data(wifi_payload)
            wifi_qr.make(fit=True)
            wifi_img = wifi_qr.make_image(fill_color="black", back_color="white")
            
            buffer = BytesIO()
            wifi_img.save(buffer, format="PNG")
            net_qimage = QImage.fromData(buffer.getvalue())
            
            # 원본 픽스맵 저장 후 실시간 스케일링 적용
            self._raw_net_pixmap = QPixmap.fromImage(net_qimage)
            self._update_scaled_qr_images()
            
            displayed_pwd = wifi_password if wifi_password else '(not available)'
            self.hotspot_network_info_label.setText(f"SSID: {wifi_ssid}   Password: {displayed_pwd}")
        except Exception as e:
            print(f"Network QR Gen Error: {e}")


        portal_url = f"http://{gateway}:5000/scan"
        try:
            portal_qr = qrcode.QRCode(version=1, box_size=10, border=4)
            portal_qr.add_data(portal_url)
            portal_qr.make(fit=True)
            portal_img = portal_qr.make_image(fill_color="black", back_color="white")
            
            buf2 = BytesIO()
            portal_img.save(buf2, format="PNG")
            portal_qimage = QImage.fromData(buf2.getvalue())
            
            # 원본 픽스맵 저장 및 실시간 스케일링 적용
            self._raw_cap_pixmap = QPixmap.fromImage(portal_qimage)
            self._update_scaled_qr_images()
            
            # [추가] 안내 문구와 링크 주소를 한 줄로 나란히 표시
            self.qr_caption.setText(f"Internet access request   |   {portal_url}")
        except Exception as e:
            print(f"Captive QR Gen Error: {e}")

    def export_qr_to_directory_with_scale(self, qr_type, pixmap, guide_text, scale):
        if pixmap.isNull():
            return
        
        output_dir = self.qr_output_dirs.get(qr_type, PathMgr.NETWORK_QR_OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)
        
        qr_size = 240 * scale
        qr_image = pixmap.toImage().convertToFormat(QImage.Format_RGB32).scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation)
        
        margin = 12 * scale
        text_font = QFont('Arial', 12 * scale)
        metrics = QFontMetrics(text_font)
        lines = guide_text.splitlines() or [qr_type]
        line_height = metrics.lineSpacing()
        
        canvas = QImage(qr_size + margin * 2, qr_size + line_height * len(lines) + margin * 2, QImage.Format_RGB32)
        canvas.fill(Qt.white)
        
        painter = QPainter(canvas)
        painter.setPen(Qt.black)
        painter.setFont(text_font)
        painter.drawImage(margin, margin, qr_image)
        
        text_y = margin + qr_size + scale * 2
        for line in lines:
            painter.drawText(margin, text_y, qr_size, line_height, Qt.AlignHCenter, line)
            text_y += line_height
        painter.end()
        
        safe_name = 'network_connection_qr' if qr_type == 'network' else 'captive_portal_qr'
        output_path = os.path.join(output_dir, f'{safe_name}_{scale}x.jpg')
        canvas.save(output_path, 'JPG')

    def run_auto_detection(self):
        self.interfaces = get_network_interfaces()
        opt_internet, opt_hotspot = choose_optimal_adapters(
            self.interfaces, '', '', '', ''
        )
        self.populate_internet_nic_combo(opt_internet[0])
        self.populate_hotspot_nic_combo(opt_hotspot[0])
        QMessageBox.information(self, "Auto Detection", "네트워크 어댑터 자동 검출이 다시 실행되었습니다.")

    def set_hotspot_state(self, enabled: bool):
        self.interfaces = get_network_interfaces()
        
        ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        pw = self.password_input.text().strip() or DEFAULT_HOTSPOT_PASSWORD
        net = self.hotspot_network_input.text().strip() or DEFAULT_HOTSPOT_NETWORK
        gw = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        internet_data = self.internet_nic_combo.currentData() or {}
        hotspot_data = self.hotspot_nic_combo.currentData() or {}

        selected_hotspot_text = self.hotspot_nic_combo.currentText()
        nic_display = hotspot_data.get('display', '') or selected_hotspot_text or 'Wi-Fi Adapter'

        if enabled:
            success, msg = set_hotspot_enabled(
                enabled=True,
                ssid_name=ssid,
                internet_nic=internet_data,
                hotspot_nic=hotspot_data,
                hotspot_network=net,
                hotspot_gateway=gw,
                enforce_checkpoints=True
            )
            if success:
                fw_res = apply_hotspot_firewall_rules(web_port=5000, hotspot_network=net, hotspot_gateway=gw)
                
                self.interfaces = get_network_interfaces()
                current_internet_val = internet_data.get('display', '')
                self.populate_internet_nic_combo(current_internet_val)
                self.populate_hotspot_nic_combo(nic_display, hotspot_gateway=gw)

                self.active_name_label.setText(f"Active Hotspot Name: <b>{ssid}</b> (Running)")
                self.active_nic_label.setText(f"Hotspot NIC: <b>{nic_display}</b>")
                self.active_range_label.setText(f"Hotspot IP range: <b>{net}</b> / gateway: <b>{gw}</b>")
                
                self.hotspot_status_btn.setText("Hotspot: ACTIVE")
                self.hotspot_status_btn.setStyleSheet(
                    "QLabel { background-color: #2e7d32; color: white; font-weight: bold; border-radius: 4px; padding: 5px; }"
                )

                QMessageBox.information(self, "Hotspot ON", f"{msg}\n\n방화벽 설정 결과: {fw_res.get('summary')}")
            else:
                QMessageBox.warning(self, "Hotspot Error", f"핫스팟을 시작할 수 없습니다:\n{msg}")
        else:
            success, msg = set_hotspot_enabled(
                enabled=False,
                ssid_name=ssid,
                internet_nic=internet_data,
                hotspot_nic=hotspot_data,
                hotspot_network=net,
                hotspot_gateway=gw,
                enforce_checkpoints=False
            )
            
            self.interfaces = get_network_interfaces()
            self.populate_internet_nic_combo('')
            self.populate_hotspot_nic_combo('', hotspot_gateway=gw)

            self.active_name_label.setText(f"Active Hotspot Name: <b>-</b> (Stopped)")
            self.active_nic_label.setText(f"Hotspot NIC: <b>{nic_display}</b>")
            self.hotspot_status_btn.setText("Hotspot: INACTIVE")
            self.hotspot_status_btn.setStyleSheet(
                "QLabel { background-color: #c62828; color: white; font-weight: bold; border-radius: 4px; padding: 5px; }"
            )

            QMessageBox.information(self, "Hotspot OFF", msg)
        
        self.diagnose_hotspot()

    def diagnose_hotspot(self):
        self.diag_timer.start()
        self.hotspot_status_btn.setText("Diagnosing...")
        QApplication.processEvents()

        net = self.hotspot_network_input.text().strip() or DEFAULT_HOTSPOT_NETWORK
        gw = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        hotspot_data = self.hotspot_nic_combo.currentData() or {}
        internet_data = self.internet_nic_combo.currentData() or {}

        diag = run_hotspot_diagnostics(
            hotspot_nic=hotspot_data,
            hotspot_network=net,
            hotspot_gateway=gw,
            internet_nic=internet_data
        )
        
        self.diag_timer.stop()
        is_active = diag.get('active', False)

        ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        nic_display = hotspot_data.get('display', '') or self.hotspot_nic_combo.currentText() or 'Not selected'

        if is_active:
            self.hotspot_status_btn.setText("Hotspot: ACTIVE")
            self.hotspot_status_btn.setStyleSheet(
                "QLabel { background-color: #2e7d32; color: white; font-weight: bold; border-radius: 4px; padding: 5px; }"
            )
            self.active_name_label.setText(f"Active Hotspot Name: <b>{ssid}</b> (Running)")
            self.active_nic_label.setText(f"Hotspot NIC: <b>{nic_display}</b>")
            self._auto_retry_done = False
        else:
            self.hotspot_status_btn.setText("Hotspot: INACTIVE")
            self.hotspot_status_btn.setStyleSheet(
                "QLabel { background-color: #c62828; color: white; font-weight: bold; border-radius: 4px; padding: 5px; }"
            )
            self.active_name_label.setText(f"Active Hotspot Name: <b>{ssid}</b> (Stopped)")
            self.active_nic_label.setText(f"Hotspot NIC: <b>{nic_display}</b>")

            if not self._auto_retry_done:
                self._auto_retry_done = True
                QTimer.singleShot(500, self._execute_one_time_auto_fix)

    def _animate_diagnostic_status(self):
        self._anim_toggle = not self._anim_toggle
        if self._anim_toggle:
            self.hotspot_status_btn.setStyleSheet(
                "QLabel { background-color: #f57c00; color: white; font-weight: bold; border-radius: 4px; padding: 5px; }"
            )
        else:
            self.hotspot_status_btn.setStyleSheet(
                "QLabel { background-color: #0288d1; color: white; font-weight: bold; border-radius: 4px; padding: 5px; }"
            )

    def _execute_one_time_auto_fix(self):
        ssid = self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID
        net = self.hotspot_network_input.text().strip() or DEFAULT_HOTSPOT_NETWORK
        gw = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        internet_data = self.internet_nic_combo.currentData() or {}
        hotspot_data = self.hotspot_nic_combo.currentData() or {}

        success, msg = set_hotspot_enabled(
            enabled=True,
            ssid_name=ssid,
            internet_nic=internet_data,
            hotspot_nic=hotspot_data,
            hotspot_network=net,
            hotspot_gateway=gw,
            enforce_checkpoints=True
        )
        if success:
            apply_hotspot_firewall_rules(web_port=5000, hotspot_network=net, hotspot_gateway=gw)
            self.diagnose_hotspot()

    def toggle_password_visibility(self, visible):
        self.password_input.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.show_password_btn.setText("Hide" if visible else "Show")

    def generate_random_password(self):
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
        self.password_input.setText(''.join(secrets.choice(alphabet) for _ in range(12)))

    def populate_internet_nic_combo(self, selected):
        self.internet_nic_combo.clear()
        for display_name, ip, connected, wireless in self.interfaces:
            self.internet_nic_combo.addItem(display_name, {'display': display_name, 'ip': ip})
            index = self.internet_nic_combo.count() - 1
            item_color = QColor(0, 180, 0) if connected else QColor(220, 0, 0)
            self.internet_nic_combo.setItemData(index, connected, Qt.UserRole + 1)
            self.internet_nic_combo.setItemData(index, item_color, Qt.ForegroundRole)

            clean_sel = selected.rsplit(' (', 1)[0] if ' (' in selected else selected
            clean_item = display_name.rsplit(' (', 1)[0] if ' (' in display_name else display_name
            if display_name == selected or ip == selected or (clean_sel and clean_sel == clean_item):
                self.internet_nic_combo.setCurrentIndex(index)

    def populate_hotspot_nic_combo(self, selected, hotspot_gateway=None):
        self.hotspot_nic_combo.clear()
        
        internet_data = self.internet_nic_combo.currentData() or {}
        selected_internet_name = internet_data.get('display', '').rsplit(' (', 1)[0]

        all_items = []
        for item in self.interfaces:
            display_name, ip, connected, wireless = item
            clean_name = display_name.rsplit(' (', 1)[0]
            
            if clean_name == selected_internet_name:
                continue
                
            is_phys = is_adapter_physical(clean_name)
            is_virtual = any(k in display_name.lower() for k in ('local area connection*', 'wi-fi direct', 'virtual', 'tailscale', 'bluetooth'))
            
            all_items.append((item, is_phys, is_virtual))

        gw = (hotspot_gateway or DEFAULT_HOTSPOT_GATEWAY).strip()
        all_items.sort(key=lambda x: (x[2], not x[1]))

        for item, is_phys, is_virtual in all_items:
            display_name, ip, connected, wireless = item
            clean_nic_name = display_name.rsplit(' (', 1)[0] if ' (' in display_name else display_name
            
            item_display = display_name
            item_ip = ip
            
            if gw and (ip.startswith('169.254.') or ip == gw or is_virtual):
                mac_suffix = display_name[display_name.find(' [MAC:'):] if ' [MAC:' in display_name else ''
                item_display = f"{clean_nic_name} ({gw}){mac_suffix}"
                item_ip = gw

            self.hotspot_nic_combo.addItem(item_display, {'display': item_display, 'ip': item_ip})
            index = self.hotspot_nic_combo.count() - 1
            
            if is_virtual or not is_phys:
                item_color = QColor(220, 0, 0)
            else:
                item_color = QColor(0, 180, 0)
                
            self.hotspot_nic_combo.setItemData(index, connected, Qt.UserRole + 1)
            self.hotspot_nic_combo.setItemData(index, item_color, Qt.ForegroundRole)

            clean_sel = selected.rsplit(' (', 1)[0] if ' (' in selected else selected
            if display_name == selected or item_display == selected or ip == selected or item_ip == selected or clean_sel == clean_nic_name:
                self.hotspot_nic_combo.setCurrentIndex(index)
                
        if self.hotspot_nic_combo.count() > 0:
            current_idx = self.hotspot_nic_combo.currentIndex()
            if current_idx < 0:
                current_idx = 0
            
            selected_text = self.hotspot_nic_combo.itemText(current_idx)
            if any(k in selected_text.lower() for k in ('local area connection*', 'wi-fi direct', 'tailscale', 'virtual')):
                for i in range(self.hotspot_nic_combo.count()):
                    t = self.hotspot_nic_combo.itemText(i)
                    if not any(k in t.lower() for k in ('local area connection*', 'wi-fi direct', 'tailscale', 'virtual', 'bluetooth')):
                        self.hotspot_nic_combo.setCurrentIndex(i)
                        break
            else:
                if current_idx >= 0:
                    self.hotspot_nic_combo.setCurrentIndex(current_idx)

    def on_internet_nic_changed(self, index):
        current_hotspot_data = self.hotspot_nic_combo.currentData() or {'display': ''}
        gw = self.hotspot_gateway_input.text().strip() or DEFAULT_HOTSPOT_GATEWAY
        self.populate_hotspot_nic_combo(current_hotspot_data.get('display', ''), hotspot_gateway=gw)

    def on_hotspot_gateway_changed(self, new_gw):
        new_gw = new_gw.strip()
        if not new_gw:
            return
        current_hotspot_data = self.hotspot_nic_combo.currentData() or {'display': ''}
        self.populate_hotspot_nic_combo(current_hotspot_data.get('display', ''), hotspot_gateway=new_gw)

    def apply_windows_hotspot_limit(self):
        limit = self.windows_hotspot_limit_input.value()
        success, message = apply_windows_hotspot_registry_limit(limit)
        if success:
            QMessageBox.information(self, "Windows limit applied", f"{message}.")
        else:
            QMessageBox.warning(self, "Windows limit not applied", message)

    def save_to_config(self):
        self.config.set('ssid', self.ssid_input.text().strip() or DEFAULT_HOTSPOT_SSID)
        self.config.set('password', self.password_input.text().strip() or DEFAULT_HOTSPOT_PASSWORD)
        self.config.set('provide_internet_for_file_transfer', self.file_transfer_internet_checkbox.isChecked())
        self.config.set('max_connections', self.max_connections_input.value())
        self.config.set('windows_hotspot_limit', self.windows_hotspot_limit_input.value())
        
        self.config.set('network_qr_output_dir', self.qr_output_dirs.get('network'))
        self.config.set('captive_qr_output_dir', self.qr_output_dirs.get('captive'))
        
        internet_data = self.internet_nic_combo.currentData() or {'display': '', 'ip': ''}
        hotspot_data = self.hotspot_nic_combo.currentData() or {'display': '', 'ip': ''}
        gw = self.hotspot_gateway_input.text().strip()
        
        self.config.set('internet_nic', internet_data.get('display', ''))
        self.config.set('internet_ip', internet_data.get('ip', ''))
        self.config.set('internet_mac', get_nic_mac_address(internet_data.get('display', '')))
        
        effective_hotspot_ip = gw if (not hotspot_data.get('ip') or hotspot_data.get('ip', '').startswith('169.254.')) else hotspot_data.get('ip', '')
        self.config.set('hotspot_nic', hotspot_data.get('display', ''))
        self.config.set('hotspot_ip', effective_hotspot_ip)
        self.config.set('hotspot_mac', get_nic_mac_address(hotspot_data.get('display', '')))
        self.config.set('hotspot_gateway', gw)
        self.config.set('hotspot_network', normalize_hotspot_network(self.hotspot_network_input.text().strip(), gw))
        
        self.print_network_qr_codes(silent=True)
        self.print_captive_qr_codes(silent=True)


register_settings_tab('linkshare.hotspot-network-settings', 'Hotspot & Network', HotspotNetworkTab, 10)
