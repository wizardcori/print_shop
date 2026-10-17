import sys
import os
import socket
import urllib.parse
import http.server
import socketserver
import ssl
import threading
import time
import datetime
import json
import configparser
import ipaddress
import qrcode
import subprocess
import psutil
import ctypes
import shutil
import logging
import secrets
import hashlib
import sqlite3
import re
import filecmp
from create_admin_shortcut import set_startup_registration
from db import AppDatabase
try:
    import winsound
except ImportError:
    winsound = None
from io import BytesIO
from email.parser import BytesParser
from email.policy import default
from flask import Flask, request, render_template, redirect, Response, make_response
from cryptography.fernet import Fernet

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox, QFileDialog,
    QCheckBox, QMenu, QDialog, QListWidget, QTabWidget, QGridLayout, QSpinBox, QHeaderView,
    QRadioButton, QButtonGroup, QDateEdit
)
from PySide6.QtGui import QPixmap, QImage, QColor, QAction, QPainter, QFont, QFontMetrics, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer, QObject, QDate

# --- Path and Subfolder Integration ---
# Source mode uses the project folder.  Frozen deployments use the executable
# folder for writable application data and PyInstaller's bundle folder only for
# read-only resources (templates, icons, and Python modules).
current_dir = os.path.dirname(os.path.abspath(__file__))
application_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else current_dir
resource_dir = getattr(sys, '_MEIPASS', current_dir)
configured_data_dir = os.environ.get('PRINTSHOP_DATA_DIR')
if configured_data_dir:
    data_dir = configured_data_dir
elif getattr(sys, 'frozen', False):
    # Program Files is read-only for standard users. Keep runtime data in
    # the per-user directory when the packaged application is installed.
    data_dir = os.path.join(
        os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
        'PrintShopApp',
        'data',
    )
else:
    data_dir = os.path.join(application_dir, 'data')
os.makedirs(data_dir, exist_ok=True)
os.chdir(application_dir)

def migrate_storage_file(filename):
    """Copy a legacy root-level file into the unified data directory once."""
    old_path = os.path.join(application_dir, filename)
    new_path = os.path.join(data_dir, filename)
    if os.path.exists(old_path) and not os.path.exists(new_path):
        shutil.copy2(old_path, new_path)


migrate_storage_file('wifi_approval_settings.ini')
migrate_storage_file('wifi_hotspot.log')

resource_linkbox_path = os.path.join(resource_dir, "LinkBox")
resource_linkshare_path = os.path.join(resource_dir, "LinkShare")
linkbox_path = resource_linkbox_path
linkshare_path = data_dir
database_dir = os.path.join(data_dir, "db")
wifi_approval_db_path = os.path.join(database_dir, "wifi_approval.db")
os.makedirs(database_dir, exist_ok=True)
legacy_db_path = os.path.join(data_dir, "LinkShare", "db", "wifi_approval.db")
if not os.path.exists(legacy_db_path):
    legacy_db_path = os.path.join(application_dir, "LinkShare", "db", "wifi_approval.db")
if not os.path.exists(wifi_approval_db_path) and os.path.exists(legacy_db_path):
    shutil.copy2(legacy_db_path, wifi_approval_db_path)
app_database = AppDatabase(wifi_approval_db_path)
approval_sound_dir = os.path.join(data_dir, "approval_sounds")
os.makedirs(approval_sound_dir, exist_ok=True)
legacy_data_linkshare = os.path.join(application_dir, "LinkShare")
for folder_name, target_path in (
    ("approval_sounds", approval_sound_dir),
    ("fare", os.path.join(data_dir, "fare")),
):
    source_path = os.path.join(legacy_data_linkshare, folder_name)
    if os.path.isdir(source_path):
        os.makedirs(target_path, exist_ok=True)
        for filename in os.listdir(source_path):
            source_file = os.path.join(source_path, filename)
            target_file = os.path.join(target_path, filename)
            if os.path.isfile(source_file) and not os.path.exists(target_file):
                shutil.copy2(source_file, target_file)
sys.path.append(resource_linkbox_path)
sys.path.append(resource_linkshare_path)

import ui_layout

# --- Configuration & Path Setup ---
SETTINGS_FILE = os.path.join(data_dir, "wifi_approval_settings.ini")


def get_writable_log_file(filename):
    """Return a log path that the current Windows user can write to."""
    preferred_path = os.path.join(data_dir, filename)
    try:
        os.makedirs(os.path.dirname(preferred_path), exist_ok=True)
        with open(preferred_path, 'a', encoding='utf-8'):
            pass
        return preferred_path
    except OSError:
        # Installed applications commonly live under C:\\Program Files,
        # which is not writable by standard users. Use the per-user data
        # directory for logs instead of requiring administrator privileges.
        user_data_dir = os.path.join(
            os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
            'PrintShopApp',
            'data',
        )
        os.makedirs(user_data_dir, exist_ok=True)
        return os.path.join(user_data_dir, filename)


WIFI_LOG_FILE = get_writable_log_file("wifi_hotspot.log")
wifi_logger = logging.getLogger("printshop.wifi")
if not wifi_logger.handlers:
    wifi_logger.setLevel(logging.INFO)
    wifi_handler = logging.FileHandler(WIFI_LOG_FILE, encoding='utf-8')
    wifi_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    wifi_logger.addHandler(wifi_handler)
DEFAULT_UPLOAD_FOLDER = os.path.join(data_dir, "LinkBox_Files")
os.makedirs(DEFAULT_UPLOAD_FOLDER, exist_ok=True)


def format_size(size_bytes):
    """Format a received file size for the file-transfer table."""
    if size_bytes < 1024:
        return f"{size_bytes} Bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def clean_transfer_folder(target_folder, records):
    """Remove non-summary files that do not match the persisted transfer log."""
    if not os.path.isdir(target_folder):
        return
    expected = {
        (str(record.get('filename', '')), str(record.get('size', '')))
        for record in records
        if record.get('filename')
    }
    for name in os.listdir(target_folder):
        if name.startswith('summary_') or name == 'transfer_summary.txt':
            continue
        path = os.path.join(target_folder, name)
        if not os.path.isfile(path):
            continue
        actual = (name, format_size(os.path.getsize(path)))
        if actual not in expected:
            try:
                os.remove(path)
                logging.getLogger(__name__).warning(
                    'Removed unmatched transfer file: %s', path
                )
            except OSError:
                logging.getLogger(__name__).exception(
                    'Failed to remove unmatched transfer file: %s', path
                )


def safe_folder_part(value, fallback='Unknown'):
    """Make a user-controlled value safe and readable in a Windows path."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '').strip())
    cleaned = cleaned.rstrip('. ')
    return cleaned[:80] or fallback

DEFAULT_ZONES = ["Counter", "Table01", "Table02", "VIP_Room"]
DEFAULT_SAVE_TABS = ["DefaultTab"]
DEFAULT_ACTIVE_MAIN_TAB = "file_receiver"
DEFAULT_HOTSPOT_SSID = "hbwifi"
DEFAULT_HOTSPOT_PASSWORD = "hbwifihb"
DEFAULT_HOTSPOT_NETWORK = "192.168.137.0/24"
DEFAULT_HOTSPOT_GATEWAY = "192.168.137.1"
DEFAULT_MAX_CONNECTIONS = 250
DEFAULT_WINDOWS_HOTSPOT_LIMIT = 8
DEFAULT_STATUS_POLL_INTERVAL = 60.0
DEFAULT_EXPIRATION_CHECK_INTERVAL = 60
DEFAULT_FILE_TRANSFER_MINUTES = 10
DEFAULT_INTERNET_FARES = [
    {'minutes': 30, 'price': 5}, {'minutes': 60, 'price': 10},
    {'minutes': 90, 'price': 15}, {'minutes': 120, 'price': 20},
    {'minutes': 180, 'price': 30}, {'minutes': 240, 'price': 40},
    {'minutes': 480, 'price': 80},
]
DEFAULT_COLOR_OPTIONS = ['Color', 'B&W']
DEFAULT_APPROVAL_SOUND_ENABLED = True
DEFAULT_APPROVAL_SOUNDS = ['', '', '', '', '']
DEFAULT_QR_OUTPUT_FORMAT = 'PDF'
DEFAULT_QR_OUTPUT_SCALE = 1
DEFAULT_QR_OUTPUT_DIR = os.path.join(data_dir, 'qr_output')
os.makedirs(DEFAULT_QR_OUTPUT_DIR, exist_ok=True)
WINDOWS_HOTSPOT_LIMIT_MAX = 128

# --- Encryption Key Management (LinkShare)[cite: 4] ---
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

# --- Hotspot Settings Load & Save ---
def load_hotspot_setting():
    config = configparser.ConfigParser()
    ssid = DEFAULT_HOTSPOT_SSID
    if os.path.exists(SETTINGS_FILE):
        try:
            config.read(SETTINGS_FILE, encoding='utf-8')
            if config.has_section('Settings') and config.has_option('Settings', 'hotspot_ssid'):
                saved_ssid = config.get('Settings', 'hotspot_ssid').strip()
                if saved_ssid:
                    ssid = saved_ssid
        except Exception as e:
            print(f"Hotspot config load error: {e}")
    return ssid

def save_hotspot_setting(ssid):
    config = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE, encoding='utf-8')
    if not config.has_section('Settings'):
        config.add_section('Settings')
    config.set('Settings', 'hotspot_ssid', ssid)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        config.write(f)


def load_app_settings():
    """Load all integrated-app settings while preserving unknown INI values."""
    config = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE, encoding='utf-8')

    zones = DEFAULT_ZONES.copy()
    save_tabs = DEFAULT_SAVE_TABS.copy()
    if config.has_section('Storage'):
        zones = [value.strip() for value in config.get('Storage', 'zones', fallback='').split(',') if value.strip()] or zones
        save_tabs = [value.strip() for value in config.get('Storage', 'save_tabs', fallback='').split(',') if value.strip()] or save_tabs

    try:
        max_connections = max(1, config.getint('Settings', 'max_connections', fallback=DEFAULT_MAX_CONNECTIONS))
    except ValueError:
        max_connections = DEFAULT_MAX_CONNECTIONS
    try:
        windows_hotspot_limit = max(
            1,
            min(
                WINDOWS_HOTSPOT_LIMIT_MAX,
                config.getint('Settings', 'windows_hotspot_limit', fallback=DEFAULT_WINDOWS_HOTSPOT_LIMIT),
            ),
        )
    except ValueError:
        windows_hotspot_limit = DEFAULT_WINDOWS_HOTSPOT_LIMIT
    try:
        status_poll_interval = max(
            0.5,
            min(60.0, config.getfloat('Settings', 'status_poll_interval', fallback=DEFAULT_STATUS_POLL_INTERVAL)),
        )
    except ValueError:
        status_poll_interval = DEFAULT_STATUS_POLL_INTERVAL
    try:
        expiration_check_interval = max(30, min(300, config.getint(
            'Settings', 'expiration_check_interval', fallback=DEFAULT_EXPIRATION_CHECK_INTERVAL
        )))
    except ValueError:
        expiration_check_interval = DEFAULT_EXPIRATION_CHECK_INTERVAL
    try:
        file_transfer_minutes = max(5, min(15, config.getint(
            'Settings', 'file_transfer_minutes', fallback=DEFAULT_FILE_TRANSFER_MINUTES
        )))
    except ValueError:
        file_transfer_minutes = DEFAULT_FILE_TRANSFER_MINUTES
    try:
        internet_fares = json.loads(config.get('Settings', 'internet_fares', fallback=''))
        if not isinstance(internet_fares, list) or not internet_fares:
            internet_fares = DEFAULT_INTERNET_FARES
        internet_fares = [
            {'minutes': int(item['minutes']), 'price': float(item['price'])}
            for item in internet_fares if int(item['minutes']) > 0 and float(item['price']) >= 0
        ] or DEFAULT_INTERNET_FARES
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        internet_fares = DEFAULT_INTERNET_FARES
    try:
        color_options = [str(item).strip() for item in json.loads(
            config.get('Settings', 'color_options', fallback='["Color", "B&W"]')
        ) if str(item).strip()] or DEFAULT_COLOR_OPTIONS
    except (TypeError, ValueError, json.JSONDecodeError):
        color_options = DEFAULT_COLOR_OPTIONS
    approval_sounds = [
        config.get('Settings', f'approval_sound_{index}', fallback=DEFAULT_APPROVAL_SOUNDS[index - 1])
        for index in range(1, 6)
    ]
    qr_output_formats = {
        'network': config.get('Settings', 'network_qr_output_format', fallback=DEFAULT_QR_OUTPUT_FORMAT),
        'captive': config.get('Settings', 'captive_qr_output_format', fallback=DEFAULT_QR_OUTPUT_FORMAT),
    }
    qr_output_scales = {
        'network': config.getint('Settings', 'network_qr_output_scale', fallback=DEFAULT_QR_OUTPUT_SCALE),
        'captive': config.getint('Settings', 'captive_qr_output_scale', fallback=DEFAULT_QR_OUTPUT_SCALE),
    }
    qr_output_dirs = {
        'network': config.get('Settings', 'network_qr_output_dir', fallback=DEFAULT_QR_OUTPUT_DIR),
        'captive': config.get('Settings', 'captive_qr_output_dir', fallback=DEFAULT_QR_OUTPUT_DIR),
    }

    try:
        linkshare_splitter_sizes = json.loads(
            config.get('Settings', 'linkshare_splitter_sizes', fallback='[520, 260]')
        )
        if not isinstance(linkshare_splitter_sizes, list) or len(linkshare_splitter_sizes) != 2:
            raise ValueError
        linkshare_splitter_sizes = [max(100, int(size)) for size in linkshare_splitter_sizes]
    except (TypeError, ValueError, json.JSONDecodeError):
        linkshare_splitter_sizes = [520, 260]
    try:
        file_receiver_splitter_sizes = json.loads(
            config.get('Settings', 'file_receiver_splitter_sizes', fallback='[520, 420]')
        )
        if not isinstance(file_receiver_splitter_sizes, list) or len(file_receiver_splitter_sizes) != 2:
            raise ValueError
        file_receiver_splitter_sizes = [max(200, int(size)) for size in file_receiver_splitter_sizes]
    except (TypeError, ValueError, json.JSONDecodeError):
        file_receiver_splitter_sizes = [520, 420]
    try:
        main_splitter_sizes = json.loads(
            config.get('Settings', 'main_splitter_sizes', fallback='[520, 420]')
        )
        if not isinstance(main_splitter_sizes, list) or len(main_splitter_sizes) != 2:
            raise ValueError
        main_splitter_sizes = [max(200, int(size)) for size in main_splitter_sizes]
    except (TypeError, ValueError, json.JSONDecodeError):
        main_splitter_sizes = [520, 420]
    try:
        qr_location_splitter_sizes = json.loads(
            config.get('Settings', 'qr_location_splitter_sizes', fallback='[260, 520]')
        )
        if not isinstance(qr_location_splitter_sizes, list) or len(qr_location_splitter_sizes) != 2:
            raise ValueError
        qr_location_splitter_sizes = [max(180, int(size)) for size in qr_location_splitter_sizes]
    except (TypeError, ValueError, json.JSONDecodeError):
        qr_location_splitter_sizes = [260, 520]

    saved_ssid = config.get('Settings', 'hotspot_ssid', fallback=DEFAULT_HOTSPOT_SSID).strip()
    # Migrate the former built-in default without altering other user-defined SSIDs.
    if saved_ssid == 'hb_wifi':
        saved_ssid = DEFAULT_HOTSPOT_SSID
    return {
        'ssid': saved_ssid,
        'hotspot_password': config.get('Settings', 'hotspot_password', fallback=DEFAULT_HOTSPOT_PASSWORD),
        'hotspot_password_user_set': config.getboolean(
            'Settings', 'hotspot_password_user_set', fallback=False
        ),
        'hotspot_image': config.get('Settings', 'hotspot_image', fallback=''),
        'fare_dir': config.get('Settings', 'fare_dir', fallback=os.path.join(linkshare_path, 'fare')),
        'max_connections': max_connections,
        'windows_hotspot_limit': windows_hotspot_limit,
        'status_poll_interval': status_poll_interval,
        'expiration_check_interval': expiration_check_interval,
        'file_transfer_minutes': file_transfer_minutes,
        'provide_internet_for_file_transfer': config.getboolean(
            'Settings', 'provide_internet_for_file_transfer', fallback=True
        ),
        'internet_fares': internet_fares,
        'color_options': color_options,
        'approval_sound_enabled': config.getboolean(
            'Settings', 'approval_sound_enabled', fallback=DEFAULT_APPROVAL_SOUND_ENABLED
        ),
        'approval_sounds': approval_sounds,
        'qr_output_formats': qr_output_formats,
        'qr_output_scales': qr_output_scales,
        'qr_output_dirs': qr_output_dirs,
        'upload_folder': config.get('Storage', 'upload_folder', fallback=DEFAULT_UPLOAD_FOLDER),
        'zones': zones,
        'save_tabs': save_tabs,
        'active_main_tab': config.get('Storage', 'active_main_tab', fallback=DEFAULT_ACTIVE_MAIN_TAB),
        'internet_nic': config.get('Network', 'internet_nic', fallback=''),
        'internet_ip': config.get('Network', 'internet_ip', fallback=''),
        'hotspot_nic': config.get('Network', 'hotspot_nic', fallback=''),
        'hotspot_ip': config.get('Network', 'hotspot_ip', fallback=''),
        'hotspot_network': config.get('Network', 'hotspot_network', fallback=DEFAULT_HOTSPOT_NETWORK),
        'hotspot_gateway': config.get('Network', 'hotspot_gateway', fallback=DEFAULT_HOTSPOT_GATEWAY),
        'linkshare_splitter_sizes': linkshare_splitter_sizes,
        'file_receiver_splitter_sizes': file_receiver_splitter_sizes,
        'main_splitter_sizes': main_splitter_sizes,
        'qr_location_splitter_sizes': qr_location_splitter_sizes,
        'startup_enabled': config.getboolean('Settings', 'startup_enabled', fallback=False),
    }


def save_app_settings(settings):
    """Persist integrated-app settings without replacing the Fernet security key."""
    config = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE, encoding='utf-8')

    for section in ('Settings', 'Network', 'Storage'):
        if not config.has_section(section):
            config.add_section(section)

    config.set('Settings', 'hotspot_ssid', settings.get('ssid', DEFAULT_HOTSPOT_SSID))
    config.set('Settings', 'startup_enabled', str(bool(settings.get('startup_enabled', False))))
    config.set('Settings', 'hotspot_password', settings.get('hotspot_password', DEFAULT_HOTSPOT_PASSWORD))
    config.set(
        'Settings', 'hotspot_password_user_set',
        str(bool(settings.get('hotspot_password_user_set', False)))
    )
    config.set('Settings', 'hotspot_image', settings.get('hotspot_image', ''))
    config.set('Settings', 'fare_dir', settings.get('fare_dir', os.path.join(linkshare_path, 'fare')))
    config.set('Settings', 'max_connections', str(max(1, int(settings.get('max_connections', DEFAULT_MAX_CONNECTIONS)))))
    config.set(
        'Settings',
        'windows_hotspot_limit',
        str(max(1, min(WINDOWS_HOTSPOT_LIMIT_MAX, int(settings.get('windows_hotspot_limit', DEFAULT_WINDOWS_HOTSPOT_LIMIT))))),
    )
    config.set('Settings', 'status_poll_interval', str(max(
        0.5, min(60.0, float(settings.get('status_poll_interval', DEFAULT_STATUS_POLL_INTERVAL)))
    )))
    config.set('Settings', 'expiration_check_interval', str(max(
        30, min(300, int(settings.get('expiration_check_interval', DEFAULT_EXPIRATION_CHECK_INTERVAL)))
    )))
    config.set('Settings', 'file_transfer_minutes', str(max(
        5, min(15, int(settings.get('file_transfer_minutes', DEFAULT_FILE_TRANSFER_MINUTES)))
    )))
    config.set('Settings', 'provide_internet_for_file_transfer', str(bool(
        settings.get('provide_internet_for_file_transfer', True)
    )))
    config.set('Settings', 'internet_fares', json.dumps(
        settings.get('internet_fares', DEFAULT_INTERNET_FARES), ensure_ascii=False
    ))
    color_options = [str(item).strip() for item in settings.get('color_options', DEFAULT_COLOR_OPTIONS) if str(item).strip()]
    config.set('Settings', 'color_options', json.dumps(color_options or DEFAULT_COLOR_OPTIONS, ensure_ascii=False))
    config.set('Settings', 'approval_sound_enabled', str(bool(
        settings.get('approval_sound_enabled', DEFAULT_APPROVAL_SOUND_ENABLED)
    )))
    approval_sounds = settings.get('approval_sounds', DEFAULT_APPROVAL_SOUNDS)
    for index in range(1, 6):
        config.set('Settings', f'approval_sound_{index}', str(
            approval_sounds[index - 1] if index - 1 < len(approval_sounds) else ''
        ))
    qr_formats = settings.get('qr_output_formats', {})
    qr_scales = settings.get('qr_output_scales', {})
    qr_dirs = settings.get('qr_output_dirs', {})
    for qr_type in ('network', 'captive'):
        output_format = qr_formats.get(qr_type, DEFAULT_QR_OUTPUT_FORMAT)
        if output_format not in ('JPG', 'BMP', 'PDF'):
            output_format = DEFAULT_QR_OUTPUT_FORMAT
        output_scale = max(1, min(4, int(qr_scales.get(qr_type, DEFAULT_QR_OUTPUT_SCALE))))
        config.set('Settings', f'{qr_type}_qr_output_format', output_format)
        config.set('Settings', f'{qr_type}_qr_output_scale', str(output_scale))
        config.set('Settings', f'{qr_type}_qr_output_dir', qr_dirs.get(qr_type, DEFAULT_QR_OUTPUT_DIR))
    splitter_sizes = settings.get('linkshare_splitter_sizes', [520, 260])
    config.set('Settings', 'linkshare_splitter_sizes', json.dumps([int(size) for size in splitter_sizes]))
    file_receiver_splitter_sizes = settings.get('file_receiver_splitter_sizes', [520, 420])
    config.set('Settings', 'file_receiver_splitter_sizes', json.dumps(
        [max(200, int(size)) for size in file_receiver_splitter_sizes]
    ))
    main_splitter_sizes = settings.get('main_splitter_sizes', [520, 420])
    config.set('Settings', 'main_splitter_sizes', json.dumps(
        [max(200, int(size)) for size in main_splitter_sizes]
    ))
    qr_location_splitter_sizes = settings.get('qr_location_splitter_sizes', [260, 520])
    config.set('Settings', 'qr_location_splitter_sizes', json.dumps(
        [max(180, int(size)) for size in qr_location_splitter_sizes]
    ))
    config.set('Network', 'internet_nic', settings.get('internet_nic', ''))
    config.set('Network', 'internet_ip', settings.get('internet_ip', ''))
    config.set('Network', 'hotspot_nic', settings.get('hotspot_nic', ''))
    config.set('Network', 'hotspot_ip', settings.get('hotspot_ip', ''))
    config.set('Network', 'hotspot_network', settings.get('hotspot_network', DEFAULT_HOTSPOT_NETWORK))
    config.set('Network', 'hotspot_gateway', settings.get('hotspot_gateway', DEFAULT_HOTSPOT_GATEWAY))
    config.set('Storage', 'upload_folder', settings.get('upload_folder', DEFAULT_UPLOAD_FOLDER))
    config.set('Storage', 'zones', ','.join(settings.get('zones', DEFAULT_ZONES)))
    config.set('Storage', 'save_tabs', ','.join(settings.get('save_tabs', DEFAULT_SAVE_TABS)))
    active_main_tab = settings.get('active_main_tab', DEFAULT_ACTIVE_MAIN_TAB)
    if active_main_tab not in ('file_receiver', 'wifi_pass'):
        active_main_tab = DEFAULT_ACTIVE_MAIN_TAB
    config.set('Storage', 'active_main_tab', active_main_tab)

    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        config.write(f)


def normalize_hotspot_network(network, gateway):
    """Validate the hotspot IPv4 CIDR and gateway, falling back to Windows' usual range."""
    try:
        parsed_network = ipaddress.ip_network(network, strict=False)
        parsed_gateway = ipaddress.ip_address(gateway)
        if parsed_network.version != 4 or parsed_network.prefixlen > 30 or parsed_gateway not in parsed_network:
            raise ValueError
        return str(parsed_network), str(parsed_gateway)
    except ValueError:
        return DEFAULT_HOTSPOT_NETWORK, DEFAULT_HOTSPOT_GATEWAY


