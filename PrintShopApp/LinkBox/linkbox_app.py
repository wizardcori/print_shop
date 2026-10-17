import sys
import os
from pathlib import Path
import socket
import urllib.parse
import http.server
import socketserver
import ssl
import threading
import datetime
import json
import configparser
import qrcode
from io import BytesIO
from email.parser import BytesParser
from email.policy import default
import psutil

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox, QFileDialog,
    QCheckBox, QMenu, QDialog, QListWidget, QSplitter, QGroupBox, QTabWidget, QGridLayout
)
from PySide6.QtGui import QPixmap, QImage, QColor, QAction
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer

# 외부로 분리된 레이아웃 모듈 임포트
import ui_layout

# Config file path
CONFIG_FILE = "linkbox_config.ini"

DEFAULT_UPLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Desktop", "LinkBox_Files")
os.makedirs(DEFAULT_UPLOAD_FOLDER, exist_ok=True)

DEFAULT_ZONES = ["Counter", "Table01", "Table02", "VIP_Room"]
DEFAULT_SAVE_TABS = ["DefaultTab"]

def load_config():
    config = configparser.ConfigParser()
    folder = DEFAULT_UPLOAD_FOLDER
    zones = DEFAULT_ZONES.copy()
    save_tabs = DEFAULT_SAVE_TABS.copy()
    top_splitter_sizes = [450, 450]
    main_splitter_sizes = [450, 250]
    window_geometry = None
    
    if os.path.exists(CONFIG_FILE):
        try:
            config.read(CONFIG_FILE, encoding='utf-8')
            if 'Settings' in config:
                saved_folder = config['Settings'].get('save_location', '')
                if saved_folder and os.path.isdir(saved_folder):
                    folder = saved_folder
            if 'Zones' in config:
                saved_zones = config['Zones'].get('zones_list', '')
                if saved_zones:
                    zones = [z.strip() for z in saved_zones.split(',') if z.strip()]
            if 'SaveTabs' in config:
                saved_tabs = config['SaveTabs'].get('tabs_list', '')
                if saved_tabs:
                    save_tabs = [t.strip() for t in saved_tabs.split(',') if t.strip()]
            if 'Layout' in config:
                t_sizes = config['Layout'].get('top_splitter', '')
                if t_sizes:
                    parts = [int(p.strip()) for p in t_sizes.split(',') if p.strip()]
                    if len(parts) == 2:
                        top_splitter_sizes = parts
                m_sizes = config['Layout'].get('main_splitter', '')
                if m_sizes:
                    parts = [int(p.strip()) for p in m_sizes.split(',') if p.strip()]
                    if len(parts) == 2:
                        main_splitter_sizes = parts
            if 'Window' in config:
                w = config['Window'].getint('width', 1100)
                h = config['Window'].getint('height', 750)
                x = config['Window'].getint('x', -1)
                y = config['Window'].getint('y', -1)
                window_geometry = (x, y, w, h)
        except Exception as e:
            print(f"Config load error: {e}")
            
    return folder, zones, save_tabs, top_splitter_sizes, main_splitter_sizes, window_geometry

def save_config(folder, zones, save_tabs, top_splitter_sizes=None, main_splitter_sizes=None, window_rect=None):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    
    if not config.has_section('Settings'):
        config.add_section('Settings')
    config['Settings']['save_location'] = folder
    
    if not config.has_section('Zones'):
        config.add_section('Zones')
    config['Zones']['zones_list'] = ','.join(zones)

    if not config.has_section('SaveTabs'):
        config.add_section('SaveTabs')
    config['SaveTabs']['tabs_list'] = ','.join(save_tabs)
    
    if top_splitter_sizes or main_splitter_sizes:
        if not config.has_section('Layout'):
            config.add_section('Layout')
        if top_splitter_sizes:
            config['Layout']['top_splitter'] = f"{top_splitter_sizes[0]},{top_splitter_sizes[1]}"
        if main_splitter_sizes:
            config['Layout']['main_splitter'] = f"{main_splitter_sizes[0]},{main_splitter_sizes[1]}"

    if window_rect:
        if not config.has_section('Window'):
            config.add_section('Window')
        config['Window']['x'] = str(window_rect[0])
        config['Window']['y'] = str(window_rect[1])
        config['Window']['width'] = str(window_rect[2])
        config['Window']['height'] = str(window_rect[3])

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            config.write(f)
    except Exception as e:
        print(f"Config save error: {e}")

