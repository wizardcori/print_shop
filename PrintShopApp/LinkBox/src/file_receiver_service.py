"""LinkBox file receiver workflow."""
from dataclasses import dataclass
import datetime
import logging
import os
import re
import sqlite3

from LinkBox.src.print_log_writer import play_notification_sound, register_today_transfer_file
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem


@dataclass
class FileReceiverDependencies:
    app_database: object
    file_transfer_minutes: int
    provide_internet_for_file_transfer: bool
    safe_folder_part: object
    format_size: object
    default_color_options: list


def find_transfer_filename_row(table, original_filename):
    """Find the top-level parent row matching original_filename."""
    for row in range(table.rowCount()):
        item = table.item(row, 3)
        if item is None:
            continue
        is_child = item.data(Qt.UserRole + 6) == 1
        stored_name = item.data(Qt.UserRole + 5) or item.text()
        if not is_child and stored_name == original_filename:
            return row
    return None


def transfer_child_insert_row(table, parent_row):
    """Determine the insertion index immediately after existing children of parent_row."""
    insert_row = parent_row + 1
    while insert_row < table.rowCount():
        item = table.item(insert_row, 3)
        if item is not None and item.data(Qt.UserRole + 6) == 1:
            insert_row += 1
        else:
            break
    return insert_row


def handle_incoming_files(window, file_list, target_folder, identity, deps, persist=True):
    app_database = deps.app_database
    file_transfer_minutes = deps.file_transfer_minutes
    provide_internet_for_file_transfer = deps.provide_internet_for_file_transfer
    safe_folder_part = deps.safe_folder_part
    format_size = deps.format_size
    DEFAULT_COLOR_OPTIONS = deps.default_color_options
    window.last_target_folder = target_folder
    transfer_started = datetime.datetime.now()
    transfer_record = {
        'transfer_key': f"{identity}:{transfer_started.isoformat()}",
        'client_ip': '-',
        'client_token_id': identity,
        'started_at': transfer_started.strftime('%Y-%m-%d %H:%M:%S'),
        'expires_at': (transfer_started + datetime.timedelta(
            minutes=window.file_transfer_minutes
        )).strftime('%Y-%m-%d %H:%M:%S'),
        'file_count': len(file_list),
        # File transfer is not internet usage and is never charged.  The
        # setting only controls whether internet access may be granted
        # alongside a transfer; a successful transfer needs no grant.
        'internet_granted': window.provide_internet_for_file_transfer,
        'charged': False,
    }
    try:
        app_database.save_file_transfer(transfer_record)
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).exception("Failed to save file transfer record")
    try:
        from Common.logger_service import log_event
        log_event('linkbox', 'TRANSFER', f"Files received: count={len(file_list)} target={target_folder} identity={identity}")
    except Exception:
        pass
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
    zone = str(first_record[3]) if len(first_record) > 3 and first_record[3] else 'Default'
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
    table = window.get_or_create_file_table(tab_name)
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
        # Keep repeated uploads of the same file visually grouped.  The
        # transfer table is a QTableWidget (rather than a QTreeWidget),
        # so the hierarchy is represented by an indented child row while
        # the original filename is retained in UserRole for file lookup.
        original_filename = str(values[3])
        parent_row = find_transfer_filename_row(table, original_filename)
        child_row = parent_row is not None
        row = transfer_child_insert_row(table, parent_row) if child_row else table.rowCount()
        table.insertRow(row)
        row_color = QColor('#f7fbff' if row % 2 else '#eaf4ff')
        file_path = os.path.join(target_folder, original_filename)
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
            display_value = value
            if column == 3 and child_row:
                display_value = f"  └─ {original_filename}"
            item = QTableWidgetItem(str(display_value))
            missing_color = QColor('#ffcdd2')
            item.setBackground(
                missing_color if file_missing
                else QColor('#c9f0d2') if column == 9 else row_color
            )
            if file_missing:
                item.setForeground(QColor('#b71c1c'))
                item.setToolTip('파일이 없거나 저장된 파일 크기와 일치하지 않습니다.')
            item.setData(Qt.UserRole, target_folder)
            if column == 3:
                item.setData(Qt.UserRole + 5, original_filename)
                item.setData(Qt.UserRole + 6, 1 if child_row else 0)
            item.setData(Qt.UserRole + 4, file_missing)
            item.setData(Qt.UserRole + 2, identity)
            table.setItem(row, column, item)
        table.item(row, 6).setData(Qt.UserRole + 3, False)
        window.set_copy_controls(table, row, int(values[4]) if values[4] is not None else 1)
        window.set_color_control(table, row, str(values[5] or DEFAULT_COLOR_OPTIONS[0]))
        window.set_completion_checkbox(table, row, False)
        if persist:
            # A second, distinct notification confirms that the detected
            # transfer has actually been inserted into the LinkBox tree.
            play_notification_sound(sound_type='tree')
        if file_missing:
            for control_column in (4, 5, 6):
                control = table.cellWidget(row, control_column)
                if control is not None:
                    control.setEnabled(False)
                    control.setToolTip('파일이 없거나 크기가 일치하지 않아 사용할 수 없습니다.')
        if persist:
            window.pending_batch_files.append(file_info)
        # Automatically make LinkBox-received files available to the
        # printer monitor for later document-name matching.
        registration_filename = original_filename
        registration_time = file_info[7] if len(file_info) >= 8 else (
            file_info[4] if len(file_info) >= 5 else ''
        )
        if registration_filename:
            register_today_transfer_file(
                registration_filename, os.path.join(target_folder, registration_filename),
                registration_time, identity=identity, target_folder=target_folder,
            )
    table.resizeColumnToContents(3)
    table.setColumnWidth(3, min(max(table.columnWidth(3), 260), 520))
    # Keep the copy controls compact; their child buttons must not cause
    # the whole column to expand to the available table width.
    table.setColumnWidth(4, 150)
    table.setSortingEnabled(sorting_enabled)
    # Reapply visibility after rows are inserted. A newly created table
    # was previously filtered while empty and could remain hidden.
    window.apply_transfer_tab_filter()
    if persist:
        window.batch_timer.start()