def escape_wifi_qr_field(value):
    """Escape a value according to the Wi-Fi QR code payload format."""
    return (
        str(value)
        .replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace(':', '\\:')
    )

# --- Mobile Hotspot Auto-Start ---
def enable_mobile_hotspot(ssid_name="hbwifi"):
    try:
        # Opening the Settings URI is only a fallback prompt.  Do not wait for
        # the Settings app from the application startup thread.
        os.startfile('ms-settings:network-mobilehotspot')
        print(f"Hotspot activated / configuration opened for SSID: {ssid_name}")
    except Exception as e:
        print(f"Hotspot execution error: {e}")


def get_current_hotspot_wifi_info():
    """Read the current Windows Mobile Hotspot SSID and passphrase via WinRT."""
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
    except Exception:
        return {'ssid': '', 'passphrase': ''}


def get_current_hotspot_ssid():
    """Read the SSID currently configured for Windows Mobile Hotspot via WinRT."""
    return get_current_hotspot_wifi_info()['ssid']


def set_current_hotspot_ssid(ssid, password=None):
    """Apply the program-defined SSID and optional password via Windows WinRT."""
    try:
        import asyncio
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            return False, 'No active Internet connection profile was found'
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        access_point = manager.get_current_access_point_configuration()
        previous_ssid = (access_point.ssid or '').strip()
        access_point.ssid = ssid
        if password:
            access_point.passphrase = password

        async def configure():
            await manager.configure_access_point_async(access_point)

        asyncio.run(configure())
        verified = get_current_hotspot_wifi_info()
        verified_ssid = verified.get('ssid', '').strip()
        verified_password = verified.get('passphrase', '').strip()
        if verified_ssid != ssid or (password and verified_password != password):
            return False, (
                "Windows did not retain the requested hotspot credentials; "
                f"actual SSID='{verified_ssid}', password verification failed"
            )
        return True, f"Hotspot credentials updated for '{ssid}'"
    except Exception as exc:
        return False, f"Hotspot SSID change failed: {exc}"


def get_windows_hotspot_client_limits():
    """Read the actual Windows Mobile Hotspot client count and OS limit."""
    try:
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            return None, None, 'No active Internet connection profile was found'
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        return int(manager.client_count), int(manager.max_client_count), ''
    except Exception as exc:
        return None, None, f'Windows hotspot limit unavailable: {exc}'


def get_windows_hotspot_registry_limit():
    """Read the optional, unofficial Windows ICS peer limit registry value."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SYSTEM\CurrentControlSet\Services\icssvc\Settings',
            0,
            winreg.KEY_READ,
        ) as key:
            value, value_type = winreg.QueryValueEx(key, 'WifiMaxPeers')
            if value_type != winreg.REG_DWORD:
                return None
            return int(value)
    except (FileNotFoundError, OSError):
        return None


def apply_windows_hotspot_registry_limit(limit):
    """Write the unofficial WifiMaxPeers value; requires an elevated process."""
    try:
        import winreg

        limit = int(limit)
        if not 1 <= limit <= WINDOWS_HOTSPOT_LIMIT_MAX:
            return False, f'Windows hotspot limit must be between 1 and {WINDOWS_HOTSPOT_LIMIT_MAX}.'
        with winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            r'SYSTEM\CurrentControlSet\Services\icssvc\Settings',
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, 'WifiMaxPeers', 0, winreg.REG_DWORD, limit)
        return True, f'WifiMaxPeers set to {limit}'
    except PermissionError:
        return False, 'Administrator permission is required. Restart PrintShopApp as Administrator and try again.'
    except OSError as exc:
        return False, f'Windows registry update failed: {exc}'


def run_hotspot_diagnostics(hotspot_nic, hotspot_network, hotspot_gateway):
    """Inspect the selected adapter and report whether the hotspot range is active."""
    network, gateway = normalize_hotspot_network(hotspot_network, hotspot_gateway)
    selected_name = hotspot_nic.get('display', '')
    adapter_name = selected_name.rsplit(' (', 1)[0] if ' (' in selected_name else selected_name
    stats = psutil.net_if_stats().get(adapter_name)
    addresses = psutil.net_if_addrs().get(adapter_name, [])
    ipv4_addresses = [addr.address for addr in addresses if addr.family == socket.AF_INET]

    lines = [f"Selected adapter: {adapter_name or 'Not selected'}", f"Expected range: {network}", f"Expected gateway: {gateway}"]

    client_count, max_client_count, limit_error = get_windows_hotspot_client_limits()
    if max_client_count is not None:
        lines.append(f"Windows Mobile Hotspot clients: {client_count} of {max_client_count}")
        lines.append("Windows client limit: read-only through the supported WinRT API")
    else:
        lines.append(limit_error)

    gateway_adapter = None
    gateway_adapter_ips = []
    for candidate_name, candidate_addrs in psutil.net_if_addrs().items():
        candidate_ipv4 = [addr.address for addr in candidate_addrs if addr.family == socket.AF_INET]
        if gateway in candidate_ipv4:
            gateway_adapter = candidate_name
            gateway_adapter_ips = candidate_ipv4
            break

    if gateway_adapter:
        gateway_stats = psutil.net_if_stats().get(gateway_adapter)
        lines.append(f"Hotspot gateway adapter: {gateway_adapter}")
        lines.append(f"Gateway adapter status: {'UP' if gateway_stats and gateway_stats.isup else 'DOWN'}")
        lines.append(f"Gateway adapter IPv4: {', '.join(gateway_adapter_ips)}")
        lines.append("Hotspot status: ON / gateway is assigned")
        return {'active': bool(gateway_stats and gateway_stats.isup), 'text': '\n'.join(lines)}

    if not stats:
        lines.append("Adapter status: NOT FOUND")
        lines.append("Hotspot status: OFF / adapter unavailable")
        return {'active': False, 'text': '\n'.join(lines)}

    lines.append(f"Adapter status: {'UP' if stats.isup else 'DOWN'}")
    lines.append(f"IPv4 addresses: {', '.join(ipv4_addresses) if ipv4_addresses else 'none'}")
    in_range = any(ipaddress.ip_address(address) in ipaddress.ip_network(network) for address in ipv4_addresses)
    gateway_assigned = gateway in ipv4_addresses
    active = bool(stats.isup and gateway_assigned)
    if active:
        lines.append("Hotspot status: ON / gateway is assigned")
    elif stats.isup and in_range:
        lines.append("Hotspot status: PARTIAL / adapter is up but gateway differs")
    elif stats.isup:
        lines.append("Hotspot status: READY / adapter is up, hotspot IP not assigned")
    else:
        lines.append("Hotspot status: OFF / adapter is down")
    return {'active': active, 'text': '\n'.join(lines)}


def set_hotspot_enabled(enabled, ssid_name):
    """Control modern Windows tethering, with legacy netsh as a fallback."""
    try:
        import asyncio
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            raise RuntimeError("No active Internet connection profile was found")
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)

        async def control_tethering():
            return await (
                manager.start_tethering_async() if enabled
                else manager.stop_tethering_async()
            )

        # WinRT can leave the tethering future pending when Mobile Hotspot is
        # unavailable.  Do not block application startup indefinitely; use
        # the legacy/settings fallback after a short bounded wait.
        result = asyncio.run(asyncio.wait_for(control_tethering(), timeout=8))
        # WinRT returns a NetworkOperatorTetheringOperationResult object.
        # Its useful status is exposed as a property; converting the object
        # itself to str() only produces a memory address and looks like a
        # failure even when the operation succeeded.
        status_value = getattr(result, 'status', None)
        if status_value is None:
            status_value = getattr(result, 'operation_status', None)
        status = str(status_value if status_value is not None else result)
        status_name = getattr(status_value, 'name', status).lower()
        normalized_status = status_name.replace('_', '').replace(' ', '')
        if any(
            token in normalized_status
            for token in ('success', 'alreadyon', 'alreadyoff')
        ):
            action_text = 'started' if enabled else 'stopped'
            return True, f"Windows mobile hotspot {action_text} ({status})"
        modern_message = f"Windows tethering returned {status}"
    except (asyncio.TimeoutError, asyncio.CancelledError, KeyboardInterrupt) as exc:
        modern_message = f"WinRT tethering timed out or was cancelled: {exc}"
    except Exception as exc:
        modern_message = f"WinRT tethering unavailable: {exc}"

    action = 'start' if enabled else 'stop'
    try:
        result = subprocess.run(
            ['netsh', 'wlan', action, 'hostednetwork'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10
        )
        output = (result.stdout or result.stderr).strip()
        if enabled and result.returncode == 0:
            enable_mobile_hotspot(ssid_name)
        if result.returncode == 0:
            return True, output or f"netsh hostednetwork {action} completed"
        if enabled:
            enable_mobile_hotspot(ssid_name)
        return False, f"{modern_message}\nLegacy netsh: {output or 'command failed'}"
    except (OSError, subprocess.SubprocessError) as exc:
        if enabled:
            enable_mobile_hotspot(ssid_name)
        return False, f"{modern_message}\nLegacy netsh: {exc}"


def log_wifi(message, level=logging.INFO):
    wifi_logger.log(level, message)

# --- NIC Auto-Search & Internet Tested Priority[cite: 2] ---
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

def is_wireless_interface(name):
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in ('wi-fi', 'wifi', 'wireless', 'wlan', '802.11'))


def get_network_interfaces():
    """Return (display name, IPv4, internet reachable, wireless) NIC entries."""
    interfaces = []
    try:
        for nic_name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ip = addr.address
                    is_connected = check_internet_via_ip(ip)
                    interfaces.append((f"{nic_name} ({ip})", ip, is_connected, is_wireless_interface(nic_name)))
    except Exception:
        pass
    
    if not interfaces:
        interfaces.append(("Default (192.168.137.1)", "192.168.137.1", False, True))
    
    def nic_priority(item):
        display_name, ip, connected, wireless = item
        name_lower = display_name.lower()
        ping_score = 0 if connected else 1
        wifi_score = 0 if wireless else 1
        return (ping_score, wifi_score)

    interfaces.sort(key=nic_priority)
    return interfaces


def choose_preferred_interface(interfaces, saved_display='', saved_ip='', wireless_only=False):
    """Choose a saved NIC when available, otherwise the best matching NIC."""
    candidates = [item for item in interfaces if not wireless_only or item[3]] or interfaces
    for item in candidates:
        if item[0] == saved_display or item[1] == saved_ip:
            return item
    if wireless_only:
        return candidates[0] if candidates else ("Default (192.168.137.1)", "192.168.137.1", False, True)
    return candidates[0] if candidates else ("Default (192.168.137.1)", "192.168.137.1", False, True)

# --- Integrated Flask Web Server[cite: 3, 4] ---
web_app = Flask(__name__, template_folder=os.path.join(resource_linkshare_path, 'templates'))
shared_sessions = {}
client_identity_map = {}
client_metadata_map = {}
session_identity_lock = threading.RLock()
usage_history = []
status_condition = threading.Condition()
runtime_settings = {
    'max_connections': DEFAULT_MAX_CONNECTIONS,
    'internet_fares': DEFAULT_INTERNET_FARES,
    'color_options': DEFAULT_COLOR_OPTIONS,
}
_upstream_dns_cache = {'timestamp': 0.0, 'servers': []}
CLIENT_COOKIE_NAME = 'printshop_client_token'
def get_client_identity():
    """Identify a portal user across reconnects without relying on a changing IP.

    The browser cookie is the primary identifier.  The IP remains a transport
    detail and is refreshed on every request.  Device name is only a friendly
    label supplied by the browser; it is not treated as a security identity.
    """
    token = request.cookies.get(CLIENT_COOKIE_NAME)
    if not token or len(token) > 256:
        token = secrets.token_urlsafe(24)
    token_id = hashlib.sha256(token.encode('utf-8')).hexdigest()
    client_ip = request.remote_addr or '-'
    with session_identity_lock:
        previous_ip = client_identity_map.get(token_id)
        if not previous_ip:
            for candidate_ip, candidate in shared_sessions.items():
                if candidate.get('client_token_id') == token_id:
                    previous_ip = candidate_ip
                    break
        if previous_ip and previous_ip != client_ip and previous_ip in shared_sessions:
            session = shared_sessions.pop(previous_ip)
            existing = shared_sessions.get(client_ip)
            if existing and existing.get('client_token_id') == token_id:
                # Prefer the newer record while preserving the active timer.
                if str(session.get('last_seen', '')) > str(existing.get('last_seen', '')):
                    existing.update(session)
                existing['client_ip'] = client_ip
            else:
                session['client_ip'] = client_ip
                shared_sessions[client_ip] = session
        client_identity_map[token_id] = client_ip
    user_agent = (request.headers.get('User-Agent') or '').strip()[:500]
    if 'Android' in user_agent:
        device_type, operating_system = 'Mobile', 'Android'
    elif any(item in user_agent for item in ('iPhone', 'iPad', 'iPod')):
        device_type, operating_system = 'Mobile', 'iOS'
    elif 'Windows' in user_agent:
        device_type, operating_system = 'PC', 'Windows'
    elif 'Mac OS X' in user_agent:
        device_type, operating_system = 'PC', 'macOS'
    else:
        device_type, operating_system = 'Unknown', 'Unknown'
    if 'Edg/' in user_agent:
        browser = 'Edge'
    elif 'Chrome/' in user_agent:
        browser = 'Chrome'
    elif 'Safari/' in user_agent and 'Chrome/' not in user_agent:
        browser = 'Safari'
    elif 'Firefox/' in user_agent:
        browser = 'Firefox'
    else:
        browser = 'Unknown'
    client_metadata_map[token_id] = {
        'user_name': (request.headers.get('X-Client-Name') or '').strip()[:80],
        'device_name': (request.headers.get('X-Client-Device') or '').strip()[:120],
        'device_type': device_type,
        'operating_system': operating_system,
        'browser': browser,
        'user_agent': user_agent,
        'accept_language': (request.headers.get('Accept-Language') or '').strip()[:120],
        'screen_size': (request.headers.get('X-Client-Screen') or '').strip()[:40],
        'timezone': (request.headers.get('X-Client-Timezone') or '').strip()[:80],
        'last_seen': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    device_name = client_metadata_map[token_id]['device_name']
    return token, token_id, client_ip, device_name


def identity_response(payload, token):
    response = make_response(payload)
    response.set_cookie(CLIENT_COOKIE_NAME, token, max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite='Lax')
    return response


def apply_client_metadata(session, token_id):
    """Copy browser-supplied automatic metadata into the persisted session record."""
    metadata = client_metadata_map.get(token_id, {})
    for key, value in metadata.items():
        if value:
            session[key] = value
    session.setdefault('first_seen', metadata.get('last_seen', ''))
    session['last_seen'] = metadata.get('last_seen', session.get('last_seen', ''))


def append_usage_log(log_type, session, **overrides):
    """Append an immutable request/approval event to the usage history."""
    record = dict(session)
    record.update(overrides)
    record['log_type'] = log_type
    usage_history.append(record)
    try:
        app_database.save_event(record)
        app_database.save_session(session)
    except (OSError, sqlite3.Error):
        pass


def get_record_price(record):
    """Return the price fixed at approval time, with a legacy fare fallback."""
    value = record.get('approved_price')
    if value is None:
        value = record.get('requested_price')
    try:
        if value is not None and float(value) > 0:
            return float(value)
    except (TypeError, ValueError):
        pass
    match = re.search(r'\(([0-9]+(?:\.[0-9]+)?)\s*PHP\)', str(record.get('fare', '')))
    return float(match.group(1)) if match else 0.0


def is_client_internet_approved(client_ip):
    """Return whether a client currently has an active approved session."""
    session = shared_sessions.get(client_ip)
    if not session or session.get('status') != 'Approved':
        return False
    end_timestamp = session.get('end_timestamp', 0)
    if end_timestamp and end_timestamp <= datetime.datetime.now().timestamp():
        session['status'] = 'Expired'
        session['connection_status'] = 'Closed'
        session['remaining_seconds'] = 0
        return False
    return True


def get_upstream_dns_servers():
    """Read Windows' configured IPv4 DNS servers, with public fallbacks."""
    fallback_servers = ['1.1.1.1', '8.8.8.8']
    now = time.monotonic()
    if now - _upstream_dns_cache['timestamp'] < 30 and _upstream_dns_cache['servers']:
        return list(_upstream_dns_cache['servers'])
    try:
        command = (
            "(Get-DnsClientServerAddress -AddressFamily IPv4).ServerAddresses "
            "| ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=2,
        )
        values = json.loads((result.stdout or '').strip())
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            configured = []
            for value in values:
                try:
                    address = str(ipaddress.ip_address(value))
                except ValueError:
                    continue
                if address != '0.0.0.0' and address not in configured:
                    configured.append(address)
            if configured:
                _upstream_dns_cache.update(timestamp=now, servers=configured)
                return configured
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        pass
    _upstream_dns_cache.update(timestamp=now, servers=fallback_servers)
    return fallback_servers


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
        # 승인된 사용자의 OS 연결성 확인(NCSI/Captive Portal probe)은
        # 사용신청 화면으로 다시 보내면 Wi-Fi에 느낌표가 표시된다.
        # 주요 Windows/Android/Apple probe에는 정상 응답을 반환한다.
        if is_client_internet_approved(self.client_address[0]):
            host = (self.headers.get('Host') or '').lower().split(':', 1)[0]
            probe_hosts = {
                'www.msftconnecttest.com', 'www.msftncsi.com',
                'connectivitycheck.gstatic.com', 'clients3.google.com',
                'connectivitycheck.android.com', 'captive.apple.com',
            }
            if host in probe_hosts:
                if host in {'www.msftconnecttest.com', 'www.msftncsi.com'}:
                    body = b'Microsoft Connect Test'
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(204)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                return
        self.send_response(302)
        self.send_header('Location', self.portal_url)
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_HEAD = do_GET

    def log_message(self, format_string, *args):
        return


