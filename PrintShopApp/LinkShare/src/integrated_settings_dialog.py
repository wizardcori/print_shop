"""Integrated settings dialog assembled from feature-owned settings tabs."""
import os
import secrets
import shutil
from dotenv import dotenv_values
try:
    import winsound
except ImportError:
    winsound = None
from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtCore import Qt
import ipaddress
import psutil
import socket
from Common import settings_service
from Common.settings_registry import iter_settings_tabs
from Common.network_utils import normalize_hotspot_network
from LinkShare.src.hotspot_service import apply_windows_hotspot_registry_limit
from LinkShare.src.network_adapter_service import ping_ip_address
from LinkBox.src.print_log_writer import play_notification_sound
from Common.paths import APPLICATION_DIR, PROGRAM_DATA_DIR, DATA_DIR, APPROVAL_SOUND_DIR, CONFIG_FILE as COMMON_SETTINGS_FILE


DEFAULT_HOTSPOT_SSID = 'hbwifi'
DEFAULT_HOTSPOT_PASSWORD = 'hbwifihb'
DEFAULT_FILE_TRANSFER_MINUTES = 10
DEFAULT_COLOR_OPTIONS = ['Color', 'B&W']
DEFAULT_INTERNET_FARES = [{'minutes': 30, 'price': 5}]
WINDOWS_HOTSPOT_LIMIT_MAX = 128
APP_MODE_LABEL = 'OpMode'
APP_PRINTER_WATCH_ENABLED = False
APP_PRINTER_WATCH_BUILD_ENABLED = False
APP_BUILD_TIME_TEST_ENABLED = False
APP_BUILD_MODE_DEVELOPMENT = False
APP_MODE_CAN_SWITCH = False
APP_SET_RUNTIME_MODE = lambda mode: False
APP_RUNTIME_TEST_ENABLED = False
APP_RUNTIME_FEATURES = {}
APP_RUNTIME_FEATURE_FILE = ''

_default_runtime_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '.env.feature.runtime')
)
if os.path.exists(_default_runtime_file):
    APP_RUNTIME_FEATURES = {
        key: value for key, value in dotenv_values(_default_runtime_file).items()
        if key and value is not None
    }

_SETTINGS_FILE = None
_SETTINGS_DEFAULTS = {
    'zones': ['Counter'],
    'save_tabs': ['DefaultTab'],
    'internet_fares': DEFAULT_INTERNET_FARES,
    'color_options': DEFAULT_COLOR_OPTIONS,
}


def configure_settings_dependencies(
    settings_file,
    defaults,
    *,
    mode_label='OpMode',
    mode_can_switch=False,
    set_runtime_mode=None,
):
    """Bind the dialog to the integrated app's Common settings store."""
    global _SETTINGS_FILE, _SETTINGS_DEFAULTS
    global APP_MODE_LABEL, APP_MODE_CAN_SWITCH, APP_SET_RUNTIME_MODE
    _SETTINGS_FILE = settings_file
    _SETTINGS_DEFAULTS = dict(defaults or _SETTINGS_DEFAULTS)
    APP_MODE_LABEL = mode_label
    APP_MODE_CAN_SWITCH = bool(mode_can_switch)
    APP_SET_RUNTIME_MODE = set_runtime_mode or (lambda mode: False)


def load_app_settings():
    if not _SETTINGS_FILE:
        return dict(_SETTINGS_DEFAULTS)
    return settings_service.load_app_settings(_SETTINGS_FILE, _SETTINGS_DEFAULTS)


def save_app_settings(settings):
    if _SETTINGS_FILE:
        return settings_service.save_app_settings(_SETTINGS_FILE, settings)
    return None


def save_settings_tab_index(index):
    if _SETTINGS_FILE:
        return settings_service.save_settings_tab_index(_SETTINGS_FILE, index)
    return None

def save_about_title_settings(mode_visible, feature_visible):
    settings = load_app_settings()
    settings['show_mode_in_title'] = bool(mode_visible)
    settings['show_feature_in_title'] = bool(feature_visible)
    save_app_settings(settings)

def save_runtime_feature_value(key, value):
    if key not in APP_RUNTIME_FEATURES:
        return
    settings = load_app_settings()
    values = dict(settings.get('runtime_feature_values', {}))
    values[key] = value
    settings['runtime_feature_values'] = values
    save_app_settings(settings)


