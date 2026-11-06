"""Zone and Table management settings and UI component."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QHBoxLayout, QMessageBox
from Common.config import FileConfigManager, ConfigType
from Common.geometry_manager import AutoGeometryWidget
from Common.settings_registry import register_settings_tab

DEFAULT_ZONES = ["Counter", "Table01", "Table02", "VIP_Room"]
DEFAULT_SAVE_TABS = ["DefaultTab"]

class ZoneManagementConfig(FileConfigManager):
    section = "ZoneManagementConfig"
    section_order = 30
    schema = {
        'zones': {"default": DEFAULT_ZONES, "type": ConfigType.LIST},
        'save_tabs': {"default": DEFAULT_SAVE_TABS, "type": ConfigType.LIST},
    }

class ZoneManagementTab(AutoGeometryWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ZoneManagementConfig()
        self.zones = list(self.config.get('zones'))
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>Table / Zone Management</h3>"))
        
        layout.addWidget(QLabel("<b>Configure Table / Zone List:</b>"))
        self.list_widget = QListWidget()
        self.list_widget.addItems(self.zones)
        layout.addWidget(self.list_widget)
        
        add_layout = QHBoxLayout()
        self.new_zone_input = QLineEdit()
        self.new_zone_input.setPlaceholderText("New table/zone name...")
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_zone)
        add_layout.addWidget(self.new_zone_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)
        
        del_btn = QPushButton("Delete Selected Zone")
        del_btn.setStyleSheet("background-color: #dc3545; color: white;")
        del_btn.clicked.connect(self.delete_zone)
        layout.addWidget(del_btn)
        
        layout.addStretch()

    def add_zone(self):
        text = self.new_zone_input.text().strip()
        if text:
            safe_text = "".join(c for c in text if c.isalnum() or c in ('_', '-'))
            if safe_text and safe_text not in self.zones:
                self.zones.append(safe_text)
                self.list_widget.addItem(safe_text)
                self.new_zone_input.clear()

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

    def save_to_config(self):
        self.config.set('zones', self.zones)

register_settings_tab('linkbox.zone-management-settings', 'Tables & Zones', ZoneManagementTab, order=20)