from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QHeaderView

class UsageHistoryTab(QWidget):
    def __init__(self, window=None, existing_table=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.table = existing_table
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        headers = ["Request Time", "Approval Time", "Usage Time", "Amount", "Cookie", "User Info"]
        
        if self.table is None:
            self.table = QTableWidget(0, len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setStyleSheet(
                "QTableWidget { background-color: #ffffff; color: #263238; gridline-color: #b0bec5; }"
                " QHeaderView::section { background-color: #1565c0; color: white; font-weight: bold; padding: 4px; }"
            )
        else:
            self.table.setHorizontalHeaderLabels(headers)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setStyleSheet(
                "QTableWidget { background-color: #ffffff; color: #263238; gridline-color: #b0bec5; }"
                " QHeaderView::section { background-color: #1565c0; color: white; font-weight: bold; padding: 4px; }"
            )
            
        layout.addWidget(self.table)