SERVER_PORT = 5000  
file_received_callback = None
file_deleted_callback = None

current_upload_folder, current_zones, current_save_tabs, initial_top_sizes, initial_main_sizes, initial_window_geom = load_config()

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} Bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def check_internet_via_ip(ip_address):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.bind((ip_address, 0))
        s.connect(("google.com", 80))
        s.close()
        return True
    except Exception:
        return False

def get_network_interfaces():
    interfaces = []
    try:
        for nic_name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ip = addr.address
                    is_connected = check_internet_via_ip(ip)
                    interfaces.append((f"{nic_name} ({ip})", ip, is_connected))
    except Exception:
        pass
    
    if not interfaces:
        interfaces.append(("Default (192.168.137.1)", "192.168.137.1", False))
    
    def nic_priority(item):
        display_name, ip, connected = item
        name_lower = display_name.lower()
        ping_score = 0 if connected else 1
        wifi_score = 0 if any(kw in name_lower for kw in ["wi-fi", "wifi", "wireless", "wlan", "무선"]) else 1
        return (ping_score, wifi_score)

    interfaces.sort(key=nic_priority)
    return interfaces

class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_zones=None):
        super().__init__(parent)
        self.setWindowTitle("Settings - Manage Tables / Zones")
        self.resize(350, 400)
        
        self.zones = current_zones.copy() if current_zones else DEFAULT_ZONES.copy()
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configure Table / Zone List:"))
        
        self.list_widget = QListWidget()
        self.list_widget.addItems(self.zones)
        layout.addWidget(self.list_widget)
        
        add_layout = QHBoxLayout()
        self.new_zone_input = QLineEdit()
        self.new_zone_input.setPlaceholderText("Enter new table/zone name...")
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_zone)
        add_layout.addWidget(self.new_zone_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)
        
        del_btn = QPushButton("Delete Selected")
        del_btn.setStyleSheet("background-color: #dc3545; color: white;")
        del_btn.clicked.connect(self.delete_zone)
        layout.addWidget(del_btn)
        
        save_close_layout = QHBoxLayout()
        save_btn = QPushButton("Save & Close")
        save_btn.setStyleSheet("background-color: #007BFF; color: white; font-weight: bold;")
        save_btn.clicked.connect(self.accept)
        save_close_layout.addWidget(save_btn)
        layout.addLayout(save_close_layout)

    def add_zone(self):
        text = self.new_zone_input.text().strip()
        if text:
            safe_text = "".join(c for c in text if c.isalnum() or c in ('_', '-'))
            if safe_text and safe_text not in self.zones:
                self.zones.append(safe_text)
                self.list_widget.addItem(safe_text)
                self.new_zone_input.clear()
            else:
                QMessageBox.warning(self, "Warning", "Zone already exists or invalid name.")

    def delete_zone(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            zone_name = item.text()
            if len(self.zones) <= 1:
                QMessageBox.warning(self, "Warning", "You must keep at least one zone.")
                return
            self.zones.remove(zone_name)
            self.list_widget.takeItem(self.list_widget.row(item))

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        zone = query_params.get('zone', ['Default'])[0]
        
        cookie_header = self.headers.get('Cookie', '')
        cookies = {}
        for cookie in cookie_header.split(';'):
            if '=' in cookie:
                k, v = cookie.strip().split('=', 1)
                cookies[k] = v.strip()
        
        full_identity = cookies.get('full_identity')
        
        if not full_identity:
            form_html = f"""
            <form method="POST" action="/register?zone={zone}">
                <p class="info">Please enter your name (Optional).</p>
                <div style="text-align: left; width: 90%; margin: 0 auto; font-size: 14px; font-weight: bold; color: #333;">Name :</div>
                <input type="text" name="user_name" placeholder="Optional"><br>
                <input type="submit" class="btn" value="Next">
            </form>
            """
        else:
            decoded_identity = urllib.parse.unquote(full_identity)
            display_name = decoded_identity.split('_')[0] if decoded_identity else "Guest"
            
            form_html = f"""
            <p class="info">Connected as: <b style="color: #007BFF;">{display_name}</b></p>
            <form onsubmit="uploadFiles(event)">
                <input type="file" id="file-input" multiple><br>
                <div style="text-align: left; width: 90%; margin: 5px auto 0 auto; font-size: 14px; font-weight: bold; color: #333;">Name :</div>
                <input type="text" id="user-name-input" value="{display_name if display_name != 'Guest' else ''}" placeholder="Optional" style="margin-top:5px;"><br>
                <div class="button-group">
                    <button type="submit" class="btn">Send</button>
                    <button type="button" class="btn-danger" onclick="deleteSelectedFiles()">Delete</button>
                </div>
            </form>
            <br>
            <table id="transfer-table">
                <thead>
                    <tr>
                        <th><input type="checkbox" id="select-all" onclick="toggleSelectAll(this)"></th>
                        <th>No.</th>
                        <th>File Name</th>
                        <th>Size</th>
                        <th>Time</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="transfer-tbody">
                </tbody>
            </table>
            <br>
            <a href="/reset?zone={zone}" style="font-size: 11px; color: #888;">Change Name</a>
            <script>
                document.getElementById('file-input').addEventListener('change', handleFileSelection);
            </script>
            """
            
        html_path = os.path.join("templates", "index.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                template = f.read()
            html = template.replace("{zone}", zone).replace("{content}", form_html)
        else:
            html = f"<html><body>Template file (templates/index.html) not found.</body></html>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        zone = query_params.get('zone', ['Default'])[0]
        
        if self.path.startswith('/register'):
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            form_data = urllib.parse.parse_qs(post_data)
            user_name = form_data.get('user_name', [''])[0].strip()
            
            cookie_header = self.headers.get('Cookie', '')
            device_info = "GalaxyS23"
            for cookie in cookie_header.split(';'):
                if 'device_info=' in cookie:
                    val = cookie.split('=', 1)[1].strip()
                    if val:
                        device_info = val
            
            safe_name = "".join(c for c in user_name if c.isalnum() or c in ('_', '-')) if user_name else "Guest"
            safe_zone = "".join(c for c in zone if c.isalnum() or c in ('_', '-'))
            safe_device = "".join(c for c in device_info if c.isalnum() or c in ('_', '-'))
            
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            identity = f"{safe_name}_{timestamp_str}_{safe_zone}_{safe_device}"
            encoded_identity = urllib.parse.quote(identity)
            
            self.send_response(303)
            self.send_header('Location', f'/?zone={zone}')
            self.send_header('Set-Cookie', f'full_identity={encoded_identity}; Path=/; Max-Age=86400')
            self.end_headers()
            
        elif self.path.startswith('/upload'):
            content_type = self.headers.get('Content-Type')
            if not content_type or 'multipart/form-data' not in content_type:
                self.send_response(400)
                self.end_headers()
                return
                
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            msg_data = f"Content-Type: {content_type}\nMIME-Version: 1.0\n\n".encode('utf-8') + body
            msg = BytesParser(policy=default).parsebytes(msg_data)
            
            user_name = "Guest"
            file_payloads = []
            
            for part in msg.walk():
                cd = part.get('Content-Disposition', '')
                name_attr = part.get_param('name', header='content-disposition')
                
                if name_attr == 'user_name':
                    val = part.get_payload(decode=True)
                    if val:
                        decoded_val = val.decode('utf-8').strip()
                        if decoded_val:
                            user_name = "".join(c for c in decoded_val if c.isalnum() or c in ('_', '-'))
                elif 'filename="' in cd:
                    filename = os.path.basename(part.get_filename())
                    if filename:
                        file_payload = part.get_payload(decode=True)
                        if file_payload is not None:
                            file_payloads.append((filename, file_payload))

            param_user_name = query_params.get('user_name', [''])[0].strip()
            if param_user_name:
                user_name = param_user_name

            cookie_header = self.headers.get('Cookie', '')
            cookies = {}
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    k, v = cookie.strip().split('=', 1)
                    cookies[k] = v.strip()
            
            device_info = cookies.get('device_info', 'GalaxyS23')

            safe_name = "".join(c for c in user_name if c.isalnum() or c in ('_', '-')) if user_name else "Guest"
            safe_zone = "".join(c for c in zone if c.isalnum() or c in ('_', '-'))
            safe_device = "".join(c for c in device_info if c.isalnum() or c in ('_', '-'))

            timestamp_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            full_identity = f"{safe_name}_{timestamp_str}_{safe_zone}_{safe_device}"
            
            target_folder = os.path.join(current_upload_folder, full_identity)
            os.makedirs(target_folder, exist_ok=True)
            
            received_files = []
            for filename, file_payload in file_payloads:
                incoming_size = len(file_payload)
                save_path = os.path.join(target_folder, filename)
                
                if os.path.exists(save_path):
                    existing_size = os.path.getsize(save_path)
                    if existing_size != incoming_size:
                        name_root, ext = os.path.splitext(filename)
                        filename = f"{name_root}_{incoming_size}{ext}"
                        save_path = os.path.join(target_folder, filename)
                        
                with open(save_path, 'wb') as f:
                    f.write(file_payload)
                    
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                received_files.append((user_name, zone, filename, format_size(incoming_size), current_time, "Completed (100%)"))
            
            if received_files and file_received_callback:
                file_received_callback(received_files, target_folder, full_identity)
                        
            encoded_identity = urllib.parse.quote(full_identity)
            self.send_response(200)
            self.send_header('Set-Cookie', f'full_identity={encoded_identity}; Path=/; Max-Age=86400')
            self.end_headers()

        elif self.path.startswith('/delete'):
            cookie_header = self.headers.get('Cookie', '')
            full_identity = ""
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    k, v = cookie.strip().split('=', 1)
                    if k == 'full_identity':
                        val = v.strip()
                        if val:
                            full_identity = urllib.parse.unquote(val)
            
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length).decode('utf-8')
                try:
                    data = json.loads(post_data)
                    file_names = data.get('files', [])
                    
                    if full_identity:
                        target_folder = os.path.join(current_upload_folder, full_identity)
                        if os.path.exists(target_folder):
                            for fname in file_names:
                                file_path = os.path.join(target_folder, fname)
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                    
                    if file_names and file_deleted_callback:
                        file_deleted_callback(full_identity, file_names)
                except Exception as e:
                    print(f"Delete error: {e}")
            
            self.send_response(200)
            self.end_headers()
            
        elif self.path.startswith('/reset'):
            self.send_response(303)
            self.send_header('Location', f'/?zone={zone}')
            self.send_header('Set-Cookie', 'full_identity=; Path=/; Max-Age=0')
            self.end_headers()

class ServerThread(QThread):
    def run(self):
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("0.0.0.0", SERVER_PORT), CustomHTTPRequestHandler) as httpd:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            project_root = Path(__file__).resolve().parents[2]
            secrets_dir = project_root / "secrets"
            bundled_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            cert_file = secrets_dir / "cert.pem"
            key_file = secrets_dir / "key.pem"
            if not cert_file.exists() or not key_file.exists():
                cert_file = bundled_dir / "cert.pem"
                key_file = bundled_dir / "key.pem"
            context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
            httpd.serve_forever()