class IntegratedSettingsDialog(QDialog):
    def change_runtime_mode(self, selected):
        changed = APP_SET_RUNTIME_MODE(
            'development' if selected == 'DevMode' else 'production'
        )
        if changed and hasattr(self.parent(), 'update_window_title'):
            self.parent().update_window_title()

    def save_runtime_feature(self, key, value):
        save_runtime_feature_value(key, value)

    def save_about_title_settings(self, _checked=False):
        save_about_title_settings(
            self.show_mode_title_checkbox.isChecked(),
            self.show_feature_title_checkbox.isChecked(),
        )
        parent = self.parent()
        if parent is not None and hasattr(parent, 'update_window_title'):
            parent.show_mode_in_title = self.show_mode_title_checkbox.isChecked()
            parent.show_feature_in_title = self.show_feature_title_checkbox.isChecked()
            parent.update_window_title()

    def __init__(self, current_zones, current_fare_dir, current_ssid, current_password, interfaces,
                 current_internet_nic, current_hotspot_nic, current_hotspot_image,
                 current_hotspot_network, current_hotspot_gateway, current_max_connections,
                 current_windows_hotspot_limit, approval_sound_enabled,
                 approval_sounds, approval_sound_dir, startup_enabled=False,
                 file_transfer_minutes=DEFAULT_FILE_TRANSFER_MINUTES,
                 provide_internet_for_file_transfer=True, color_options=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Integrated Environment Settings")
        self.resize(520, 650)
        
        self.zones = current_zones.copy()
        self.color_options = list(color_options or DEFAULT_COLOR_OPTIONS)
        root_layout = QVBoxLayout(self)
        settings_tabs = QTabWidget()
        self.settings_tabs = settings_tabs
        root_layout.addWidget(settings_tabs)
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)
        category_layouts = {}
        for tab_title, tab_description in (
            ("Hotspot", "Hotspot SSID, client count, IP range, gateway, and adapter settings"),
            ("Storage/Display", "Image and log storage settings"),
            ("Tables/Zones", "Table and service zone settings"),
        ):
            category_tab = QWidget()
            category_layout = QVBoxLayout(category_tab)
            category_layouts[tab_title] = category_layout
            settings_tabs.addTab(category_tab, tab_title)
        settings_tabs.addTab(general_tab, "General")
        
        layout.addWidget(QLabel("<b>Hotspot SSID (Name):</b>"))
        self.ssid_input = QLineEdit(current_ssid or DEFAULT_HOTSPOT_SSID)
        self.ssid_input.setMaxLength(32)
        self.ssid_input.setPlaceholderText(DEFAULT_HOTSPOT_SSID)
        layout.addWidget(self.ssid_input)
        self.startup_checkbox = QCheckBox("Register automatically at Windows startup")
        self.startup_checkbox.setChecked(startup_enabled)
        self.startup_checkbox.setToolTip("Automatically run PrintShopApp with administrator privileges at Windows login.")
        layout.addWidget(self.startup_checkbox)
        self.file_transfer_minutes_input = QSpinBox()
        self.file_transfer_minutes_input.setRange(5, 15)
        self.file_transfer_minutes_input.setValue(file_transfer_minutes)
        self.file_transfer_minutes_input.setSuffix(" min")
        layout.addWidget(QLabel("File transfer connection duration (5-15 min):"))
        layout.addWidget(self.file_transfer_minutes_input)
        self.file_transfer_internet_checkbox = QCheckBox("Allow Internet access during file transfer")
        self.file_transfer_internet_checkbox.setChecked(provide_internet_for_file_transfer)
        self.file_transfer_internet_checkbox.setToolTip(
            "File transfers are logged separately and are not included in Internet usage charges."
        )
        layout.addWidget(self.file_transfer_internet_checkbox)

        layout.addWidget(QLabel("<b>Hotspot password:</b>"))
        password_layout = QHBoxLayout()
        self.password_input = QLineEdit(current_password or DEFAULT_HOTSPOT_PASSWORD)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMaxLength(63)
        self.password_input.setPlaceholderText(DEFAULT_HOTSPOT_PASSWORD)
        password_layout.addWidget(self.password_input)
        self.show_password_btn = QPushButton("Show")
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.toggled.connect(self.toggle_password_visibility)
        password_layout.addWidget(self.show_password_btn)
        default_password_btn = QPushButton("Default")
        default_password_btn.clicked.connect(
            lambda: self.password_input.setText(DEFAULT_HOTSPOT_PASSWORD)
        )
        password_layout.addWidget(default_password_btn)
        random_password_btn = QPushButton("Random")
        random_password_btn.clicked.connect(self.generate_random_password)
        password_layout.addWidget(random_password_btn)
        layout.addLayout(password_layout)

        layout.addWidget(QLabel("<b>Maximum connections:</b>"))
        self.max_connections_input = QSpinBox()
        self.max_connections_input.setRange(1, 250000)
        self.max_connections_input.setValue(current_max_connections)
        self.max_connections_input.setSuffix(" devices")
        layout.addWidget(self.max_connections_input)

        layout.addWidget(QLabel("<b>Windows Mobile Hotspot actual limit (unofficial):</b>"))
        self.windows_hotspot_limit_input = QSpinBox()
        self.windows_hotspot_limit_input.setRange(1, WINDOWS_HOTSPOT_LIMIT_MAX)
        self.windows_hotspot_limit_input.setValue(current_windows_hotspot_limit)
        self.windows_hotspot_limit_input.setSuffix(" devices")
        layout.addWidget(self.windows_hotspot_limit_input)
        apply_windows_limit_btn = QPushButton("Apply Windows limit (registry)")
        apply_windows_limit_btn.setStyleSheet("background-color: #a15c00; color: white; font-weight: bold;")
        apply_windows_limit_btn.clicked.connect(self.apply_windows_hotspot_limit)
        layout.addWidget(apply_windows_limit_btn)
        layout.addWidget(QLabel(
            "Requires Administrator. Stop/restart Mobile Hotspot; Windows may require a reboot."
        ))

        self.approval_sound_enabled = approval_sound_enabled
        self.approval_sounds = list(approval_sounds[:5])
        self.approval_sound_dir = approval_sound_dir

        layout.addWidget(QLabel("<b>Internet NIC (internet line):</b>"))
        self.internet_nic_combo = QComboBox()
        self.populate_nic_combo(self.internet_nic_combo, interfaces, current_internet_nic, wireless_only=False)
        layout.addWidget(self.internet_nic_combo)

        layout.addWidget(QLabel("<b>Hotspot NIC (recommended wireless adapter):</b>"))
        self.hotspot_nic_combo = QComboBox()
        self.populate_nic_combo(self.hotspot_nic_combo, interfaces, current_hotspot_nic, wireless_only=True, hotspot_gateway=current_hotspot_gateway)
        layout.addWidget(self.hotspot_nic_combo)

        layout.addWidget(QLabel("<b>Hotspot gateway IP:</b>"))
        self.hotspot_gateway_input = QLineEdit(current_hotspot_gateway)
        self.hotspot_gateway_input.setPlaceholderText("192.168.137.1")
        self.hotspot_gateway_input.textChanged.connect(self.on_hotspot_gateway_changed)
        layout.addWidget(self.hotspot_gateway_input)

        layout.addWidget(QLabel("<b>Hotspot IPv4 range (CIDR):</b>"))
        self.hotspot_network_input = QLineEdit(current_hotspot_network)
        self.hotspot_network_input.setPlaceholderText("192.168.137.0/24")
        layout.addWidget(self.hotspot_network_input)

        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("Hotspot image:"))
        self.image_path_input = QLineEdit(current_hotspot_image)
        image_layout.addWidget(self.image_path_input)
        image_browse_btn = QPushButton("Select image...")
        image_browse_btn.clicked.connect(self.browse_hotspot_image)
        image_layout.addWidget(image_browse_btn)
        layout.addLayout(image_layout)
        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumHeight(100)
        layout.addWidget(self.image_preview)
        self.update_image_preview(current_hotspot_image)

        layout.addWidget(QLabel("<b>Log Storage Folder Path:</b>"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(current_fare_dir)
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

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
        
        # Move the existing general-settings controls into their category tabs.
        for category_layout in category_layouts.values():
            while category_layout.count():
                placeholder = category_layout.takeAt(0)
                if placeholder.widget():
                    placeholder.widget().deleteLater()

        general_items = []
        while layout.count():
            general_items.append(layout.takeAt(0))

        def append_settings_items(target_layout, items):
            for item in items:
                if item.widget():
                    target_layout.addWidget(item.widget())
                elif item.layout():
                    target_layout.addLayout(item.layout())
                else:
                    target_layout.addItem(item)

        # Unified Hotspot & Network tab:
        # Item ranges: hotspot identity/limits/range/NICs (0:22),
        # image/log storage (22:26), and table/zone controls (26:).
        append_settings_items(category_layouts["Hotspot"], general_items[0:22])
        category_layouts["Hotspot"].setSpacing(4)
        category_layouts["Hotspot"].setContentsMargins(8, 8, 8, 8)
        append_settings_items(category_layouts["Storage/Display"], general_items[22:26])
        append_settings_items(category_layouts["Tables/Zones"], general_items[26:])
        for tab_title, category_layout in category_layouts.items():
            category_layout.insertWidget(0, QLabel(f"<h3>{tab_title} Settings</h3>"))
            category_layout.addStretch()

        # Apply validation results highlighting on load
        self.validation_results = dict(load_app_settings().get('hotspot_validation_results', {}))
        self.apply_validation_highlighting()

        # The former catch-all tab is no longer exposed; all controls are in category tabs.
        general_index = settings_tabs.indexOf(general_tab)
        if general_index >= 0:
            settings_tabs.removeTab(general_index)

        sound_tab = QWidget()
        sound_layout = QVBoxLayout(sound_tab)
        settings_tabs.addTab(sound_tab, "Approval Alerts")
        self.approval_sound_checkbox = QCheckBox("Play sound on approval")
        self.approval_sound_checkbox.setChecked(self.approval_sound_enabled)
        sound_layout.addWidget(self.approval_sound_checkbox)
        sound_layout.addWidget(QLabel("Add sounds to play on approval and select one."))
        self.internet_fares = load_app_settings().get('internet_fares', DEFAULT_INTERNET_FARES)
        fare_tab = QWidget(); fare_layout = QVBoxLayout(fare_tab)
        fare_layout.addWidget(QLabel('<h3>Internet Rate Table</h3>'))
        self.fare_list = QListWidget(); fare_layout.addWidget(self.fare_list)
        fare_input = QHBoxLayout()
        self.fare_minutes_input = QSpinBox(); self.fare_minutes_input.setRange(1, 1440); self.fare_minutes_input.setSuffix(' min')
        self.fare_price_input = QSpinBox(); self.fare_price_input.setRange(0, 1000000); self.fare_price_input.setSuffix(' PHP')
        fare_input.addWidget(self.fare_minutes_input); fare_input.addWidget(self.fare_price_input); fare_layout.addLayout(fare_input)
        fare_buttons = QHBoxLayout()
        for text, slot in (("Add", self.add_fare), ("Edit", self.edit_fare), ("Remove", self.remove_fare)):
            button = QPushButton(text); button.clicked.connect(slot); fare_buttons.addWidget(button)
        fare_layout.addLayout(fare_buttons); settings_tabs.addTab(fare_tab, 'Internet Rates')
        self.refresh_fare_list()
        color_tab = QWidget(); color_layout = QVBoxLayout(color_tab)
        color_layout.addWidget(QLabel('<h3>Color Output Options</h3>'))
        self.color_list = QListWidget(); self.color_list.addItems(self.color_options)
        color_layout.addWidget(self.color_list)
        color_input = QHBoxLayout(); self.color_input = QLineEdit()
        self.color_input.setPlaceholderText('Example: Color, B&W, Grayscale')
        color_input.addWidget(self.color_input)
        add_color = QPushButton('Add'); add_color.clicked.connect(self.add_color_option)
        edit_color = QPushButton('Edit'); edit_color.clicked.connect(self.edit_color_option)
        remove_color = QPushButton('Remove'); remove_color.clicked.connect(self.remove_color_option)
        color_input.addWidget(add_color); color_input.addWidget(edit_color); color_input.addWidget(remove_color)
        color_layout.addLayout(color_input); settings_tabs.addTab(color_tab, 'Color Output')
        for _, tab_title, tab_factory in iter_settings_tabs():
            settings_tabs.addTab(tab_factory(self), tab_title)
        # About is always appended last so feature-owned settings keep order.
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_layout.addWidget(QLabel('<h2>PrintShop Integrated Manager</h2>'))
        about_layout.addWidget(QLabel(
            'Integrated file transfer, hotspot, and print management application.'
        ))
        about_settings = load_app_settings()
        self.show_mode_title_checkbox = QCheckBox()
        self.show_mode_title_checkbox.setChecked(about_settings.get('show_mode_in_title', True))
        self.show_feature_title_checkbox = QCheckBox()
        self.show_feature_title_checkbox.setChecked(about_settings.get('show_feature_in_title', True))
        self.show_mode_title_checkbox.toggled.connect(self.save_about_title_settings)
        self.show_feature_title_checkbox.toggled.connect(self.save_about_title_settings)
        build_group = QGroupBox('Build')
        build_table = QGridLayout(build_group)
        build_table.addWidget(QLabel('Item'), 0, 0)
        build_table.addWidget(QLabel('Status'), 0, 1)
        build_table.addWidget(QLabel(''), 0, 2)
        build_table.setColumnStretch(0, 2)
        build_table.setColumnStretch(1, 2)
        build_table.setColumnStretch(2, 1)
        build_table.setColumnMinimumWidth(0, 280)
        build_table.setColumnMinimumWidth(1, 280)
        build_table.setColumnMinimumWidth(2, 80)
        build_table.addWidget(QLabel('MODE'), 1, 0)
        mode_editor = QComboBox()
        mode_editor.addItems(['DevMode', 'OpMode'])
        mode_editor.setCurrentText(APP_MODE_LABEL)
        mode_editor.setEnabled(APP_MODE_CAN_SWITCH)
        mode_editor.blockSignals(True)
        mode_editor.blockSignals(False)
        mode_editor.currentTextChanged.connect(
            self.change_runtime_mode
        )
        build_table.addWidget(mode_editor, 1, 1)
        build_table.addWidget(self.show_mode_title_checkbox, 1, 2)
        for row, (name, value) in enumerate([
            ('USE_PRINTER_WATCH', 'ON' if APP_PRINTER_WATCH_BUILD_ENABLED else 'OFF'),
            ('USE_BUILD_TIME_TEST', 'ON' if APP_BUILD_TIME_TEST_ENABLED else 'OFF'),
        ], start=2):
            build_table.addWidget(QLabel(name), row, 0)
            build_table.addWidget(QLabel(value), row, 1)
            build_table.addWidget(QLabel(''), row, 2)
        build_table.addWidget(QLabel('Build mode'), 4, 0)
        build_table.addWidget(QLabel('development' if APP_BUILD_MODE_DEVELOPMENT else 'production'), 4, 1)
        build_table.addWidget(QLabel(''), 4, 2)
        about_layout.addWidget(build_group)
        spacer = QWidget()
        spacer.setFixedHeight(12)
        about_layout.addWidget(spacer)

        run_group = QGroupBox('Run')
        run_table = QGridLayout(run_group)
        run_table.addWidget(QLabel('Item'), 0, 0)
        run_table.addWidget(QLabel('Value'), 0, 1)
        run_table.setColumnStretch(0, 2)
        run_table.setColumnStretch(1, 2)
        run_table.setColumnMinimumWidth(0, 280)
        run_table.setColumnMinimumWidth(1, 520)
        runtime_settings = load_app_settings().get('runtime_feature_values', {})
        for row, (name, default_value) in enumerate(sorted(APP_RUNTIME_FEATURES.items()), start=1):
            run_table.addWidget(QLabel(name), row, 0)
            editor = QComboBox()
            if name == 'USE_RUN_TIME_TEST2':
                editor.addItems([str(value) for value in range(1, 6)])
            elif name == 'USE_RUN_TIME_TEST3':
                editor.addItems(['no', 'yes'])
            else:
                editor.addItems(['true', 'false'])
            editor.blockSignals(True)
            editor.setCurrentText(str(runtime_settings.get(name, default_value)).strip().lower())
            editor.blockSignals(False)
            editor.currentTextChanged.connect(
                lambda selected, key=name: self.save_runtime_feature(key, selected)
            )
            run_table.addWidget(editor, row, 1)
        about_layout.addWidget(run_group)

        # 1. 애플리케이션 디렉토리
        self.label_app_dir = QLabel("APPLICATION_DIR:\n" + str(APPLICATION_DIR))
        self.label_app_dir.setWordWrap(True)
        self.label_app_dir.setStyleSheet("font-family: Consolas; font-size: 12px; color: #335577;")
        about_layout.addWidget(self.label_app_dir)

        # 2. 프로그램 데이터 디렉토리 (설정/로그 저장 위치)
        # [확인] 이 부분이 누락되었거나 변수 참조 시점 문제가 발생했다면, 
        # 여기에서 명시적으로 값을 가져와서 표시합니다.
        self.label_data_dir = QLabel("PROGRAM_DATA_DIR:\n" + str(PROGRAM_DATA_DIR))
        self.label_data_dir.setWordWrap(True)
        self.label_data_dir.setStyleSheet("font-family: Consolas; font-size: 12px; color: #335577;")
        about_layout.addWidget(self.label_data_dir)

        # 3. 데이터 루트 디렉토리 (참고용)
        self.label_root_dir = QLabel("DATA_ROOT:\n" + str(DATA_DIR))
        self.label_root_dir.setWordWrap(True)
        self.label_root_dir.setStyleSheet("font-family: Consolas; font-size: 12px; color: #335577;")
        about_layout.addWidget(self.label_root_dir)


        about_layout.addStretch()
        settings_tabs.addTab(about_tab, 'About')
        saved_tab = load_app_settings().get('settings_active_tab', 0)
        settings_tabs.setCurrentIndex(max(0, min(int(saved_tab), settings_tabs.count() - 1)))
        settings_tabs.currentChanged.connect(save_settings_tab_index)
        self.sound_radio_group = QButtonGroup(self)
        self.sound_radio_group.setExclusive(True)
        self.sound_radios = []
        self.selected_sound_index = -1
        self.play_sound_button = QPushButton("Play Sound")
        self.play_sound_button.clicked.connect(self.play_selected_approval_sound)
        self.play_sound_button.setEnabled(False)
        sound_layout.addWidget(self.play_sound_button)
        self.sound_inputs = []
        for index in range(5):
            sound_row = QHBoxLayout()
            sound_radio = QRadioButton()
            sound_radio.setEnabled(bool(self.approval_sounds[index] if index < len(self.approval_sounds) else ''))
            sound_radio.toggled.connect(lambda checked, i=index: self.select_approval_sound(i, checked))
            self.sound_radio_group.addButton(sound_radio, index)
            self.sound_radios.append(sound_radio)
            sound_row.addWidget(sound_radio)
            sound_row.addWidget(QLabel(f"Sound {index + 1}"))
            sound_input = QLineEdit(self.approval_sounds[index] if index < len(self.approval_sounds) else '')
            self.sound_inputs.append(sound_input)
            sound_row.addWidget(sound_input)
            browse_sound_btn = QPushButton("Select")
            browse_sound_btn.clicked.connect(lambda checked=False, i=index: self.browse_approval_sound(i))
            sound_row.addWidget(browse_sound_btn)
            delete_sound_btn = QPushButton("Delete")
            delete_sound_btn.clicked.connect(lambda checked=False, i=index: self.delete_approval_sound(i))
            sound_row.addWidget(delete_sound_btn)
            sound_layout.addLayout(sound_row)
        for index, path in enumerate(self.approval_sounds[:5]):
            if path:
                self.sound_radios[index].setChecked(True)
                break
        self.update_sound_button_text()
        sound_layout.addStretch()

        save_btn = QPushButton("Save & Close")
        save_btn.setStyleSheet("background-color: #007BFF; color: white; font-weight: bold; padding: 8px;")
        save_btn.clicked.connect(self.accept)
        root_layout.addWidget(save_btn)

    def browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Log Directory", self.path_input.text())
        if dir_path:
            self.path_input.setText(dir_path)

    def browse_approval_sound(self, index):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Approval Alert Sound", self.sound_inputs[index].text(),
            "Wave files (*.wav);;All files (*.*)"
        )
        if path:
            try:
                os.makedirs(self.approval_sound_dir, exist_ok=True)
                target_name = os.path.basename(path)
                target_path = os.path.join(self.approval_sound_dir, target_name)
                if os.path.abspath(path) != os.path.abspath(target_path):
                    shutil.copy2(path, target_path)
                self.sound_inputs[index].setText(target_path)
                self.sound_radios[index].setEnabled(True)
                self.sound_radios[index].setChecked(True)
                self.update_sound_button_text()
            except OSError as exc:
                QMessageBox.warning(self, "Sound copy failed", str(exc))

    def delete_approval_sound(self, index):
        current_path = self.sound_inputs[index].text().strip()
        try:
            if current_path and os.path.isfile(current_path):
                sound_root = os.path.abspath(self.approval_sound_dir)
                if os.path.commonpath([sound_root, os.path.abspath(current_path)]) == sound_root:
                    os.remove(current_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Sound deletion failed", str(exc))
        self.sound_inputs[index].clear()
        self.sound_radios[index].setChecked(False)
        self.sound_radios[index].setEnabled(False)
        self.update_sound_button_text()

    def select_approval_sound(self, index, checked):
        if checked:
            self.selected_sound_index = index
            self.update_sound_button_text()

    def update_sound_button_text(self):
        index = self.selected_sound_index
        path = self.sound_inputs[index].text().strip() if 0 <= index < len(self.sound_inputs) else ''
        self.play_sound_button.setText(f"Play: {os.path.basename(path)}" if path else "Play Sound")
        self.play_sound_button.setEnabled(bool(path and os.path.isfile(path)))

    def play_selected_approval_sound(self):
        index = self.selected_sound_index
        if not (0 <= index < len(self.sound_inputs)):
            return
        path = self.sound_inputs[index].text().strip()
        if winsound is not None and os.path.isfile(path):
            play_notification_sound(path)

    def populate_nic_combo(self, combo, interfaces, selected, wireless_only, hotspot_gateway=None):
        combo.clear()
        candidates = [item for item in interfaces if item[3]] if wireless_only else list(interfaces)
        candidates = candidates or list(interfaces)
        gw = (hotspot_gateway or '192.168.137.1').strip()
        for display_name, ip, connected, wireless in candidates:
            # If configuring HotSpot NIC and the adapter holds APIPA (169.254.x.x) before hotspot starts,
            # display and bind it with the configured Hotspot Gateway IP (e.g., 192.168.137.1)
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
        current_hotspot_data = self.get_hotspot_nic()
        sel_display = current_hotspot_data.get('display', '')
        self.populate_nic_combo(self.hotspot_nic_combo, self.interfaces, sel_display, wireless_only=True, hotspot_gateway=new_gw)

    def refresh_fare_list(self):
        self.fare_list.clear()
        for fare in sorted(self.internet_fares, key=lambda item: item['minutes']):
            self.fare_list.addItem(f"{fare['minutes']} min - {fare['price']:g} PHP")

    def add_fare(self):
        self.internet_fares.append({'minutes': self.fare_minutes_input.value(), 'price': self.fare_price_input.value()})
        self.refresh_fare_list()

    def edit_fare(self):
        row = self.fare_list.currentRow()
        if row < 0 or row >= len(self.internet_fares): return
        self.internet_fares[row] = {'minutes': self.fare_minutes_input.value(), 'price': self.fare_price_input.value()}
        self.refresh_fare_list()

    def remove_fare(self):
        row = self.fare_list.currentRow()
        if row >= 0: self.internet_fares.pop(row); self.refresh_fare_list()

    def refresh_color_list(self):
        self.color_list.clear(); self.color_list.addItems(self.color_options)

    def add_color_option(self):
        value = self.color_input.text().strip()
        if value and value not in self.color_options:
            self.color_options.append(value); self.refresh_color_list(); self.color_input.clear()

    def edit_color_option(self):
        row = self.color_list.currentRow(); value = self.color_input.text().strip()
        if 0 <= row < len(self.color_options) and value:
            self.color_options[row] = value; self.refresh_color_list(); self.color_list.setCurrentRow(row)

    def remove_color_option(self):
        row = self.color_list.currentRow()
        if len(self.color_options) <= 1:
            return
        if 0 <= row < len(self.color_options):
            self.color_options.pop(row); self.refresh_color_list()

    def get_color_options(self):
        return self.color_options or DEFAULT_COLOR_OPTIONS

    def get_internet_fares(self):
        return sorted(self.internet_fares, key=lambda item: item['minutes']) or DEFAULT_INTERNET_FARES

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

    def get_fare_path(self):
        return self.path_input.text().strip()

    def get_hotspot_ssid(self):
        ssid = self.ssid_input.text().strip()
        return ssid or DEFAULT_HOTSPOT_SSID

    def get_startup_enabled(self):
        return self.startup_checkbox.isChecked()

    def get_file_transfer_settings(self):
        return (self.file_transfer_minutes_input.value(),
                self.file_transfer_internet_checkbox.isChecked())

    def get_hotspot_password(self):
        password = self.password_input.text().strip()
        return password or DEFAULT_HOTSPOT_PASSWORD

    def toggle_password_visibility(self, visible):
        self.password_input.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )
        self.show_password_btn.setText("Hide" if visible else "Show")

    def generate_random_password(self):
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
        self.password_input.setText(''.join(secrets.choice(alphabet) for _ in range(12)))

    def get_selected_nic(self, combo):
        data = combo.currentData()
        return data or {'display': '', 'ip': ''}

    def get_internet_nic(self):
        return self.get_selected_nic(self.internet_nic_combo)

    def get_hotspot_nic(self):
        data = dict(self.get_selected_nic(self.hotspot_nic_combo))
        gw = self.hotspot_gateway_input.text().strip() if hasattr(self, 'hotspot_gateway_input') else '192.168.137.1'
        if gw and (not data.get('ip') or data.get('ip', '').startswith('169.254.')):
            data['ip'] = gw
            disp = data.get('display', '')
            if ' (' in disp:
                clean = disp.rsplit(' (', 1)[0]
                mac_suffix = disp[disp.find(' [MAC:'):] if ' [MAC:' in disp else ''
                data['display'] = f"{clean} ({gw}){mac_suffix}"
        return data

    def get_hotspot_image(self):
        return self.image_path_input.text().strip()

    def get_hotspot_network(self):
        return normalize_hotspot_network(self.hotspot_network_input.text().strip(), self.hotspot_gateway_input.text().strip())

    def get_max_connections(self):
        return self.max_connections_input.value()

    def get_windows_hotspot_limit(self):
        return self.windows_hotspot_limit_input.value()

    def get_approval_sound_enabled(self):
        return self.approval_sound_checkbox.isChecked()

    def get_approval_sounds(self):
        sounds = [input_widget.text().strip() for input_widget in self.sound_inputs]
        if 0 <= self.selected_sound_index < len(sounds) and sounds[self.selected_sound_index]:
            selected = sounds.pop(self.selected_sound_index)
            sounds.insert(0, selected)
        return sounds

    def apply_windows_hotspot_limit(self):
        limit = self.get_windows_hotspot_limit()
        answer = QMessageBox.warning(
            self,
            "Unofficial Windows setting",
            f"Write WifiMaxPeers={limit} to the Windows registry?\n\n"
            "This is not a supported Windows UI setting. Administrator permission is required, "
            "and the hotspot may need to be stopped, restarted, or Windows rebooted.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        success, message = apply_windows_hotspot_registry_limit(limit)
        if success:
            QMessageBox.information(
                self,
                "Windows limit applied",
                f"{message}.\n\nTurn Mobile Hotspot off and on again. If Windows still shows the old value, reboot Windows.",
            )
        else:
            QMessageBox.warning(self, "Windows limit not applied", message)

    def apply_validation_highlighting(self):
        """Highlight fields in red if their saved validation status is FAIL."""
        failed_style = "border: 1px solid #d32f2f; background-color: #ffebee; border-radius: 4px;"
        normal_style = ""
        
        # Gateway
        if self.validation_results.get('hotspot_gateway') == 'FAIL':
            self.hotspot_gateway_input.setStyleSheet(failed_style)
            self.hotspot_gateway_input.setToolTip("Validation FAIL: Invalid gateway IP, subnet mismatch, or IP conflict detected.")
        else:
            self.hotspot_gateway_input.setStyleSheet(normal_style)
            self.hotspot_gateway_input.setToolTip("")

        # Network
        if self.validation_results.get('hotspot_network') == 'FAIL':
            self.hotspot_network_input.setStyleSheet(failed_style)
            self.hotspot_network_input.setToolTip("Validation FAIL: Invalid IPv4 CIDR range format.")
        else:
            self.hotspot_network_input.setStyleSheet(normal_style)
            self.hotspot_network_input.setToolTip("")

        # Hotspot NIC
        if self.validation_results.get('hotspot_nic') == 'FAIL':
            self.hotspot_nic_combo.setStyleSheet(failed_style)
            self.hotspot_nic_combo.setToolTip("Validation FAIL: Hotspot adapter is disconnected, invalid, or conflicts with Internet line.")
        else:
            self.hotspot_nic_combo.setStyleSheet(normal_style)
            self.hotspot_nic_combo.setToolTip("")

        # Internet NIC
        if self.validation_results.get('internet_nic') == 'FAIL':
            self.internet_nic_combo.setStyleSheet(failed_style)
            self.internet_nic_combo.setToolTip("Validation FAIL: Internet adapter has no active connection or valid IPv4.")
        else:
            self.internet_nic_combo.setStyleSheet(normal_style)
            self.internet_nic_combo.setToolTip("")

    def accept(self):
        """Validate hotspot settings, run pre-assignment ping check, persist validation results, and accept."""
        gateway_str = self.hotspot_gateway_input.text().strip()
        network_str = self.hotspot_network_input.text().strip()
        
        # Step 1: Pre-assignment ping check & gateway validation
        gateway_valid = True
        gw_obj = None
        try:
            gw_obj = ipaddress.ip_address(gateway_str)
            if gw_obj.version != 4:
                gateway_valid = False
        except ValueError:
            gateway_valid = False

        if not gateway_valid:
            self.validation_results['hotspot_gateway'] = 'FAIL'
        else:
            # Pre-assignment ping check
            # Find if this IP is already assigned locally to our machine
            local_ips = set()
            try:
                for addrs in psutil.net_if_addrs().values():
                    for a in addrs:
                        if a.family == socket.AF_INET:
                            local_ips.add(a.address)
            except Exception:
                pass
            
            # If gateway IP is not already bound to a local adapter, ping to check if another host responds
            if gateway_str not in local_ips:
                is_alive = ping_ip_address(gateway_str, timeout_ms=600)
                if is_alive:
                    ans = QMessageBox.warning(
                        self,
                        "IP Conflict Detected",
                        f"Ping to gateway IP {gateway_str} succeeded from an external host on the network!\n\n"
                        f"Using this IP may cause an IP collision with another active device.\n"
                        f"Do you want to continue saving this IP anyway?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if ans != QMessageBox.Yes:
                        self.validation_results['hotspot_gateway'] = 'FAIL'
                        self.apply_validation_highlighting()
                        return
                    else:
                        self.validation_results['hotspot_gateway'] = 'PASS'
                else:
                    self.validation_results['hotspot_gateway'] = 'PASS'
            else:
                self.validation_results['hotspot_gateway'] = 'PASS'

        # Step 2: Network CIDR validation
        network_valid = True
        try:
            net_obj = ipaddress.ip_network(network_str, strict=False)
            if net_obj.version != 4:
                network_valid = False
            elif gw_obj and gw_obj not in net_obj:
                network_valid = False
                gateway_valid = False
                self.validation_results['hotspot_gateway'] = 'FAIL'
        except ValueError:
            network_valid = False

        self.validation_results['hotspot_network'] = 'PASS' if network_valid else 'FAIL'

        # Step 3: Hotspot NIC & Internet NIC validation
        hotspot_nic_data = self.get_hotspot_nic()
        internet_nic_data = self.get_internet_nic()
        
        hotspot_ip = hotspot_nic_data.get('ip', '')
        internet_ip = internet_nic_data.get('ip', '')

        # Hotspot NIC check
        if not hotspot_nic_data.get('display') or (hotspot_ip and hotspot_ip.startswith('169.254.')):
            self.validation_results['hotspot_nic'] = 'FAIL'
        else:
            self.validation_results['hotspot_nic'] = 'PASS'

        # Internet NIC check
        if not internet_nic_data.get('display') or not internet_ip or internet_ip.startswith('169.254.'):
            self.validation_results['internet_nic'] = 'FAIL'
        else:
            self.validation_results['internet_nic'] = 'PASS'

        # Save validation results to app settings config
        current_settings = load_app_settings()
        current_settings['hotspot_validation_results'] = self.validation_results

        # Save MAC addresses to config along with NIC displays and IPs
        from LinkShare.src.network_adapter_service import get_nic_mac_address
        current_settings['internet_nic'] = internet_nic_data.get('display', '')
        current_settings['internet_ip'] = internet_nic_data.get('ip', '')
        current_settings['internet_mac'] = get_nic_mac_address(internet_nic_data.get('display', ''))
        # Ensure hotspot NIC IP reflects the configured hotspot gateway
        effective_hotspot_ip = gateway_str if (not hotspot_ip or hotspot_ip.startswith('169.254.')) else hotspot_ip
        current_settings['hotspot_nic'] = hotspot_nic_data.get('display', '')
        current_settings['hotspot_ip'] = effective_hotspot_ip
        current_settings['hotspot_mac'] = get_nic_mac_address(hotspot_nic_data.get('display', ''))

        save_app_settings(current_settings)

        self.apply_validation_highlighting()
        super().accept()
