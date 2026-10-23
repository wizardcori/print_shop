"""LinkShare runtime and settings controller.

This module owns the LinkShare side of the integrated window: hotspot
startup/control, adapter display, diagnostics, connection expiry, QR layout,
and the settings dialog.  The main window remains an event host and supplies
only the shared application services through the constructor.
"""

import datetime
import logging
import os
import sqlite3

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QDialog, QMessageBox

from LinkShare.src.hotspot_service import (
    get_current_hotspot_wifi_info,
    get_windows_hotspot_client_limits,
    run_hotspot_diagnostics,
    set_current_hotspot_ssid,
    set_hotspot_enabled,
)
from LinkShare.src.firewall_service import apply_hotspot_firewall_rules
from LinkShare.src.integrated_settings_dialog import (
    configure_settings_dependencies,
)
from LinkShare.src.network_adapter_service import choose_optimal_adapters
from LinkShare.src.usage_history_controller import (
    update_usage_history_tables as render_usage_history_tables,
)


class LinkShareRuntimeController:
    """Own LinkShare runtime behavior while reusing the host window widgets."""

    def __init__(
        self,
        window,
        *,
        shared_sessions,
        client_identity_map,
        session_identity_lock,
        usage_history,
        app_database,
        runtime_settings,
        default_internet_fares,
        get_default_zones,
        set_default_zones,
        append_usage_log,
        notify_status_change,
        get_record_price,
        log_wifi,
        get_network_interfaces,
        choose_preferred_interface,
        settings_file,
        application_dir,
        approval_sound_dir,
        integrated_settings_dialog,
        set_startup_registration,
        restore_window_geometry,
        save_window_geometry,
        settings_defaults,
        mode_label='OpMode',
        mode_can_switch=False,
        set_runtime_mode=None,
        captive_portal_service,
        is_client_internet_approved,
        get_upstream_dns_servers,
        update_captive_portal_status,
    ):
        self.window = window
        self.shared_sessions = shared_sessions
        self.client_identity_map = client_identity_map
        self.session_identity_lock = session_identity_lock
        self.usage_history = usage_history
        self.app_database = app_database
        self.runtime_settings = runtime_settings
        self.default_internet_fares = default_internet_fares
        self.get_default_zones = get_default_zones
        self.set_default_zones = set_default_zones
        self.append_usage_log = append_usage_log
        self.notify_status_change = notify_status_change
        self.get_record_price = get_record_price
        self.log_wifi = log_wifi
        self.get_network_interfaces = get_network_interfaces
        self.choose_preferred_interface = choose_preferred_interface
        self.settings_file = settings_file
        self.application_dir = application_dir
        self.approval_sound_dir = approval_sound_dir
        self.integrated_settings_dialog = integrated_settings_dialog
        self.set_startup_registration = set_startup_registration
        self.restore_window_geometry = restore_window_geometry
        self.save_window_geometry = save_window_geometry
        self.captive_portal_service = captive_portal_service
        self.is_client_internet_approved = is_client_internet_approved
        self.get_upstream_dns_servers = get_upstream_dns_servers
        self.update_captive_portal_status = update_captive_portal_status
        configure_settings_dependencies(
            settings_file,
            settings_defaults,
            mode_label=mode_label,
            mode_can_switch=mode_can_switch,
            set_runtime_mode=set_runtime_mode,
        )

    def initialize_hotspot_state(self):
        """Check each hotspot requirement and change only mismatched stages."""
        window = self.window
        self.log_wifi('Hotspot startup check started.')

        current_info = get_current_hotspot_wifi_info()
        current_ssid = current_info.get('ssid', '').strip()
        self.log_wifi(f"SSID check: current='{current_ssid}', expected='{window.hotspot_ssid}'.")
        current_password = current_info.get('passphrase', '').strip()
        if current_ssid == window.hotspot_ssid and current_password == window.hotspot_password:
            self.log_wifi('SSID and password already match; no hotspot credential change required.')
        else:
            changed, message = set_current_hotspot_ssid(window.hotspot_ssid, window.hotspot_password)
            self.log_wifi(
                f"SSID configuration result: changed={changed}, {message}",
                logging.INFO if changed else logging.ERROR,
            )
            if changed and not window.hotspot_password_user_set:
                window.hotspot_password = get_current_hotspot_wifi_info().get(
                    'passphrase', window.hotspot_password
                )

        diagnostics = run_hotspot_diagnostics(
            window.hotspot_nic,
            window.hotspot_network,
            window.hotspot_gateway,
            internet_nic=getattr(window, 'internet_nic', None),
        )
        self.log_wifi(
            f"Hotspot active check: {diagnostics['active']}. "
            f"{diagnostics['text'].replace(chr(10), ' | ')}"
        )
        if diagnostics['active']:
            self.log_wifi('Hotspot is already active; keeping current hotspot running.')
        else:
            started, message = set_hotspot_enabled(
                True,
                window.hotspot_ssid,
                internet_nic=getattr(window, 'internet_nic', None),
                hotspot_nic=window.hotspot_nic,
                hotspot_network=window.hotspot_network,
                hotspot_gateway=window.hotspot_gateway,
            )
            self.log_wifi(
                f"Hotspot enable result: started={started}, {message}",
                logging.INFO if started else logging.ERROR,
            )

        # Apply hotspot client isolation firewall rules (Check -> Configure -> Verify)
        # Check-first policy: skip redundant PowerShell configuration if rules are already valid
        fw_init = apply_hotspot_firewall_rules(
            web_port=5000,
            hotspot_network=window.hotspot_network,
            hotspot_gateway=window.hotspot_gateway,
            enforce_hotspot_active=False,
            skip_if_already_valid=True,
        )
        self.log_wifi(f"Hotspot client isolation firewall result: {fw_init['summary']}")

        self.log_wifi(
            f"Network settings registered: NIC='{window.hotspot_nic.get('display', '')}', "
            f"IP='{window.hotspot_nic.get('ip', '')}', network='{window.hotspot_network}', "
            f"gateway='{window.hotspot_gateway}'."
        )
        self.log_wifi('Hotspot startup check completed.')

    def start_captive_portal(self):
        window = self.window
        portal_url = f"http://{window.hotspot_gateway}:5000/scan"
        self.stop_captive_portal()
        window.captive_portal_service = self.captive_portal_service(
            window.hotspot_gateway,
            portal_url,
            self.is_client_internet_approved,
            self.get_upstream_dns_servers,
            status_sink=lambda text: self.update_captive_portal_status(window, text),
        )
        messages = window.captive_portal_service.start()
        window.captive_portal_servers = window.captive_portal_service.servers
        return messages

    def restore_persisted_sessions(self, sessions, history):
        """Merge persisted LinkShare sessions and rebuild token indexes."""
        with self.session_identity_lock:
            for client_ip, session in sessions.items():
                token_id = session.get('client_token_id')
                if token_id:
                    duplicate_ip = next(
                        (
                            ip for ip, current in self.shared_sessions.items()
                            if current.get('client_token_id') == token_id and ip != client_ip
                        ),
                        None,
                    )
                    if duplicate_ip:
                        current = self.shared_sessions.pop(duplicate_ip)
                        if str(current.get('last_seen', '')) > str(session.get('last_seen', '')):
                            session.update(current)
                self.shared_sessions[client_ip] = session
        self.usage_history.extend(history)
        for client_ip, session in sessions.items():
            token_id = session.get('client_token_id')
            if token_id:
                self.client_identity_map[token_id] = client_ip

    def stop_captive_portal(self):
        window = self.window
        service = getattr(window, 'captive_portal_service', None)
        if service is not None:
            service.stop()
        window.captive_portal_servers = []

    def open_settings_dialog(self):
        window = self.window
        default_zones = list(self.get_default_zones())
        before_settings = {
            'zones': default_zones,
            'ssid': window.hotspot_ssid,
            'password': window.hotspot_password,
            'internet_nic': window.internet_nic,
            'hotspot_nic': window.hotspot_nic,
            'image': window.hotspot_image_path,
            'network': (window.hotspot_network, window.hotspot_gateway),
            'max_connections': window.max_connections,
            'hotspot_limit': window.windows_hotspot_limit,
            'sound_enabled': window.approval_sound_enabled,
            'sounds': list(window.approval_sounds),
            'startup': window.startup_enabled,
            'file_transfer': (
                window.file_transfer_minutes,
                window.provide_internet_for_file_transfer,
            ),
            'colors': list(window.color_options),
            'fares': list(self.runtime_settings.get('internet_fares', self.default_internet_fares)),
            'fare_dir': window.fare_base_dir,
        }
        # Update interfaces list dynamically before opening settings dialog
        window.interfaces = self.get_network_interfaces()
        dialog = self.integrated_settings_dialog(
            default_zones,
            window.fare_base_dir,
            window.hotspot_ssid,
            window.hotspot_password,
            window.interfaces,
            window.internet_nic['display'],
            window.hotspot_nic['display'],
            window.hotspot_image_path,
            window.hotspot_network,
            window.hotspot_gateway,
            window.max_connections,
            window.windows_hotspot_limit,
            window.approval_sound_enabled,
            window.approval_sounds,
            self.approval_sound_dir,
            window.startup_enabled,
            window.file_transfer_minutes,
            window.provide_internet_for_file_transfer,
            window.color_options,
            window,
        )
        settings = QSettings(self.settings_file, QSettings.IniFormat)
        self.restore_window_geometry(dialog, settings, 'windows/settings_dialog', QSize(520, 650))
        dialog_result = dialog.exec()
        self.save_window_geometry(dialog, settings, 'windows/settings_dialog')
        if dialog_result != QDialog.Accepted:
            return

        settings_changed = any((
            dialog.zones != before_settings['zones'],
            dialog.get_hotspot_ssid() != before_settings['ssid'],
            dialog.get_hotspot_password() != before_settings['password'],
            dialog.get_internet_nic() != before_settings['internet_nic'],
            dialog.get_hotspot_nic() != before_settings['hotspot_nic'],
            dialog.get_hotspot_image() != before_settings['image'],
            dialog.get_hotspot_network() != before_settings['network'],
            dialog.get_max_connections() != before_settings['max_connections'],
            dialog.get_windows_hotspot_limit() != before_settings['hotspot_limit'],
            dialog.get_approval_sound_enabled() != before_settings['sound_enabled'],
            dialog.get_approval_sounds() != before_settings['sounds'],
            dialog.get_startup_enabled() != before_settings['startup'],
            dialog.get_file_transfer_settings() != before_settings['file_transfer'],
            dialog.get_color_options() != before_settings['colors'],
            dialog.get_internet_fares() != before_settings['fares'],
            dialog.get_fare_path() != before_settings['fare_dir'],
        ))
        self.set_default_zones(list(dialog.zones))

        previous_ssid = window.hotspot_ssid
        new_ssid = dialog.get_hotspot_ssid()
        new_password = dialog.get_hotspot_password()
        window.hotspot_ssid = new_ssid
        if new_ssid != previous_ssid or new_password != window.hotspot_password:
            changed, message = set_current_hotspot_ssid(new_ssid, new_password)
            self.log_wifi(f"SSID changed by settings: {message}")
            if not changed:
                QMessageBox.warning(window, "SSID change failed", message)
            else:
                window.hotspot_password = new_password
                window.hotspot_password_user_set = True

        window.internet_nic = dialog.get_internet_nic()
        window.hotspot_nic = dialog.get_hotspot_nic()
        window.hotspot_image_path = dialog.get_hotspot_image()
        window.hotspot_network, window.hotspot_gateway = dialog.get_hotspot_network()
        window.max_connections = dialog.get_max_connections()
        window.windows_hotspot_limit = dialog.get_windows_hotspot_limit()
        window.approval_sound_enabled = dialog.get_approval_sound_enabled()
        window.approval_sounds = dialog.get_approval_sounds()
        window.startup_enabled = dialog.get_startup_enabled()
        (
            window.file_transfer_minutes,
            window.provide_internet_for_file_transfer,
        ) = dialog.get_file_transfer_settings()
        window.color_options = dialog.get_color_options()
        self.runtime_settings['color_options'] = window.color_options
        try:
            self.set_startup_registration(self.application_dir, window.startup_enabled)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(window, "Startup registration failed", str(exc))
        self.runtime_settings['internet_fares'] = dialog.get_internet_fares()
        self.runtime_settings['max_connections'] = window.max_connections
        self.runtime_settings['settings_active_tab'] = dialog.settings_tabs.currentIndex()

        new_fare_path = dialog.get_fare_path()
        if new_fare_path:
            window.fare_base_dir = new_fare_path

        window.refresh_internet_nic()
        window.update_hotspot_info()
        window.update_connection_summary()
        window.diagnose_hotspot()
        window.persist_settings()
        if settings_changed:
            QMessageBox.information(window, "Success", "Settings updated successfully.")
        window.update_zone_combo_items()
        window.update_zone_buttons()

    def refresh_internet_nic(self):
        window = self.window
        window.nic_combo.blockSignals(True)
        window.nic_combo.clear()
        for display_name, ip, is_connected, _is_wireless in window.interfaces:
            window.nic_combo.addItem(display_name, ip)
            index = window.nic_combo.count() - 1
            window.nic_combo.setItemData(index, is_connected, Qt.UserRole + 1)
            window.nic_combo.setItemData(
                index,
                QColor(0, 180, 0) if is_connected else QColor(220, 0, 0),
                Qt.ForegroundRole,
            )
        index = window.nic_combo.findData(window.internet_nic['ip'])
        if index >= 0:
            window.nic_combo.setCurrentIndex(index)
        window.nic_combo.blockSignals(False)
        window.update_qr_code()

    def on_nic_index_changed(self, index):
        window = self.window
        if index >= 0:
            window.internet_nic = {
                'display': window.nic_combo.itemText(index),
                'ip': window.nic_combo.itemData(index, Qt.UserRole),
            }
            window.persist_settings()
        window.update_qr_code()

    def rescan_network_interfaces(self):
        window = self.window
        window.interfaces = self.get_network_interfaces()
        opt_internet, opt_hotspot = choose_optimal_adapters(
            window.interfaces,
            window.internet_nic.get('display', ''),
            window.internet_nic.get('ip', ''),
            window.hotspot_nic.get('display', ''),
            window.hotspot_nic.get('ip', ''),
        )
        internet_interface = opt_internet if opt_internet[0] else self.choose_preferred_interface(
            window.interfaces, window.internet_nic['display'], window.internet_nic['ip'], wireless_only=False
        )
        hotspot_interface = opt_hotspot if opt_hotspot[0] else self.choose_preferred_interface(
            window.interfaces, window.hotspot_nic['display'], window.hotspot_nic['ip'], wireless_only=True
        )
        window.internet_nic = {'display': internet_interface[0], 'ip': internet_interface[1]}
        window.hotspot_nic = {'display': hotspot_interface[0], 'ip': hotspot_interface[1]}
        self.refresh_internet_nic()
        window.update_hotspot_info()
        window.persist_settings()

    def update_hotspot_info(self):
        window = self.window
        if hasattr(window, 'hotspot_name_label'):
            window.hotspot_name_label.setText(
                f"â€¢ Active Hotspot Name: <b>{window.hotspot_ssid}</b> (Auto-started)"
            )
        if hasattr(window, 'hotspot_nic_label'):
            window.hotspot_nic_label.setText(f"â€¢ Hotspot NIC: <b>{window.hotspot_nic['display']}</b>")
        if hasattr(window, 'hotspot_network_label'):
            window.hotspot_network_label.setText(
                f"â€¢ Hotspot IP range: <b>{window.hotspot_network}</b> / gateway: <b>{window.hotspot_gateway}</b>"
            )
        if hasattr(window, 'hotspot_image_label'):
            if window.hotspot_image_path and os.path.exists(window.hotspot_image_path):
                pixmap = QPixmap(window.hotspot_image_path)
                if not pixmap.isNull():
                    window.hotspot_image_label.setPixmap(
                        pixmap.scaled(320, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    return
            window.hotspot_image_label.clear()

    def diagnose_hotspot(self):
        window = self.window
        result = run_hotspot_diagnostics(
            window.hotspot_nic,
            window.hotspot_network,
            window.hotspot_gateway,
            internet_nic=getattr(window, 'internet_nic', None),
        )
        if hasattr(window, 'hotspot_status_btn'):
            if result['active']:
                window.hotspot_status_btn.setText('Current status: On')
                window.hotspot_status_btn.setStyleSheet(
                    "QLabel { background-color: #e8f5e9; color: #1b5e20; font-weight: bold; "
                    "border: 1px solid #1b5e20; border-radius: 4px; padding: 5px 10px; }"
                )
            else:
                window.hotspot_status_btn.setText('Current status: Off')
                window.hotspot_status_btn.setStyleSheet(
                    "QLabel { background-color: #ffebee; color: #b71c1c; font-weight: bold; "
                    "border: 1px solid #8e0000; border-radius: 4px; padding: 5px 10px; }"
                )
        if hasattr(window, 'hotspot_status_label'):
            window.hotspot_status_label.setText(result['text'].replace('\n', ' | '))
            window.hotspot_status_label.setStyleSheet(
                "color: #16803c; font-weight: bold;" if result['active']
                else "color: #a15c00; font-weight: bold;"
            )
        return result

    def update_connection_summary(self):
        window = self.window
        now_timestamp = datetime.datetime.now().timestamp()
        for session in self.shared_sessions.values():
            if session.get('status') == 'Approved':
                remaining = max(0, int(session.get('end_timestamp', 0) - now_timestamp))
                session['remaining_seconds'] = remaining
                if remaining == 0:
                    session['status'] = 'Expired'
                    session['connection_status'] = 'Closed'
                    session['remaining_seconds'] = 0
                    session['completed_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.append_usage_log('completed', session)
                    try:
                        self.app_database.save_session(session)
                    except (OSError, sqlite3.Error):
                        pass
                    self.notify_status_change()

        active_statuses = {'Pending', 'Approved'}
        active_count = sum(
            1 for session in self.shared_sessions.values()
            if session.get('status') in active_statuses
        )
        window.status_label.setText(
            f"Devices connected: {active_count} of {window.max_connections}"
        )
        client_count, max_client_count, error = get_windows_hotspot_client_limits()
        if hasattr(window, 'windows_hotspot_clients_label'):
            if max_client_count is not None:
                window.windows_hotspot_clients_label.setText(
                    f"Windows Mobile Hotspot: {client_count} of {max_client_count} "
                    "(actual Windows limit; read-only)"
                )
            else:
                window.windows_hotspot_clients_label.setText(error)
        self.update_usage_history_tables()

    def update_usage_history_tables(self):
        render_usage_history_tables(
            self.window, self.usage_history, self.shared_sessions, self.get_record_price
        )

    def update_selected_usage_history(self):
        window = self.window
        if not hasattr(window, 'usage_history_tabs'):
            return
        if window.usage_history_tabs.currentIndex() == window.usage_history_tabs.count() - 1:
            self.update_usage_history_tables()

    def on_usage_history_tab_changed(self, _index):
        self.update_usage_history_tables()

    def adjust_linkshare_spacing(self):
        """Fit the hotspot pane's spacing and image area to the splitter height."""
        window = self.window
        if not hasattr(window, 'linkshare_splitter'):
            return
        pane_height = window.linkshare_splitter.sizes()[0]
        compact = pane_height < 420
        if hasattr(window, 'hotspot_control_layout'):
            window.hotspot_control_layout.setSpacing(2 if compact else 6)
        if hasattr(window, 'qr_layout'):
            window.qr_layout.setSpacing(0 if compact else 1)
        if hasattr(window, 'hotspot_image_label'):
            window.hotspot_image_label.setMinimumHeight(0 if compact else 60)
            window.hotspot_image_label.setMaximumHeight(80 if compact else 140)
        if hasattr(window, 'hotspot_qr_label'):
            qr_size = max(120, min(220, int((pane_height - 55) * 0.9)))
            window.hotspot_qr_label.setMaximumSize(qr_size, qr_size)
            if hasattr(window, 'hotspot_qr_pixmap') and not window.hotspot_qr_pixmap.isNull():
                window.hotspot_qr_label.setPixmap(
                    window.hotspot_qr_pixmap.scaled(
                        qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
            if hasattr(window, 'hotspot_network_qr_label'):
                window.hotspot_network_qr_label.setMaximumSize(qr_size, qr_size)
            if hasattr(window, 'hotspot_network_pixmap') and not window.hotspot_network_pixmap.isNull():
                window.hotspot_network_qr_label.setPixmap(
                    window.hotspot_network_pixmap.scaled(
                        qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )

    def handle_splitter_moved(self, *_args):
        window = self.window
        self.adjust_linkshare_spacing()
        if hasattr(window, 'linkshare_splitter_save_timer'):
            window.linkshare_splitter_save_timer.start()

    def set_hotspot_state(self, enabled):
        window = self.window
        if enabled:
            current_info = get_current_hotspot_wifi_info()
            current_ssid = current_info.get('ssid', '').strip()
            current_password = current_info.get('passphrase', '').strip()
            if current_ssid != window.hotspot_ssid or current_password != window.hotspot_password:
                changed, credential_message = set_current_hotspot_ssid(
                    window.hotspot_ssid, window.hotspot_password
                )
                self.log_wifi(
                    f"Hotspot start credential check: changed={changed}, {credential_message}",
                    logging.INFO if changed else logging.ERROR,
                )
                if not changed:
                    QMessageBox.warning(
                        window,
                        "í•«ìŠ¤íŒŸ ì„¤ì • ì‹¤íŒ¨",
                        f"í”„ë¡œê·¸ëž¨ ì„¤ì •ê°’ì„ í•«ìŠ¤íŒŸì— ì ìš©í•˜ì§€ ëª»í–ˆìŠµë‹ˆë‹¤.\n{credential_message}",
                    )
                    self.diagnose_hotspot()
                    return
        success, message = set_hotspot_enabled(
            enabled,
            window.hotspot_ssid,
            internet_nic=getattr(window, 'internet_nic', None),
            hotspot_nic=window.hotspot_nic,
            hotspot_network=window.hotspot_network,
            hotspot_gateway=window.hotspot_gateway,
        )
        self.diagnose_hotspot()
        if success:
            if enabled:
                fw_result = apply_hotspot_firewall_rules(
                    web_port=5000,
                    hotspot_network=window.hotspot_network,
                    hotspot_gateway=window.hotspot_gateway,
                    enforce_hotspot_active=False,
                )
                self.log_wifi(f"Hotspot firewall configuration: {fw_result['summary']}")
                msg_body = f"{message}\n\n[ë°©í™”ë²½ ê²©ë¦¬ ê·œì¹™]\n{fw_result['summary']}"
            else:
                msg_body = message
            QMessageBox.information(window, "Hotspot", msg_body)
        else:
            QMessageBox.warning(
                window,
                "Hotspot control",
                f"The Windows hotspot command was not completed:\n{message}\n\n"
                "Use the Windows Mobile Hotspot settings page to finish the operation.",
            )

    def handle_qr_export_completed(self, qr_type, success, detail):
        window = self.window
        if success:
            window.show_auto_close_message(
                QMessageBox.Information,
                'QR ì¶œë ¥ í™•ì¸ ì™„ë£Œ',
                f'{qr_type} QR JPG ë¹„êµ ê²°ê³¼\n{detail}',
                timeout=3000,
            )
        else:
            window.show_auto_close_message(
                QMessageBox.Warning,
                'QR ì¶œë ¥ ì‹¤íŒ¨',
                f'{qr_type} QR JPG ì €ìž¥ ì‹¤íŒ¨\n{detail}',
                timeout=3000,
            )

