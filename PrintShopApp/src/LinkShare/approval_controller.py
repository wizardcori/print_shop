"""LinkShare customer internet approval workflow.

The application shell owns persistence and session storage; this controller
owns the approval dialog and the LinkShare-specific state transition.
"""

import datetime

from PySide6.QtWidgets import QCheckBox, QMessageBox


class ApprovalController:
    def __init__(
        self,
        *,
        parent,
        sessions,
        append_usage_log,
        notify_status_change,
        bring_to_front,
        update_connection_summary,
        play_approval_sound,
        stop_approval_sound,
        persist_settings,
        show_auto_close_message,
        get_sound_enabled,
        set_sound_enabled,
    ):
        self.parent = parent
        self.sessions = sessions
        self.append_usage_log = append_usage_log
        self.notify_status_change = notify_status_change
        self.bring_to_front = bring_to_front
        self.update_connection_summary = update_connection_summary
        self.play_approval_sound = play_approval_sound
        self.stop_approval_sound = stop_approval_sound
        self.persist_settings = persist_settings
        self.show_auto_close_message = show_auto_close_message
        self.get_sound_enabled = get_sound_enabled
        self.set_sound_enabled = set_sound_enabled

    def handle_customer_request(self, client_ip, minutes, dur_str):
        self.bring_to_front()
        self.update_connection_summary()
        session = self.sessions.get(client_ip)
        if not session:
            return
        is_extension = bool(session.get('extension_pending'))
        if session.get('status') != 'Pending' and not (
            is_extension and session.get('status') == 'Approved'
        ):
            return

        approval_box = QMessageBox(self.parent)
        approval_box.setWindowTitle("Internet Request")
        approval_box.setText(
            f"Client IP: {client_ip}\nSelected time: {dur_str}\n\nApprove Internet access?"
        )
        approval_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        approval_box.setDefaultButton(QMessageBox.No)
        sound_checkbox = QCheckBox("사용승인 소리알림")
        sound_checkbox.setChecked(self.get_sound_enabled())
        approval_box.setCheckBox(sound_checkbox)
        if self.get_sound_enabled():
            self.play_approval_sound()
        reply = approval_box.exec()
        self.stop_approval_sound()
        if sound_checkbox.isChecked() != self.get_sound_enabled():
            self.set_sound_enabled(sound_checkbox.isChecked())
            self.persist_settings()

        if reply == QMessageBox.Yes:
            self._approve(session, client_ip, minutes, is_extension)
        else:
            self._reject(session, client_ip, is_extension)
        self.update_connection_summary()

    def _approve(self, session, client_ip, minutes, is_extension):
        start = datetime.datetime.now()
        if is_extension:
            current_end = max(float(session.get('end_timestamp', 0)), start.timestamp())
            end = datetime.datetime.fromtimestamp(current_end) + datetime.timedelta(minutes=minutes)
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
            self.append_usage_log('approval', session, requested_minutes=minutes,
                                  approved_price=session.get('approved_price', 0))
            self.notify_status_change()
            self.show_auto_close_message(QMessageBox.Information, 'Approved',
                                        f'Additional Internet time approved for {client_ip}.')
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
        self.append_usage_log('approval', session, requested_minutes=minutes,
                              approved_price=session.get('approved_price', 0))
        self.notify_status_change()
        self.show_auto_close_message(QMessageBox.Information, "Approved",
                                     f"Internet access started for {client_ip}.")

    def _reject(self, session, client_ip, is_extension):
        if is_extension:
            session.update({'extension_pending': False, 'extension_minutes': 0, 'extension_fare': ''})
            self.append_usage_log(
                'approval', session, status='Rejected', usage_approval='Rejected',
                approval_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            )
            self.notify_status_change()
            QMessageBox.warning(self.parent, 'Rejected',
                                f'Additional Internet request from {client_ip} was rejected.')
            return
        session.update({
            'status': 'Rejected',
            'connection_status': '연결됨',
            'usage_approval': '거부',
            'approval_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'remaining_seconds': 0,
        })
        self.append_usage_log('approval', session)
        self.notify_status_change()
        QMessageBox.warning(self.parent, "Rejected",
                            f"Internet request from {client_ip} was rejected.")
