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
from io import BytesIO
from email.parser import BytesParser
from email.policy import default
from flask import Flask, request, render_template, redirect
from cryptography.fernet import Fernet

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox, QFileDialog,
    QCheckBox, QMenu, QDialog, QListWidget, QTabWidget, QGridLayout, QSpinBox
)
from PySide6.QtGui import QPixmap, QImage, QColor, QAction, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer, QObject

# --- Path and Subfolder Integration ---
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

linkbox_path = os.path.join(current_dir, "LinkBox")
linkshare_path = os.path.join(current_dir, "LinkShare")
sys.path.append(linkbox_path)
sys.path.append(linkshare_path)

import ui_layout

# --- Configuration & Path Setup ---
SETTINGS_FILE = "wifi_approval_settings.ini"
DEFAULT_UPLOAD_FOLDER = os.path.join(linkbox_path, "LinkBox_Files")
os.makedirs(DEFAULT_UPLOAD_FOLDER, exist_ok=True)

DEFAULT_ZONES = ["Counter", "Table01", "Table02", "VIP_Room"]
DEFAULT_SAVE_TABS = ["DefaultTab"]
DEFAULT_HOTSPOT_SSID = "hb_wifi"
DEFAULT_HOTSPOT_NETWORK = "192.168.137.0/24"
DEFAULT_HOTSPOT_GATEWAY = "192.168.137.1"
DEFAULT_MAX_CONNECTIONS = 250
DEFAULT_WINDOWS_HOTSPOT_LIMIT = 8
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
        linkshare_splitter_sizes = json.loads(
            config.get('Settings', 'linkshare_splitter_sizes', fallback='[520, 260]')
        )
        if not isinstance(linkshare_splitter_sizes, list) or len(linkshare_splitter_sizes) != 2:
            raise ValueError
        linkshare_splitter_sizes = [max(100, int(size)) for size in linkshare_splitter_sizes]
    except (TypeError, ValueError, json.JSONDecodeError):
        linkshare_splitter_sizes = [520, 260]

    return {
        'ssid': config.get('Settings', 'hotspot_ssid', fallback=DEFAULT_HOTSPOT_SSID),
        'hotspot_image': config.get('Settings', 'hotspot_image', fallback=''),
        'fare_dir': config.get('Settings', 'fare_dir', fallback=os.path.join(linkshare_path, 'fare')),
        'max_connections': max_connections,
        'windows_hotspot_limit': windows_hotspot_limit,
        'upload_folder': config.get('Storage', 'upload_folder', fallback=DEFAULT_UPLOAD_FOLDER),
        'zones': zones,
        'save_tabs': save_tabs,
        'internet_nic': config.get('Network', 'internet_nic', fallback=''),
        'internet_ip': config.get('Network', 'internet_ip', fallback=''),
        'hotspot_nic': config.get('Network', 'hotspot_nic', fallback=''),
        'hotspot_ip': config.get('Network', 'hotspot_ip', fallback=''),
        'hotspot_network': config.get('Network', 'hotspot_network', fallback=DEFAULT_HOTSPOT_NETWORK),
        'hotspot_gateway': config.get('Network', 'hotspot_gateway', fallback=DEFAULT_HOTSPOT_GATEWAY),
        'linkshare_splitter_sizes': linkshare_splitter_sizes,
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
    config.set('Settings', 'hotspot_image', settings.get('hotspot_image', ''))
    config.set('Settings', 'fare_dir', settings.get('fare_dir', os.path.join(linkshare_path, 'fare')))
    config.set('Settings', 'max_connections', str(max(1, int(settings.get('max_connections', DEFAULT_MAX_CONNECTIONS)))))
    config.set(
        'Settings',
        'windows_hotspot_limit',
        str(max(1, min(WINDOWS_HOTSPOT_LIMIT_MAX, int(settings.get('windows_hotspot_limit', DEFAULT_WINDOWS_HOTSPOT_LIMIT))))),
    )
    splitter_sizes = settings.get('linkshare_splitter_sizes', [520, 260])
    config.set('Settings', 'linkshare_splitter_sizes', json.dumps([int(size) for size in splitter_sizes]))
    config.set('Network', 'internet_nic', settings.get('internet_nic', ''))
    config.set('Network', 'internet_ip', settings.get('internet_ip', ''))
    config.set('Network', 'hotspot_nic', settings.get('hotspot_nic', ''))
    config.set('Network', 'hotspot_ip', settings.get('hotspot_ip', ''))
    config.set('Network', 'hotspot_network', settings.get('hotspot_network', DEFAULT_HOTSPOT_NETWORK))
    config.set('Network', 'hotspot_gateway', settings.get('hotspot_gateway', DEFAULT_HOTSPOT_GATEWAY))
    config.set('Storage', 'upload_folder', settings.get('upload_folder', DEFAULT_UPLOAD_FOLDER))
    config.set('Storage', 'zones', ','.join(settings.get('zones', DEFAULT_ZONES)))
    config.set('Storage', 'save_tabs', ','.join(settings.get('save_tabs', DEFAULT_SAVE_TABS)))

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
def enable_mobile_hotspot(ssid_name="hb_wifi"):
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


def set_current_hotspot_ssid(ssid):
    """Apply the program-defined SSID while preserving the existing hotspot password."""
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

        async def configure():
            await manager.configure_access_point_async(access_point)

        asyncio.run(configure())
        return True, f"Hotspot SSID changed from '{previous_ssid}' to '{ssid}'"
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
web_app = Flask(__name__, template_folder=os.path.join(linkshare_path, 'templates'))
shared_sessions = {}
usage_history = []
runtime_settings = {'max_connections': DEFAULT_MAX_CONNECTIONS}
_upstream_dns_cache = {'timestamp': 0.0, 'servers': []}


def append_usage_log(log_type, session, **overrides):
    """Append an immutable request/approval event to the usage history."""
    record = dict(session)
    record.update(overrides)
    record['log_type'] = log_type
    usage_history.append(record)


def is_client_internet_approved(client_ip):
    """Return whether a client currently has an active approved session."""
    session = shared_sessions.get(client_ip)
    if not session or session.get('status') != 'Approved':
        return False
    end_timestamp = session.get('end_timestamp', 0)
    if end_timestamp and end_timestamp <= datetime.datetime.now().timestamp():
        session['status'] = 'Expired'
        session['connection_status'] = '종료'
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

signals = ServerSignals()

@web_app.route('/')
def portal_root():
    return redirect('/scan')

@web_app.route('/scan')
def customer_scan():
    return render_template('portal.html')

@web_app.route('/file_share')
def file_share_page():
    return render_template('file_share.html')

@web_app.route('/request')
def customer_request():
    allowed_minutes = {30, 60, 90, 120, 180, 240}
    try:
        minutes = int(request.args.get('min', 60))
    except (TypeError, ValueError):
        return {'msg': 'Invalid usage time.'}, 400
    if minutes not in allowed_minutes:
        return {'msg': 'Select one of the available usage times.'}, 400

    client_ip = request.remote_addr
    dur_str = f"{minutes} Min Pass" if minutes < 60 else f"{minutes//60} Hour Pass"
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
            signals.approval_requested.emit(client_ip, minutes, dur_str)
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
        'fare': dur_str,
        'client_ip': client_ip,
        'connection_status': '연결됨',
        'usage_request': dur_str,
        'usage_approval': '승인대기',
        'request_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'approval_time': '-',
        'start_time': '-',
        'end_time': '-',
    }
    shared_sessions[client_ip] = session_record
    append_usage_log('request', session_record)
    signals.approval_requested.emit(client_ip, minutes, dur_str)
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