class CaptivePortalDNSHandler(socketserver.BaseRequestHandler):
    """Redirect unapproved DNS and forward approved DNS to the real resolver."""

    def handle(self):
        query, udp_socket = self.request
        client_address = self.client_address
        if len(query) < 12:
            return
        try:
            if is_client_internet_approved(client_address[0]):
                for upstream in get_upstream_dns_servers():
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as resolver:
                            resolver.settimeout(1.5)
                            resolver.sendto(query, (upstream, 53))
                            response, _ = resolver.recvfrom(4096)
                        udp_socket.sendto(response, client_address)
                        return
                    except (OSError, socket.timeout):
                        continue

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
            udp_socket.sendto(response, client_address)
        except (IndexError, OSError, ValueError):
            return


class CaptivePortalDNSServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True

    def __init__(self, server_address, gateway):
        self.gateway = gateway
        super().__init__(server_address, CaptivePortalDNSHandler)

class ServerSignals(QObject):
    approval_requested = Signal(str, int, str)
    transfer_updated = Signal(str, str, int, str)

signals = ServerSignals()
file_transfer_callback = None
transfer_records_by_client = {}
transfer_records_lock = threading.RLock()
transfer_change_versions = {}
transfer_ack_versions = {}
transfer_change_condition = threading.Condition(transfer_records_lock)
processed_uploads = {}

@web_app.route('/')
def portal_root():
    return redirect('/scan')

@web_app.route('/scan')
def customer_scan():
    token, token_id, client_ip, device_name = get_client_identity()
    response = make_response(render_template(
        'portal.html',
        status_poll_interval=runtime_settings.get('status_poll_interval', DEFAULT_STATUS_POLL_INTERVAL),
        internet_fares=runtime_settings.get('internet_fares', DEFAULT_INTERNET_FARES),
    ))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.set_cookie(CLIENT_COOKIE_NAME, token, max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite='Lax')
    return response

@web_app.route('/manifest.webmanifest')
def app_manifest():
    return Response(json.dumps({
        'name': 'Internet Access Request',
        'short_name': 'Access Request',
        'start_url': '/scan',
        'display': 'standalone',
        'background_color': '#f3f6f8',
        'theme_color': '#1565c0',
        'icons': [
            {'src': '/app-icon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any maskable'},
        ],
    }, ensure_ascii=False), mimetype='application/manifest+json')

