"""LinkBox transfer-tab and received-file UI controller.

The integrated window hosts the widgets, but LinkBox owns the received-file
workflow: filtering tabs, validating files, changing task state, handling
remote updates, and exposing row actions.  Keeping those operations here
leaves the application shell responsible only for wiring services together.
"""

import datetime
import os
import re
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from .file_receiver_service import handle_incoming_files
from .transfer_summary import create_transfer_summary


class TransferUiController:
    """Own LinkBox's transfer-table interactions for an integrated window."""

    def __init__(self, window):
        self.window = window

    def apply_transfer_tab_filter(self, *_args):
        window = self.window
        period = window.transfer_period_combo.currentText()
        today = datetime.date.today()
        start = end = None
        if period in ('오늘', 'Today'):
            start = end = today
        elif period in ('이번 달', 'This month'):
            start = today.replace(day=1)
            end = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        elif period in ('기간', 'Custom'):
            start = window.transfer_start_date.date().toPython()
            end = window.transfer_end_date.date().toPython()
            if start > end:
                start, end = end, start

        show_completed = window.completed_only_checkbox.isChecked()
        for index in range(window.tab_widget.count()):
            table = window.tab_widget.widget(index)
            if table is getattr(window, 'print_job_table', None):
                window.tab_widget.setTabVisible(index, True)
                continue

            visible = True
            if isinstance(table, QTableWidget):
                # The checkbox filters whole tabs.  Rows inside a visible tab
                # remain visible so the operator can inspect the full batch.
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
                        match = re.search(
                            r'_(\d{8})-\d{6}$',
                            os.path.basename(str(item.data(Qt.UserRole) or '')),
                        )
                        if match:
                            folder_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
                            break
                visible = visible and folder_date is not None and start <= folder_date <= end

            window.tab_widget.setTabVisible(index, visible)
        self.update_transfer_tab_colors()

    def inspect_selected_transfer_tab(self, index):
        """Recheck files whenever the administrator selects a transfer tab."""
        window = self.window
        if index < 0:
            return
        table = window.tab_widget.widget(index)
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
                    size_mismatch = window._linkbox_format_size(os.path.getsize(actual_path)) != stored_size
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
        window = self.window
        current_index = window.tab_widget.currentIndex()
        for index in range(window.tab_widget.count()):
            window.tab_widget.tabBar().setTabTextColor(
                index, QColor('#1565c0' if index == current_index else '#455a64')
            )

    def set_file_task_completed(self, table, row, completed):
        window = self.window
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
        window._linkbox_app_database.update_transfer_completed(
            str(file_item.data(Qt.UserRole) or ''), file_item.text(), completed
        )
        with window._linkbox_transfer_records_lock:
            changed_clients = set()
            for client_id, records in window._linkbox_transfer_records_by_client.items():
                for record in records:
                    if record.get('folder') == str(file_item.data(Qt.UserRole) or '') \
                            and record.get('filename') == file_item.text():
                        record['task_completed'] = completed
                        changed_clients.add(client_id)
            for client_id in changed_clients:
                window._linkbox_transfer_change_versions[client_id] = (
                    window._linkbox_transfer_change_versions.get(client_id, 0) + 1
                )
            if changed_clients:
                window._linkbox_transfer_change_condition.notify_all()
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
        window = self.window
        index = window.tab_widget.tabBar().tabAt(pos)
        if index < 0:
            return
        table = window.tab_widget.widget(index)
        if not isinstance(table, QTableWidget):
            return
        menu = QMenu(window.tab_widget)
        complete = menu.addAction('작업완료')
        incomplete = menu.addAction('작업미완료')
        chosen = menu.exec(window.tab_widget.tabBar().mapToGlobal(pos))
        if chosen == complete:
            self.set_tab_tasks_completed(table, True)
        elif chosen == incomplete:
            self.set_tab_tasks_completed(table, False)

    def on_save_tab_changed(self, _tab_name):
        # Reserved for future per-zone save-tab behavior.  The callback stays
        # in LinkBox so the UI layout never needs to know about the shell.
        return None

    def restore_transfer_logs(self, transfer_logs):
        """Restore persisted LinkBox rows before the UI starts serving files."""
        window = self.window
        for (target_folder, identity), records in transfer_logs.items():
            if not records:
                continue
            file_list = [(
                record.get('user_name', 'Guest'),
                record.get('user_info', 'Unknown'),
                record.get('cookie', ''),
                record.get('zone', 'Default'),
                record.get('filename', ''),
                record.get('copies') if record.get('copies') is not None else 1,
                record.get('size', ''),
                record.get('received_time', ''),
                record.get('status', 'Completed (100%)'),
                record.get('color', window._linkbox_default_color_options[0]),
            ) for record in records]
            handle_incoming_files(
                window,
                file_list,
                target_folder,
                identity,
                window._linkbox_file_receiver_dependencies,
                persist=False,
            )
            table = next(
                (
                    candidate for candidate in window.tab_tables.values()
                    if any(
                        candidate.item(row, 3)
                        and str(candidate.item(row, 3).data(Qt.UserRole) or '') == target_folder
                        for row in range(candidate.rowCount())
                    )
                ),
                None,
            )
            if table is None:
                continue
            for record in records:
                for row in range(table.rowCount()):
                    item = table.item(row, 3)
                    if (
                        item
                        and item.text() == record.get('filename', '')
                        and str(item.data(Qt.UserRole) or '') == target_folder
                    ):
                        self.set_file_task_completed(
                            table, row, record.get('task_completed', False)
                        )

    def close_tab(self, index):
        """Close a received-file tab created by LinkBox."""
        window = self.window
        widget = window.tab_widget.widget(index)
        for identity, table in list(window.tab_tables.items()):
            if table is widget:
                del window.tab_tables[identity]
                break
        window.tab_widget.removeTab(index)

    def update_zone_combo_items(self):
        window = self.window
        window.zone_combo.blockSignals(True)
        window.zone_combo.clear()
        window.zone_combo.addItems(window._linkbox_get_default_zones() + ["Custom Input"])
        window.zone_combo.blockSignals(False)

    def update_save_tab_combo_items(self):
        window = self.window
        window.save_tab_combo.blockSignals(True)
        window.save_tab_combo.clear()
        window.save_tab_combo.addItems(window._linkbox_get_default_save_tabs())
        window.save_tab_combo.blockSignals(False)

    def update_zone_buttons(self):
        window = self.window
        while window.zone_buttons_layout.count():
            item = window.zone_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for index, zone_name in enumerate(window._linkbox_get_default_zones()):
            btn = QPushButton(zone_name)
            btn.setMinimumHeight(34)
            btn.setStyleSheet(
                """
                QPushButton { background-color: #f8f9fa; color: #17202a;
                              border: 1px solid #6c757d; border-radius: 4px;
                              padding: 6px; font-weight: bold; }
                QPushButton:hover { background-color: #dbeafe; color: #0b3d91; }
                QPushButton:pressed { background-color: #93c5fd; color: #102a43; }
                """
            )
            btn.clicked.connect(lambda _checked, z=zone_name: window.select_zone_from_button(z))
            window.zone_buttons_layout.addWidget(btn, index // 3, index % 3)

    def select_zone_from_button(self, zone_name):
        window = self.window
        index = window.zone_combo.findText(zone_name)
        if index >= 0:
            window.zone_combo.setCurrentIndex(index)
        else:
            window.zone_combo.setCurrentText("Custom Input")
            window.zone_input.setText(zone_name)

    def select_save_folder(self):
        window = self.window
        current_folder = window._linkbox_get_default_upload_folder()
        dir_path = QFileDialog.getExistingDirectory(window, "Select Save Directory", current_folder)
        if dir_path:
            window._linkbox_set_default_upload_folder(dir_path)
            window.folder_input.setText(dir_path)
            window.persist_settings()

    def on_zone_changed(self, text):
        window = self.window
        if text == "Custom Input":
            window.zone_input.setEnabled(True)
            window.zone_input.setText("")
        else:
            window.zone_input.setEnabled(False)
            window.zone_input.setText(text)

    def handle_remote_transfer_update(self, target_folder, filename, copies, color):
        for table in self.window.tab_tables.values():
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

    def handle_deleted_files(self, identity, file_names):
        tab_name = os.path.basename(identity)
        table = self.window.tab_tables.get(tab_name)
        if table is None:
            return
        for row in range(table.rowCount() - 1, -1, -1):
            item = table.item(row, 3)
            if item and item.text() in file_names:
                table.removeRow(row)

    def show_batch_notification(self):
        window = self.window
        if not window.pending_batch_files:
            return
        count = len(window.pending_batch_files)
        window.pending_batch_files.clear()
        QMessageBox.information(window, "파일 수신 완료", f"파일 {count}개를 수신했습니다.")

    def on_row_double_clicked(self, row, _col):
        window = self.window
        table = window.sender()
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
        window = self.window
        item = table.item(row, 3)
        if item is None:
            return
        file_path = os.path.join(str(item.data(Qt.UserRole) or ''), item.text())
        answer = QMessageBox.question(
            window, "삭제 확인", f"파일을 삭제할까요?\n{item.text()}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
            table.removeRow(row)
        except OSError as exc:
            QMessageBox.warning(window, "삭제 실패", str(exc))

    def write_transfer_summary(self, table, row):
        window = self.window
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
            # Do not depend on the .txt file association.
            subprocess.Popen(['notepad.exe', os.path.normpath(summary_path)])
        except (OSError, subprocess.SubprocessError) as exc:
            QMessageBox.warning(window, "요약정보 열기 실패", str(exc))

    def create_transfer_summary(self, table, target_folder):
        return create_transfer_summary(
            self.window, table, target_folder, self.window._linkbox_default_color_options
        )
