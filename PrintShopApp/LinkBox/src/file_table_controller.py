"""LinkBox transfer-table editing controller."""
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QHeaderView, QLabel, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QWidget,
)


class FileTableController:
    def __init__(self, window):
        self.window = window
    def get_or_create_file_table(self, tab_name):
        table = self.window.tab_tables.get(tab_name)
        if table is not None:
            return table
        table = QTableWidget(0, 11, self.window)
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
        table.customContextMenuRequested.connect(lambda pos, t=table: self.window.show_context_menu(pos, t))
        table.cellDoubleClicked.connect(self.window.on_row_double_clicked)
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
        self.window.tab_tables[tab_name] = table
        self.window.tab_widget.addTab(table, tab_name)
        self.window.tab_widget.setTabToolTip(self.window.tab_widget.indexOf(table), tab_name)
        self.window.update_transfer_tab_colors()
        self.window.apply_transfer_tab_filter()
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
        combo.addItems(self.window._linkbox_runtime_settings.get('color_options', self.window._linkbox_default_color_options))
        combo.setCurrentText(color if color in [combo.itemText(i) for i in range(combo.count())]
                             else self.window._linkbox_default_color_options[0])
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
        self.window._linkbox_app_database.update_transfer_log(target_folder, filename, color=color)
        with self.window._linkbox_transfer_change_condition:
            changed_clients = set()
            for client_id, records in self.window._linkbox_transfer_records_by_client.items():
                for record in records:
                    if record.get('folder') == target_folder and record.get('filename') == filename:
                        if record.get('color') != color:
                            record['color'] = color
                            changed_clients.add(client_id)
            for client_id in changed_clients:
                self.window._linkbox_transfer_change_versions[client_id] = self.window._linkbox_transfer_change_versions.get(client_id, 0) + 1
            if changed_clients:
                self.window._linkbox_transfer_change_condition.notify_all()
        if changed_clients:
            self.window._linkbox_signals.transfer_updated.emit(
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
        self.window._linkbox_app_database.update_transfer_log(target_folder, filename, copies=count)
        with self.window._linkbox_transfer_records_lock:
            changed_clients = set()
            for records in self.window._linkbox_transfer_records_by_client.values():
                for record in records:
                    if record.get('folder') == target_folder and record.get('filename') == filename:
                        if record.get('copies') != count:
                            record['copies'] = count
                            for client_id, client_records in self.window._linkbox_transfer_records_by_client.items():
                                if record in client_records:
                                    changed_clients.add(client_id)
            for client_id in changed_clients:
                self.window._linkbox_transfer_change_versions[client_id] = self.window._linkbox_transfer_change_versions.get(client_id, 0) + 1
            if changed_clients:
                self.window._linkbox_transfer_change_condition.notify_all()

