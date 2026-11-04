"""File Transfer Minutes configuration settings and UI component."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QLineEdit, QPushButton
from Common.config import FileConfigManager, ConfigType
from Common.settings_registry import register_settings_tab

DEFAULT_FILE_TRANSFER_MINUTES = 10

class LinkBoxConfig(FileConfigManager):
    section = "LinkBoxConfig"
    section_order = 55
    schema = {
        'file_transfer_minutes': {"default": DEFAULT_FILE_TRANSFER_MINUTES, "type": ConfigType.INTEGER},
    }

class FileransferMinutesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = LinkBoxConfig()
        self.file_transfer_minutes = self.config.get('file_transfer_minutes')
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('<h3>File Transfer Minutes Configuration</h3>'))
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel('File Transfer Minutes:'))
        
        self.minutes_input = QLineEdit()
        self.minutes_input.setText(str(self.file_transfer_minutes))
        input_layout.addWidget(self.minutes_input)
        
        layout.addLayout(input_layout)
        layout.addStretch()

    def save_to_config(self):
        try:
            value = int(self.minutes_input.text().strip())
            self.config.set('file_transfer_minutes', value)
        except ValueError:
            pass

register_settings_tab('linkbox.file-transfer-settings', 'File Transfer', FileransferMinutesTab, order=35)