class LinkBoxApp(QMainWindow):
    file_signal = Signal(list, str, str)
    delete_signal = Signal(str, list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinkBox - Smart File Receiver Manager (HTTPS)")
        
        global file_received_callback, file_deleted_callback
        file_received_callback = lambda files, folder, identity: self.file_signal.emit(files, folder, identity)
        file_deleted_callback = lambda identity, files: self.delete_signal.emit(identity, files)
        
        self.pending_batch_files = []
        self.last_target_folder = ""
        self.batch_timer = QTimer()
        self.batch_timer.setSingleShot(True)
        self.batch_timer.setInterval(300)
        self.batch_timer.timeout.connect(self.show_batch_notification)
        
        self.tab_tables = {}  
        self.initial_top_sizes = initial_top_sizes
        self.initial_main_sizes = initial_main_sizes
        
        self.validate_and_clean_save_tabs()
        
        # ui_layout 모듈을 통해 UI 초기화 실행
        interfaces = get_network_interfaces()
        ui_layout.setup_ui(self, current_upload_folder, current_zones, current_save_tabs, interfaces)
        
        if initial_window_geom:
            x, y, w, h = initial_window_geom
            self.resize(w, h)
            if x >= 0 and y >= 0:
                screen = QApplication.screenAt(QApplication.primaryScreen().geometry().center())
                if not screen:
                    screen = QApplication.primaryScreen()
                screen_rect = screen.availableGeometry()
                if x < screen_rect.x() + screen_rect.width() - 100 and y < screen_rect.y() + screen_rect.height() - 100:
                    self.move(x, y)
                else:
                    self.setGeometry(100, 100, w, h)
            else:
                self.resize(1100, 750)
        else:
            self.resize(1100, 750)

        if current_save_tabs:
            self.load_tab_with_files(current_save_tabs[0])

        self.update_qr_code()
        self.file_signal.connect(self.handle_incoming_files)
        self.delete_signal.connect(self.handle_deleted_files)

        self.server_thread = ServerThread()
        self.server_thread.start()

    def validate_and_clean_save_tabs(self):
        global current_save_tabs
        valid_tabs = []
        for tab_name in current_save_tabs:
            tab_path = os.path.join(current_upload_folder, tab_name)
            if os.path.isdir(tab_path):
                valid_tabs.append(tab_name)
        if not valid_tabs:
            valid_tabs = ["DefaultTab"]
            os.makedirs(os.path.join(current_upload_folder, "DefaultTab"), exist_ok=True)
        current_save_tabs = valid_tabs
        save_config(current_upload_folder, current_zones, current_save_tabs)

    def update_save_tab_combo_items(self):
        self.save_tab_combo.blockSignals(True)
        self.save_tab_combo.clear()
        self.save_tab_combo.addItems(current_save_tabs)
        self.save_tab_combo.blockSignals(False)

    def on_save_tab_changed(self, tab_name):
        if tab_name:
            self.load_tab_with_files(tab_name)

    def load_tab_with_files(self, tab_name):
        table = self.get_or_create_table_tab(tab_name)
        if table.rowCount() == 0:
            tab_path = os.path.join(current_upload_folder, tab_name)
            if os.path.exists(tab_path) and os.path.isdir(tab_path):
                try:
                    # 세션 폴더 이름으로부터 Name과 Zone 추출 시도 (예: Ppp_20261015-140100_Table01_GalaxyS23)
                    parts = tab_name.split('_')
                    restored_name = parts[0] if len(parts) > 0 and parts[0] else "Restored"
                    restored_zone = parts[2] if len(parts) > 2 else tab_name

                    for fname in os.listdir(tab_path):
                        fpath = os.path.join(tab_path, fname)
                        if os.path.isfile(fpath):
                            fsize = os.path.getsize(fpath)
                            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%H:%M:%S")
                            
                            row_position = table.rowCount()
                            table.insertRow(row_position)
                            
                            items = [
                                QTableWidgetItem(restored_name),
                                QTableWidgetItem(restored_zone),
                                QTableWidgetItem(fname),
                                QTableWidgetItem(format_size(fsize)),
                                QTableWidgetItem(mtime),
                                QTableWidgetItem("Completed (100%)")
                            ]
                            
                            bg_color = QColor(212, 237, 218)
                            for col, item in enumerate(items):
                                item.setBackground(bg_color)
                                item.setData(Qt.UserRole, tab_path)
                                table.setItem(row_position, col, item)
                except Exception as e:
                    print(f"Error loading files from directory {tab_path}: {e}")

    def update_zone_buttons(self):
        while self.zone_buttons_layout.count():
            item = self.zone_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        max_cols = 3
        for index, zone_name in enumerate(current_zones):
            btn = QPushButton(zone_name)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f8f9fa;
                    border: 1px solid #ced4da;
                    border-radius: 4px;
                    padding: 6px;
                    font-size: 12px;
                    font-weight: bold;
                    color: #333;
                }
                QPushButton:hover {
                    background-color: #e2e6ea;
                    border-color: #adb5bd;
                }
                QPushButton:pressed {
                    background-color: #dae0e5;
                }
            """)
            btn.clicked.connect(lambda checked, z=zone_name: self.select_zone_from_button(z))
            
            row = index // max_cols
            col = index % max_cols
            self.zone_buttons_layout.addWidget(btn, row, col)

    def select_zone_from_button(self, zone_name):
        index = self.zone_combo.findText(zone_name)
        if index >= 0:
            self.zone_combo.setCurrentIndex(index)
        else:
            self.zone_combo.setCurrentText("Custom Input")
            self.zone_input.setText(zone_name)

    def get_or_create_table_tab(self, identity):
        if identity in self.tab_tables:
            table = self.tab_tables[identity]
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == identity:
                    self.tab_widget.setCurrentIndex(i)
                    break
            return table
            
        # ui_layout 모듈을 통해 최적화된 테이블 생성
        table = ui_layout.create_table_widget(self, identity)
        
        self.tab_tables[identity] = table
        self.tab_widget.addTab(table, identity)
        self.tab_widget.setCurrentWidget(table)
        return table

    def close_tab(self, index):
        widget = self.tab_widget.widget(index)
        for identity, table in list(self.tab_tables.items()):
            if table == widget:
                del self.tab_tables[identity]
                break
        self.tab_widget.removeTab(index)

    def closeEvent(self, event):
        pos = self.pos()
        size = self.size()
        window_rect = (pos.x(), pos.y(), size.width(), size.height())
        top_sizes = [self.top_splitter.sizes()[0], self.top_splitter.sizes()[1]]
        main_sizes = [self.main_splitter.sizes()[0], self.main_splitter.sizes()[1]]
        
        save_config(current_upload_folder, current_zones, current_save_tabs, top_sizes, main_sizes, window_rect)
        event.accept()

    def update_zone_combo_items(self):
        self.zone_combo.blockSignals(True)
        self.zone_combo.clear()
        self.zone_combo.addItems(current_zones + ["Custom Input"])
        self.zone_combo.blockSignals(False)

    def open_settings_dialog(self):
        global current_zones
        dialog = SettingsDialog(self, current_zones)
        if dialog.exec() == QDialog.Accepted:
            current_zones = dialog.zones
            pos = self.pos()
            size = self.size()
            window_rect = (pos.x(), pos.y(), size.width(), size.height())
            top_sizes = [self.top_splitter.sizes()[0], self.top_splitter.sizes()[1]]
            main_sizes = [self.main_splitter.sizes()[0], self.main_splitter.sizes()[1]]
            save_config(current_upload_folder, current_zones, current_save_tabs, top_sizes, main_sizes, window_rect)
            self.update_zone_combo_items()
            self.update_zone_buttons()

    def select_save_folder(self):
        global current_upload_folder
        dir_path = QFileDialog.getExistingDirectory(self, "Select Save Directory", current_upload_folder)
        if dir_path:
            current_upload_folder = dir_path
            self.folder_input.setText(current_upload_folder)
            pos = self.pos()
            size = self.size()
            window_rect = (pos.x(), pos.y(), size.width(), size.height())
            top_sizes = [self.top_splitter.sizes()[0], self.top_splitter.sizes()[1]]
            main_sizes = [self.main_splitter.sizes()[0], self.main_splitter.sizes()[1]]
            save_config(current_upload_folder, current_zones, current_save_tabs, top_sizes, main_sizes, window_rect)

    def on_nic_index_changed(self, index):
        pass

    def on_zone_changed(self, text):
        if text == "Custom Input":
            self.zone_input.setEnabled(True)
            self.zone_input.setText("")
        else:
            self.zone_input.setEnabled(False)
            self.zone_input.setText(text)

    @Slot(str)
    def update_qr_code(self):
        current_nic_index = self.nic_combo.currentIndex()
        ip = self.nic_combo.itemData(current_nic_index, Qt.UserRole) or "192.168.137.1"
        zone = self.zone_input.text().strip() or "Default"
        target_url = f"https://{ip}:{SERVER_PORT}/?zone={zone}"
        self.url_label.setText(f"Generated URL: {target_url}")

        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(target_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qimage = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(qimage)

            self.qr_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            pass

    @Slot(list, str, str)
    def handle_incoming_files(self, file_list, target_folder, identity):
        self.last_target_folder = target_folder
        
        tab_name = os.path.basename(target_folder)
        if tab_name not in current_save_tabs:
            current_save_tabs.append(tab_name)
            save_config(current_upload_folder, current_zones, current_save_tabs)
            self.update_save_tab_combo_items()
        
        self.save_tab_combo.setCurrentText(tab_name)
        table = self.get_or_create_table_tab(tab_name)
        
        for file_info in file_list:
            self.pending_batch_files.append(file_info)
            
            user_name, zone, filename, size, time_str, status = file_info
            row_position = table.rowCount()
            table.insertRow(row_position)
            
            items = [
                QTableWidgetItem(user_name),
                QTableWidgetItem(zone),
                QTableWidgetItem(filename),
                QTableWidgetItem(size),
                QTableWidgetItem(time_str),
                QTableWidgetItem(status)
            ]
            
            bg_color = QColor(212, 237, 218)
            for col, item in enumerate(items):
                item.setBackground(bg_color)
                item.setData(Qt.UserRole, target_folder)
                table.setItem(row_position, col, item)

        self.batch_timer.start()

    @Slot(str, list)
    def handle_deleted_files(self, identity, file_names):
        tab_name = os.path.basename(identity)
        if tab_name in self.tab_tables:
            table = self.tab_tables[tab_name]
            row = table.rowCount() - 1
            while row >= 0:
                name_item = table.item(row, 2)
                if name_item and name_item.text() in file_names:
                    table.removeRow(row)
                row -= 1

    def show_batch_notification(self):
        if not self.pending_batch_files:
            return
            
        file_count = len(self.pending_batch_files)
        first_zone = self.pending_batch_files[0][1]
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("LinkBox Transfer Completed")
        msg_box.setText(f"Successfully received {file_count} file(s) from [{first_zone}].")
        
        if not hasattr(self, 'global_open_checkbox_state'):
            self.global_open_checkbox_state = False
            
        checkbox = QCheckBox("Open target folder")
        checkbox.setChecked(self.global_open_checkbox_state)
        msg_box.setCheckBox(checkbox)
        
        open_btn = msg_box.addButton("Open Folder", QMessageBox.ActionRole)
        ok_btn = msg_box.addButton(QMessageBox.Ok)
        
        msg_box.exec()
        
        self.global_open_checkbox_state = checkbox.isChecked()
        
        if msg_box.clickedButton() == open_btn or (msg_box.clickedButton() == ok_btn and self.global_open_checkbox_state):
            if self.last_target_folder and os.path.exists(self.last_target_folder):
                os.startfile(self.last_target_folder)
                
        self.pending_batch_files.clear()

    def on_row_double_clicked(self, row, col):
        current_table = self.tab_widget.currentWidget()
        if isinstance(current_table, QTableWidget):
            item = current_table.item(row, 0)
            file_item = current_table.item(row, 2) # File Name 컬럼
            if item:
                folder_path = item.data(Qt.UserRole)
                file_name = file_item.text() if file_item else ""
                file_path = os.path.join(folder_path, file_name) if folder_path and file_name else ""
                
                if file_path and os.path.exists(file_path):
                    # 탐색기를 열고 해당 파일을 선택(하이라이트)함
                    os.system(f'explorer /select,"{os.path.normpath(file_path)}"')
                elif folder_path and os.path.exists(folder_path):
                    os.startfile(folder_path)
                else:
                    QMessageBox.warning(self, "Error", "Target folder or file does not exist.")

    def show_context_menu(self, pos, table):
        menu = QMenu(self)
        open_action = QAction("Open Folder & Select File", self)
        delete_action = QAction("Clear Record", self)
        
        menu.addAction(open_action)
        menu.addAction(delete_action)
        
        action = menu.exec(table.viewport().mapToGlobal(pos))
        
        selected_row = table.currentRow()
        if selected_row < 0:
            return
            
        if action == open_action:
            item = table.item(selected_row, 0)
            file_item = table.item(selected_row, 2)
            if item:
                folder_path = item.data(Qt.UserRole)
                file_name = file_item.text() if file_item else ""
                file_path = os.path.join(folder_path, file_name) if folder_path and file_name else ""
                
                if file_path and os.path.exists(file_path):
                    os.system(f'explorer /select,"{os.path.normpath(file_path)}"')
                elif folder_path and os.path.exists(folder_path):
                    os.startfile(folder_path)
                else:
                    QMessageBox.warning(self, "Error", "Target folder or file does not exist.")
                    
        elif action == delete_action:
            table.removeRow(selected_row)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LinkBoxApp()
    window.show()
    sys.exit(app.exec())