@web_app.route('/app-icon.svg')
@web_app.route('/favicon.ico')
def app_icon():
    return Response('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
      <rect width="512" height="512" rx="96" fill="#1565c0"/>
      <path d="M128 176h256v160H128z" fill="#fff"/>
      <path d="M176 144c64-64 96-64 160 0M208 112c40-40 56-40 96 0" fill="none" stroke="#fff" stroke-width="24" stroke-linecap="round"/>
      <circle cx="256" cy="256" r="28" fill="#1565c0"/>
    </svg>''', mimetype='image/svg+xml')

@web_app.route('/file_share')
def file_share_page():
    zone = request.args.get('zone', 'Default')
    return render_template(
        'file_share.html', zone=zone,
        color_options=runtime_settings.get('color_options', DEFAULT_COLOR_OPTIONS)
    )


@web_app.route('/upload', methods=['POST'])
def file_share_upload():
    zone = request.args.get('zone', 'Default')
    files = [item for item in request.files.getlist('file') if item and item.filename]
    if not files:
        return {'error': 'No files selected'}, 400
    try:
        requested_copies = json.loads(request.form.get('copies', '[]'))
        if not isinstance(requested_copies, list):
            requested_copies = []
    except (TypeError, ValueError, json.JSONDecodeError):
        requested_copies = []
    try:
        requested_colors = json.loads(request.form.get('colors', '[]'))
        if not isinstance(requested_colors, list):
            requested_colors = []
    except (TypeError, ValueError, json.JSONDecodeError):
        requested_colors = []
    token, token_id, client_ip, device_name = get_client_identity()
    upload_id = (request.headers.get('X-Upload-Id') or '').strip()[:100]
    if upload_id:
        with transfer_records_lock:
            previous = processed_uploads.get((token_id, upload_id))
        if previous is not None:
            response = make_response(previous['payload'], previous['status'])
            response.set_cookie(CLIENT_COOKIE_NAME, token, max_age=60 * 60 * 24 * 30,
                                httponly=True, samesite='Lax')
            return response
    metadata = client_metadata_map.get(token_id, {})
    user_name = metadata.get('user_name', '').strip() or device_name or 'Guest'
    user_info = ' / '.join(filter(None, [
        metadata.get('device_type'), metadata.get('operating_system'),
        metadata.get('browser'), metadata.get('device_name'),
    ])) or 'Unknown'
    cookie_id = token_id[:12]
    transfer_id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    safe_zone = safe_folder_part(zone, 'Default')
    safe_user = safe_folder_part(user_name, 'Guest')
    safe_ip = safe_folder_part(client_ip, 'UnknownIP')
    safe_identity = re.sub(r'[^A-Za-z0-9_.-]', '_', token_id or client_ip)
    target_folder = os.path.join(
        DEFAULT_UPLOAD_FOLDER,
        f'{safe_zone}_{safe_user}_{safe_ip}_{transfer_id}'
    )
    os.makedirs(target_folder, exist_ok=True)
    received = []
    client_transfer_records = []
    failed_count = 0
    for index, uploaded in enumerate(files):
        try:
            copy_count = max(0, min(999, int(requested_copies[index])))
        except (IndexError, TypeError, ValueError):
            copy_count = 1
        color_value = str(requested_colors[index]).strip() if index < len(requested_colors) else DEFAULT_COLOR_OPTIONS[0]
        if color_value not in runtime_settings.get('color_options', DEFAULT_COLOR_OPTIONS):
            color_value = DEFAULT_COLOR_OPTIONS[0]
        filename = os.path.basename(uploaded.filename)
        path = os.path.join(target_folder, filename)
        try:
            uploaded.save(path)
            file_size = format_size(os.path.getsize(path))
        except OSError:
            failed_count += 1
            continue
        received.append((user_name, user_info, cookie_id, zone, filename, copy_count,
                         file_size,
                         datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
                         'Completed (100%)', color_value))
        client_transfer_records.append({
            'folder': target_folder,
            'filename': filename,
            'copies': copy_count,
            'user_name': user_name,
            'user_info': user_info,
            'cookie': cookie_id,
            'zone': zone,
            'size': file_size,
            'received_time': datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
            'status': 'Completed (100%)',
            'color': color_value,
            'task_completed': False,
        })
    with transfer_records_lock:
        transfer_records_by_client.setdefault(token_id, []).extend(client_transfer_records)
        transfer_change_versions[token_id] = transfer_change_versions.get(token_id, 0) + 1
        transfer_change_condition.notify_all()
    if file_transfer_callback:
        file_transfer_callback(received, target_folder, safe_identity)
    response_status = 200 if received else 500
    response = make_response({'ok': bool(received), 'count': len(received),
                              'failed_count': failed_count, 'folder': target_folder,
                              'records': client_transfer_records,
                              'error': 'All files failed to upload' if not received else ''}, response_status)
    if upload_id:
        with transfer_records_lock:
            processed_uploads[(token_id, upload_id)] = {
                'payload': response.get_json(), 'status': response_status
            }
    response.set_cookie(CLIENT_COOKIE_NAME, token, max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite='Lax')
    return response


@web_app.route('/transfer_status')
def transfer_status():
    _token, token_id, _client_ip, _device_name = get_client_identity()
    try:
        since = int(request.args.get('since', 0))
    except (TypeError, ValueError):
        since = 0
    with transfer_change_condition:
        # After a server restart, restore this client's persisted transfer
        # list before answering the QR page's long-poll request.
        if not transfer_records_by_client.get(token_id):
            persisted = app_database.load_transfer_logs_for_identity(
                re.sub(r'[^A-Za-z0-9_.-]', '_', token_id or _client_ip)
            )
            restored = []
            for folder, records in persisted.items():
                for record in records:
                    restored.append({
                        'folder': folder,
                        'filename': record.get('filename', ''),
                        'copies': record.get('copies') if record.get('copies') is not None else 1,
                        'user_name': record.get('user_name', 'Guest'),
                        'user_info': record.get('user_info', 'Unknown'),
                        'cookie': record.get('cookie', token_id[:12]),
                        'zone': record.get('zone', 'Default'),
                        'size': record.get('size', ''),
                        'received_time': record.get('received_time', ''),
                        'status': record.get('status', 'Completed (100%)'),
                        'color': record.get('color', DEFAULT_COLOR_OPTIONS[0]),
                        'task_completed': bool(record.get('task_completed', False)),
                    })
            if restored:
                transfer_records_by_client[token_id] = restored
                transfer_change_versions[token_id] = max(
                    transfer_change_versions.get(token_id, 0), 1
                )
        version = transfer_change_versions.get(token_id, 0)
        if version <= since:
            transfer_change_condition.wait(timeout=25)
        version = transfer_change_versions.get(token_id, 0)
        # The QR screen represents files that can actually be downloaded or
        # acted on. Keep historical records in the admin DB, but do not sync
        # records whose physical file has been removed or moved.
        records = [
            dict(record)
            for record in transfer_records_by_client.get(token_id, [])
            if not str(record.get('filename', '')).startswith('summary_')
            and str(record.get('filename', '')) != 'transfer_summary.txt'
            and os.path.isfile(os.path.join(
                str(record.get('folder', '')), str(record.get('filename', ''))
            ))
            and (
                not record.get('size')
                or format_size(os.path.getsize(os.path.join(
                    str(record.get('folder', '')), str(record.get('filename', ''))
                ))) == str(record.get('size'))
            )
        ]
    response = make_response({'version': version, 'changed': version != since, 'records': records})
    response.set_cookie(CLIENT_COOKIE_NAME, _token, max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite='Lax')
    return response


@web_app.route('/transfer_ack', methods=['POST'])
def transfer_ack():
    _token, token_id, _client_ip, _device_name = get_client_identity()
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get('version', 0))
    except (TypeError, ValueError):
        version = 0
    with transfer_records_lock:
        transfer_ack_versions[token_id] = max(transfer_ack_versions.get(token_id, 0), version)
    return {'ok': True, 'version': transfer_ack_versions[token_id]}


@web_app.route('/transfer_update', methods=['POST'])
def transfer_update():
    _token, token_id, _client_ip, _device_name = get_client_identity()
    payload = request.get_json(silent=True) or {}
    filename = str(payload.get('filename', ''))
    folder = str(payload.get('folder', ''))
    try:
        copies = max(0, min(999, int(payload.get('copies', 1))))
    except (TypeError, ValueError):
        copies = 1
    color = str(payload.get('color', '')).strip()
    if color not in runtime_settings.get('color_options', DEFAULT_COLOR_OPTIONS):
        color = DEFAULT_COLOR_OPTIONS[0]
    with transfer_change_condition:
        updated = False
        for record in transfer_records_by_client.get(token_id, []):
            if record.get('folder') == folder and record.get('filename') == filename:
                record['copies'] = copies
                record['color'] = color
                updated = True
        if updated:
            app_database.update_transfer_log(folder, filename, copies=copies, color=color)
            transfer_update_event = (folder, filename, copies, color)
            transfer_change_versions[token_id] = transfer_change_versions.get(token_id, 0) + 1
            transfer_change_condition.notify_all()
        else:
            transfer_update_event = None
    if transfer_update_event:
        signals.transfer_updated.emit(*transfer_update_event)
    return {'ok': updated}

@web_app.route('/request')
def customer_request():
    fare_map = {int(item['minutes']): item for item in runtime_settings.get('internet_fares', DEFAULT_INTERNET_FARES)}
    allowed_minutes = set(fare_map)
    try:
        minutes = int(request.args.get('min', 60))
    except (TypeError, ValueError):
        return {'msg': 'Invalid usage time.'}, 400
    if minutes not in allowed_minutes:
        return {'msg': 'Select one of the available usage times.'}, 400

    token, token_id, client_ip, device_name = get_client_identity()
    fare = fare_map[minutes]['price']
    dur_str = f"{minutes} Min Pass ({fare:g} PHP)" if minutes < 60 else f"{minutes//60} Hour Pass ({fare:g} PHP)"
    existing_session = shared_sessions.get(client_ip)
    if existing_session:
        existing_status = get_client_session(client_ip).get('status')
        if existing_status == 'Approved':
            if existing_session.get('extension_pending'):
                return {
                    'status': 'Pending',
                    'msg': 'Your additional usage request is waiting for approval.',
                    'session': get_client_session(client_ip),
                }
            existing_session.update({
                'extension_pending': True,
                'extension_minutes': minutes,
                'extension_fare': dur_str,
                'extension_price': fare,
                'extension_request_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            })
            append_usage_log(
                'request',
                existing_session,
                status='Pending',
                requested_minutes=minutes,
                fare=dur_str,
                usage_request=dur_str,
                usage_approval='-',
                request_time=existing_session['extension_request_time'],
                approval_time='-',
                start_time='-',
                end_time='-',
            )
            threading.Thread(
                target=signals.approval_requested.emit,
                args=(client_ip, minutes, dur_str),
                daemon=True,
            ).start()
            return {
                'status': 'Pending',
                'msg': f"[{dur_str}] Additional usage request sent for approval.",
                'session': get_client_session(client_ip),
            }
        if existing_status == 'Pending':
            return {
                'status': 'Pending',
                'msg': 'Your previous request is waiting for approval.',
                'session': get_client_session(client_ip),
            }

    active_statuses = {'Pending', 'Approved'}
    active_count = sum(
        1 for session in shared_sessions.values()
        if session.get('status') in active_statuses
    )
    existing_session = shared_sessions.get(client_ip)
    if existing_session is None and active_count >= runtime_settings['max_connections']:
        return {
            'msg': 'Maximum connection limit reached. Please try again later.',
            'status': 'Full',
            'current': active_count,
            'maximum': runtime_settings['max_connections'],
        }, 429

    session_record = {
        'status': 'Pending',
        'requested_minutes': minutes,
        'requested_price': fare,
        'approved_price': None,
        'fare': dur_str,
        'client_ip': client_ip,
        'client_token_id': token_id,
        'device_name': device_name or 'Unknown Device',
        'last_seen': datetime.datetime.now().isoformat(timespec='seconds'),
        'connection_status': '연결됨',
        'usage_request': dur_str,
        'usage_approval': 'Pending Approval',
        'request_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'approval_time': '-',
        'start_time': '-',
        'end_time': '-',
        'internet_status': 'Checking',
        'total_used_seconds': 0,
    }
    apply_client_metadata(session_record, token_id)
    shared_sessions[client_ip] = session_record
    append_usage_log('request', session_record)
    threading.Thread(
        target=signals.approval_requested.emit,
        args=(client_ip, minutes, dur_str),
        daemon=True,
    ).start()
    return {
        'status': 'Pending',
        'msg': f"[{dur_str}] Approval request sent. Please pay at the counter.",
        'session': get_client_session(client_ip),
    }


def get_client_session(client_ip):
    """Return a browser-safe, current snapshot of one client session."""
    session = shared_sessions.get(client_ip)
    if not session:
        return {'status': 'None'}

    snapshot = dict(session)
    if snapshot.get('status') == 'Approved':
        remaining = max(0, int(snapshot.get('end_timestamp', 0) - datetime.datetime.now().timestamp()))
        snapshot['remaining_seconds'] = remaining
        if remaining == 0:
            snapshot['status'] = 'Expired'
            session['status'] = 'Expired'
    snapshot.pop('end_timestamp', None)
    return snapshot


def notify_status_change():
    with status_condition:
        status_condition.notify_all()


def session_status_signature(session):
    return tuple(session.get(key) for key in (
        'status', 'approval_time', 'end_time', 'remaining_seconds', 'internet_status'
    ))


@web_app.route('/status')
def get_status():
    # 상태 전달 흐름:
    # - 화면 최초 진입과 상태확인 버튼은 일반 /status 요청으로 즉시 응답한다.
    # - 스마트폰 화면의 자동 조회는 /status?wait=1 대기 연결을 사용한다.
    # - 대기 연결은 승인/비승인/인터넷 연결 상태가 바뀔 때까지 서버에서 대기한다.
    # - 상태 변경 시 notify_status_change()가 모든 대기 연결을 즉시 깨워 새 상태를 전송한다.
    # - 브라우저가 숨겨지면 대기 연결을 만들지 않고, 다시 보이면 연결을 재개한다.
    wait_for_change = request.args.get('wait') == '1'
    token, token_id, client_ip, device_name = get_client_identity()
    session = shared_sessions.get(client_ip)
    if session:
        session['last_seen'] = datetime.datetime.now().isoformat(timespec='seconds')
        session['client_token_id'] = token_id
        apply_client_metadata(session, token_id)
        if device_name:
            session['device_name'] = device_name
    if wait_for_change:
        with status_condition:
            before = session_status_signature(shared_sessions.get(client_ip, {}))
            status_condition.wait_for(
                lambda: session_status_signature(shared_sessions.get(client_ip, {})) != before,
                timeout=30,
            )
    return identity_response(get_client_session(client_ip), token)

@web_app.route('/internet-status', methods=['GET', 'POST'])
def report_internet_status():
    # 사용자 브라우저의 실제 인터넷 연결 확인 결과를 관리자 앱 세션에 기록한다.
    # 기록 즉시 대기 중인 /status?wait=1 연결을 깨워 관리자 화면에 반영한다.
    token, token_id, client_ip, device_name = get_client_identity()
    session = shared_sessions.get(client_ip)
    if not session:
        return identity_response({'status': 'None'}, token), 404
    session['last_seen'] = datetime.datetime.now().isoformat(timespec='seconds')
    session['client_token_id'] = token_id
    apply_client_metadata(session, token_id)
    if device_name:
        session['device_name'] = device_name
    payload = request.get_json(silent=True) or {}
    if request.method == 'GET':
        payload = request.args.to_dict()
        if payload.get('browser_online') is not None:
            payload['browser_online'] = payload['browser_online'].lower() == 'true'
        if payload.get('internet_check'):
            try:
                payload['internet_check'] = json.loads(payload['internet_check'])
            except (TypeError, json.JSONDecodeError):
                payload['internet_check'] = {'raw': str(payload['internet_check'])[:200]}
    internet_status = payload.get('internet_status')
    if isinstance(payload.get('internet_check'), dict):
        session['internet_check'] = dict(payload['internet_check'])
    if 'browser_online' in payload:
        session['browser_online'] = bool(payload['browser_online'])
    if payload.get('checked_at'):
        session['internet_checked_at'] = str(payload['checked_at'])[:80]
    if payload.get('test_result'):
        session['internet_test_result'] = str(payload['test_result'])[:20]
    try:
        app_database.save_session(session)
    except (OSError, sqlite3.Error):
        pass
    if internet_status in ('Checking', 'Available', 'Check failed', '확인 중', '사용 가능', '확인 실패'):
        if session.get('internet_status') != internet_status:
            session['internet_status'] = internet_status
            notify_status_change()
    return {'status': session.get('internet_status', 'Checking')}

# --- Integrated Settings Dialog ---
class IntegratedSettingsDialog(QDialog):
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
        root_layout.addWidget(settings_tabs)
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)
        category_layouts = {}
        for tab_title, tab_description in (("Hotspot", "Hotspot SSID, client count, IP range, and gateway settings"), ("Network", "Internet connection and hotspot adapter settings"), ("Storage/Display", "Image and log storage settings"), ("Tables/Zones", "Table and service zone settings")):
            category_tab = QWidget()
            category_layout = QVBoxLayout(category_tab)
            category_layouts[tab_title] = category_layout
            settings_tabs.addTab(category_tab, tab_title)
        settings_tabs.addTab(general_tab, "General")
        
        layout.addWidget(QLabel("<b>📶 Hotspot SSID (Name):</b>"))
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

        layout.addWidget(QLabel("<b>🔒 Hotspot password:</b>"))
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

        layout.addWidget(QLabel("<b>Hotspot IPv4 range (CIDR):</b>"))
        self.hotspot_network_input = QLineEdit(current_hotspot_network)
        self.hotspot_network_input.setPlaceholderText("192.168.137.0/24")
        layout.addWidget(self.hotspot_network_input)

        layout.addWidget(QLabel("<b>Hotspot gateway IP:</b>"))
        self.hotspot_gateway_input = QLineEdit(current_hotspot_gateway)
        self.hotspot_gateway_input.setPlaceholderText("192.168.137.1")
        layout.addWidget(self.hotspot_gateway_input)

        layout.addWidget(QLabel("<b>Internet NIC (internet line):</b>"))
        self.internet_nic_combo = QComboBox()
        self.populate_nic_combo(self.internet_nic_combo, interfaces, current_internet_nic, wireless_only=False)
        layout.addWidget(self.internet_nic_combo)

        layout.addWidget(QLabel("<b>Hotspot NIC (recommended wireless adapter):</b>"))
        self.hotspot_nic_combo = QComboBox()
        self.populate_nic_combo(self.hotspot_nic_combo, interfaces, current_hotspot_nic, wireless_only=True)
        layout.addWidget(self.hotspot_nic_combo)

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

        layout.addWidget(QLabel("<b>📁 Log Storage Folder Path:</b>"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(current_fare_dir)
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        layout.addWidget(QLabel("<b>📍 Configure Table / Zone List:</b>"))
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

        # Keep both adapter selectors together on the Network tab.
        # Item ranges: hotspot identity/limits/range (0:18), NICs (18:22),
        # image/log storage (22:26), and table/zone controls (26:).
        append_settings_items(category_layouts["Hotspot"], general_items[0:18])
        append_settings_items(category_layouts["Network"], general_items[18:22])
        append_settings_items(category_layouts["Storage/Display"], general_items[22:26])
        append_settings_items(category_layouts["Tables/Zones"], general_items[26:])
        for tab_title, category_layout in category_layouts.items():
            category_layout.insertWidget(0, QLabel(f"<h3>{tab_title} Settings</h3>"))
            category_layout.addStretch()

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
        self.sound_radio_group = QButtonGroup(self)
        self.sound_radio_group.setExclusive(True)
        self.sound_radios = []
        self.selected_sound_index = -1
        self.play_sound_button = QPushButton("▶ Play Sound")
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
        self.play_sound_button.setText(f"▶ {os.path.basename(path)}" if path else "▶ Play Sound")
        self.play_sound_button.setEnabled(bool(path and os.path.isfile(path)))

    def play_selected_approval_sound(self):
        index = self.selected_sound_index
        if not (0 <= index < len(self.sound_inputs)):
            return
        path = self.sound_inputs[index].text().strip()
        if winsound is not None and os.path.isfile(path):
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)

    def populate_nic_combo(self, combo, interfaces, selected, wireless_only):
        combo.clear()
        candidates = [item for item in interfaces if item[3]] if wireless_only else list(interfaces)
        candidates = candidates or list(interfaces)
        for display_name, ip, connected, wireless in candidates:
            combo.addItem(display_name, {'display': display_name, 'ip': ip})
            index = combo.count() - 1
            combo.setItemData(index, connected, Qt.UserRole + 1)
            combo.setItemData(index, QColor(0, 180, 0) if connected else QColor(220, 0, 0), Qt.ForegroundRole)
            if display_name == selected or ip == selected:
                combo.setCurrentIndex(index)

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
        return self.get_selected_nic(self.hotspot_nic_combo)

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

def is_running_as_administrator():
    """Return the actual Windows elevation state of this process."""
    if os.name != 'nt':
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


# --- Main Application Window ---
class IntegratedManagerApp(QMainWindow):
    file_signal = Signal(list, str, str)
    delete_signal = Signal(str, list)
    database_loaded = Signal(object, object, object)
    qr_export_completed = Signal(str, bool, str)

    def __init__(self):
        super().__init__()
        privilege_label = "Administrator privileges" if is_running_as_administrator() else "Standard privileges"
        self.setWindowTitle(f"PrintShop Integrated Manager (HTTPS) - {privilege_label}")

        app_settings = load_app_settings()
        detected_hotspot_info = get_current_hotspot_wifi_info()
        detected_hotspot_ssid = detected_hotspot_info['ssid']
        self.hotspot_ssid = app_settings.get('ssid', DEFAULT_HOTSPOT_SSID) or DEFAULT_HOTSPOT_SSID
        configured_password = app_settings.get('hotspot_password', '').strip()
        self.hotspot_password_user_set = bool(
            app_settings.get('hotspot_password_user_set', False)
            or (configured_password and configured_password != DEFAULT_HOTSPOT_PASSWORD)
        )
        detected_password = detected_hotspot_info['passphrase'].strip()
        # Keep an existing Windows hotspot password when the stored value is
        # only the built-in default. This prevents an unchanged setting from
        # replacing the actual password on every restart.
        if detected_password and not self.hotspot_password_user_set:
            self.hotspot_password = detected_password
        else:
            self.hotspot_password = configured_password or detected_password or DEFAULT_HOTSPOT_PASSWORD
        self.hotspot_ssid_sync_message = ''
        self.fare_base_dir = app_settings['fare_dir']
        self.hotspot_image_path = app_settings['hotspot_image']
        self.hotspot_network, self.hotspot_gateway = normalize_hotspot_network(
            app_settings['hotspot_network'], app_settings['hotspot_gateway']
        )
        self.linkshare_splitter_sizes = app_settings.get('linkshare_splitter_sizes', [520, 260])
        self.file_receiver_splitter_sizes = app_settings.get('file_receiver_splitter_sizes', [520, 420])
        self.main_splitter_sizes = app_settings.get('main_splitter_sizes', [520, 420])
        self.qr_location_splitter_sizes = app_settings.get('qr_location_splitter_sizes', [260, 520])
        self.max_connections = app_settings['max_connections']
        self.status_poll_interval = app_settings.get('status_poll_interval', DEFAULT_STATUS_POLL_INTERVAL)
        self.expiration_check_interval = app_settings.get(
            'expiration_check_interval', DEFAULT_EXPIRATION_CHECK_INTERVAL
        )
        self.windows_hotspot_limit = app_settings['windows_hotspot_limit']
        self.startup_enabled = app_settings.get('startup_enabled', False)
        self.file_transfer_minutes = app_settings.get('file_transfer_minutes', DEFAULT_FILE_TRANSFER_MINUTES)
        self.provide_internet_for_file_transfer = app_settings.get(
            'provide_internet_for_file_transfer', True
        )
        self.approval_sound_enabled = app_settings.get('approval_sound_enabled', DEFAULT_APPROVAL_SOUND_ENABLED)
        self.approval_sounds = app_settings.get('approval_sounds', DEFAULT_APPROVAL_SOUNDS)
        self.approval_sound_index = 0
        self.approval_sound_playback_timer = None
        self.qr_output_formats = app_settings.get('qr_output_formats', {
            'network': DEFAULT_QR_OUTPUT_FORMAT,
            'captive': DEFAULT_QR_OUTPUT_FORMAT,
        })
        self.qr_output_scales = app_settings.get('qr_output_scales', {
            'network': DEFAULT_QR_OUTPUT_SCALE,
            'captive': DEFAULT_QR_OUTPUT_SCALE,
        })
        self.qr_output_dirs = app_settings.get('qr_output_dirs', {
            'network': DEFAULT_QR_OUTPUT_DIR,
            'captive': DEFAULT_QR_OUTPUT_DIR,
        })
        runtime_settings['max_connections'] = self.max_connections
        runtime_settings['status_poll_interval'] = self.status_poll_interval
        runtime_settings['internet_fares'] = app_settings.get('internet_fares', DEFAULT_INTERNET_FARES)
        self.color_options = app_settings.get('color_options', DEFAULT_COLOR_OPTIONS)
        runtime_settings['color_options'] = self.color_options
        self.internet_nic = {'display': app_settings['internet_nic'], 'ip': app_settings['internet_ip']}
        self.hotspot_nic = {'display': app_settings['hotspot_nic'], 'ip': app_settings['hotspot_ip']}
        self.load_saved_defaults(app_settings)

        interfaces = get_network_interfaces()
        self.interfaces = interfaces
        internet_interface = choose_preferred_interface(
            interfaces, self.internet_nic['display'], self.internet_nic['ip'], wireless_only=False
        )
        hotspot_interface = choose_preferred_interface(
            interfaces, self.hotspot_nic['display'], self.hotspot_nic['ip'], wireless_only=True
        )
        self.internet_nic = {'display': internet_interface[0], 'ip': internet_interface[1]}
        self.hotspot_nic = {'display': hotspot_interface[0], 'ip': hotspot_interface[1]}

        self.initialize_hotspot_state()
        
        ui_layout.setup_integrated_ui(
            self, DEFAULT_UPLOAD_FOLDER, DEFAULT_ZONES, DEFAULT_SAVE_TABS, interfaces,
            self.hotspot_ssid, self.internet_nic, self.hotspot_nic, self.hotspot_image_path,
            self.hotspot_network, self.hotspot_gateway, self.max_connections,
            app_settings.get('active_main_tab', DEFAULT_ACTIVE_MAIN_TAB)
        )

        self.tab_tables = {}
        self.tab_widget.currentChanged.connect(self.inspect_selected_transfer_tab)
        self.pending_batch_files = []
        self.last_target_folder = ""
        
        self.batch_timer = QTimer()
        self.batch_timer.setSingleShot(True)
        self.batch_timer.setInterval(300)
        self.batch_timer.timeout.connect(self.show_batch_notification)

        self.connection_timer = QTimer(self)
        self.connection_timer.setInterval(self.expiration_check_interval * 1000)
        self.connection_timer.timeout.connect(self.update_connection_summary)
        self.connection_timer.start()

        self.usage_history_timer = QTimer(self)
        self.usage_history_timer.setInterval(1000)
        self.usage_history_timer.timeout.connect(self.update_selected_usage_history)
        self.usage_history_timer.start()

        self.database_loaded.connect(self.apply_database_state, Qt.QueuedConnection)
        self.qr_export_completed.connect(self.handle_qr_export_completed, Qt.QueuedConnection)
        threading.Thread(target=self.load_database_state, daemon=True).start()

        self.resize(1150, 750)
        self.update_connection_summary()
        self.update_qr_code()

        self.file_signal.connect(self.handle_incoming_files)
        self.delete_signal.connect(self.handle_deleted_files)
        # Forward Flask worker-thread uploads through Qt so the GUI log is
        # updated safely on the GUI thread.
        global file_transfer_callback
        file_transfer_callback = self.file_signal.emit
        # HTTP /request 응답을 승인 팝업의 exec()가 붙잡지 않도록
        # 승인 처리는 GUI 이벤트 큐에서 비동기로 실행한다.
        signals.approval_requested.connect(self.handle_customer_request, Qt.QueuedConnection)
        signals.transfer_updated.connect(self.handle_remote_transfer_update, Qt.QueuedConnection)

        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()
        self.captive_portal_servers = []
        self.captive_portal_retry_count = 0
        self.start_captive_portal()
        self.persist_settings()
        # Windows Mobile Hotspot reports start success before the adapter and
        # gateway are ready. Diagnose again after the asynchronous startup settles.
        QTimer.singleShot(4000, self.diagnose_hotspot)

    def load_database_state(self):
        """Load persisted sessions/history off the GUI thread so startup remains responsive."""
        sessions, history = app_database.load()
        self.database_loaded.emit(sessions, history, app_database.load_transfer_logs())

    @Slot(object, object)
    def apply_database_state(self, sessions, history, transfer_logs):
        with session_identity_lock:
            for client_ip, session in sessions.items():
                token_id = session.get('client_token_id')
                if token_id:
                    duplicate_ip = next(
                        (ip for ip, current in shared_sessions.items()
                         if current.get('client_token_id') == token_id and ip != client_ip),
                        None,
                    )
                    if duplicate_ip:
                        current = shared_sessions.pop(duplicate_ip)
                        if str(current.get('last_seen', '')) > str(session.get('last_seen', '')):
                            session.update(current)
                shared_sessions[client_ip] = session
        usage_history.extend(history)
        for (target_folder, identity), records in transfer_logs.items():
            # Keep the DB record visible even when the physical file is gone;
            # the row is marked as missing below. User synchronization applies
            # the stricter physical-file check separately.
            if records:
                file_list = [(
                    record.get('user_name', 'Guest'), record.get('user_info', 'Unknown'),
                    record.get('cookie', ''), record.get('zone', 'Default'),
                    record.get('filename', ''),
                    record.get('copies') if record.get('copies') is not None else 1,
                    record.get('size', ''), record.get('received_time', ''),
                    record.get('status', 'Completed (100%)'), record.get('color', DEFAULT_COLOR_OPTIONS[0])
                ) for record in records]
                self.handle_incoming_files(file_list, target_folder, identity, persist=False)
                table = next((candidate for candidate in self.tab_tables.values()
                              if any(candidate.item(row, 3) and
                                     str(candidate.item(row, 3).data(Qt.UserRole) or '') == target_folder
                                     for row in range(candidate.rowCount()))), None)
                if table is not None:
                    for record in records:
                        for row in range(table.rowCount()):
                            item = table.item(row, 3)
                            if item and item.text() == record.get('filename', '') and \
                                    str(item.data(Qt.UserRole) or '') == target_folder:
                                self.set_file_task_completed(table, row, record.get('task_completed', False))
        for client_ip, session in sessions.items():
            token_id = session.get('client_token_id')
            if token_id:
                client_identity_map[token_id] = client_ip
        self.update_connection_summary()

    def load_saved_defaults(self, app_settings):
        global DEFAULT_UPLOAD_FOLDER, DEFAULT_ZONES, DEFAULT_SAVE_TABS
        DEFAULT_UPLOAD_FOLDER = app_settings['upload_folder'] or DEFAULT_UPLOAD_FOLDER
        DEFAULT_ZONES = app_settings['zones'] or DEFAULT_ZONES
        DEFAULT_SAVE_TABS = app_settings['save_tabs'] or DEFAULT_SAVE_TABS
        os.makedirs(DEFAULT_UPLOAD_FOLDER, exist_ok=True)

    def initialize_hotspot_state(self):
        """Check each hotspot requirement and change only mismatched stages."""
        log_wifi('Hotspot startup check started.')

        # Stage 1: SSID. Keep the configured hotspot when it already matches.
        current_info = get_current_hotspot_wifi_info()
        current_ssid = current_info.get('ssid', '').strip()
        log_wifi(f"SSID check: current='{current_ssid}', expected='{self.hotspot_ssid}'.")
        current_password = current_info.get('passphrase', '').strip()
        if current_ssid == self.hotspot_ssid and current_password == self.hotspot_password:
            log_wifi('SSID and password already match; no hotspot credential change required.')
        else:
            changed, message = set_current_hotspot_ssid(self.hotspot_ssid, self.hotspot_password)
            log_wifi(f"SSID configuration result: changed={changed}, {message}", logging.INFO if changed else logging.ERROR)
            if changed and not self.hotspot_password_user_set:
                self.hotspot_password = get_current_hotspot_wifi_info().get('passphrase', self.hotspot_password)

        # Stage 2: tethering and gateway state.
        diagnostics = run_hotspot_diagnostics(
            self.hotspot_nic, self.hotspot_network, self.hotspot_gateway
        )
        log_wifi(f"Hotspot active check: {diagnostics['active']}. {diagnostics['text'].replace(chr(10), ' | ')}")
        if diagnostics['active']:
            log_wifi('Hotspot is already active; keeping current hotspot running.')
        else:
            started, message = set_hotspot_enabled(True, self.hotspot_ssid)
            log_wifi(f"Hotspot enable result: started={started}, {message}", logging.INFO if started else logging.ERROR)

        # Stage 3: persist the final selected NIC/network/gateway values.
        log_wifi(
            f"Network settings registered: NIC='{self.hotspot_nic.get('display', '')}', "
            f"IP='{self.hotspot_nic.get('ip', '')}', network='{self.hotspot_network}', gateway='{self.hotspot_gateway}'."
        )
        log_wifi('Hotspot startup check completed.')

    def run_server(self):
        socketserver.TCPServer.allow_reuse_address = True
        web_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

    def start_captive_portal(self):
        """Start gateway-bound DNS and HTTP redirect services for hotspot clients."""
        portal_url = f"http://{self.hotspot_gateway}:5000/scan"
        CaptivePortalRedirectHandler.portal_url = portal_url
        messages = []

        try:
            http_server = http.server.ThreadingHTTPServer(
                (self.hotspot_gateway, 80), CaptivePortalRedirectHandler
            )
            threading.Thread(target=http_server.serve_forever, daemon=True).start()
            self.captive_portal_servers.append(http_server)
            messages.append('HTTP redirect ON (port 80)')
        except OSError as exc:
            messages.append(f'HTTP redirect unavailable: {exc}')

        try:
            dns_server = CaptivePortalDNSServer((self.hotspot_gateway, 53), self.hotspot_gateway)
            threading.Thread(target=dns_server.serve_forever, daemon=True).start()
            self.captive_portal_servers.append(dns_server)
            messages.append('DNS redirect ON (port 53)')
        except OSError as exc:
            messages.append(f'DNS redirect unavailable: {exc}')

        if hasattr(self, 'captive_portal_status_label'):
            self.captive_portal_status_label.setText('Captive Portal: ' + ' | '.join(messages))
        # Windows may need several seconds to assign 192.168.137.1 after
        # tethering starts.  Keep retrying while that adapter comes up so the
        # captive-portal redirect is available to the first connected client.
        if not self.captive_portal_servers and self.captive_portal_retry_count < 10:
            self.captive_portal_retry_count += 1
            QTimer.singleShot(3000, self.start_captive_portal)

    def stop_captive_portal(self):
        for server in getattr(self, 'captive_portal_servers', []):
            try:
                server.shutdown()
                server.server_close()
            except OSError:
                pass
        self.captive_portal_servers = []

    def open_settings_dialog(self):
        global DEFAULT_ZONES, DEFAULT_UPLOAD_FOLDER
        dialog = IntegratedSettingsDialog(
            DEFAULT_ZONES, self.fare_base_dir, self.hotspot_ssid, self.hotspot_password, self.interfaces,
            self.internet_nic['display'], self.hotspot_nic['display'], self.hotspot_image_path,
            self.hotspot_network, self.hotspot_gateway, self.max_connections,
            self.windows_hotspot_limit, self.approval_sound_enabled,
            self.approval_sounds, approval_sound_dir, self.startup_enabled,
            self.file_transfer_minutes, self.provide_internet_for_file_transfer,
            self.color_options, self
        )
        if dialog.exec() == QDialog.Accepted:
            DEFAULT_ZONES = dialog.zones
            previous_ssid = self.hotspot_ssid
            new_ssid = dialog.get_hotspot_ssid()
            new_password = dialog.get_hotspot_password()
            self.hotspot_ssid = new_ssid
            if new_ssid != previous_ssid or new_password != self.hotspot_password:
                changed, message = set_current_hotspot_ssid(new_ssid, new_password)
                log_wifi(f"SSID changed by settings: {message}")
                if not changed:
                    QMessageBox.warning(self, "SSID change failed", message)
                else:
                    self.hotspot_password = new_password
                    self.hotspot_password_user_set = True
            self.internet_nic = dialog.get_internet_nic()
            self.hotspot_nic = dialog.get_hotspot_nic()
            self.hotspot_image_path = dialog.get_hotspot_image()
            self.hotspot_network, self.hotspot_gateway = dialog.get_hotspot_network()
            self.max_connections = dialog.get_max_connections()
            self.windows_hotspot_limit = dialog.get_windows_hotspot_limit()
            self.approval_sound_enabled = dialog.get_approval_sound_enabled()
            self.approval_sounds = dialog.get_approval_sounds()
            self.startup_enabled = dialog.get_startup_enabled()
            (self.file_transfer_minutes,
             self.provide_internet_for_file_transfer) = dialog.get_file_transfer_settings()
            self.color_options = dialog.get_color_options()
            runtime_settings['color_options'] = self.color_options
            try:
                set_startup_registration(application_dir, self.startup_enabled)
            except (OSError, RuntimeError) as exc:
                QMessageBox.warning(self, "Startup registration failed", str(exc))
            runtime_settings['internet_fares'] = dialog.get_internet_fares()
            runtime_settings['max_connections'] = self.max_connections

            new_fare_path = dialog.get_fare_path()
            if new_fare_path:
                self.fare_base_dir = new_fare_path

            self.refresh_internet_nic()
            self.update_hotspot_info()
            self.update_connection_summary()
            self.diagnose_hotspot()
            self.persist_settings()
            QMessageBox.information(self, "Success", "Settings updated successfully.")
            self.update_zone_combo_items()
            self.update_zone_buttons()

    def refresh_internet_nic(self):
        self.nic_combo.blockSignals(True)
        self.nic_combo.clear()
        for display_name, ip, is_connected, is_wireless in self.interfaces:
            self.nic_combo.addItem(display_name, ip)
            index = self.nic_combo.count() - 1
            self.nic_combo.setItemData(index, is_connected, Qt.UserRole + 1)
            self.nic_combo.setItemData(index, QColor(0, 180, 0) if is_connected else QColor(220, 0, 0), Qt.ForegroundRole)
        index = self.nic_combo.findData(self.internet_nic['ip'])
        if index >= 0:
            self.nic_combo.setCurrentIndex(index)
        self.nic_combo.blockSignals(False)
        self.update_qr_code()

    def rescan_network_interfaces(self):
        """Rescan adapters, preserve saved choices when possible, and refresh the UI."""
        self.interfaces = get_network_interfaces()
        internet_interface = choose_preferred_interface(
            self.interfaces, self.internet_nic['display'], self.internet_nic['ip'], wireless_only=False
        )
        hotspot_interface = choose_preferred_interface(
            self.interfaces, self.hotspot_nic['display'], self.hotspot_nic['ip'], wireless_only=True
        )
        self.internet_nic = {'display': internet_interface[0], 'ip': internet_interface[1]}
        self.hotspot_nic = {'display': hotspot_interface[0], 'ip': hotspot_interface[1]}
        self.refresh_internet_nic()
        self.update_hotspot_info()
        self.persist_settings()

    def update_hotspot_info(self):
        if hasattr(self, 'hotspot_name_label'):
            self.hotspot_name_label.setText(
                f"• Active Hotspot Name: <b>{self.hotspot_ssid}</b> (Auto-started)"
            )
        if hasattr(self, 'hotspot_nic_label'):
            self.hotspot_nic_label.setText(f"• Hotspot NIC: <b>{self.hotspot_nic['display']}</b>")
        if hasattr(self, 'hotspot_network_label'):
            self.hotspot_network_label.setText(
                f"• Hotspot IP range: <b>{self.hotspot_network}</b> / gateway: <b>{self.hotspot_gateway}</b>"
            )
        if hasattr(self, 'hotspot_image_label'):
            if self.hotspot_image_path and os.path.exists(self.hotspot_image_path):
                pixmap = QPixmap(self.hotspot_image_path)
                if not pixmap.isNull():
                    self.hotspot_image_label.setPixmap(
                        pixmap.scaled(320, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    return
            self.hotspot_image_label.clear()

    def update_connection_summary(self):
        now_timestamp = datetime.datetime.now().timestamp()
        for session in shared_sessions.values():
            if session.get('status') == 'Approved':
                remaining = max(0, int(session.get('end_timestamp', 0) - now_timestamp))
                session['remaining_seconds'] = remaining
                if remaining == 0:
                    session['status'] = 'Expired'
                    session['connection_status'] = 'Closed'
                    session['remaining_seconds'] = 0
                    session['completed_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    append_usage_log('completed', session)
                    try:
                        app_database.save_session(session)
                    except (OSError, sqlite3.Error):
                        pass
                    notify_status_change()

        active_statuses = {'Pending', 'Approved'}
        active_count = sum(
            1 for session in shared_sessions.values()
            if session.get('status') in active_statuses
        )
        self.status_label.setText(
            f"Devices connected: {active_count} of {self.max_connections}"
        )
        client_count, max_client_count, error = get_windows_hotspot_client_limits()
        if hasattr(self, 'windows_hotspot_clients_label'):
            if max_client_count is not None:
                self.windows_hotspot_clients_label.setText(
                    f"Windows Mobile Hotspot: {client_count} of {max_client_count} "
                    "(actual Windows limit; read-only)"
                )
            else:
                self.windows_hotspot_clients_label.setText(error)
        self.update_usage_history_tables()

    def update_selected_usage_history(self):
        """Refresh the usage-history screen once per second only while selected."""
        if not hasattr(self, 'usage_history_tabs'):
            return
        if self.usage_history_tabs.currentIndex() == self.usage_history_tabs.count() - 1:
            self.update_usage_history_tables()

    def on_usage_history_tab_changed(self, _index):
        """Refresh the newly selected status/history tab immediately."""
        self.update_usage_history_tables()

    def refresh_all_views(self):
        """Refresh every manager view immediately (used by F5)."""
        self.update_connection_summary()
        self.update_usage_history_tables()
        self.update_save_tab_combo_items()
        self.update_zone_combo_items()
        self.diagnose_hotspot()
        self.update_qr_code()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F5:
            self.refresh_all_views()
            event.accept()
            return
        super().keyPressEvent(event)

    def update_usage_history_tables(self):
        if not hasattr(self, 'usage_history_tables'):
            return

        def deduplicate_events(records):
            unique = {}
            for record in records:
                identity = record.get('client_token_id') or f"ip:{record.get('client_ip', '-')}"
                event_key = (
                    identity,
                    record.get('log_type', ''),
                    record.get('request_time', ''),
                    record.get('approval_time', ''),
                    record.get('completed_time', ''),
                    record.get('requested_minutes', ''),
                    record.get('usage_approval', ''),
                )
                unique[event_key] = record
            return list(unique.values())

        request_records = deduplicate_events(
            [record for record in usage_history if record.get('log_type') == 'request']
        )
        approval_records = deduplicate_events(
            [record for record in usage_history if record.get('log_type') == 'approval']
        )

        table_records = {
            'Connection Status': (usage_history, [
                'connection_status', 'request_time', 'start_time', 'end_time', 'remaining', 'client_ip', 'client_token_id', 'user_info'
            ]),
            'Usage Requests': (request_records, [
                'usage_request', 'request_time', 'client_ip', 'client_token_id', 'user_info'
            ]),
            'Usage Approvals': (
                approval_records,
                ['usage_approval', 'approval_time', 'requested_time', 'client_ip', 'client_token_id', 'user_info']
            ),
        }
        history_records = list(reversed(deduplicate_events(usage_history)))
        if hasattr(self, 'usage_history_filter'):
            filter_name = self.usage_history_filter.currentText()
            today = datetime.date.today()
            start_text = self.usage_history_start.text().strip()
            end_text = self.usage_history_end.text().strip()
            def history_date(record):
                raw = (record.get('completed_time') or record.get('approval_time') or
                       record.get('request_time') or '')
                try:
                    return datetime.datetime.strptime(raw[:10], '%Y-%m-%d').date()
                except ValueError:
                    return None
            if filter_name in ('오늘', 'Today'):
                history_records = [r for r in history_records if history_date(r) == today]
            elif filter_name in ('이번 달', 'This month'):
                history_records = [r for r in history_records if history_date(r) and
                                   history_date(r).year == today.year and history_date(r).month == today.month]
            elif filter_name in ('기간', 'Custom'):
                try:
                    start_date = datetime.datetime.strptime(start_text, '%Y-%m-%d').date()
                    end_date = datetime.datetime.strptime(end_text, '%Y-%m-%d').date()
                    history_records = [r for r in history_records if history_date(r) and
                                       start_date <= history_date(r) <= end_date]
                except ValueError:
                    history_records = []
        table_records['Usage History'] = (history_records, [
            'log_type', 'status', 'request_time', 'approval_time', 'completed_time', 'client_ip'
        ])
        approved_history = [r for r in history_records if r.get('log_type') == 'approval' and
                            str(r.get('usage_approval', '')).startswith('Approved')]
        total_minutes = sum(int(r.get('requested_minutes', 0)) for r in approved_history)
        total_amount = sum(get_record_price(r) for r in approved_history)
        if hasattr(self, 'usage_history_total_label'):
            self.usage_history_total_label.setText(
                f'사용시간 누적: {total_minutes}분                         금액 누적: {total_amount:g} PHP'
            )
        table_records['Usage History'] = (approved_history, [
            'request_time', 'approval_time', 'requested_time', 'requested_price', 'client_token_id', 'user_info'
        ])
        connection_tab_name = next(iter(table_records))
        latest_by_client = {}
        requested_seconds_by_client = {}
        for record in usage_history:
            client_ip = record.get('client_ip', '-')
            identity_key = record.get('client_token_id') or f'ip:{client_ip}'
            previous = latest_by_client.get(identity_key)
            if previous is None or str(record.get('last_seen', record.get('request_time', ''))) >= str(
                previous.get('last_seen', previous.get('request_time', ''))
            ):
                latest_by_client[identity_key] = record
            if record.get('log_type') == 'request':
                requested_seconds_by_client[client_ip] = requested_seconds_by_client.get(client_ip, 0) + (
                    int(record.get('requested_minutes', 0)) * 60
                )
        for client_ip, session in shared_sessions.items():
            identity_key = session.get('client_token_id') or f'ip:{client_ip}'
            latest_by_client[identity_key] = session
        table_records[connection_tab_name] = (
            list(latest_by_client.values()),
            ['connection_status', 'usage_approval', 'internet_status',
             'request_time', 'start_time', 'end_time', 'total_requested', 'remaining', 'client_ip', 'client_token_id', 'user_info']
        )

        for tab_name, (records, fields) in table_records.items():
            table = self.usage_history_tables[tab_name]
            table.setRowCount(len(records))
            for row, record in enumerate(reversed(records)):
                remaining = record.get('remaining_seconds', 0)
                if record.get('status') == 'Approved' and remaining > 0:
                    minutes, seconds = divmod(remaining, 60)
                    remaining_text = f'{minutes:02d} min {seconds:02d} sec'
                else:
                    remaining_text = '-'
                total_requested = requested_seconds_by_client.get(record.get('client_ip', '-'), 0)
                requested_minutes, requested_seconds = divmod(total_requested, 60)
                requested_hours, requested_minutes = divmod(requested_minutes, 60)
                total_requested_text = (
                    f'{requested_hours} hr {requested_minutes:02d} min'
                    if requested_hours else f'{requested_minutes} min'
                )
                values = {
                    'log_type': record.get('log_type', '-'),
                    'status': record.get('status', '-'),
                    'completed_time': record.get('completed_time', '-'),
                    'connection_status': record.get('connection_status', '-'),
                    'internet_status': record.get('internet_status', 'Checking'),
                    'usage_request': record.get('usage_request', record.get('fare', '-')),
                    'usage_approval': record.get('usage_approval', '-'),
                    'request_time': record.get('request_time', '-'),
                    'approval_time': record.get('approval_time', '-'),
                    'requested_time': (
                        f"{record.get('requested_minutes', 0)} min"
                        if record.get('requested_minutes') else record.get('usage_request', '-')
                    ),
                    'requested_price': f"{get_record_price(record):g} PHP",
                    'user_info': (
                        f"{record.get('device_name', 'Unknown Device')} / "
                        f"{record.get('device_type', 'Unknown')} / "
                        f"{record.get('browser', 'Unknown')} / {record.get('client_ip', '-')}"
                    ),
                    'start_time': record.get('start_time', '-'),
                    'end_time': record.get('end_time', '-'),
                    'total_requested': total_requested_text,
                    'remaining': remaining_text,
                    'client_ip': record.get('client_ip', '-'),
                    'client_token_id': record.get('client_token_id', '-') or '-',
                }
                legacy_status_labels = {
                    '\uc885\ub8cc': 'Closed',
                    '\uc0ac\uc6a9 \uac00\ub2a5': 'Available',
                    '\ud655\uc778 \uc911': 'Checking',
                    '\ud655\uc778 \uc2e4\ud328': 'Check failed',
                    '\uc2b9\uc778\ub300\uae30': 'Pending Approval',
                    '\ud5c8\uac00': 'Approved',
                    '\uac70\ubd80': 'Rejected',
                    '\uc54c \uc218 \uc5c6\ub294 \uae30\uae30': 'Unknown Device',
                }
                values = {
                    key: legacy_status_labels.get(str(value), value)
                    for key, value in values.items()
                }
                for column, field in enumerate(fields):
                    table.setItem(row, column, QTableWidgetItem(str(values[field])))

    def diagnose_hotspot(self):
        result = run_hotspot_diagnostics(
            self.hotspot_nic, self.hotspot_network, self.hotspot_gateway
        )
        if hasattr(self, 'hotspot_status_btn'):
            if result['active']:
                self.hotspot_status_btn.setText('Current status: On')
                self.hotspot_status_btn.setStyleSheet(
                    "QLabel { background-color: #e8f5e9; color: #1b5e20; font-weight: bold; "
                        "border: 1px solid #1b5e20; border-radius: 4px; padding: 5px 10px; }"
                )
            else:
                self.hotspot_status_btn.setText('Current status: Off')
                self.hotspot_status_btn.setStyleSheet(
                    "QLabel { background-color: #ffebee; color: #b71c1c; font-weight: bold; "
                        "border: 1px solid #8e0000; border-radius: 4px; padding: 5px 10px; }"
                )
        if hasattr(self, 'hotspot_status_label'):
            self.hotspot_status_label.setText(result['text'].replace('\n', ' | '))
            self.hotspot_status_label.setStyleSheet(
                "color: #16803c; font-weight: bold;" if result['active']
                else "color: #a15c00; font-weight: bold;"
            )
        return result

    def adjust_linkshare_spacing(self):
        """Fit the hotspot pane's spacing and image area to the splitter height."""
        if not hasattr(self, 'linkshare_splitter'):
            return
        pane_height = self.linkshare_splitter.sizes()[0]
        compact = pane_height < 420
        if hasattr(self, 'hotspot_control_layout'):
            self.hotspot_control_layout.setSpacing(2 if compact else 6)
        if hasattr(self, 'qr_layout'):
            self.qr_layout.setSpacing(0 if compact else 1)
        if hasattr(self, 'hotspot_image_label'):
            self.hotspot_image_label.setMinimumHeight(0 if compact else 60)
            self.hotspot_image_label.setMaximumHeight(80 if compact else 140)
        if hasattr(self, 'hotspot_qr_label'):
            qr_size = max(120, min(220, int((pane_height - 55) * 0.9)))
            self.hotspot_qr_label.setMaximumSize(qr_size, qr_size)
            if hasattr(self, 'hotspot_qr_pixmap') and not self.hotspot_qr_pixmap.isNull():
                self.hotspot_qr_label.setPixmap(
                    self.hotspot_qr_pixmap.scaled(
                        qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
            if hasattr(self, 'hotspot_network_qr_label'):
                self.hotspot_network_qr_label.setMaximumSize(qr_size, qr_size)
            if hasattr(self, 'hotspot_network_pixmap') and not self.hotspot_network_pixmap.isNull():
                self.hotspot_network_qr_label.setPixmap(
                    self.hotspot_network_pixmap.scaled(
                        qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )

    def handle_linkshare_splitter_moved(self, *_):
        self.adjust_linkshare_spacing()
        if hasattr(self, 'linkshare_splitter_save_timer'):
            self.linkshare_splitter_save_timer.start()
        else:
            self.persist_settings()

    def set_hotspot_state(self, enabled):
        if enabled:
            current_info = get_current_hotspot_wifi_info()
            current_ssid = current_info.get('ssid', '').strip()
            current_password = current_info.get('passphrase', '').strip()
            if current_ssid != self.hotspot_ssid or current_password != self.hotspot_password:
                changed, credential_message = set_current_hotspot_ssid(
                    self.hotspot_ssid, self.hotspot_password
                )
                log_wifi(
                    f"Hotspot start credential check: changed={changed}, {credential_message}",
                    logging.INFO if changed else logging.ERROR,
                )
                if not changed:
                    QMessageBox.warning(
                        self,
                        "핫스팟 설정 실패",
                        f"프로그램 설정값을 핫스팟에 적용하지 못했습니다.\n{credential_message}",
                    )
                    self.diagnose_hotspot()
                    return
        success, message = set_hotspot_enabled(enabled, self.hotspot_ssid)
        self.diagnose_hotspot()
        if success:
            QMessageBox.information(self, "Hotspot", message)
        else:
            QMessageBox.warning(
                self, "Hotspot control", f"The Windows hotspot command was not completed:\n{message}\n\n"
                "Use the Windows Mobile Hotspot settings page to finish the operation."
            )

    def persist_settings(self):
        if hasattr(self, 'linkshare_splitter'):
            self.linkshare_splitter_sizes = self.linkshare_splitter.sizes()
        if hasattr(self, 'top_splitter'):
            self.file_receiver_splitter_sizes = self.top_splitter.sizes()
        if hasattr(self, 'main_splitter'):
            self.main_splitter_sizes = self.main_splitter.sizes()
        if hasattr(self, 'qr_location_splitter'):
            self.qr_location_splitter_sizes = self.qr_location_splitter.sizes()
        save_app_settings({
            'ssid': self.hotspot_ssid,
            'hotspot_password': self.hotspot_password,
            'hotspot_password_user_set': self.hotspot_password_user_set,
            'hotspot_image': self.hotspot_image_path,
            'fare_dir': self.fare_base_dir,
            'upload_folder': DEFAULT_UPLOAD_FOLDER,
            'zones': DEFAULT_ZONES,
            'save_tabs': DEFAULT_SAVE_TABS,
            'active_main_tab': self.get_active_main_tab_key(),
            'internet_nic': self.internet_nic['display'],
            'internet_ip': self.internet_nic['ip'],
            'hotspot_nic': self.hotspot_nic['display'],
            'hotspot_ip': self.hotspot_nic['ip'],
            'hotspot_network': self.hotspot_network,
            'hotspot_gateway': self.hotspot_gateway,
            'max_connections': self.max_connections,
            'status_poll_interval': self.status_poll_interval,
            'expiration_check_interval': self.expiration_check_interval,
            'internet_fares': runtime_settings.get('internet_fares', DEFAULT_INTERNET_FARES),
            'approval_sound_enabled': self.approval_sound_enabled,
            'approval_sounds': self.approval_sounds,
            'qr_output_formats': self.qr_output_formats,
            'qr_output_scales': self.qr_output_scales,
            'qr_output_dirs': self.qr_output_dirs,
            'windows_hotspot_limit': self.windows_hotspot_limit,
            'startup_enabled': self.startup_enabled,
            'file_transfer_minutes': self.file_transfer_minutes,
            'provide_internet_for_file_transfer': self.provide_internet_for_file_transfer,
            'color_options': self.color_options,
            'linkshare_splitter_sizes': self.linkshare_splitter_sizes,
            'file_receiver_splitter_sizes': self.file_receiver_splitter_sizes,
            'main_splitter_sizes': self.main_splitter_sizes,
            'qr_location_splitter_sizes': self.qr_location_splitter_sizes,
        })

    def update_zone_combo_items(self):
        self.zone_combo.blockSignals(True)
        self.zone_combo.clear()
        self.zone_combo.addItems(DEFAULT_ZONES + ["Custom Input"])
        self.zone_combo.blockSignals(False)

    def update_save_tab_combo_items(self):
        self.save_tab_combo.blockSignals(True)
        self.save_tab_combo.clear()
        self.save_tab_combo.addItems(DEFAULT_SAVE_TABS)
        self.save_tab_combo.blockSignals(False)

    def get_active_main_tab_key(self):
        return 'wifi_pass' if self.main_tabs.currentIndex() == 1 else 'file_receiver'

    def on_main_tab_changed(self, _index):
        self.persist_settings()

    def close_tab(self, index):
        """Close a received-file tab created by the integrated manager."""
        widget = self.tab_widget.widget(index)
        for identity, table in list(self.tab_tables.items()):
            if table is widget:
                del self.tab_tables[identity]
                break
        self.tab_widget.removeTab(index)

    def apply_transfer_tab_filter(self, *_args):
        period = self.transfer_period_combo.currentText()
        today = datetime.date.today()
        start = end = None
        if period in ('오늘', 'Today'):
            start = end = today
        elif period in ('이번 달', 'This month'):
            start = today.replace(day=1)
            end = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        elif period in ('기간', 'Custom'):
            start = self.transfer_start_date.date().toPython()
            end = self.transfer_end_date.date().toPython()
            if start > end:
                start, end = end, start
        show_completed = self.completed_only_checkbox.isChecked()
        for index in range(self.tab_widget.count()):
            table = self.tab_widget.widget(index)
            visible = True
            if isinstance(table, QTableWidget):
                # The checkbox filters whole tabs. When checked, all tabs
                # matching the period are shown; when unchecked, completed-
                # only tabs are hidden. Rows inside a visible tab are not
                # hidden.
                for row in range(table.rowCount()):
                    table.setRowHidden(row, False)
                has_valid_file = any(
                    not bool(table.item(row, 3).data(Qt.UserRole + 4))
                    for row in range(table.rowCount()) if table.item(row, 3)
                )
                visible = has_valid_file
                if visible and not show_completed:
                    visible = any(
                        not bool(table.item(row, 6).data(Qt.UserRole + 3))
                        and not bool(table.item(row, 3).data(Qt.UserRole + 4))
                        for row in range(table.rowCount()) if table.item(row, 6)
                    )
            if start is not None and isinstance(table, QTableWidget):
                folder_date = None
                for row in range(table.rowCount()):
                    item = table.item(row, 3)
                    if item:
                        match = re.search(r'_(\d{8})-\d{6}$', os.path.basename(str(item.data(Qt.UserRole) or '')))
                        if match:
                            folder_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
                            break
                visible = visible and folder_date is not None and start <= folder_date <= end
            self.tab_widget.setTabVisible(index, visible)
        self.update_transfer_tab_colors()

    def inspect_selected_transfer_tab(self, index):
        """Recheck files whenever the administrator selects a transfer tab."""
        if index < 0:
            return
        table = self.tab_widget.widget(index)
        if table is None:
            return
        for row in range(table.rowCount()):
            folder_item = table.item(row, 3)
            filename_item = table.item(row, 3)
            if folder_item is None or filename_item is None:
                continue
            target_folder = str(folder_item.data(Qt.UserRole) or '')
            filename = str(filename_item.text() or '')
            size_item = table.item(row, 7)
            stored_size = str(size_item.text() if size_item else '').strip()
            actual_path = os.path.join(target_folder, filename)
            missing = not os.path.isfile(actual_path)
            size_mismatch = False
            if not missing and stored_size:
                try:
                    size_mismatch = format_size(os.path.getsize(actual_path)) != stored_size
                except OSError:
                    missing = True
            invalid = missing or size_mismatch
            for column in range(table.columnCount()):
                item = table.item(row, column)
                if item is not None:
                    item.setBackground(QColor('#ffd6d6') if invalid else QColor('#ffffff'))
                    if invalid:
                        item.setToolTip('File is missing or its size does not match the saved record.')
            table.item(row, 7).setData(Qt.UserRole + 4, invalid)
            for column in (4, 5, 6):
                widget = table.cellWidget(row, column)
                if widget is not None:
                    widget.setEnabled(not invalid)

    def update_transfer_tab_colors(self, *_args):
        current_index = self.tab_widget.currentIndex()
        for index in range(self.tab_widget.count()):
            self.tab_widget.tabBar().setTabTextColor(
                index, QColor('#1565c0' if index == current_index else '#455a64')
            )

    def set_file_task_completed(self, table, row, completed):
        completion_item = table.item(row, 6)
        file_item = table.item(row, 3)
        if completion_item is None or file_item is None:
            return
        completed = bool(completed)
        completion_item.setBackground(QColor('#80cbc4' if completed else '#eaf4ff'))
        completion_item.setData(Qt.UserRole + 3, completed)
        toggle = table.cellWidget(row, 6)
        if isinstance(toggle, QPushButton):
            toggle.blockSignals(True)
            toggle.setChecked(completed)
            toggle.blockSignals(False)
            self.style_completion_toggle(toggle, completed)
        app_database.update_transfer_completed(
            str(file_item.data(Qt.UserRole) or ''), file_item.text(), completed
        )
        with transfer_records_lock:
            changed_clients = set()
            for client_id, records in transfer_records_by_client.items():
                for record in records:
                    if record.get('folder') == str(file_item.data(Qt.UserRole) or '') \
                            and record.get('filename') == file_item.text():
                        record['task_completed'] = completed
                        changed_clients.add(client_id)
            for client_id in changed_clients:
                transfer_change_versions[client_id] = transfer_change_versions.get(client_id, 0) + 1
            if changed_clients:
                transfer_change_condition.notify_all()
        self.apply_transfer_tab_filter()

    def set_completion_checkbox(self, table, row, completed=False):
        toggle = QPushButton(table)
        toggle.setCheckable(True)
        toggle.setChecked(bool(completed))
        self.style_completion_toggle(toggle, completed)
        toggle.toggled.connect(
            lambda checked: self.set_file_task_completed(table, row, checked)
        )
        table.setCellWidget(row, 6, toggle)

    @staticmethod
    def style_completion_toggle(toggle, completed):
        background = '#4db6ac' if completed else '#f1f5f9'
        border = '#00695c' if completed else '#607d8b'
        text_color = '#003c36' if completed else '#263238'
        toggle.setText('Complete' if completed else 'Incomplete')
        toggle.setStyleSheet(
            f"QPushButton {{ color: {text_color}; background-color: {background}; "
            f"border: 3px solid {border}; border-radius: 5px; padding: 5px 8px; "
            "font-size: 14px; font-weight: bold; }"
            " QPushButton:hover { border-color: #1565c0; }"
        )

    def set_tab_tasks_completed(self, table, completed):
        for row in range(table.rowCount()):
            self.set_file_task_completed(table, row, completed)
        self.apply_transfer_tab_filter()

    def show_tab_context_menu(self, pos):
        index = self.tab_widget.tabBar().tabAt(pos)
        if index < 0:
            return
        table = self.tab_widget.widget(index)
        if not isinstance(table, QTableWidget):
            return
        menu = QMenu(self.tab_widget)
        complete = menu.addAction('작업완료')
        incomplete = menu.addAction('작업미완료')
        chosen = menu.exec(self.tab_widget.tabBar().mapToGlobal(pos))
        if chosen == complete:
            self.set_tab_tasks_completed(table, True)
        elif chosen == incomplete:
            self.set_tab_tasks_completed(table, False)

    def on_save_tab_changed(self, tab_name):
        pass

    def update_zone_buttons(self):
        while self.zone_buttons_layout.count():
            item = self.zone_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        max_cols = 3
        for index, zone_name in enumerate(DEFAULT_ZONES):
            btn = QPushButton(zone_name)
            btn.setMinimumHeight(34)
            btn.setStyleSheet("""
                QPushButton { background-color: #f8f9fa; color: #17202a;
                              border: 1px solid #6c757d; border-radius: 4px;
                              padding: 6px; font-weight: bold; }
                QPushButton:hover { background-color: #dbeafe; color: #0b3d91; }
                QPushButton:pressed { background-color: #93c5fd; color: #102a43; }
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

    def select_save_folder(self):
        global DEFAULT_UPLOAD_FOLDER
        dir_path = QFileDialog.getExistingDirectory(self, "Select Save Directory", DEFAULT_UPLOAD_FOLDER)
        if dir_path:
            DEFAULT_UPLOAD_FOLDER = dir_path
            self.folder_input.setText(DEFAULT_UPLOAD_FOLDER)
            self.persist_settings()

    def on_nic_index_changed(self, index):
        if index >= 0:
            self.internet_nic = {
                'display': self.nic_combo.itemText(index),
                'ip': self.nic_combo.itemData(index, Qt.UserRole),
            }
            self.persist_settings()
        self.update_qr_code()

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
        hotspot_status = run_hotspot_diagnostics(
            self.hotspot_nic, self.hotspot_network, self.hotspot_gateway
        )
        if hotspot_status['active']:
            ip = self.hotspot_gateway
        zone = self.zone_input.text().strip() or "Default"
        # The file-transfer QR must open the upload page directly.  The root
        # route is the LinkShare portal and redirects to /scan, so using it
        # here makes the QR appear to work while never showing file upload.
        target_url = f"http://{ip}:5000/file_share?{urllib.parse.urlencode({'zone': zone})}"
        self.url_label.setText(f"Generated URL: {target_url}")
        if hasattr(self, 'hotspot_url_label'):
            self.hotspot_url_label.setText(f"Generated URL: {target_url}")

        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(target_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qimage = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(qimage)
            self.qr_pixmap = pixmap
            self.qr_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.queue_qr_background_export(
                'network', pixmap,
                f"SSID: {self.hotspot_ssid}\nPassword: {self.hotspot_password or '(not available)'}"
            )
            if hasattr(self, 'hotspot_qr_label'):
                self.update_hotspot_qr_code()
        except Exception as e:
            print(f"QR Gen Error: {e}")

    def update_hotspot_qr_code(self):
        """Generate a QR code that opens the captive portal immediately."""
        portal_url = f"http://{self.hotspot_gateway}:5000/scan"
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(portal_url)
            qr.make(fit=True)
            image = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            self.hotspot_qr_pixmap = QPixmap.fromImage(QImage.fromData(buffer.getvalue()))
            qr_size = min(220, self.hotspot_qr_label.maximumWidth() or 220)
            self.hotspot_qr_label.setPixmap(
                self.hotspot_qr_pixmap.scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self.hotspot_qr_caption.setText("This QR code is for Internet access requests.")
            self.hotspot_url_label.setText(f"Access Request URL: {portal_url}")

            wifi_ssid = self.hotspot_ssid or 'hbwifi'
            wifi_password = self.hotspot_password or ''
            wifi_type = 'WPA' if wifi_password else 'nopass'
            wifi_payload = (
                f"WIFI:T:{wifi_type};S:{escape_wifi_qr_field(wifi_ssid)};"
                f"P:{escape_wifi_qr_field(wifi_password)};H:false;;"
            )
            wifi_qr = qrcode.QRCode(version=1, box_size=10, border=4)
            wifi_qr.add_data(wifi_payload)
            wifi_qr.make(fit=True)
            wifi_image = wifi_qr.make_image(fill_color="black", back_color="white")
            wifi_buffer = BytesIO()
            wifi_image.save(wifi_buffer, format="PNG")
            network_pixmap = QPixmap.fromImage(QImage.fromData(wifi_buffer.getvalue()))
            self.hotspot_network_pixmap = network_pixmap
            if hasattr(self, 'hotspot_network_qr_label'):
                self.hotspot_network_qr_label.setPixmap(
                    network_pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            if hasattr(self, 'hotspot_network_info_label'):
                displayed_password = wifi_password or '(not available)'
                self.hotspot_network_info_label.setText(
                    f"SSID: {wifi_ssid}\nPassword: {displayed_password}"
                )
            self.queue_qr_background_export(
                'captive', self.hotspot_qr_pixmap,
                f"Internet access request\n{portal_url}"
            )
        except Exception as exc:
            self.hotspot_qr_pixmap = QPixmap()
            self.hotspot_qr_label.setText(f"Internet QR generation failed: {exc}")

    def queue_qr_background_export(self, qr_type, pixmap, guide_text):
        """Export a changed QR as JPG in a worker without blocking the GUI."""
        if pixmap.isNull():
            return
        image = pixmap.toImage().convertToFormat(QImage.Format_RGB32)
        output_dir = self.qr_output_dirs.get(qr_type, DEFAULT_QR_OUTPUT_DIR) or DEFAULT_QR_OUTPUT_DIR
        if not os.path.isdir(output_dir):
            output_dir = DEFAULT_QR_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        safe_name = 'network_connection_qr' if qr_type == 'network' else 'captive_portal_qr'
        threading.Thread(
            target=self._export_qr_jpg_worker,
            args=(qr_type, image, guide_text, output_dir, safe_name),
            daemon=True,
        ).start()

    def _export_qr_jpg_worker(self, qr_type, qr_image, guide_text, output_dir, safe_name):
        try:
            output_results = []
            changed = False
            for scale in (1, 2, 3, 4):
                qr_size = max(240, 240 * scale)
                scaled_qr = qr_image.scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation)
                margin = max(12, 12 * scale)
                text_font = QFont('Arial', max(12, 12 * scale))
                metrics = QFontMetrics(text_font)
                lines = guide_text.splitlines() or [qr_type]
                line_height = metrics.lineSpacing()
                canvas = QImage(
                    qr_size + margin * 2,
                    qr_size + line_height * len(lines) + margin * 2,
                    QImage.Format_RGB32,
                )
                canvas.fill(Qt.white)
                painter = QPainter(canvas)
                painter.setPen(Qt.black)
                painter.setFont(text_font)
                painter.drawImage(margin, margin, scaled_qr)
                text_y = margin + qr_size + max(2, scale)
                for line in lines:
                    painter.drawText(margin, text_y, qr_size, line_height, Qt.AlignHCenter, line)
                    text_y += line_height
                painter.end()
                output_path = os.path.join(output_dir, f'{safe_name}_{scale}x.jpg')
                temp_path = f'{output_path}.tmp-{threading.get_ident()}'
                if not canvas.save(temp_path, 'JPG'):
                    raise OSError(f'{output_path} 저장에 실패했습니다.')
                if os.path.exists(output_path) and filecmp.cmp(temp_path, output_path, shallow=False):
                    os.remove(temp_path)
                    output_results.append(f'{scale}x: 변경 없음')
                else:
                    os.replace(temp_path, output_path)
                    changed = True
                    output_results.append(f'{scale}x: 갱신됨 ({output_path})')
            if changed:
                self.qr_export_completed.emit(qr_type, True, '\n'.join(output_results))
        except Exception as exc:
            self.qr_export_completed.emit(qr_type, False, str(exc))

    def handle_qr_export_completed(self, qr_type, success, detail):
        if success:
            self.show_auto_close_message(
                QMessageBox.Information,
                'QR 출력 확인 완료',
                f'{qr_type} QR JPG 비교 결과\n{detail}',
                timeout=3000,
            )
        else:
            self.show_auto_close_message(
                QMessageBox.Warning,
                'QR 출력 실패',
                f'{qr_type} QR JPG 저장 실패\n{detail}',
                timeout=3000,
            )

    def show_network_qr_print_dialog(self):
        if not hasattr(self, 'hotspot_network_pixmap') or self.hotspot_network_pixmap.isNull():
            QMessageBox.warning(self, "Print QR Code", "The network QR code is not ready yet.")
            return
        self.show_qr_print_dialog(
            "Network Connection QR",
            self.hotspot_network_pixmap,
            f"SSID: {self.hotspot_ssid}\nPassword: {self.hotspot_password or '(not available)'}",
        )

    def show_captive_qr_print_dialog(self):
        if not hasattr(self, 'hotspot_qr_pixmap') or self.hotspot_qr_pixmap.isNull():
            QMessageBox.warning(self, "Print QR Code", "The captive portal QR code is not ready yet.")
            return
        self.show_qr_print_dialog(
            "Captive Portal QR",
            self.hotspot_qr_pixmap,
            f"Internet access request\nhttp://{self.hotspot_gateway}:5000/scan",
        )

    def show_qr_print_dialog(self, title, pixmap, guide_text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(380, 460)
        layout = QVBoxLayout(dialog)
        qr_type = 'network' if 'Network' in title else 'captive'
        saved_format = self.qr_output_formats.get(qr_type, DEFAULT_QR_OUTPUT_FORMAT)
        saved_scale = int(self.qr_output_scales.get(qr_type, DEFAULT_QR_OUTPUT_SCALE))

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(preview)

        guide = QLabel(guide_text)
        guide.setAlignment(Qt.AlignCenter)
        guide.setWordWrap(True)
        guide.setStyleSheet("font-size: 11px; color: #263238; padding: 6px;")
        layout.addWidget(guide)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("출력 형식:"))
        format_group = QButtonGroup(dialog)
        format_buttons = {}
        for file_format in ("JPG", "BMP", "PDF"):
            radio = QRadioButton(file_format)
            radio.setChecked(file_format == saved_format)
            format_group.addButton(radio)
            format_buttons[file_format] = radio
            format_layout.addWidget(radio)
        format_layout.addStretch()
        layout.addLayout(format_layout)

        scale_layout = QHBoxLayout()
        for scale in (1, 2, 3, 4):
            button = QPushButton(f"{scale}x")
            button.setMinimumHeight(32)
            if scale == saved_scale:
                button.setStyleSheet("font-weight: bold; border: 2px solid #1565c0;")
            button.clicked.connect(
                lambda checked=False, value=scale: self.export_qr_with_text(
                    pixmap, title, guide_text, value,
                    next((name for name, radio in format_buttons.items() if radio.isChecked()), "PDF"),
                    dialog, qr_type
                )
            )
            scale_layout.addWidget(button)
        layout.addLayout(scale_layout)
        dialog.exec()

    def export_qr_with_text(self, pixmap, title, guide_text, scale, file_format, preview_dialog=None, qr_type=None):
        """Save a compact, readable QR+text output with a fixed filename."""
        qr_type = qr_type or ('network' if 'Network' in title else 'captive')
        output_dir = self.qr_output_dirs.get(qr_type, DEFAULT_QR_OUTPUT_DIR)
        if not output_dir or not os.path.isdir(output_dir):
            output_dir = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", output_dir or current_dir)
            if not output_dir:
                return False
            self.qr_output_dirs[qr_type] = output_dir
            self.persist_settings()

        safe_name = "network_connection_qr" if "Network" in title else "captive_portal_qr"
        extension = file_format.lower()
        output_path = os.path.join(output_dir, f"{safe_name}_{scale}x.{extension}")
        self.qr_output_formats[qr_type] = file_format
        self.qr_output_scales[qr_type] = scale
        self.persist_settings()
        qr_size = max(240, 240 * scale)
        qr_image = pixmap.toImage().scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation)
        margin = max(12, 12 * scale)
        text_font = QFont("Arial", max(12, 12 * scale))
        text_metrics = QFontMetrics(text_font)
        text_lines = guide_text.splitlines() or [title]
        text_height = text_metrics.lineSpacing() * len(text_lines)
        canvas = QImage(qr_size + margin * 2, qr_size + text_height + margin * 2, QImage.Format_RGB32)
        canvas.fill(Qt.white)
        painter = QPainter(canvas)
        painter.setPen(Qt.black)
        painter.setFont(text_font)
        painter.drawImage(margin, margin, qr_image)
        text_y = margin + qr_size + max(2, scale)
        for line in text_lines:
            painter.drawText(margin, text_y, qr_size, text_metrics.lineSpacing(), Qt.AlignHCenter, line)
            text_y += text_metrics.lineSpacing()
        painter.end()

        try:
            if file_format in ("JPG", "BMP"):
                if not canvas.save(output_path, file_format):
                    raise OSError("이미지 파일 저장에 실패했습니다.")
            else:
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(output_path)
                printer.setPageSize(QPageSize(QPageSize.A4))
                painter = QPainter(printer)
                page_rect = printer.pageLayout().paintRectPixels(printer.resolution())
                fitted = canvas.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = page_rect.left() + (page_rect.width() - fitted.width()) // 2
                y = page_rect.top() + (page_rect.height() - fitted.height()) // 2
                painter.drawImage(x, y, fitted)
                painter.end()
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "출력 실패", str(exc))
            return False

        QMessageBox.information(self, "출력 완료", f"파일이 저장되었습니다.\n{output_path}")
        if preview_dialog is not None:
            preview_dialog.accept()
        return True

    def print_qr_pixmap(self, pixmap, title, scale, preview_dialog=None):
        printer = QPrinter(QPrinter.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() != QDialog.Accepted:
            return False

        painter = QPainter(printer)
        try:
            page_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            qr_size = int(printer.resolution() * 40 * scale / 25.4)
            qr_size = min(qr_size, page_rect.width(), page_rect.height())
            x = page_rect.left() + (page_rect.width() - qr_size) // 2
            y = page_rect.top() + (page_rect.height() - qr_size) // 2
            print_pixmap = pixmap.scaled(
                qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation
            )
            painter.drawPixmap(x, y, print_pixmap)
        finally:
            painter.end()
        if preview_dialog is not None:
            preview_dialog.accept()
        return True

    def print_network_qr_code(self):
        self.show_network_qr_print_dialog()

    def show_qr_print_sizes(self):
        self.show_captive_qr_print_dialog()

    def print_qr_code(self, scale):
        if not hasattr(self, 'hotspot_qr_pixmap') or self.hotspot_qr_pixmap.isNull():
            QMessageBox.warning(self, "Print QR Code", "The QR code is not ready yet.")
            return
        self.print_qr_pixmap(self.hotspot_qr_pixmap, "Captive Portal QR", scale)

    @Slot(list, str, str)
    def handle_incoming_files(self, file_list, target_folder, identity, persist=True):
        self.last_target_folder = target_folder
        transfer_started = datetime.datetime.now()
        transfer_record = {
            'transfer_key': f"{identity}:{transfer_started.isoformat()}",
            'client_ip': '-',
            'client_token_id': identity,
            'started_at': transfer_started.strftime('%Y-%m-%d %H:%M:%S'),
            'expires_at': (transfer_started + datetime.timedelta(
                minutes=self.file_transfer_minutes
            )).strftime('%Y-%m-%d %H:%M:%S'),
            'file_count': len(file_list),
            # File transfer is not internet usage and is never charged.  The
            # setting only controls whether internet access may be granted
            # alongside a transfer; a successful transfer needs no grant.
            'internet_granted': self.provide_internet_for_file_transfer,
            'charged': False,
        }
        try:
            app_database.save_file_transfer(transfer_record)
        except (OSError, sqlite3.Error):
            logging.getLogger(__name__).exception("Failed to save file transfer record")
        if persist:
            for record in file_list:
                if len(record) >= 10:
                    app_database.save_transfer_log(target_folder, identity, {
                        'user_name': record[0], 'user_info': record[1], 'cookie': record[2],
                        'zone': record[3], 'filename': record[4], 'copies': record[5],
                        'size': record[6], 'received_time': record[7],
                        'status': record[8], 'color': record[9], 'task_completed': False,
                    })
        first_record = list(file_list[0]) if file_list else ['Guest']
        tab_user = safe_folder_part(first_record[0] if first_record else 'Guest', 'Guest')
        folder_match = re.search(r'_(\d{1,3}(?:\.\d{1,3}){3})_\d{8}-\d{6}$', os.path.basename(target_folder))
        tab_ip = folder_match.group(1) if folder_match else safe_folder_part(identity, 'UnknownIP')
        # Keep each upload batch in its own admin tab, matching the QR view.
        # Previously only zone/user/IP were used, so repeated uploads from
        # the same user were merged into one tab.
        target_folder_name = os.path.basename(target_folder)
        transfer_match = re.search(r'(\d{8}-\d{6})$', target_folder_name)
        transfer_batch = safe_folder_part(
            transfer_match.group(1) if transfer_match else target_folder_name,
            'Transfer'
        )
        tab_name = (
            f'{safe_folder_part(first_record[3] if len(first_record) > 3 else "Default", "Default")}_'
            f'{tab_user}_{tab_ip}_{transfer_batch}'
        )
        table = self.get_or_create_file_table(tab_name)
        sorting_enabled = table.isSortingEnabled()
        table.setSortingEnabled(False)
        # Remove incomplete rows left by the pre-metadata table format.
        for old_row in range(table.rowCount() - 1, -1, -1):
            old_file = table.item(old_row, 3)
            if old_file is None or not old_file.text().strip():
                table.removeRow(old_row)

        # If a client or an older upload path reports fewer records than were
        # physically saved, rebuild the missing rows from the target folder.
        reported_names = {
            str(record[4]) for record in file_list if len(record) >= 9 and record[4]
        }
        # Keep the canonical incoming tuple order here:
        # user, info, cookie, zone, filename, copies, size, time, status, color.
        # The old fallback omitted ``color`` and shifted every following
        # field, which made the admin and customer views disagree after a
        # missing/legacy record was reconstructed.
        template_record = list(file_list[0]) if file_list else [
            'Guest', 'Unknown', '', zone, '', 1, '', '',
            'Completed (100%)', DEFAULT_COLOR_OPTIONS[0]
        ]
        if os.path.isdir(target_folder):
            for saved_name in os.listdir(target_folder):
                saved_path = os.path.join(target_folder, saved_name)
                if (os.path.isfile(saved_path) and not saved_name.startswith('summary_')
                        and saved_name != 'transfer_summary.txt' and saved_name not in reported_names):
                    file_list.append((
                        template_record[0], template_record[1], template_record[2], zone,
                        saved_name, 1, format_size(os.path.getsize(saved_path)),
                        datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
                        'Completed (100%)', DEFAULT_COLOR_OPTIONS[0]
                    ))
        for file_info in file_list:
            # Never create a visible row without a filename. If the stored
            # record is incomplete, the physical-file reconciliation above
            # will add the real file instead.
            if len(file_info) < 5 or not str(file_info[4]).strip():
                continue
            # Keep every received row aligned with the nine-column table,
            # including records produced by older clients.
            if len(file_info) == 6:
                # Legacy tuple: user, zone, filename, size, time, status.
                values = [file_info[0], 'Unknown', '', file_info[1], file_info[2], 1,
                          DEFAULT_COLOR_OPTIONS[0], file_info[3], file_info[4], file_info[5]]
            else:
                values = list(file_info[:10])
                # Normalize the previous server tuple order
                # (..., copies, size, received_time, status, color) to the
                # current table order (..., copies, color, size, time, status).
                if len(values) >= 10:
                    values[6:10] = [values[9], values[6], values[7], values[8]]
                elif len(values) >= 9:
                    values[6:9] = [DEFAULT_COLOR_OPTIONS[0], values[6], values[7]]
            while len(values) < 11:
                values.append('')
            values = [values[0], values[1], values[3], values[4], values[5],
                      values[6], values[10], values[7], values[8], values[9], values[2]]
            # The filename is the stable fifth field of every modern
            # incoming tuple. Set it explicitly so legacy/color normalization
            # can never leave the filename column blank or shifted.
            if len(file_info) >= 5 and file_info[4]:
                values[3] = str(file_info[4])
            if not values[4]:
                values[4] = 1
            row = table.rowCount()
            table.insertRow(row)
            row_color = QColor('#f7fbff' if row % 2 else '#eaf4ff')
            file_path = os.path.join(target_folder, str(values[3]))
            file_missing = True
            if values[3]:
                actual_size = None
                if os.path.isfile(file_path):
                    try:
                        actual_size = os.path.getsize(file_path)
                    except OSError:
                        # The file may disappear between the existence check
                        # and the size lookup. Treat it as missing instead of
                        # aborting the UI update.
                        pass
                file_missing = (
                    actual_size is None
                    or bool(values[7]) and format_size(actual_size) != str(values[7])
                )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                missing_color = QColor('#ffcdd2')
                item.setBackground(
                    missing_color if file_missing
                    else QColor('#c9f0d2') if column == 9 else row_color
                )
                if file_missing:
                    item.setForeground(QColor('#b71c1c'))
                    item.setToolTip('파일이 없거나 저장된 파일 크기와 일치하지 않습니다.')
                item.setData(Qt.UserRole, target_folder)
                item.setData(Qt.UserRole + 4, file_missing)
                item.setData(Qt.UserRole + 2, identity)
                table.setItem(row, column, item)
            table.item(row, 6).setData(Qt.UserRole + 3, False)
            self.set_copy_controls(table, row, int(values[4]) if values[4] is not None else 1)
            self.set_color_control(table, row, str(values[5] or DEFAULT_COLOR_OPTIONS[0]))
            self.set_completion_checkbox(table, row, False)
            if file_missing:
                for control_column in (4, 5, 6):
                    control = table.cellWidget(row, control_column)
                    if control is not None:
                        control.setEnabled(False)
                        control.setToolTip('파일이 없거나 크기가 일치하지 않아 사용할 수 없습니다.')
            if persist:
                self.pending_batch_files.append(file_info)
        table.resizeColumnToContents(3)
        table.setColumnWidth(3, min(max(table.columnWidth(3), 260), 520))
        # Keep the copy controls compact; their child buttons must not cause
        # the whole column to expand to the available table width.
        table.setColumnWidth(4, 150)
        table.setSortingEnabled(sorting_enabled)
        # Reapply visibility after rows are inserted. A newly created table
        # was previously filtered while empty and could remain hidden.
        self.apply_transfer_tab_filter()
        if persist:
            self.batch_timer.start()

    def get_or_create_file_table(self, tab_name):
        table = self.tab_tables.get(tab_name)
        if table is not None:
            return table
        table = QTableWidget(0, 11, self)
        table.setHorizontalHeaderLabels([
            "사용자명", "사용자 부가정보", "쿠키", "구역", "파일명",
            "카피수", "컬러", "크기", "수신시간", "상태"
        ])
        table.setHorizontalHeaderItem(10, QTableWidgetItem("완료"))
        table.setHorizontalHeaderLabels([
            "User Name", "User Info", "Zone", "File Name", "Copies", "Color",
            "Complete", "Size", "Received Time", "Status", "Cookie"
        ])
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, t=table: self.show_context_menu(pos, t))
        table.cellDoubleClicked.connect(self.on_row_double_clicked)
        table.setSortingEnabled(True)
        table.setWordWrap(True)
        table.setStyleSheet(
            "QTableWidget { font-size: 13px; color: #263238; background-color: #ffffff; gridline-color: #78909c; }"
            " QTableWidget::item { color: #263238; padding: 4px; }"
            " QTableWidget::item:selected { color: #102a43; background-color: #b3d7ff; }"
            " QHeaderView::section { color: #102a43; background-color: #d7e7f7; font-size: 13px; font-weight: bold; padding: 7px; }"
        )
        table.verticalHeader().setDefaultSectionSize(38)
        table.horizontalHeader().setMinimumSectionSize(80)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().sectionDoubleClicked.connect(
            lambda column, t=table: t.resizeColumnToContents(column)
        )
        for column, width in enumerate((140, 240, 120, 110, 280, 90, 100, 100, 110, 150, 90)):
            table.setColumnWidth(column, width)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.tab_tables[tab_name] = table
        self.tab_widget.addTab(table, tab_name)
        self.tab_widget.setTabToolTip(self.tab_widget.indexOf(table), tab_name)
        self.update_transfer_tab_colors()
        self.apply_transfer_tab_filter()
        return table

    def set_copy_controls(self, table, row, count):
        """Install administrator-only copy count controls in one row."""
        container = QWidget(table)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(3)
        down = QPushButton("−")
        value = QLabel(str(max(0, min(999, int(count)))))
        up = QPushButton("+")
        container.setStyleSheet(
            "QWidget { background-color: #eaf4ff; border-radius: 5px; }"
            " QLabel { color: #102a43; font-size: 14px; font-weight: bold; }"
            " QPushButton { background-color: #1976d2; color: white; font-weight: bold;"
            " border: 0; border-radius: 4px; }"
            " QPushButton:hover { background-color: #0d47a1; }"
        )
        for button in (down, up):
            button.setFixedSize(28, 28)
        value.setAlignment(Qt.AlignCenter)
        value.setMinimumWidth(28)
        down.clicked.connect(lambda: self.change_copy_count(table, row, value, -1))
        up.clicked.connect(lambda: self.change_copy_count(table, row, value, 1))
        layout.addWidget(down)
        layout.addWidget(value)
        layout.addWidget(up)
        table.setCellWidget(row, 4, container)
        item = table.item(row, 4)
        if item is not None:
            item.setData(Qt.UserRole + 1, int(count))

    def set_color_control(self, table, row, color):
        combo = QComboBox(table)
        combo.addItems(runtime_settings.get('color_options', DEFAULT_COLOR_OPTIONS))
        combo.setCurrentText(color if color in [combo.itemText(i) for i in range(combo.count())]
                             else DEFAULT_COLOR_OPTIONS[0])
        combo.setStyleSheet(
            "QComboBox { background: #ffd166; color: #102a43; padding: 4px; border: 1px solid #e09f00; }"
            " QComboBox QAbstractItemView { color: #102a43; background: white; }"
        )
        combo.currentTextChanged.connect(
            lambda value: self.change_color_value(table, row, value)
        )
        table.setCellWidget(row, 5, combo)
        item = table.item(row, 5)
        if item is not None:
            item.setText('')

    def change_color_value(self, table, row, color):
        file_item = table.item(row, 3)
        if file_item is None:
            return
        target_folder = str(file_item.data(Qt.UserRole) or '')
        filename = file_item.text()
        app_database.update_transfer_log(target_folder, filename, color=color)
        with transfer_change_condition:
            changed_clients = set()
            for client_id, records in transfer_records_by_client.items():
                for record in records:
                    if record.get('folder') == target_folder and record.get('filename') == filename:
                        if record.get('color') != color:
                            record['color'] = color
                            changed_clients.add(client_id)
            for client_id in changed_clients:
                transfer_change_versions[client_id] = transfer_change_versions.get(client_id, 0) + 1
            if changed_clients:
                transfer_change_condition.notify_all()
        if changed_clients:
            signals.transfer_updated.emit(
                target_folder, filename,
                int(table.item(row, 4).data(Qt.UserRole + 1) if table.item(row, 4).data(Qt.UserRole + 1) is not None else 0), color
            )

    def change_copy_count(self, table, row, value_label, delta):
        count = max(0, min(999, int(value_label.text()) + delta))
        value_label.setText(str(count))
        item = table.item(row, 4)
        if item is None:
            item = QTableWidgetItem()
            table.setItem(row, 4, item)
        original = item.data(Qt.UserRole + 1)
        if original is None:
            original = count
        if count != int(original):
            value_label.parentWidget().setStyleSheet(
                "QWidget { background-color: #ffd166; border: 2px solid #e09f00; border-radius: 5px; }"
                " QLabel { color: #5d3a00; font-size: 14px; font-weight: bold; }"
                " QPushButton { background-color: #d97706; color: white; font-weight: bold; border: 0; border-radius: 4px; }"
            )
        else:
            value_label.parentWidget().setStyleSheet(
                "QWidget { background-color: #eaf4ff; border-radius: 5px; }"
                " QLabel { color: #102a43; font-size: 14px; font-weight: bold; }"
                " QPushButton { background-color: #1976d2; color: white; font-weight: bold; border: 0; border-radius: 4px; }"
            )
        item.setText('')
        self.update_transfer_copy_count(
            str(table.item(row, 3).data(Qt.UserRole) or ''),
            str(table.item(row, 3).text()), count
        )

    def update_transfer_copy_count(self, target_folder, filename, count):
        app_database.update_transfer_log(target_folder, filename, copies=count)
        with transfer_records_lock:
            changed_clients = set()
            for records in transfer_records_by_client.values():
                for record in records:
                    if record.get('folder') == target_folder and record.get('filename') == filename:
                        if record.get('copies') != count:
                            record['copies'] = count
                            for client_id, client_records in transfer_records_by_client.items():
                                if record in client_records:
                                    changed_clients.add(client_id)
            for client_id in changed_clients:
                transfer_change_versions[client_id] = transfer_change_versions.get(client_id, 0) + 1
            if changed_clients:
                transfer_change_condition.notify_all()

    @Slot(str, str, int, str)
    def handle_remote_transfer_update(self, target_folder, filename, copies, color):
        for table in self.tab_tables.values():
            for row in range(table.rowCount()):
                file_item = table.item(row, 3)
                if not file_item or file_item.text() != filename:
                    continue
                if str(file_item.data(Qt.UserRole) or '') != target_folder:
                    continue
                copy_item = table.item(row, 4)
                if copy_item:
                    copy_item.setData(Qt.UserRole + 1, copies)
                container = table.cellWidget(row, 4)
                if container:
                    labels = container.findChildren(QLabel)
                    if labels:
                        labels[0].setText(str(copies))
                color_item = table.item(row, 5)
                if color_item:
                    color_item.setText('')
                    color_item.setBackground(QColor('#ffd166'))
                color_combo = table.cellWidget(row, 5)
                if isinstance(color_combo, QComboBox):
                    color_combo.blockSignals(True)
                    color_combo.setCurrentText(color)
                    color_combo.blockSignals(False)

    @Slot(str, list)
    def handle_deleted_files(self, identity, file_names):
        tab_name = os.path.basename(identity)
        table = self.tab_tables.get(tab_name)
        if table is None:
            return
        for row in range(table.rowCount() - 1, -1, -1):
            item = table.item(row, 3)
            if item and item.text() in file_names:
                table.removeRow(row)

    def show_batch_notification(self):
        if not self.pending_batch_files:
            return
        count = len(self.pending_batch_files)
        self.pending_batch_files.clear()
        QMessageBox.information(self, "파일 수신 완료", f"파일 {count}개를 수신했습니다.")

    def on_row_double_clicked(self, row, col):
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        item = table.item(row, 3)
        if item is None:
            return
        target_folder = item.data(Qt.UserRole)
        if not target_folder:
            return
        target_folder = str(target_folder)
        self.create_transfer_summary(table, target_folder)
        if os.path.isdir(target_folder):
            subprocess.Popen(['explorer.exe', os.path.normpath(target_folder)])

    def show_context_menu(self, pos, table):
        index = table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        table.selectRow(row)
        menu = QMenu(table)
        delete_action = menu.addAction("삭제")
        summary_action = menu.addAction("요약정보 표시")
        menu.addSeparator()
        complete_action = menu.addAction("작업완료")
        incomplete_action = menu.addAction("작업미완료")
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == delete_action:
            self.delete_transfer_row(table, row)
        elif chosen == summary_action:
            self.write_transfer_summary(table, row)
        elif chosen == complete_action:
            self.set_file_task_completed(table, row, True)
            self.apply_transfer_tab_filter()
        elif chosen == incomplete_action:
            self.set_file_task_completed(table, row, False)
            self.apply_transfer_tab_filter()

    def delete_transfer_row(self, table, row):
        item = table.item(row, 3)
        if item is None:
            return
        file_path = os.path.join(str(item.data(Qt.UserRole) or ''), item.text())
        answer = QMessageBox.question(
            self, "삭제 확인", f"파일을 삭제할까요?\n{item.text()}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
            table.removeRow(row)
        except OSError as exc:
            QMessageBox.warning(self, "삭제 실패", str(exc))

    def write_transfer_summary(self, table, row):
        item = table.item(row, 4)
        if item is None:
            return
        target_folder = str(item.data(Qt.UserRole) or '')
        if not target_folder:
            return
        summary_path = self.create_transfer_summary(table, target_folder)
        if not summary_path:
            return
        try:
            # Do not depend on the .txt file association. Some Windows
            # installations have no registered text editor for os.startfile.
            subprocess.Popen(['notepad.exe', os.path.normpath(summary_path)])
        except (OSError, subprocess.SubprocessError) as exc:
            QMessageBox.warning(self, "요약정보 열기 실패", str(exc))

    def create_transfer_summary(self, table, target_folder):
        """Write the current transfer table rows to the target folder."""
        if not target_folder:
            return ''
        folder_name = os.path.basename(os.path.normpath(target_folder))
        summary_path = os.path.join(target_folder, f'summary_{folder_name}.txt')
        try:
            os.makedirs(target_folder, exist_ok=True)
            records = []
            user_name = user_info = cookie = zone = request_time = ''
            for row in range(table.rowCount()):
                file_item = table.item(row, 3)
                if file_item is None or str(file_item.data(Qt.UserRole) or '') != str(target_folder):
                    continue
                cells = [table.item(row, column) for column in range(table.columnCount())]
                values = [cell.text() if cell else '' for cell in cells]
                if not user_name:
                    user_name, user_info, zone, cookie = values[0], values[1], values[2], values[10]
                    request_time = values[8]
                if table.cellWidget(row, 4) is not None:
                    labels = table.cellWidget(row, 4).findChildren(QLabel)
                    values[4] = labels[0].text() if labels else values[4]
                color_combo = table.cellWidget(row, 5)
                if isinstance(color_combo, QComboBox):
                    values[5] = color_combo.currentText()
                completed = bool(table.item(row, 6).data(Qt.UserRole + 3))
                records.append((
                    values[3], values[4],
                    values[5] if len(values) > 5 else DEFAULT_COLOR_OPTIONS[0],
                    '완료' if completed else '미완료'
                ))
            records.sort(key=lambda record: record[0].lower())
            with open(summary_path, 'w', encoding='utf-8') as summary:
                summary.write(f'사용자명: {user_name}\n')
                summary.write(f'사용자 부가정보: {user_info}\n')
                summary.write(f'쿠키: {cookie}\n')
                summary.write(f'구역: {zone}\n')
                summary.write(f'요청시간: {request_time}\n\n')
                filename_width = max([len('파일명')] + [len(str(record[0])) for record in records])
                color_width = max([len('컬러유무')] + [len(str(record[2])) for record in records])
                completed_width = max([len('완료여부')] + [len(str(record[3])) for record in records])
                summary.write(
                    f'{"파일명":<{filename_width}}  {"카피수":>6}  {"컬러유무":<{color_width}}  '
                    f'{"완료여부":<{completed_width}}\n'
                )
                summary.write(
                    f'{"-" * filename_width}  {"-" * 6}  {"-" * color_width}  '
                    f'{"-" * completed_width}\n'
                )
                for filename, copy_count, color_value, completed_value in records:
                    summary.write(
                        f'{str(filename):<{filename_width}}  {str(copy_count):>6}  '
                        f'{str(color_value):<{color_width}}  {str(completed_value):<{completed_width}}\n'
                    )
            return summary_path
        except OSError as exc:
            QMessageBox.warning(self, "요약정보 실패", str(exc))
            return ''

    def handle_customer_request(self, client_ip, minutes, dur_str):
        self.bring_to_front()
        self.update_connection_summary()
        session = shared_sessions.get(client_ip)
        if not session:
            return
        is_extension = bool(session.get('extension_pending'))
        if session.get('status') != 'Pending' and not (
            is_extension and session.get('status') == 'Approved'
        ):
            return

        approval_box = QMessageBox(self)
        approval_box.setWindowTitle("Internet Request")
        approval_box.setText(
            f"Client IP: {client_ip}\nSelected time: {dur_str}\n\nApprove Internet access?"
        )
        approval_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        approval_box.setDefaultButton(QMessageBox.No)
        approval_sound_checkbox = QCheckBox("사용승인 소리알림")
        approval_sound_checkbox.setChecked(self.approval_sound_enabled)
        approval_box.setCheckBox(approval_sound_checkbox)
        if self.approval_sound_enabled:
            self.play_approval_sound()
        reply = approval_box.exec()
        self.stop_approval_sound()
        if approval_sound_checkbox.isChecked() != self.approval_sound_enabled:
            self.approval_sound_enabled = approval_sound_checkbox.isChecked()
            self.persist_settings()
        if reply == QMessageBox.Yes:
            start = datetime.datetime.now()
            if is_extension:
                current_end_timestamp = max(
                    float(session.get('end_timestamp', 0)), start.timestamp()
                )
                end = datetime.datetime.fromtimestamp(current_end_timestamp) + datetime.timedelta(
                    minutes=minutes
                )
                session.update({
                    'extension_pending': False,
                    'extension_minutes': 0,
                    'extension_fare': '',
                    'end_time': end.strftime('%Y-%m-%d %H:%M:%S'),
                    'end_timestamp': end.timestamp(),
                    'remaining_seconds': max(0, int(end.timestamp() - start.timestamp())),
                    'usage_approval': 'Approved (additional)',
                    'approved_price': float(session.get('extension_price', 0) or 0),
                    'total_used_seconds': int(session.get('total_used_seconds', 0)) + minutes * 60,
                })
                append_usage_log(
                    'approval', session,
                    requested_minutes=minutes,
                    approved_price=session.get('approved_price', 0),
                )
                notify_status_change()
                self.show_auto_close_message(
                    QMessageBox.Information,
                    'Approved',
                    f'Additional Internet time approved for {client_ip}.'
                )
                self.update_connection_summary()
                return
            end = start + datetime.timedelta(minutes=minutes)
            session.update({
                'status': 'Approved',
                'connection_status': '사용중',
                'usage_approval': '허가',
                'approval_time': start.strftime('%Y-%m-%d %H:%M:%S'),
                'start_time': start.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end.strftime('%Y-%m-%d %H:%M:%S'),
                'end_timestamp': end.timestamp(),
                'remaining_seconds': minutes * 60,
                'total_used_seconds': int(session.get('total_used_seconds', 0)) + minutes * 60,
                'approved_price': float(session.get('requested_price', 0) or 0),
            })
            session['usage_approval'] = 'Approved (first)'
            append_usage_log(
                'approval', session,
                requested_minutes=minutes,
                approved_price=session.get('approved_price', 0),
            )
            notify_status_change()
            self.show_auto_close_message(
                QMessageBox.Information,
                "Approved",
                f"Internet access started for {client_ip}."
            )
        else:
            if is_extension:
                session.update({
                    'extension_pending': False,
                    'extension_minutes': 0,
                    'extension_fare': '',
                })
                append_usage_log(
                    'approval',
                    session,
                    status='Rejected',
                    usage_approval='Rejected',
                    approval_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                )
                notify_status_change()
                QMessageBox.warning(
                    self,
                    'Rejected',
                    f'Additional Internet request from {client_ip} was rejected.',
                )
                self.update_connection_summary()
                return
            session['status'] = 'Rejected'
            session['connection_status'] = '연결됨'
            session['usage_approval'] = '거부'
            session['approval_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            session['remaining_seconds'] = 0
            append_usage_log('approval', session)
            notify_status_change()
            QMessageBox.warning(self, "Rejected", f"Internet request from {client_ip} was rejected.")
        self.update_connection_summary()

    def bring_to_front(self):
        """Restore and activate the manager when a customer request arrives."""
        was_maximized = bool(self.windowState() & Qt.WindowMaximized)
        if was_maximized:
            self.setWindowState(
                (self.windowState() & ~Qt.WindowMinimized) | Qt.WindowMaximized | Qt.WindowActive
            )
        else:
            self.showNormal()
            self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 3 if was_maximized else 9)  # SW_MAXIMIZE/SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

    def show_auto_close_message(self, icon, title, message, timeout=1000):
        dialog = QMessageBox(icon, title, message, QMessageBox.Ok, self)
        QTimer.singleShot(timeout, dialog.accept)
        dialog.exec()

    def play_approval_sound(self):
        if not self.approval_sound_enabled or winsound is None:
            return
        path = next((path for path in self.approval_sounds if path and os.path.isfile(path)), '')
        if not path:
            return
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            if self.approval_sound_playback_timer:
                self.approval_sound_playback_timer.stop()
            self.approval_sound_playback_timer = QTimer(self)
            self.approval_sound_playback_timer.setSingleShot(True)
            self.approval_sound_playback_timer.timeout.connect(self.stop_approval_sound)
            self.approval_sound_playback_timer.start(15 * 60 * 1000)
        except (OSError, RuntimeError) as exc:
            print(f"Approval sound playback error: {exc}")

    def stop_approval_sound(self):
        if self.approval_sound_playback_timer:
            self.approval_sound_playback_timer.stop()
            self.approval_sound_playback_timer = None
        if winsound is not None:
            winsound.PlaySound(None, 0)

    def closeEvent(self, event):
        log_wifi('Application closing; hotspot will remain running.')
        self.stop_captive_portal()
        self.persist_settings()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IntegratedManagerApp()
    window.show()
    sys.exit(app.exec())
