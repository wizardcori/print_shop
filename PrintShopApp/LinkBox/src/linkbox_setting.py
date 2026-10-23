"""LinkBox printer-monitor settings persistence and settings tab UI."""
import configparser
import ast
import json
import os
import subprocess
import socket
import concurrent.futures
import ipaddress
import psutil

from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QLabel, QFileDialog
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

from Common.settings_registry import register_settings_tab
from Common.paths import CONFIG_FILE, PRINT_MONITOR_SOUND_DIR
from Common.globals import CONFIG_ENCODING, resource_path, load_ui_safely
from Common.config import config_manager

from .print_log_writer import write_system_log


MONITORED_PRINTERS_SECTION = 'MonitoredPrinters'
# Values edited from the integrated Settings screen belong to the shared
# application settings file, not the LinkBox implementation config.
DEFAULT_CONFIG_PATH = CONFIG_FILE


def list_system_printers():
    """Return printers installed in the local Windows print spooler."""
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        rows = win32print.EnumPrinters(flags, None, 2)
        printers = []
        for row in rows:
            name = row.get('pPrinterName') or ''
            if not name:
                continue
            printers.append({
                'name': name,
                'host': row.get('pPortName') or '',
                'driver': row.get('pDriverName') or '',
                'comment': row.get('pComment') or '',
            })
        return printers
    except (ImportError, OSError):
        # Keep the feature usable on installations where pywin32 was not
        # bundled yet. Get-Printer is available on supported Windows systems.
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 'Get-Printer | Select-Object Name,PortName,DriverName | ConvertTo-Json -Compress'],
                capture_output=True, text=True, encoding=CONFIG_ENCODING, errors='replace', timeout=5,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []
            rows = json.loads(result.stdout)
            if isinstance(rows, dict):
                rows = [rows]
            return [
                {'name': row.get('Name', ''), 'host': row.get('PortName', ''),
                 'driver': row.get('DriverName', ''), 'comment': ''}
                for row in rows if row.get('Name')
            ]
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            return []


def discover_network_printers(max_hosts=254):
    """Find likely printers on local IPv4 networks using common print ports."""
    networks = []
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if getattr(address, 'family', None) != socket.AF_INET or address.address.startswith('127.'):
                continue
            try:
                network = ipaddress.ip_network(f'{address.address}/{address.netmask}', strict=False)
                if network.prefixlen >= 24:
                    networks.extend(str(host) for host in network.hosts())
            except ValueError:
                continue
    hosts = list(dict.fromkeys(networks))[:max_hosts]

    def probe(host):
        open_ports = []
        for port in (161, 631, 9100):
            try:
                with socket.create_connection((host, port), timeout=0.18):
                    open_ports.append(port)
            except OSError:
                pass
        if not open_ports:
            return None
        return {'name': f'Network printer ({host})', 'host': host,
                'community': 'public', 'port': 161, 'ports': open_ports,
                'enabled': True}

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        return [result for result in executor.map(probe, hosts) if result]


def load_monitored_printers(config_path=DEFAULT_CONFIG_PATH):
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        return []
    try:
        config.read(config_path, encoding=CONFIG_ENCODING)
        raw_items = config.get(MONITORED_PRINTERS_SECTION, 'items', fallback='[]')
        try:
            items = json.loads(raw_items)
        except json.JSONDecodeError:
            items = ast.literal_eval(raw_items)
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict) and item.get('name')]
    except (OSError, ValueError, SyntaxError, TypeError, configparser.Error):
        return []


def save_monitored_printers(printers, config_path=DEFAULT_CONFIG_PATH):
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path, encoding=CONFIG_ENCODING)
    config[MONITORED_PRINTERS_SECTION] = {
        'items': repr(printers),
    }
    with open(config_path, 'w', encoding=CONFIG_ENCODING) as stream:
        config.write(stream)


