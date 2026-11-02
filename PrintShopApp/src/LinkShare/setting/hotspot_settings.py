"""Hotspot and Network settings and UI component."""
import os
import ipaddress
import psutil
import socket

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QLineEdit
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QSpinBox, QPushButton, QHBoxLayout, QMessageBox
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from Common.config import FileConfigManager, ConfigType
from Common.settings_dialog import register_settings_tab
from Common.network_utils import normalize_hotspot_network
from LinkShare.hotspot_service import apply_windows_hotspot_registry_limit
from LinkShare.network_adapter_service import ping_ip_address, get_nic_mac_address

DEFAULT_HOTSPOT_SSID = "hbwifi"
DEFAULT_HOTSPOT_PASSWORD = "hbwifihb"
DEFAULT_HOTSPOT_NETWORK = "192.168.137.0/24"
DEFAULT_HOTSPOT_GATEWAY = "192.168.137.1"
DEFAULT_MAX_CONNECTIONS = 250
DEFAULT_WINDOWS_HOTSPOT_LIMIT = 8
WINDOWS_HOTSPOT_LIMIT_MAX = 128
DEFAULT_FILE_TRANSFER_MINUTES = 10

class HotspotNetworkConfig(FileConfigManager):
    section = "HotspotNetworkConfig"
    section_order = 10
    schema = {
        'ssid': {"default": DEFAULT_HOTSPOT_SSID, "type": ConfigType.STRING},
        'password': {"default": DEFAULT_HOTSPOT_PASSWORD, "type": ConfigType.STRING},
        'hotspot_password_user_set': {"default": False, "type": ConfigType.BOOLEAN},
        'startup_enabled': {"default": False, "type": ConfigType.BOOLEAN},
        'file_transfer_minutes': {"default": DEFAULT_FILE_TRANSFER_MINUTES, "type": ConfigType.INTEGER},
        'provide_internet_for_file_transfer': {"default": True, "type": ConfigType.BOOLEAN},
        'max_connections': {"default": DEFAULT_MAX_CONNECTIONS, "type": ConfigType.INTEGER},
        'windows_hotspot_limit': {"default": DEFAULT_WINDOWS_HOTSPOT_LIMIT, "type": ConfigType.INTEGER},
        'internet_nic': {"default": "", "type": ConfigType.STRING},
        'internet_ip': {"default": "", "type": ConfigType.STRING},
        'hotspot_nic': {"default": "", "type": ConfigType.STRING},
        'hotspot_ip': {"default": "", "type": ConfigType.STRING},
        'hotspot_gateway': {"default": DEFAULT_HOTSPOT_GATEWAY, "type": ConfigType.STRING},
        'hotspot_network': {"default": DEFAULT_HOTSPOT_NETWORK, "type": ConfigType.STRING},
    }

