"""LinkBox printer detection UI integration."""
import logging
import os
import sqlite3

from PySide6.QtWidgets import QTableWidgetItem
def handle_print_request(window, request, order_service):
    """Append a detected printer job to the LinkBox Print Jobs tab."""
    document_name = os.path.basename(str(request.document_name or request.output_path or ''))
    try:
        order_service.mark_print_event(document_name, request.status)
    except (OSError, sqlite3.Error, ValueError) as exc:
        try:
            from Common.logger_service import log_event
            log_event('order', 'PRINT_EVENT', f'Order state update failed for document={document_name}: {exc}', level=logging.ERROR)
        except Exception:
            pass
    matched_table = None
    matched_row = -1
    for transfer_table in window.tab_tables.values():
        for candidate_row in range(transfer_table.rowCount()):
            filename_item = transfer_table.item(candidate_row, 3)
            if filename_item and os.path.basename(filename_item.text()).casefold() == document_name.casefold():
                matched_table = transfer_table
                matched_row = candidate_row
                break
        if matched_table is not None:
            break
    if matched_table is not None:
        window.tab_widget.setCurrentWidget(matched_table)
        matched_table.selectRow(matched_row)
        detected_row = matched_row + 1
        matched_table.setSortingEnabled(False)
        matched_table.insertRow(detected_row)
        detected_values = {
            0: '검출',
            1: f'Printer: {request.printer_name}',
            2: f'Job ID: {request.job_id or ""}',
            3: f'↳ {document_name}',
            6: request.status,
            9: '인쇄 검출됨',
            10: request.output_path or '',
        }
        for column, value in detected_values.items():
            matched_table.setItem(detected_row, column, QTableWidgetItem(str(value)))
        matched_table.selectRow(detected_row)
        from Common.logger_service import log_event
        log_event('printer', 'MATCH', f'Print job matched open transfer tab: filename={document_name} row={matched_row}')
    else:
        from Common.logger_service import log_event
        log_event('printer', 'MISMATCH', f'Print job filename did not match an open transfer tab: filename={document_name}', level=logging.WARNING)
    return

