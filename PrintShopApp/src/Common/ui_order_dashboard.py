"""PySide6 order dashboard used by the integrated administrator window."""
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


def create_order_dashboard(window: Any) -> QWidget:
    """Build an order table with warning details and worker actions."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.addWidget(QLabel('Orders / 주문 상태'))
    window.order_table = QTableWidget(0, 4, widget)
    window.order_table.setHorizontalHeaderLabels(['Order ID', 'Client', 'State', 'Total'])
    window.order_table.setSelectionBehavior(QTableWidget.SelectRows)
    window.order_table.setEditTriggers(QTableWidget.NoEditTriggers)
    window.order_table.itemSelectionChanged.connect(window.refresh_order_warnings)
    layout.addWidget(window.order_table)

    layout.addWidget(QLabel('Validation warnings / 검증 경고'))
    window.order_warning_list = QListWidget(widget)
    layout.addWidget(window.order_warning_list)

    action_layout = QHBoxLayout()
    window.order_approve_button = QPushButton('Worker approve / 작업자 승인', widget)
    window.order_approve_button.clicked.connect(window.approve_selected_order)
    window.order_rollback_button = QPushButton('Rollback / 이전 단계 롤백', widget)
    window.order_rollback_button.clicked.connect(window.rollback_selected_order)
    window.order_refresh_button = QPushButton('Refresh / 새로고침', widget)
    window.order_refresh_button.clicked.connect(window.refresh_order_dashboard)
    action_layout.addWidget(window.order_approve_button)
    action_layout.addWidget(window.order_rollback_button)
    action_layout.addWidget(window.order_refresh_button)
    layout.addLayout(action_layout)
    return widget
