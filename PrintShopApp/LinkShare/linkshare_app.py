import sys
import threading
import subprocess
import configparser
import os
import io
import time
import socket
import http.server
import socketserver
import psutil
from datetime import datetime, timedelta
from flask import Flask, request, render_template
from werkzeug.serving import make_server
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QImage, QPixmap, QPainter, QAction
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, 
    QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QGroupBox,
    QDialog, QInputDialog, QFileDialog, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QTabWidget, QSizePolicy
)
import qrcode
from cryptography.fernet import Fernet

SETTINGS_FILE = "wifi_approval_settings.ini"


def get_current_hotspot_wifi_info():
    """Read the Windows Mobile Hotspot SSID and passphrase."""
    try:
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            return {'ssid': '', 'passphrase': ''}
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        access_point = manager.get_current_access_point_configuration()
        return {
            'ssid': (access_point.ssid or '').strip(),
            'passphrase': (access_point.passphrase or '').strip(),
        }
    except Exception as exc:
        print(f"Hotspot Wi-Fi information unavailable: {exc}")
        return {'ssid': '', 'passphrase': ''}


def escape_wifi_qr_field(value):
    return (
        str(value)
        .replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace(':', '\\:')
    )


def make_wifi_qr_payload(ssid, passphrase):
    auth_type = 'WPA' if passphrase else 'nopass'
    return (
        f"WIFI:T:{auth_type};S:{escape_wifi_qr_field(ssid)};"
        f"P:{escape_wifi_qr_field(passphrase)};H:false;;"
    )

# --- Fernet Encryption Key Management ---
def get_or_create_encryption_key():
    settings = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        settings.read(SETTINGS_FILE, encoding='utf-8')
    
    if settings.has_section('Security') and settings.has_option('Security', 'secret_key'):
        key = settings.get('Security', 'secret_key').encode()
    else:
        key = Fernet.generate_key()
        if not settings.has_section('Security'):
            settings.add_section('Security')
        settings.set('Security', 'secret_key', key.decode())
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            settings.write(f)
    return key

encryption_key = get_or_create_encryption_key()
cipher = Fernet(encryption_key)

web_app = Flask(__name__, template_folder='templates')
shared_sessions = {}
usage_history = []
last_request_times = {}
pending_request_ips = set()


class CaptivePortalRedirectHandler(http.server.BaseHTTPRequestHandler):
    portal_url = ''

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Mobile browsers commonly cancel captive-network probes after
            # receiving the redirect. This is a normal client disconnect.
            return

    def do_GET(self):
        self.send_response(302)
        self.send_header('Location', self.portal_url)
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_HEAD = do_GET

    def log_message(self, format_string, *args):
        return


class CaptivePortalDNSHandler(socketserver.BaseRequestHandler):
    """Resolve hotspot clients' IPv4 DNS requests to the hotspot gateway."""

    def handle(self):
        query, udp_socket = self.request
        if len(query) < 12:
            return
        try:
            offset = 12
            while offset < len(query) and query[offset] != 0:
                offset += 1 + query[offset]
            question_end = offset + 5
            if question_end > len(query):
                return
            question = query[12:question_end]
            query_type = int.from_bytes(query[offset + 1:offset + 3], 'big')
            answers = b''
            answer_count = 0
            if query_type == 1:
                answers = (
                    b'\xc0\x0c' + b'\x00\x01\x00\x01' + (30).to_bytes(4, 'big') +
                    b'\x00\x04' + socket.inet_aton(self.server.gateway)
                )
                answer_count = 1
            response = (
                query[:2] + b'\x81\x80' + b'\x00\x01' + answer_count.to_bytes(2, 'big') +
                b'\x00\x00\x00\x00' + question + answers
            )
            udp_socket.sendto(response, self.client_address)
        except (IndexError, OSError, ValueError):
            return


class CaptivePortalDNSServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True

    def __init__(self, server_address, gateway):
        self.gateway = gateway
        super().__init__(server_address, CaptivePortalDNSHandler)


class ServerSignals(QObject):
    approval_requested = Signal(str, int, str)

signals = ServerSignals()

@web_app.route('/scan')
def customer_scan():
    return render_template('portal.html')

@web_app.route('/file_share')
def file_share_page():
    return render_template('file_share.html')

@web_app.route('/request')
def customer_request():
    minutes = int(request.args.get('min', 60))
    client_ip = request.remote_addr
    dur_str = f"{minutes} Min Pass" if minutes < 60 else f"{minutes//60} Hour Pass"

    now = time.monotonic()
    if client_ip in pending_request_ips:
        return {
            'status': 'Duplicate',
            'msg': 'A request from this device is already waiting for approval.',
        }

    existing_session = shared_sessions.get(client_ip)
    last_request = last_request_times.get(client_ip, 0)
    if now - last_request < 0.2 and not (
        existing_session and existing_session.get('status') == 'Approved'
    ):
        return {
            'status': 'Duplicate',
            'msg': 'The request was already received. Please wait for the administrator.',
        }
    last_request_times[client_ip] = now

    if existing_session and existing_session.get('status') == 'Pending':
        return {
            'status': 'Pending',
            'msg': 'Your previous request is waiting for approval.',
            'session': existing_session,
        }

    pending_request_ips.add(client_ip)
    signals.approval_requested.emit(client_ip, minutes, dur_str)
    return {
        'status': 'Pending',
        'msg': f"[{dur_str}] Approval request sent. Please pay at the counter.",
    }

