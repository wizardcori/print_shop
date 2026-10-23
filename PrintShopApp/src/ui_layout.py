from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PySide6.QtGui import QAction
from LinkBox.src.ui_linkbox_layout import create_tab as create_linkbox_tab
from LinkShare.src.ui_linkshare_layout import create_tab as create_linkshare_tab

def setup_integrated_ui(window, current_upload_folder, current_zones, current_save_tabs, interfaces, current_ssid, internet_nic, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections, current_main_tab='file_receiver'):
    window.settings_action = QAction('Open Settings', window)
    window.settings_action.triggered.connect(window.open_settings_dialog)
    # Put Settings directly on the title/menu bar. Clicking it opens the
    # settings dialog immediately; there is no second submenu level.
    window.menuBar().addAction(window.settings_action)
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    layout.setContentsMargins(10, 10, 10, 10)
    window.main_tabs = QTabWidget()
    window.main_tabs.currentChanged.connect(window.on_main_tab_changed)
    layout.addWidget(window.main_tabs)
    window._main_tabs = window.main_tabs
    create_linkbox_tab(window, current_upload_folder, current_zones, current_save_tabs, interfaces, current_ssid, internet_nic, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections)
    create_linkshare_tab(window, current_ssid, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections, current_main_tab)
