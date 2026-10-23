"""Order workflow dashboard callbacks for the integrated administrator UI."""

import datetime
import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from .order_workflow import OrderState


class OrderUiController:
    """Render order state/warnings and execute worker approve/rollback actions."""

    def __init__(self, window, app_database):
        self.window = window
        self.app_database = app_database

    def selected_order_id(self):
        rows = self.window.order_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.window.order_table.item(rows[0].row(), 0).text()

    def refresh_order_dashboard(self):
        window = self.window
        if not hasattr(window, 'order_table'):
            return
        orders = self.app_database.load_orders()
        window.order_table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            for column, key in enumerate(('order_id', 'client_info', 'current_state', 'total_price')):
                item = QTableWidgetItem(str(order.get(key, '')))
                if column == 0:
                    item.setData(Qt.UserRole, order['order_id'])
                window.order_table.setItem(row, column, item)
        self.refresh_order_warnings()

    def refresh_order_warnings(self):
        window = self.window
        if not hasattr(window, 'order_warning_list'):
            return
        window.order_warning_list.clear()
        order_id = self.selected_order_id()
        if not order_id:
            return
        for warning in self.app_database.load_order_notifications(order_id):
            window.order_warning_list.addItem(
                f"[{warning['severity']}] {warning['code']}: {warning['message']}"
            )

    def approve_selected_order(self):
        order_id = self.selected_order_id()
        if not order_id:
            return
        current = self.app_database.get_order_state(order_id)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            if current == OrderState.CONFIGURED.value:
                current = self.app_database.transition_order(
                    order_id, OrderState.USER_CONFIRMED.value,
                    'worker', 'worker approval', timestamp,
                )
            if current == OrderState.USER_CONFIRMED.value:
                current = self.app_database.transition_order(
                    order_id, OrderState.WORKER_REVIEW.value,
                    'worker', 'worker approval', timestamp,
                )
            if current == OrderState.WORKER_REVIEW.value:
                self.app_database.transition_order(
                    order_id, OrderState.PRINT_QUEUED.value,
                    'worker', 'worker approval', timestamp,
                )
        except (KeyError, ValueError, sqlite3.Error) as exc:
            from Common.logger_service import log_event
            log_event('order', 'APPROVAL', f'Order approval failed: {exc}', level=logging.WARNING)
        self.refresh_order_dashboard()

    def rollback_selected_order(self):
        order_id = self.selected_order_id()
        if not order_id:
            return
        current = self.app_database.get_order_state(order_id)
        target = {
            OrderState.CONFIGURED.value: OrderState.UPLOADED.value,
            OrderState.USER_CONFIRMED.value: OrderState.CONFIGURED.value,
            OrderState.WORKER_REVIEW.value: OrderState.CONFIGURED.value,
            OrderState.PRINT_QUEUED.value: OrderState.WORKER_REVIEW.value,
            OrderState.PRINTING.value: OrderState.WORKER_REVIEW.value,
            OrderState.COMPLETED.value: OrderState.PRINT_QUEUED.value,
        }.get(current)
        if target:
            try:
                self.app_database.transition_order(
                    order_id,
                    target,
                    'worker',
                    'manual rollback',
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
            except (KeyError, ValueError, sqlite3.Error) as exc:
                from Common.logger_service import log_event
                log_event('order', 'ROLLBACK', f'Order rollback failed: {exc}', level=logging.WARNING)
        self.refresh_order_dashboard()