@web_app.route('/status')
def get_status():
    client_ip = request.remote_addr
    session = shared_sessions.get(client_ip)
    if not session:
        return {"status": "None"}
    return session


class QRDisplayDialog(QDialog):
    def __init__(self, title, qr_pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(350, 400)
        
        layout = QVBoxLayout(self)
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 14pt; color: #2e7d32; margin-bottom: 10px;")
        layout.addWidget(title_label)

        qr_view = QLabel()
        qr_view.setPixmap(qr_pixmap.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        qr_view.setAlignment(Qt.AlignCenter)
        layout.addWidget(qr_view)

        desc_label = QLabel("Show this screen to the customer for scanning.")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("color: #666; font-size: 10pt; margin-top: 10px;")
        layout.addWidget(desc_label)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class ConnectionListDialog(QDialog):
    def __init__(self, sessions_dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Active Connections & Sessions")
        self.resize(750, 400)
        
        layout = QVBoxLayout(self)
        title_label = QLabel("<b>🌐 Current Client Sessions in Memory</b>")
        layout.addWidget(title_label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Serial No", "IP Address", "Pass Type", "Status", "Remaining Time", "Start Time"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #ffffff; color: #263238; gridline-color: #b0bec5; }"
            " QHeaderView::section { background-color: #1565c0; color: #ffffff; font-weight: bold; padding: 5px; }"
        )
        layout.addWidget(self.table)

        self.populate_table(sessions_dict)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def populate_table(self, sessions_dict):
        self.table.setRowCount(len(sessions_dict))
        row = 0
        for ip, data in sessions_dict.items():
            serial = data.get('serial_no', '-')
            fare = data.get('dur_str', '-')
            status = data.get('status', '-')
            
            status_map = {'Pending': 'Pending', 'Approved': 'Active', 'Expired': 'Expired'}
            status_text = status_map.get(status, status)
            start_t = data.get('start_time', '-')
            rem_sec = data.get('remaining_seconds', 0)
            
            if status == 'Approved' and rem_sec > 0:
                m, s = divmod(rem_sec, 60)
                rem_str = f"{m:02d}m {s:02d}s"
            else:
                rem_str = "-"

            self.table.setItem(row, 0, QTableWidgetItem(serial))
            self.table.setItem(row, 1, QTableWidgetItem(ip))
            self.table.setItem(row, 2, QTableWidgetItem(fare))
            self.table.setItem(row, 3, QTableWidgetItem(status_text))
            self.table.setItem(row, 4, QTableWidgetItem(rem_str))
            self.table.setItem(row, 5, QTableWidgetItem(str(start_t)))
            row += 1


class FareLogListDialog(QDialog):
    def __init__(self, fare_base_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Encrypted Fare Log History")
        self.resize(850, 480)

        layout = QVBoxLayout(self)
        title_label = QLabel(f"<b>📁 All Encrypted Logs (Path: {fare_base_dir})</b>")
        layout.addWidget(title_label)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["Serial No", "Log Date", "IP Address", "Pass Type", "Status", "Request Time", "Start Time", "End Time"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #ffffff; color: #263238; gridline-color: #b0bec5; }"
            " QHeaderView::section { background-color: #1565c0; color: #ffffff; font-weight: bold; padding: 5px; }"
        )
        layout.addWidget(self.table)

        self.load_encrypted_logs(fare_base_dir)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def load_encrypted_logs(self, base_dir):
        log_entries = []
        if os.path.exists(base_dir):
            try:
                for ym_folder in os.listdir(base_dir):
                    ym_path = os.path.join(base_dir, ym_folder)
                    if os.path.isdir(ym_path):
                        for file in os.listdir(ym_path):
                            if file.startswith("fare_") and file.endswith(".ini"):
                                file_path = os.path.join(ym_path, file)
                                try:
                                    with open(file_path, 'rb') as f:
                                        encrypted_data = f.read()
                                        decrypted_data = cipher.decrypt(encrypted_data).decode('utf-8')
                                    config = configparser.ConfigParser()
                                    config.read_string(decrypted_data)
                                    
                                    for section in config.sections():
                                        entry = {
                                            'serial': config.get(section, 'serial_number', fallback=section),
                                            'file_date': file.replace("fare_", "").replace(".ini", ""),
                                            'ip': config.get(section, 'client_ip', fallback='-'),
                                            'fare': config.get(section, 'fare', fallback='-'),
                                            'status': config.get(section, 'status', fallback='-'),
                                            'req_time': config.get(section, 'request_time', fallback='-'),
                                            'start_time': config.get(section, 'start_time', fallback='-'),
                                            'end_time': config.get(section, 'end_time', fallback='-'),
                                        }
                                        log_entries.append(entry)
                                except Exception as dec_err:
                                    print(f"Decryption error ({file}): {dec_err}")
            except Exception as e:
                print(f"Log directory scan error: {e}")

        log_entries = sorted(log_entries, key=lambda x: x['req_time'], reverse=True)

        self.table.setRowCount(len(log_entries))
        for row, data in enumerate(log_entries):
            self.table.setItem(row, 0, QTableWidgetItem(data['serial']))
            self.table.setItem(row, 1, QTableWidgetItem(data['file_date']))
            self.table.setItem(row, 2, QTableWidgetItem(data['ip']))
            self.table.setItem(row, 3, QTableWidgetItem(data['fare']))
            self.table.setItem(row, 4, QTableWidgetItem(data['status']))
            self.table.setItem(row, 5, QTableWidgetItem(data['req_time']))
            self.table.setItem(row, 6, QTableWidgetItem(data['start_time']))
            self.table.setItem(row, 7, QTableWidgetItem(data['end_time']))


class SettingsDialog(QDialog):
    def __init__(self, current_fare_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Environment Settings")
        self.resize(400, 200)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>📁 Log Storage Folder (fare folder) Path</b>"))
        
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(current_fare_dir)
        path_layout.addWidget(self.path_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        
        layout.addLayout(path_layout)
        
        desc = QLabel("• Subfolders (e.g., YYYYMM) will be created inside this path.\n• Log files are safely encrypted using Fernet.\n• Logs older than 6 months are automatically cleaned up.")
        desc.setStyleSheet("color: #37474f; font-size: 9pt;")
        layout.addWidget(desc)

        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("font-weight: bold; color: #ffffff; background-color: #2e7d32; border: 1px solid #1b5e20;")
        save_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Log Directory", self.path_input.text())
        if dir_path:
            self.path_input.setText(dir_path)

    def get_fare_path(self):
        return self.path_input.text().strip()


class LinkShareApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(800, 650)
        self.notification_queue = []
        self.notification_dialog_open = False
        self.active_notification_client_ip = None

        self.fare_base_dir = self.load_fare_dir_setting()
        self.clean_old_logs()

        self.request_counter = self.load_initial_counter()
        self.portal_host = self.detect_portal_host()
        self.hotspot_wifi_info = get_current_hotspot_wifi_info()
        self.server_bind_host = '0.0.0.0'
        self.server_port = 5000
        self.web_server = None
        self.captive_portal_servers = []
        self.captive_portal_retry_count = 0
        signals.approval_requested.connect(self.handle_customer_request)

        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.update_timers)
        self.master_timer.start(1000)

        self.init_menu()
        self.init_ui()
        self.start_local_server()
        self.start_captive_portal()
        self.update_window_title_stats()

    def load_fare_dir_setting(self):
        if os.path.exists(SETTINGS_FILE):
            config = configparser.ConfigParser()
            config.read(SETTINGS_FILE, encoding='utf-8')
            if config.has_section('Settings') and config.has_option('Settings', 'fare_dir'):
                return config.get('Settings', 'fare_dir')
        return "fare"

    @staticmethod
    def detect_portal_host():
        """Find the IPv4 address exposed by the Windows hotspot adapter."""
        fallback_address = None
        for interface_name, addresses in psutil.net_if_addrs().items():
            for address in addresses:
                if address.family != socket.AF_INET:
                    continue
                ip_address = address.address
                if ip_address.startswith('192.168.137.') and not ip_address.endswith('.255'):
                    return ip_address
                if (
                    fallback_address is None
                    and 'local area connection' in interface_name.lower()
                    and not ip_address.startswith('127.')
                ):
                    fallback_address = ip_address
        return fallback_address or '192.168.137.1'

    def save_fare_dir_setting(self, path):
        config = configparser.ConfigParser()
        if os.path.exists(SETTINGS_FILE):
            config.read(SETTINGS_FILE, encoding='utf-8')
        if not config.has_section('Settings'):
            config.add_section('Settings')
        config.set('Settings', 'fare_dir', path)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            config.write(f)

    def get_today_log_filepath(self):
        now = datetime.now()
        year_month = now.strftime('%Y%m')
        date_str = now.strftime('%Y%m%d')
        
        target_dir = os.path.join(self.fare_base_dir, year_month)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        filename = f"fare_{date_str}.ini"
        return os.path.join(target_dir, filename)

    def clean_old_logs(self):
        if not os.path.exists(self.fare_base_dir):
            return
            
        threshold_date = datetime.now() - timedelta(days=180)
        try:
            for ym_folder in os.listdir(self.fare_base_dir):
                ym_path = os.path.join(self.fare_base_dir, ym_folder)
                if os.path.isdir(ym_path):
                    for file in os.listdir(ym_path):
                        if file.startswith("fare_") and file.endswith(".ini"):
                            file_path = os.path.join(ym_path, file)
                            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                            if file_mtime < threshold_date:
                                os.remove(file_path)
                    if not os.listdir(ym_path):
                        os.rmdir(ym_path)
        except Exception as e:
            print(f"Log cleanup error: {e}")

    def load_initial_counter(self):
        log_file = self.get_today_log_filepath()
        if os.path.exists(log_file):
            try:
                with open(log_file, 'rb') as f:
                    decrypted_data = cipher.decrypt(f.read()).decode('utf-8')
                config = configparser.ConfigParser()
                config.read_string(decrypted_data)
                sections = config.sections()
                if sections:
                    max_num = 0
                    for sec in sections:
                        if sec.startswith("REQ-"):
                            try:
                                num = int(sec.split("-")[1])
                                if num > max_num: max_num = num
                            except: pass
                    return max_num + 1
            except Exception as e:
                print(f"Initial counter load decryption error: {e}")
        return 1

    def update_window_title_stats(self):
        log_file = self.get_today_log_filepath()
        fare_counts = {}
        total_approved_count = 0
        
        if os.path.exists(log_file):
            try:
                with open(log_file, 'rb') as f:
                    decrypted_data = cipher.decrypt(f.read()).decode('utf-8')
                config = configparser.ConfigParser()
                config.read_string(decrypted_data)
                for sec in config.sections():
                    status = config.get(sec, 'status', fallback='')
                    if 'Approved' in status:
                        total_approved_count += 1
                        fare_str = config.get(sec, 'fare', fallback='Unknown')
                        fare_counts[fare_str] = fare_counts.get(fare_str, 0) + 1
            except Exception as e:
                print(f"Title stats update error: {e}")

        details = [f"{fare_name}: {count}" for fare_name, count in fare_counts.items()]
        detail_str = ", ".join(details) if details else "No records"
        
        title_text = f"Wi-Fi Sharing & Pass Management System | [Today Approved] Total {total_approved_count} ({detail_str})"
        self.setWindowTitle(title_text)

    def init_menu(self):
        menubar = self.menuBar()
        
        print_menu = menubar.addMenu("🖨️ Print Management")
        print_file_action = QAction("Print File Share QR", self)
        print_file_action.triggered.connect(lambda: self.confirm_and_print("File Share", f"http://{self.portal_host}:5000/file_share"))
        print_menu.addAction(print_file_action)

        print_net_action = QAction("Print Internet Access QR", self)
        print_net_action.triggered.connect(lambda: self.confirm_and_print("Internet Access", f"http://{self.portal_host}:5000/scan"))
        print_menu.addAction(print_net_action)

        admin_menu = menubar.addMenu("📊 Management Tools")
        
        list_action = QAction("Active Connections List", self)
        list_action.triggered.connect(self.open_connection_list)
        admin_menu.addAction(list_action)

        fare_log_action = QAction("📋 View Fare Logs", self)
        fare_log_action.triggered.connect(self.open_fare_log_list)
        admin_menu.addAction(fare_log_action)

        setting_action = QAction("⚙️ Environment Settings", self)
        setting_action.triggered.connect(self.open_settings_dialog)
        admin_menu.addAction(setting_action)

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setStyleSheet(
            "QWidget { background-color: #eef3f7; color: #263238; }"
            " QPushButton { background-color: #1565c0; color: #ffffff; border: 1px solid #0d47a1; "
            "border-radius: 4px; padding: 5px 9px; font-weight: bold; }"
            " QPushButton:hover { background-color: #1976d2; }"
            " QPushButton:pressed { background-color: #0d47a1; }"
            " QTabWidget::pane { background-color: #ffffff; border: 1px solid #90a4ae; }"
            " QTabBar::tab { background-color: #d9e5ef; color: #263238; padding: 6px 12px; "
            "border: 1px solid #90a4ae; }"
            " QTabBar::tab:selected { background-color: #1565c0; color: #ffffff; }"
        )
        main_layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        top_label = QLabel(f"💡 Storage Path: <code>{self.fare_base_dir}/YYYYMM/</code> (Encrypted)")
        top_label.setStyleSheet("color: #263238; font-weight: bold; font-size: 10pt;")
        top_layout.addWidget(top_label)

        setting_btn = QPushButton("⚙️ Settings")
        setting_btn.clicked.connect(self.open_settings_dialog)
        top_layout.addWidget(setting_btn)

        list_btn = QPushButton("📊 Active Sessions")
        list_btn.setStyleSheet("font-weight: bold;")
        list_btn.clicked.connect(self.open_connection_list)
        top_layout.addWidget(list_btn)

        log_btn = QPushButton("📋 Fare Logs")
        log_btn.setStyleSheet("font-weight: bold;")
        log_btn.clicked.connect(self.open_fare_log_list)
        top_layout.addWidget(log_btn)
        
        main_layout.addLayout(top_layout)

        qr_grid_layout = QGridLayout()
        qr_grid_layout.setAlignment(Qt.AlignTop)
        server_ip = self.portal_host

        # 1. File Share QR Card
        file_box = QGroupBox("📁 1. File Share QR")
        file_box.setStyleSheet("QGroupBox { color: #0d47a1; font-weight: bold; font-size: 10pt; background: #ffffff; border: 2px solid #90a4ae; border-radius: 6px; margin-top: 8px; padding-top: 8px; }")
        file_layout = QVBoxLayout()
        
        file_url = f"http://{server_ip}:5000/file_share"
        file_pixmap = self.generate_qr_pixmap(file_url, 150)
        file_lbl = QLabel()
        file_lbl.setPixmap(file_pixmap)
        file_lbl.setAlignment(Qt.AlignCenter)
        file_layout.addWidget(file_lbl)

        file_btn_box = QHBoxLayout()
        file_show_btn = QPushButton("🖥️ Show on Screen")
        file_show_btn.clicked.connect(lambda: self.show_qr_on_screen("File Share", file_url))
        file_save_btn = QPushButton("💾 Save Image")
        file_save_btn.clicked.connect(lambda: self.save_qr_image("File_Share_QR.png", file_url))
        file_btn_box.addWidget(file_show_btn)
        file_btn_box.addWidget(file_save_btn)
        file_layout.addLayout(file_btn_box)
        file_box.setLayout(file_layout)
        file_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        qr_grid_layout.addWidget(file_box, 0, 0)

        # 2. Internet Access QR Card
        net_box = QGroupBox("🌐 2. Internet Access Portal QR")
        net_box.setStyleSheet("QGroupBox { color: #0d47a1; font-weight: bold; font-size: 10pt; background: #ffffff; border: 2px solid #90a4ae; border-radius: 6px; margin-top: 8px; padding-top: 8px; }")
        net_layout = QVBoxLayout()
        net_layout.setContentsMargins(4, 4, 4, 4)
        net_layout.setSpacing(2)
        qr_pair_layout = QHBoxLayout()
        network_group = QGroupBox("Network Connection")
        network_group.setStyleSheet(
            "QGroupBox { color: #1565c0; font-weight: bold; background: #e3f2fd; "
            "border: 2px solid #64b5f6; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
        )
        network_layout = QVBoxLayout(network_group)
        captive_group = QGroupBox("Captive Portal")
        captive_group.setStyleSheet(
            "QGroupBox { color: #2e7d32; font-weight: bold; background: #e8f5e9; "
            "border: 2px solid #81c784; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
        )
        captive_layout = QVBoxLayout(captive_group)

        wifi_ssid = self.hotspot_wifi_info.get('ssid') or 'hb_wifi'
        wifi_password = self.hotspot_wifi_info.get('passphrase') or '(not available)'
        wifi_payload = make_wifi_qr_payload(
            wifi_ssid,
            '' if wifi_password == '(not available)' else wifi_password,
        )
        wifi_title = QLabel("Network Connection QR")
        wifi_title.setAlignment(Qt.AlignCenter)
        network_layout.addWidget(wifi_title)
        wifi_lbl = QLabel()
        wifi_lbl.setPixmap(self.generate_qr_pixmap(wifi_payload, 150))
        wifi_lbl.setAlignment(Qt.AlignCenter)
        network_layout.addWidget(wifi_lbl)
        wifi_info = QLabel(f"SSID: {wifi_ssid}\nPassword: {wifi_password}")
        wifi_info.setAlignment(Qt.AlignCenter)
        wifi_info.setStyleSheet("font-size: 9pt; color: #263238;")
        network_layout.addWidget(wifi_info)
        wifi_print_btn = QPushButton("Print network QR")
        wifi_print_btn.setFixedHeight(26)
        wifi_print_btn.clicked.connect(
            lambda: self.confirm_and_print("Network Connection", wifi_payload)
        )
        network_layout.addWidget(wifi_print_btn)
        
        captive_title = QLabel("Captive Portal QR")
        captive_title.setAlignment(Qt.AlignCenter)
        captive_layout.addWidget(captive_title)
        net_url = f"http://{server_ip}:5000/scan"
        net_pixmap = self.generate_qr_pixmap(net_url, 150)
        net_lbl = QLabel()
        net_lbl.setPixmap(net_pixmap)
        net_lbl.setAlignment(Qt.AlignCenter)
        captive_layout.addWidget(net_lbl)

        net_btn_box = QHBoxLayout()
        net_show_btn = QPushButton("🖥️ Show on Screen")
        net_show_btn.clicked.connect(lambda: self.show_qr_on_screen("Internet Access", net_url))
        net_save_btn = QPushButton("💾 Save Image")
        net_save_btn.clicked.connect(lambda: self.save_qr_image("Internet_Access_QR.png", net_url))
        net_btn_box.addWidget(net_show_btn)
        net_btn_box.addWidget(net_save_btn)
        captive_layout.addLayout(net_btn_box)
        captive_print_btn = QPushButton("Print captive QR")
        captive_print_btn.setFixedHeight(26)
        captive_print_btn.clicked.connect(
            lambda: self.confirm_and_print("Captive Portal", net_url)
        )
        captive_layout.addWidget(captive_print_btn)
        qr_pair_layout.addWidget(network_group)
        qr_pair_layout.addWidget(captive_group)
        net_layout.addLayout(qr_pair_layout)
        net_box.setLayout(net_layout)
        net_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        qr_grid_layout.addWidget(net_box, 0, 1)

        main_layout.addLayout(qr_grid_layout)

        self.status_group = QGroupBox("Currently Connected Clients Summary")
        self.status_layout = QVBoxLayout()
        self.status_label = QLabel("No active sessions")
        self.status_layout.addWidget(self.status_label)
        self.status_group.setLayout(self.status_layout)
        self.status_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.status_group.setMaximumHeight(72)
        main_layout.addWidget(self.status_group, 0, Qt.AlignTop)

        self.usage_history_tabs = QTabWidget()
        self.usage_history_tables = {}
        usage_tabs = {
            "연결상태": ["연결상태", "요청시간", "시작시간", "종료시간", "남은시간", "IP 주소"],
            "사용요청": ["사용요청", "요청시간", "IP 주소"],
            "사용허가": ["사용허가", "승인시간", "시작시간", "종료시간", "남은시간", "IP 주소"],
        }
        for tab_name, headers in usage_tabs.items():
            usage_tab = QWidget()
            usage_tab_layout = QVBoxLayout(usage_tab)
            table = QTableWidget(0, len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            table.horizontalHeader().setStretchLastSection(True)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setStyleSheet(
                "QTableWidget { background-color: #ffffff; color: #263238; "
                "gridline-color: #b0bec5; }"
                " QHeaderView::section { background-color: #1565c0; color: white; "
                "font-weight: bold; padding: 4px; }"
            )
            usage_tab_layout.addWidget(table)
            self.usage_history_tables[tab_name] = table
            self.usage_history_tabs.addTab(usage_tab, tab_name)
        self.usage_history_table = self.usage_history_tables["연결상태"]
        main_layout.addWidget(self.usage_history_tabs, 1)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.fare_base_dir, self)
        if dialog.exec() == QDialog.Accepted:
            new_path = dialog.get_fare_path()
            if new_path:
                self.fare_base_dir = new_path
                self.save_fare_dir_setting(new_path)
                QMessageBox.information(self, "Success", f"Log storage folder updated.\nPath: {new_path}")
                self.request_counter = self.load_initial_counter()
                self.update_window_title_stats()

    def open_connection_list(self):
        dialog = ConnectionListDialog(shared_sessions, self)
        dialog.exec()

    def open_fare_log_list(self):
        dialog = FareLogListDialog(self.fare_base_dir, self)
        dialog.exec()

    def start_local_server(self):
        def run_server():
            try:
                # Create the listening socket explicitly so bind errors are
                # reported instead of being hidden by Flask's background
                # thread startup.
                self.web_server = make_server(
                    self.server_bind_host,
                    self.server_port,
                    web_app,
                    threaded=True,
                )
                print(
                    f"[INFO] LinkShare server listening on "
                    f"{self.server_bind_host}:{self.server_port} "
                    f"(portal: http://{self.portal_host}:{self.server_port}/scan)"
                )
                self.web_server.serve_forever()
            except OSError as exc:
                print(
                    f"[ERROR] Could not bind LinkShare server to "
                    f"{self.server_bind_host}:{self.server_port}: {exc}"
                )
            except Exception as exc:
                print(f"[ERROR] LinkShare server stopped: {exc}")
        t = threading.Thread(target=run_server, daemon=True)
        t.start()

    def start_captive_portal(self):
        """Start gateway-bound HTTP and DNS redirects for hotspot clients."""
        portal_url = f"http://{self.portal_host}:{self.server_port}/scan"
        CaptivePortalRedirectHandler.portal_url = portal_url
        messages = []

        try:
            http_server = http.server.ThreadingHTTPServer(
                (self.portal_host, 80), CaptivePortalRedirectHandler
            )
            threading.Thread(target=http_server.serve_forever, daemon=True).start()
            self.captive_portal_servers.append(http_server)
            messages.append('HTTP redirect ON (port 80)')
        except OSError as exc:
            messages.append(f'HTTP redirect unavailable: {exc}')

        try:
            dns_server = CaptivePortalDNSServer((self.portal_host, 53), self.portal_host)
            threading.Thread(target=dns_server.serve_forever, daemon=True).start()
            self.captive_portal_servers.append(dns_server)
            messages.append('DNS redirect ON (port 53)')
        except OSError as exc:
            messages.append(f'DNS redirect unavailable: {exc}')

        print('[INFO] Captive portal: ' + ' | '.join(messages))
        if not self.captive_portal_servers and self.captive_portal_retry_count < 10:
            self.captive_portal_retry_count += 1
            QTimer.singleShot(3000, self.start_captive_portal)

    def stop_captive_portal(self):
        for server in self.captive_portal_servers:
            try:
                server.shutdown()
                server.server_close()
            except OSError:
                pass
        self.captive_portal_servers = []

    def generate_qr_pixmap(self, data, size=150):
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        data_bytes = img.tobytes("raw", "RGBA")
        qimage = QImage(data_bytes, img.size[0], img.size[1], QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimage).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def show_qr_on_screen(self, title, url):
        high_res_pixmap = self.generate_qr_pixmap(url, 300)
        dialog = QRDisplayDialog(title, high_res_pixmap, self)
        dialog.exec()

    def confirm_and_print(self, title, url):
        reply = QMessageBox.question(self, "Print Confirmation", f"Do you want to print the [{title}] QR code to the physical printer?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.print_qr_directly(title, url)

    def print_qr_directly(self, title, url):
        printer = QPrinter(QPrinter.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() == QPrintDialog.Accepted:
            painter = QPainter()
            if painter.begin(printer):
                qr = qrcode.QRCode(version=2, box_size=10, border=2)
                qr.add_data(url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                temp_path = "temp_print_qr.png"
                img.save(temp_path)
                qimg = QImage(temp_path)
                painter.drawText(100, 150, f"=== {title} Ticket ===")
                painter.drawImage(100, 200, qimg.scaled(800, 800, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                painter.drawText(100, 1050, "Scan with your smartphone camera to connect.")
                painter.end()
                if os.path.exists(temp_path): os.remove(temp_path)
                QMessageBox.information(self, "Print Complete", f"[{title}] QR code sent to the printer.")

    def save_qr_image(self, filename, url):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save QR", filename, "PNG Files (*.png)")
        if file_path:
            qr = qrcode.QRCode(version=2, box_size=10, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(file_path)
            QMessageBox.information(self, "Saved", "QR code successfully saved.")

    def handle_customer_request(self, client_ip, minutes, dur_str):
        serial_no = f"REQ-{self.request_counter:03d}"
        self.request_counter += 1

        request_time = datetime.now()
        record = {
            'status': 'Pending',
            'connection_status': '연결됨',
            'dur_str': dur_str,
            'usage_request': dur_str,
            'usage_approval': '승인대기',
            'remaining_seconds': minutes * 60,
            'serial_no': serial_no,
            'client_ip': client_ip,
            'request_time': request_time.strftime('%Y-%m-%d %H:%M:%S'),
            'approval_time': '-',
            'start_time': '-',
            'end_time': '-',
        }
        shared_sessions[client_ip] = record
        usage_history.append(record)
        self.notification_queue.append((record, minutes))

        self.update_or_write_fare_log(serial_no, client_ip, dur_str, "Pending", "-", "-")
        self.update_window_title_stats()
        self.update_usage_history_table()
        self.show_next_request_notification()

    def show_next_request_notification(self):
        if self.notification_dialog_open or not self.notification_queue:
            return
        try:
            self._process_request_notification()
        except Exception as exc:
            print(f"Customer request notification error: {exc}")
        finally:
            self.notification_dialog_open = False
            if self.active_notification_client_ip:
                pending_request_ips.discard(self.active_notification_client_ip)
                self.active_notification_client_ip = None
            self.update_usage_history_table()
            if self.notification_queue:
                QTimer.singleShot(0, self.show_next_request_notification)

    def _process_request_notification(self):
        if self.notification_dialog_open or not self.notification_queue:
            return

        record, minutes = self.notification_queue.pop(0)
        self.active_notification_client_ip = record['client_ip']
        self.notification_dialog_open = True
        serial_no = record['serial_no']
        client_ip = record['client_ip']
        dur_str = record['dur_str']

        reply = QMessageBox.question(
            self, 
            "Payment & Access Approval", 
            f"📍 [Internet Request - {serial_no}]\n\n• Client IP: {client_ip}\n• Selected Pass: {dur_str}\n\nHas the payment been received?\nClick [Yes] to start internet access.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            total_seconds = minutes * 60
            start_time = datetime.now()
            end_time = start_time + timedelta(seconds=total_seconds)

            record.update({
                'status': 'Approved',
                'connection_status': '사용중',
                'usage_approval': '허가',
                'remaining_seconds': total_seconds,
                'approval_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_timestamp': end_time.timestamp(),
            })

            self.update_or_write_fare_log(serial_no, client_ip, dur_str, "Approved", start_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'))
            self.control_client_internet(client_ip, allow=True)
            self.update_window_title_stats()
            
            QMessageBox.information(self, "Approved", f"[{serial_no}] Internet access started for IP ({client_ip}).")
            self.update_status_display()
        else:
            record['status'] = 'Rejected'
            record['connection_status'] = '연결됨'
            record['usage_approval'] = '거부'
            record['remaining_seconds'] = 0
            self.update_or_write_fare_log(serial_no, client_ip, dur_str, "Rejected", "-", "-")
            self.update_window_title_stats()
            QMessageBox.warning(self, "Rejected", f"[{serial_no}] Request from IP ({client_ip}) was rejected.")

        self.notification_dialog_open = False
        self.update_usage_history_table()

    def update_usage_history_table(self):
        if not hasattr(self, 'usage_history_tables'):
            return

        table_records = {
            "연결상태": (usage_history, [
                "connection_status", "request_time", "start_time", "end_time", "remaining", "client_ip"
            ]),
            "사용요청": (usage_history, [
                "usage_request", "request_time", "client_ip"
            ]),
            "사용허가": (
                [record for record in usage_history if record.get('usage_approval', '-') != '-'],
                ["usage_approval", "approval_time", "start_time", "end_time", "remaining", "client_ip"]
            ),
        }

        for tab_name, (records, fields) in table_records.items():
            table = self.usage_history_tables[tab_name]
            table.setRowCount(len(records))
            for row, record in enumerate(reversed(records)):
                remaining = record.get('remaining_seconds', 0)
                if record.get('status') == 'Approved' and remaining > 0:
                    mins, secs = divmod(remaining, 60)
                    remaining_text = f"{mins:02d}분 {secs:02d}초"
                else:
                    remaining_text = '-'

                values = {
                    "connection_status": record.get('connection_status', '-'),
                    "usage_request": record.get('usage_request', record.get('dur_str', '-')),
                    "usage_approval": record.get('usage_approval', '-'),
                    "request_time": record.get('request_time', '-'),
                    "approval_time": record.get('approval_time', '-'),
                    "start_time": record.get('start_time', '-'),
                    "end_time": record.get('end_time', '-'),
                    "remaining": remaining_text,
                    "client_ip": record.get('client_ip', '-'),
                }
                for column, field in enumerate(fields):
                    table.setItem(row, column, QTableWidgetItem(str(values[field])))

    def update_or_write_fare_log(self, serial_no, client_ip, dur_str, status, start_time, end_time):
        log_file = self.get_today_log_filepath()
        config = configparser.ConfigParser()
        
        if os.path.exists(log_file):
            try:
                with open(log_file, 'rb') as f:
                    decrypted_data = cipher.decrypt(f.read()).decode('utf-8')
                config.read_string(decrypted_data)
            except Exception as e:
                print(f"Log read/decryption error: {e}")
            
        if not config.has_section(serial_no):
            config.add_section(serial_no)
            
        config.set(serial_no, 'serial_number', serial_no)
        config.set(serial_no, 'fare', dur_str)
        config.set(serial_no, 'client_ip', client_ip)
        config.set(serial_no, 'status', status)
        config.set(serial_no, 'request_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        config.set(serial_no, 'start_time', str(start_time))
        config.set(serial_no, 'end_time', str(end_time))
        
        output = io.StringIO()
        config.write(output)
        config_string = output.getvalue()
        encrypted_bytes = cipher.encrypt(config_string.encode('utf-8'))
        
        with open(log_file, 'wb') as f:
            f.write(encrypted_bytes)

    def update_timers(self):
        expired_ips = []
        for ip, data in shared_sessions.items():
            if data.get('status') == 'Approved':
                if data['remaining_seconds'] > 1:
                    data['remaining_seconds'] -= 1
                else:
                    expired_ips.append(ip)

        for ip in expired_ips:
            serial_no = shared_sessions[ip]['serial_no']
            shared_sessions[ip]['status'] = 'Expired'
            shared_sessions[ip]['connection_status'] = '종료'
            shared_sessions[ip]['remaining_seconds'] = 0
            self.control_client_internet(ip, allow=False)
            QMessageBox.warning(self, "Session Expired", f"[{serial_no}] Client session (IP: {ip}) has expired.")

        self.update_status_display()
        self.update_usage_history_table()

    def update_status_display(self):
        text = ""
        active_count = 0
        for ip, data in shared_sessions.items():
            if data.get('status') == 'Approved':
                active_count += 1
                secs = data['remaining_seconds']
                m, s = divmod(secs, 60)
                text += f"• [{data['serial_no']}] IP: {ip} | Pass: {data['dur_str']} | Remaining: {m:02d}m {s:02d}s\n"
        
        if active_count == 0:
            self.status_label.setText("No active sessions")
        else:
            self.status_label.setText(text.strip())

    def control_client_internet(self, client_ip, allow):
        try:
            rule_name = f"WiFi_TimeLimit_{client_ip}"
            if allow:
                subprocess.run(f'netsh advfirewall firewall delete rule name="{rule_name}"', capture_output=True, shell=True)
                cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=out action=allow remoteip={client_ip}'
                subprocess.run(cmd, capture_output=True, shell=True)
            else:
                subprocess.run(f'netsh advfirewall firewall delete rule name="{rule_name}"', capture_output=True, shell=True)
                cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=out action=block remoteip={client_ip}'
                subprocess.run(cmd, capture_output=True, shell=True)
        except Exception as e:
            print(f"Firewall Error: {e}")

    def closeEvent(self, event):
        self.stop_captive_portal()
        if self.web_server is not None:
            self.web_server.shutdown()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LinkShareApp()
    window.show()
    sys.exit(app.exec())