@web_app.route('/status')
def get_status():
    return get_client_session(request.remote_addr)

# --- Integrated Settings Dialog ---
class IntegratedSettingsDialog(QDialog):
    def __init__(self, current_zones, current_fare_dir, current_ssid, interfaces,
                 current_internet_nic, current_hotspot_nic, current_hotspot_image,
                 current_hotspot_network, current_hotspot_gateway, current_max_connections,
                 current_windows_hotspot_limit, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Integrated Environment Settings")
        self.resize(520, 650)
        
        self.zones = current_zones.copy()
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("<b>📶 Hotspot SSID (Name):</b>"))
        self.ssid_input = QLineEdit(DEFAULT_HOTSPOT_SSID)
        self.ssid_input.setReadOnly(True)
        layout.addWidget(self.ssid_input)

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
        
        save_btn = QPushButton("Save & Close")
        save_btn.setStyleSheet("background-color: #007BFF; color: white; font-weight: bold; padding: 8px;")
        save_btn.clicked.connect(self.accept)
        layout.addWidget(save_btn)

    def browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Log Directory", self.path_input.text())
        if dir_path:
            self.path_input.setText(dir_path)

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
        return DEFAULT_HOTSPOT_SSID

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

# --- Main Application Window ---
class IntegratedManagerApp(QMainWindow):
    file_signal = Signal(list, str, str)
    delete_signal = Signal(str, list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PrintShop Integrated Manager (HTTPS)")

        app_settings = load_app_settings()
        detected_hotspot_info = get_current_hotspot_wifi_info()
        detected_hotspot_ssid = detected_hotspot_info['ssid']
        self.hotspot_ssid = DEFAULT_HOTSPOT_SSID
        self.hotspot_password = detected_hotspot_info['passphrase']
        self.hotspot_ssid_sync_message = ''
        if detected_hotspot_ssid and detected_hotspot_ssid != DEFAULT_HOTSPOT_SSID:
            changed, message = set_current_hotspot_ssid(DEFAULT_HOTSPOT_SSID)
            self.hotspot_ssid_sync_message = message
            self.hotspot_password = get_current_hotspot_wifi_info()['passphrase']
        self.fare_base_dir = app_settings['fare_dir']
        self.hotspot_image_path = app_settings['hotspot_image']
        self.hotspot_network, self.hotspot_gateway = normalize_hotspot_network(
            app_settings['hotspot_network'], app_settings['hotspot_gateway']
        )
        self.linkshare_splitter_sizes = app_settings.get('linkshare_splitter_sizes', [520, 260])
        self.max_connections = app_settings['max_connections']
        self.windows_hotspot_limit = app_settings['windows_hotspot_limit']
        runtime_settings['max_connections'] = self.max_connections
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

        # The QR code points to the hotspot gateway.  Merely opening the
        # Windows settings page leaves that gateway unassigned, so clients
        # can scan the QR code but cannot connect to the web server.  Start
        # the hotspot through the WinRT API (with the existing fallback) and
        # let the diagnostics/retry logic handle the adapter's startup delay.
        hotspot_started, hotspot_message = set_hotspot_enabled(True, self.hotspot_ssid)
        if not hotspot_started:
            print(f"Hotspot startup was not completed: {hotspot_message}")
        
        ui_layout.setup_integrated_ui(
            self, DEFAULT_UPLOAD_FOLDER, DEFAULT_ZONES, DEFAULT_SAVE_TABS, interfaces,
            self.hotspot_ssid, self.internet_nic, self.hotspot_nic, self.hotspot_image_path,
            self.hotspot_network, self.hotspot_gateway, self.max_connections
        )

        self.tab_tables = {}
        self.pending_batch_files = []
        self.last_target_folder = ""
        
        self.batch_timer = QTimer()
        self.batch_timer.setSingleShot(True)
        self.batch_timer.setInterval(300)
        self.batch_timer.timeout.connect(self.show_batch_notification)

        self.connection_timer = QTimer(self)
        self.connection_timer.setInterval(2000)
        self.connection_timer.timeout.connect(self.update_connection_summary)
        self.connection_timer.start()

        self.resize(1150, 750)
        self.update_qr_code()

        self.file_signal.connect(self.handle_incoming_files)
        self.delete_signal.connect(self.handle_deleted_files)
        signals.approval_requested.connect(self.handle_customer_request)

        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()
        self.captive_portal_servers = []
        self.captive_portal_retry_count = 0
        self.start_captive_portal()
        self.persist_settings()
        QTimer.singleShot(250, self.diagnose_hotspot)

    def load_saved_defaults(self, app_settings):
        global DEFAULT_UPLOAD_FOLDER, DEFAULT_ZONES, DEFAULT_SAVE_TABS
        DEFAULT_UPLOAD_FOLDER = app_settings['upload_folder'] or DEFAULT_UPLOAD_FOLDER
        DEFAULT_ZONES = app_settings['zones'] or DEFAULT_ZONES
        DEFAULT_SAVE_TABS = app_settings['save_tabs'] or DEFAULT_SAVE_TABS
        os.makedirs(DEFAULT_UPLOAD_FOLDER, exist_ok=True)

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
            DEFAULT_ZONES, self.fare_base_dir, self.hotspot_ssid, self.interfaces,
            self.internet_nic['display'], self.hotspot_nic['display'], self.hotspot_image_path,
            self.hotspot_network, self.hotspot_gateway, self.max_connections,
            self.windows_hotspot_limit, self
        )
        if dialog.exec() == QDialog.Accepted:
            DEFAULT_ZONES = dialog.zones
            new_ssid = dialog.get_hotspot_ssid()
            self.hotspot_ssid = new_ssid
            self.internet_nic = dialog.get_internet_nic()
            self.hotspot_nic = dialog.get_hotspot_nic()
            self.hotspot_image_path = dialog.get_hotspot_image()
            self.hotspot_network, self.hotspot_gateway = dialog.get_hotspot_network()
            self.max_connections = dialog.get_max_connections()
            self.windows_hotspot_limit = dialog.get_windows_hotspot_limit()
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
                    session['connection_status'] = '종료'
                    session['remaining_seconds'] = 0

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

    def update_usage_history_tables(self):
        if not hasattr(self, 'usage_history_tables'):
            return

        table_records = {
            '연결상태': (usage_history, [
                'connection_status', 'request_time', 'start_time', 'end_time', 'remaining', 'client_ip'
            ]),
            '사용요청': ([record for record in usage_history if record.get('log_type') == 'request'], [
                'usage_request', 'request_time', 'client_ip'
            ]),
            '사용허가': (
                [record for record in usage_history if record.get('log_type') == 'approval'],
                ['usage_approval', 'approval_time', 'start_time', 'end_time', 'remaining', 'client_ip']
            ),
        }

        for tab_name, (records, fields) in table_records.items():
            table = self.usage_history_tables[tab_name]
            table.setRowCount(len(records))
            for row, record in enumerate(reversed(records)):
                remaining = record.get('remaining_seconds', 0)
                if record.get('status') == 'Approved' and remaining > 0:
                    minutes, seconds = divmod(remaining, 60)
                    remaining_text = f'{minutes:02d}분 {seconds:02d}초'
                else:
                    remaining_text = '-'
                values = {
                    'connection_status': record.get('connection_status', '-'),
                    'usage_request': record.get('usage_request', record.get('fare', '-')),
                    'usage_approval': record.get('usage_approval', '-'),
                    'request_time': record.get('request_time', '-'),
                    'approval_time': record.get('approval_time', '-'),
                    'start_time': record.get('start_time', '-'),
                    'end_time': record.get('end_time', '-'),
                    'remaining': remaining_text,
                    'client_ip': record.get('client_ip', '-'),
                }
                for column, field in enumerate(fields):
                    table.setItem(row, column, QTableWidgetItem(str(values[field])))

    def diagnose_hotspot(self):
        result = run_hotspot_diagnostics(
            self.hotspot_nic, self.hotspot_network, self.hotspot_gateway
        )
        if hasattr(self, 'hotspot_status_btn'):
            if result['active']:
                self.hotspot_status_btn.setText('Hotspot ON')
                self.hotspot_status_btn.setStyleSheet(
                    "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
                    "border: 1px solid #1b5e20; border-radius: 4px; padding: 5px 10px; }"
                    "QPushButton:hover { background-color: #388e3c; }"
                )
            else:
                self.hotspot_status_btn.setText('Hotspot OFF')
                self.hotspot_status_btn.setStyleSheet(
                    "QPushButton { background-color: #c62828; color: white; font-weight: bold; "
                    "border: 1px solid #8e0000; border-radius: 4px; padding: 5px 10px; }"
                    "QPushButton:hover { background-color: #d32f2f; }"
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
        save_app_settings({
            'ssid': self.hotspot_ssid,
            'hotspot_image': self.hotspot_image_path,
            'fare_dir': self.fare_base_dir,
            'upload_folder': DEFAULT_UPLOAD_FOLDER,
            'zones': DEFAULT_ZONES,
            'save_tabs': DEFAULT_SAVE_TABS,
            'internet_nic': self.internet_nic['display'],
            'internet_ip': self.internet_nic['ip'],
            'hotspot_nic': self.hotspot_nic['display'],
            'hotspot_ip': self.hotspot_nic['ip'],
            'hotspot_network': self.hotspot_network,
            'hotspot_gateway': self.hotspot_gateway,
            'max_connections': self.max_connections,
            'windows_hotspot_limit': self.windows_hotspot_limit,
            'linkshare_splitter_sizes': self.linkshare_splitter_sizes,
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

    def close_tab(self, index):
        """Close a received-file tab created by the integrated manager."""
        widget = self.tab_widget.widget(index)
        for identity, table in list(self.tab_tables.items()):
            if table is widget:
                del self.tab_tables[identity]
                break
        self.tab_widget.removeTab(index)

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
            btn.setStyleSheet("QPushButton { background-color: #f8f9fa; border: 1px solid #ced4da; padding: 6px; font-weight: bold; }")
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
        target_url = f"http://{ip}:5000/?zone={zone}"
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
            self.hotspot_qr_caption.setText("이 QR 코드는 인터넷 사용신청용입니다.")
            self.hotspot_url_label.setText(f"사용신청 URL: {portal_url}")

            wifi_ssid = self.hotspot_ssid or 'hb_wifi'
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
        except Exception as exc:
            self.hotspot_qr_pixmap = QPixmap()
            self.hotspot_qr_label.setText(f"Internet QR generation failed: {exc}")

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

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(preview)

        guide = QLabel(guide_text)
        guide.setAlignment(Qt.AlignCenter)
        guide.setWordWrap(True)
        guide.setStyleSheet("font-size: 11px; color: #263238; padding: 6px;")
        layout.addWidget(guide)

        scale_layout = QHBoxLayout()
        for scale in (1, 2, 3, 4):
            button = QPushButton(f"{scale}x")
            button.setMinimumHeight(32)
            button.clicked.connect(
                lambda checked=False, value=scale: self.print_qr_pixmap(
                    pixmap, title, value, dialog
                )
            )
            scale_layout.addWidget(button)
        layout.addLayout(scale_layout)
        dialog.exec()

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
    def handle_incoming_files(self, file_list, target_folder, identity):
        pass

    @Slot(str, list)
    def handle_deleted_files(self, identity, file_names):
        pass

    def show_batch_notification(self):
        pass

    def on_row_double_clicked(self, row, col):
        pass

    def show_context_menu(self, pos, table):
        pass

    def handle_customer_request(self, client_ip, minutes, dur_str):
        self.update_connection_summary()
        session = shared_sessions.get(client_ip)
        if not session:
            return
        is_extension = bool(session.get('extension_pending'))
        if session.get('status') != 'Pending' and not (
            is_extension and session.get('status') == 'Approved'
        ):
            return

        reply = QMessageBox.question(
            self,
            "Internet Request",
            f"Client IP: {client_ip}\nSelected time: {dur_str}\n\nApprove Internet access?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
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
                })
                append_usage_log('approval', session)
                QMessageBox.information(
                    self, 'Approved', f'Additional Internet time approved for {client_ip}.'
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
            })
            append_usage_log('approval', session)
            QMessageBox.information(self, "Approved", f"Internet access started for {client_ip}.")
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
            QMessageBox.warning(self, "Rejected", f"Internet request from {client_ip} was rejected.")
        self.update_connection_summary()

    def closeEvent(self, event):
        self.stop_captive_portal()
        self.persist_settings()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IntegratedManagerApp()
    window.show()
    sys.exit(app.exec())
