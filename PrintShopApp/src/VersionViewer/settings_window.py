from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton, QWidget, QScrollArea
)


class SettingsWindow(QDialog):
    """탭 추가 기능만 제공하는 설정 윈도우"""

    def __init__(self, title: str = "설정", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 650)

        layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget(self)
        layout.addWidget(self.tab_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def add_tab(self, tab_widget: QWidget, title: str, scrollable: bool = False) -> int:
        """외부에서 생성한 탭 위젯을 세팅 윈도우에 추가"""
        if scrollable:
            scroll = QScrollArea(self.tab_widget)
            scroll.setWidgetResizable(True)
            scroll.setWidget(tab_widget)
            return self.tab_widget.addTab(scroll, title)
        return self.tab_widget.addTab(tab_widget, title)