def create_print_log_settings(parent=None):
    from PySide6.QtWidgets import QWidget, QFormLayout, QHBoxLayout, QSpinBox, QDoubleSpinBox, QPushButton, QLabel, QLineEdit, QFileDialog
    try:
        from .print_log_writer import load_log_settings, save_log_settings, load_log_viewer_path, save_log_viewer_path
    except ImportError:
        from print_log_writer import load_log_settings, save_log_settings

    widget = QWidget(parent)
    layout = QFormLayout(widget)
    settings = load_log_settings()
    log_viewer = QLineEdit(load_log_viewer_path(), widget)
    browse_viewer = QPushButton('찾기', widget)
    browse_viewer.clicked.connect(lambda: log_viewer.setText(
        QFileDialog.getOpenFileName(widget, '로그뷰어 선택', log_viewer.text() or '', '실행 파일 (*.exe);;모든 파일 (*.*)')[0] or log_viewer.text()
    ))
    batch_size = QSpinBox(widget)
    batch_size.setRange(1, 100000)
    batch_size.setValue(settings['batch_size'])
    flush_interval = QDoubleSpinBox(widget)
    flush_interval.setRange(0.05, 3600.0)
    flush_interval.setDecimals(2)
    flush_interval.setSuffix(' 초')
    flush_interval.setValue(settings['flush_interval'])
    save_button = QPushButton('저장', widget)
    status = QLabel('기본값: 최대 100건 또는 5초마다 기록', widget)

    def save():
        save_log_settings(batch_size.value(), flush_interval.value())
        save_log_viewer_path(log_viewer.text())
        status.setText('저장되었습니다. 다음 실행부터 적용됩니다.')

    save_button.clicked.connect(save)
    layout.addRow('배치 최대 건수', batch_size)
    layout.addRow('배치 기록 주기', flush_interval)
    viewer_row = QHBoxLayout()
    viewer_row.addWidget(log_viewer)
    viewer_row.addWidget(browse_viewer)
    layout.addRow('로그뷰어 경로', viewer_row)
    layout.addRow(save_button)
    layout.addRow(status)
    return widget