class HotspotNetworkTab(QWidget):
    def __init__(self, interfaces=None, parent=None):
        super().__init__(parent)
        self.config = HotspotNetworkConfig()
        self.interfaces = interfaces or []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>Hotspot Settings</h3>"))
        
        layout.addWidget(QLabel("<b>Hotspot SSID (Name):</b>"))
        self.ssid_input = QLineEdit(self.config.get('ssid') or DEFAULT_HOTSPOT_SSID)
        self.ssid_input.setMaxLength(32)
        layout.addWidget(self.ssid_input)

        self.startup_checkbox = QCheckBox("Register automatically at Windows startup")
        self.startup_checkbox.setChecked(self.config.get('startup_enabled'))
        layout.addWidget(self.startup_checkbox)

        self.file_transfer_minutes_input = QSpinBox()
        self.file_transfer_minutes_input.setRange(5, 15)
        self.file_transfer_minutes_input.setValue(self.config.get('file_transfer_minutes'))
        self.file_transfer_minutes_input.setSuffix(" min")
        layout.addWidget(QLabel("File transfer connection duration (5-15 min):"))
        layout.addWidget(self.file_transfer_minutes_input)

        self.file_transfer_internet_checkbox = QCheckBox("Allow Internet access during file transfer")
        self.file_transfer_internet_checkbox.setChecked(self.config.get('provide_internet_for_file_transfer'))
        layout.addWidget(self.file_transfer_internet_checkbox)

        layout.addWidget(QLabel("<b>Hotspot password:</b>"))
        password_layout = QHBoxLayout()
        self.password_input = QLineEdit(self.config.get('password') or DEFAULT_HOTSPOT_PASSWORD)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMaxLength(63)
        password_layout.addWidget(self.password_input)
        
        self.show_password_btn = QPushButton("Show")
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.toggled.connect(self.toggle_password_visibility)
        password_layout.addWidget(self.show_password_btn)
        
        default_password_btn = QPushButton("Default")
        default_password_btn.clicked.connect(lambda: self.password_input.setText(DEFAULT_HOTSPOT_PASSWORD))
        password_layout.addWidget(default_password_btn)
        
        random_password_btn = QPushButton("Random")
        random_password_btn.clicked.connect(self.generate_random_password)
        password_layout.addWidget(random_password_btn)
        layout.addLayout(password_layout)

        layout.addWidget(QLabel("<b>Maximum connections:</b>"))
        self.max_connections_input = QSpinBox()
        self.max_connections_input.setRange(1, 250000)
        self.max_connections_input.setValue(self.config.get('max_connections'))
        self.max_connections_input.setSuffix(" devices")
        layout.addWidget(self.max_connections_input)

        layout.addWidget(QLabel("<b>Windows Mobile Hotspot actual limit (unofficial):</b>"))
        self.windows_hotspot_limit_input = QSpinBox()
        self.windows_hotspot_limit_input.setRange(1, WINDOWS_HOTSPOT_LIMIT_MAX)
        self.windows_hotspot_limit_input.setValue(self.config.get('windows_hotspot_limit'))
        self.windows_hotspot_limit_input.setSuffix(" devices")
        layout.addWidget(self.windows_hotspot_limit_input)
        
        apply_windows_limit_btn = QPushButton("Apply Windows limit (registry)")
        apply_windows_limit_btn.setStyleSheet("background-color: #a15c00; color: white; font-weight: bold;")
        apply_windows_limit_btn.clicked.connect(self.apply_windows_hotspot_limit)
        layout.addWidget(apply_windows_limit_btn)
        layout.addWidget(QLabel("Requires Administrator. Stop/restart Mobile Hotspot; Windows may require a reboot."))

        layout.addWidget(QLabel("<b>Internet NIC (internet line):</b>"))
        self.internet_nic_combo = QComboBox()
        self.populate_nic_combo(self.internet_nic_combo, self.interfaces, self.config.get('internet_nic'), wireless_only=False)
        layout.addWidget(self.internet_nic_combo)

        layout.addWidget(QLabel("<b>Hotspot NIC (recommended wireless adapter):</b>"))
        self.hotspot_nic_combo = QComboBox()
        self.populate_nic_combo(self.hotspot_nic_combo, self.interfaces, self.config.get('hotspot_nic'), wireless_only=True, hotspot_gateway=self.config.get('hotspot_gateway'))
        layout.addWidget(self.hotspot_nic_combo)

        layout.addWidget(QLabel("<b>Hotspot gateway IP:</b>"))
        self.hotspot_gateway_input = QLineEdit(self.config.get('hotspot_gateway'))
        self.hotspot_gateway_input.setPlaceholderText("192.168.137.1")
        self.hotspot_gateway_input.textChanged.connect(self.on_hotspot_gateway_changed)
        layout.addWidget(self.hotspot_gateway_input)

        layout.addWidget(QLabel("<b>Hotspot IPv4 range (CIDR):</b>"))
        self.hotspot_network_input = QLineEdit(self.config.get('hotspot_network'))
        self.hotspot_network_input.setPlaceholderText("192.168.137.0/24")
        layout.addWidget(self.hotspot_network_input)
        layout.addStretch()

    def toggle_password_visibility(self, visible):
        self.password_input.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.show_password_btn.setText("Hide" if visible else "Show")

    def generate_random_password(self):
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
        self.password_input.setText(''.join(secrets.choice(alphabet) for _ in range(12)))

    def populate_nic_combo(self, combo, interfaces, selected, wireless_only, hotspot_gateway=None):
        combo.clear()
        candidates = [item for item in interfaces if item[3]] if wireless_only else list(interfaces)
        candidates = candidates or list(interfaces)
        gw = (hotspot_gateway or '192.168.137.1').strip()
        for display_name, ip, connected, wireless in candidates:
            item_display = display_name
            item_ip = ip
            if wireless_only and gw:
                if ip.startswith('169.254.') or ip == gw:
                    clean_name = display_name.rsplit(' (', 1)[0] if ' (' in display_name else display_name
                    mac_suffix = display_name[display_name.find(' [MAC:'):] if ' [MAC:' in display_name else ''
                    item_display = f"{clean_name} ({gw}){mac_suffix}"
                    item_ip = gw

            combo.addItem(item_display, {'display': item_display, 'ip': item_ip})
            index = combo.count() - 1
            combo.setItemData(index, connected, Qt.UserRole + 1)
            combo.setItemData(index, QColor(0, 180, 0) if connected else QColor(220, 0, 0), Qt.ForegroundRole)

            clean_sel = selected.rsplit(' (', 1)[0] if ' (' in selected else selected
            clean_item = item_display.rsplit(' (', 1)[0] if ' (' in item_display else item_display
            if display_name == selected or item_display == selected or ip == selected or item_ip == selected or (clean_sel and clean_sel == clean_item):
                combo.setCurrentIndex(index)

    def on_hotspot_gateway_changed(self, new_gw):
        new_gw = new_gw.strip()
        if not new_gw:
            return
        current_hotspot_data = self.hotspot_nic_combo.currentData() or {'display': ''}
        self.populate_nic_combo(self.hotspot_nic_combo, self.interfaces, current_hotspot_data.get('display', ''), wireless_only=True, hotspot_gateway=new_gw)

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
        self.config.set('startup_enabled', self.startup_checkbox.isChecked())
        self.config.set('file_transfer_minutes', self.file_transfer_minutes_input.value())
        self.config.set('provide_internet_for_file_transfer', self.file_transfer_internet_checkbox.isChecked())
        self.config.set('max_connections', self.max_connections_input.value())
        self.config.set('windows_hotspot_limit', self.windows_hotspot_limit_input.value())
        
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

register_settings_tab('linkbox.hotspot-network-settings', 'Hotspot & Network', HotspotNetworkTab, order=10)