"""Color Output options settings and UI component."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QHBoxLayout, QLineEdit, QPushButton
from Common.config import FileConfigManager, ConfigType
from Common.settings_dialog import register_settings_tab

DEFAULT_COLOR_OPTIONS = ['Color', 'B&W']

class ColorOutputConfig(FileConfigManager):
    section = "ColorOutputConfig"
    section_order = 55
    schema = {
        'color_options': {"default": DEFAULT_COLOR_OPTIONS, "type": ConfigType.LIST},
    }

class ColorOutputTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ColorOutputConfig()
        self.color_options = list(self.config.get('color_options'))
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('<h3>Color Output Options</h3>'))
        
        self.color_list = QListWidget()
        self.color_list.addItems(self.color_options)
        layout.addWidget(self.color_list)
        
        color_input = QHBoxLayout()
        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText('Example: Color, B&W, Grayscale')
        color_input.addWidget(self.color_input)
        
        add_color = QPushButton('Add')
        add_color.clicked.connect(self.add_color_option)
        edit_color = QPushButton('Edit')
        edit_color.clicked.connect(self.edit_color_option)
        remove_color = QPushButton('Remove')
        remove_color.clicked.connect(self.remove_color_option)
        
        color_input.addWidget(add_color)
        color_input.addWidget(edit_color)
        color_input.addWidget(remove_color)
        layout.addLayout(color_input)
        layout.addStretch()

    def refresh_color_list(self):
        self.color_list.clear()
        self.color_list.addItems(self.color_options)

    def add_color_option(self):
        value = self.color_input.text().strip()
        if value and value not in self.color_options:
            self.color_options.append(value)
            self.refresh_color_list()
            self.color_input.clear()

    def edit_color_option(self):
        row = self.color_list.currentRow()
        value = self.color_input.text().strip()
        if 0 <= row < len(self.color_options) and value:
            self.color_options[row] = value
            self.refresh_color_list()
            self.color_list.setCurrentRow(row)

    def remove_color_option(self):
        row = self.color_list.currentRow()
        if len(self.color_options) <= 1:
            return
        if 0 <= row < len(self.color_options):
            self.color_options.pop(row)
            self.refresh_color_list()

    def save_to_config(self):
        options = self.color_options or DEFAULT_COLOR_OPTIONS
        self.config.set('color_options', options)

register_settings_tab('linkbox.color-output-settings', 'Color Output', ColorOutputTab, order=35)