class PrinterMonitorSettingsWidget:
    @staticmethod
    def create(parent=None, config_path=DEFAULT_CONFIG_PATH):
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
            QPushButton, QInputDialog, QMessageBox, QDialog,
        )
        from PySide6.QtCore import Qt

        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        table = QTableWidget(0, 6, widget)
        table.setHorizontalHeaderLabels(['사용', '프린터명', 'IP/호스트', '커뮤니티', '포트', '상태'])
        table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(table)

        buttons = QHBoxLayout()
        add_button, all_button, network_button, edit_button, delete_button = (
            QPushButton(text) for text in ('추가', '모두 추가', '네트워크 검색', '수정', '삭제')
        )
        buttons.addWidget(add_button)
        buttons.addWidget(all_button)
        buttons.addWidget(network_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        printers = load_monitored_printers(config_path)

        def refresh():
            table.setRowCount(0)
            for printer in printers:
                row = table.rowCount()
                table.insertRow(row)
                enabled = QTableWidgetItem('✓' if printer.get('enabled', True) else '')
                enabled.setCheckState(Qt.Checked if printer.get('enabled', True) else Qt.Unchecked)
                table.setItem(row, 0, enabled)
                for col, key in enumerate(('name', 'host', 'community', 'port'), 1):
                    table.setItem(row, col, QTableWidgetItem(str(printer.get(key, ''))))
                table.setItem(row, 5, QTableWidgetItem('활성' if printer.get('enabled', True) else '중지'))
            table.resizeColumnsToContents()

        def edit(selected=None):
            index = table.currentRow() if selected is None else selected
            if index == -1:
                system_printers = list_system_printers()
                if not system_printers:
                    QMessageBox.warning(widget, '프린터 검색', 'Windows에 등록된 프린터를 찾지 못했습니다. pywin32 설치 여부를 확인하세요.')
                    return
                dialog = QDialog(widget)
                dialog.setWindowTitle('시스템 프린터 선택')
                dialog.resize(620, 320)
                dialog_layout = QVBoxLayout(dialog)
                printer_table = QTableWidget(0, 3, dialog)
                printer_table.setHorizontalHeaderLabels(['프린터명', '포트/IP', '드라이버'])
                printer_table.setSelectionBehavior(QTableWidget.SelectRows)
                for printer in system_printers:
                    row = printer_table.rowCount(); printer_table.insertRow(row)
                    for column, key in enumerate(('name', 'host', 'driver')):
                        printer_table.setItem(row, column, QTableWidgetItem(printer[key]))
                printer_table.resizeColumnsToContents()
                dialog_layout.addWidget(printer_table)
                select_button = QPushButton('선택', dialog)
                dialog_layout.addWidget(select_button)
                select_button.clicked.connect(dialog.accept)
                printer_table.cellDoubleClicked.connect(lambda *_: dialog.accept())
                if dialog.exec() != QDialog.Accepted or printer_table.currentRow() < 0:
                    return
                selected_printer = system_printers[printer_table.currentRow()]
                current = {
                    'name': selected_printer['name'], 'host': selected_printer['host'],
                    'community': 'public', 'port': 161, 'enabled': True,
                }
                index = -2
            else:
                current = printers[index] if 0 <= index < len(printers) else {
                    'name': '', 'host': '', 'community': 'public', 'port': 161, 'enabled': True,
                }
            values = []
            fields = [('프린터명', 'name'), ('IP/호스트', 'host'),
                      ('SNMP 커뮤니티', 'community'), ('SNMP 포트', 'port')]
            for title, key in fields:
                value, ok = QInputDialog.getText(widget, '프린터 감시 설정', title, text=str(current.get(key, '')))
                if not ok:
                    return
                values.append(value.strip())
            if not values[0] or not values[1]:
                QMessageBox.warning(widget, '확인', '프린터명과 IP/호스트는 필수입니다.')
                return
            try:
                port = int(values[3])
            except ValueError:
                QMessageBox.warning(widget, '확인', '포트는 숫자여야 합니다.')
                return
            item = {
                'name': values[0], 'host': values[1], 'community': values[2] or 'public',
                'port': port, 'enabled': current.get('enabled', True),
            }
            if 0 <= index < len(printers):
                printers[index] = item
            else:
                printers.append(item)
            save_monitored_printers(printers, config_path)
            refresh()

        def add_printers(items):
            existing = {str(item.get('host') or item.get('name')).casefold() for item in printers}
            for item in items:
                key = str(item.get('host') or item.get('name')).casefold()
                if key and key not in existing:
                    printers.append(item)
                    existing.add(key)
            save_monitored_printers(printers, config_path)
            refresh()

        def add_all_system():
            add_printers([
                {'name': item['name'], 'host': item['host'], 'community': 'public',
                 'port': 161, 'enabled': True}
                for item in list_system_printers()
            ])

        def search_network():
            network_button.setEnabled(False)
            network_button.setText('검색 중...')
            try:
                add_printers(discover_network_printers())
            finally:
                network_button.setText('네트워크 검색')
                network_button.setEnabled(True)

        def remove():
            index = table.currentRow()
            if 0 <= index < len(printers):
                printers.pop(index)
                save_monitored_printers(printers, config_path)
                refresh()

        add_button.clicked.connect(lambda: edit(-1))
        all_button.clicked.connect(add_all_system)
        network_button.clicked.connect(search_network)
        edit_button.clicked.connect(edit)
        delete_button.clicked.connect(remove)
        refresh()
        widget.printers = printers
        widget.table = table
        return widget

class PrintMonitorSoundSettings(QWidget):
    SOUND_SETTINGS_SECTION = 'PrintMonitorSounds'

    def __init__(self, parent=None):
        super().__init__(parent)

        # 내부 변수
        self.widget_id = "print_monitor_sound_settings"
        self.widget_title = "프린트 모니터 사운드 설정"

        # .ui 파일 로드
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(current_dir, "ui", "print_monitor_sound_settings.ui")
        write_system_log('WARNING', f"UI 파일 경로: {ui_path}")
        print(f"UI 파일 경로: {ui_path}")  # 디버그용 출력

        try:
            # 안전한 로딩 함수 호출
            self.ui = load_ui_safely(ui_path, self)
        except Exception as e:
            print(e)
            write_system_log('ERROR', f"UI 파일 경로 로드 실패 ({ui_path}): {e}")

        # 위젯 참조
        self.detection_edit   = self.ui.findChild(QLineEdit, "detectionEdit")
        self.detection_browse = self.ui.findChild(QPushButton, "detectionBrowse")
        self.detection_test   = self.ui.findChild(QPushButton, "detectionTest")

        self.tree_edit   = self.ui.findChild(QLineEdit, "treeEdit")
        self.tree_browse = self.ui.findChild(QPushButton, "treeBrowse")
        self.tree_test   = self.ui.findChild(QPushButton, "treeTest")

        self.save_button  = self.ui.findChild(QPushButton, "saveButton")
        self.status_label = self.ui.findChild(QLabel, "statusLabel")

        # 시그널 연결
        self.detection_browse.clicked.connect(self.select_detection_sound)
        self.detection_test.clicked.connect(lambda: self.test_sound(self.detection_edit.text()))

        self.tree_browse.clicked.connect(self.select_tree_sound)
        self.tree_test.clicked.connect(lambda: self.test_sound(self.tree_edit.text()))

        self.save_button.clicked.connect(self.save_settings)

        # 초기값 로드
        self.load_settings()
    
    def load_settings(self):
        """사운드 설정 로드 및 UI 반영"""
        defaults = {
            'detection_sound': os.path.join(PRINT_MONITOR_SOUND_DIR, 'detect.wav'),
            'tree_sound': os.path.join(PRINT_MONITOR_SOUND_DIR, 'insert.wav'),
        }
        settings = config_manager.load(self.SOUND_SETTINGS_SECTION, defaults)
        
        # UI 입력 필드에 값 채우기
        if self.detection_edit and 'detection_sound' in settings:
            self.detection_edit.setText(settings['detection_sound'])
        if self.tree_edit and 'tree_sound' in settings:
            self.tree_edit.setText(settings['tree_sound'])
        
    def save_settings(self):
        """사운드 설정을 설정 파일에 저장하고 상태를 표시합니다."""
        detection_sound = self.detection_edit.text() if self.detection_edit else ""
        tree_sound = self.tree_edit.text() if self.tree_edit else ""

        # 저장할 설정 데이터를 딕셔너리로 구성
        settings = {
            'detection_sound': detection_sound,
            'tree_sound': tree_sound
        }
        
        # ConfigManager 인스턴스의 save 메서드 호출
        config_manager.save(section=self.SOUND_SETTINGS_SECTION, settings=settings)
        
        if self.status_label:
            self.status_label.setText("저장되었습니다.")

    def select_detection_sound(self):
        path, _ = QFileDialog.getOpenFileName(self, "WAV 선택", "", "WAV (*.wav)")
        if path:
            self.detection_edit.setText(path)

    def select_tree_sound(self):
        path, _ = QFileDialog.getOpenFileName(self, "WAV 선택", "", "WAV (*.wav)")
        if path:
            self.tree_edit.setText(path)

    def test_sound(self, file_path):
        if file_path:
            from .print_log_writer import play_notification_sound
            play_notification_sound(file_path.strip())


register_settings_tab(
    'linkbox.printer-monitor', 'Printer Monitor',
    lambda parent: PrinterMonitorSettingsWidget.create(parent), order=20,
)

register_settings_tab(
    'linkbox.printer-monitor-sounds', 'Printer Monitor Sounds',
    PrintMonitorSoundSettings, order=20.5,
)

register_settings_tab(
    'linkbox.print-log', 'Print Log',
    create_print_log_settings, order=21,
)


