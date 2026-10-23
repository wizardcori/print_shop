"""LinkShare-owned settings tab registration."""
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from Common.settings_registry import register_settings_tab


def create_linkshare_settings(parent=None):
    widget = QWidget(parent)
    layout = QVBoxLayout(widget)
    layout.addWidget(QLabel('<h3>LinkShare Settings</h3>'))
    layout.addWidget(QLabel('LinkShare Wi-Fi approval, session and fare settings are managed here.'))
    layout.addStretch()
    return widget


register_settings_tab('linkshare.general', 'LinkShare', create_linkshare_settings, order=30)
