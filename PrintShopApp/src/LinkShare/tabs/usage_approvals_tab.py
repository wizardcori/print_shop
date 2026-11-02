from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QHeaderView

class UsageApprovalsTab(QWidget):
    def __init__(self, window=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        headers = ["Usage Approval", "Approval Time", "Requested Usage Time", "IP Address", "Cookie", "User Info"]
        
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #ffffff; color: #263238; gridline-color: #b0bec5; }"
            " QHeaderView::section { background-color: #1565c0; color: white; font-weight: bold; padding: 4px; }"
        )
        
        layout.addWidget(self.table)