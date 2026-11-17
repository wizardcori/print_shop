"""Storage and Display settings and UI component."""
import os

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QHBoxLayout 
from PySide6.QtCore import Qt
from PySide6.QtGui  import QPixmap

from Common.config import FileConfigManager, ConfigType
from Common.geometry_manager import AutoGeometryWidget
from Common.settings_registry import register_settings_tab

INTERNET_SHARE_COOKIE = 'internet_share_client_token'
DEFAULT_INTERNET_SHARE_STATUS_POLL_INTERVAL = 30


class LinkshareConfig(FileConfigManager):
    section = "LinkshareConfig"
    section_order = 20
    schema = {
        'internet_share_client_cookie': {"default": INTERNET_SHARE_COOKIE, "type": ConfigType.STRING},
        'link_share_database': {"default": "", "type": ConfigType.STRING},
        'internet_share_status_poll_interval': {"default": DEFAULT_INTERNET_SHARE_STATUS_POLL_INTERVAL, "type": ConfigType.INTEGER},        
        'active_tab_index': {"default": 0, "type": ConfigType.INTEGER},        
        'fare_image_dir': {"default": "", "type": ConfigType.STRING},                
        'hotspot_image': {"default": "", "type": ConfigType.STRING},                
        # 💡 [추가] 탭별 필터 상태(콤보박스 인덱스 및 날짜)를 저장하기 위한 스키마 키 등록
        'tab_filter_states': {'type': 'dict', 'default': {}}        
    }

class LinkshareTab(AutoGeometryWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = LinkshareConfig()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>Storage & Display Settings</h3>"))
        
        layout.addWidget(QLabel("<b>Log Storage Folder Path:</b>"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(self.config.get('fare_image_dir'))
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("Hotspot image:"))
        self.image_path_input = QLineEdit(self.config.get('hotspot_image'))
        image_layout.addWidget(self.image_path_input)
        image_browse_btn = QPushButton("Select image...")
        image_browse_btn.clicked.connect(self.browse_hotspot_image)
        image_layout.addWidget(image_browse_btn)
        layout.addLayout(image_layout)
        
        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumHeight(100)
        layout.addWidget(self.image_preview)
        self.update_image_preview(self.config.get('hotspot_image'))
        
        layout.addStretch()

    def browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Log Directory", self.path_input.text())
        if dir_path:
            self.path_input.setText(dir_path)

    def browse_hotspot_image(self):
        image_path, _ = QFileDialog.getOpenFileName(
            self, "Select Hotspot Image", self.image_path_input.text(),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if image_path:
            self.image_path_input.setText(image_path)
            self.update_image_preview(image_path)

    def update_image_preview(self, image_path):
        if image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self.image_preview.setPixmap(pixmap.scaled(300, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.image_preview.clear()

    def save_to_config(self):
        self.config.set('fare_image_dir', self.path_input.text().strip())
        self.config.set('hotspot_image', self.image_path_input.text().strip())

register_settings_tab('linkshare-settings', 'LinkShare Setting', LinkshareTab, order=16)