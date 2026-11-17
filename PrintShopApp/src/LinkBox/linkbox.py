"""LinkBox File Receiver Tab & Runtime Implementation."""

import os
import logging
from PySide6.QtWidgets import (
    QWidget, QFileDialog, QTableWidget, QGridLayout, 
    QCheckBox, QSplitter, QGroupBox, QComboBox, QTabWidget, QLabel, QLineEdit, QDateEdit, QPushButton, QVBoxLayout
)
from PySide6.QtCore import Qt, QTimer, QDate, QFile
from PySide6.QtUiTools import QUiLoader

from LinkBox.file_table_controller import FileTableController
from LinkBox.transfer_ui_controller import TransferUiController
from LinkBox.print_ui_controller import open_print_log_viewer, update_print_log_outputs as controller_update_print_log_outputs

from .print_portal import start_print_portal_background

logger = logging.getLogger("printshop.linkbox")

from Common.geometry_manager import AutoSplitterWidget

from .ui.ui_linkbox import Ui_Tab1Widget


class LinkBoxManager(AutoSplitterWidget):
    """LinkBox File Receiver UI와 런타임 비즈니스 로직이 통합된 클래스"""

    title = "File Receiver (LinkBox)"

    def __init__(self, window=None):
        super().__init__(window)
        self.window = window
        
        # 배경 프린트 포털 시작
        start_print_portal_background()

        # UI 파일 로드 및 초기화
        self.init_ui()

    def init_ui(self):
        window = self.window if self.window is not None else self

        # ==========================================
        # 1. 변환된 파이썬 UI 모듈(Ui_Tab1Widget)을 self에 직접 적용
        # ==========================================
        try:
            ui_instance = Ui_Tab1Widget()
            ui_instance.setupUi(self)
            logd("UI_LOAD (Python Module 성공) : Ui_Tab1Widget setupUi 완료")
        except Exception as e:
            loge(f"[오류] UI setupUi 실행 중 예외 발생: {e}")
            # 폴백: UI 로드 실패 시 기본 레이아웃 생성
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_tabs = QTabWidget(self)
            main_layout.addWidget(self.main_tabs)

        # ==========================================
        # 2. 위젯 객체 매핑 및 초기화 실행
        # ==========================================
        self._bind_widgets()
        self._apply_styles()
        self._setup_folder_input()
        self._setup_network_controls()
        self._setup_zone_controls()
        self._setup_splitters()
        self._setup_bottom_area()

        # ==========================================
        # 3. 컨트롤러 초기화
        # ==========================================
        target_window = self.window if self.window is not None else self
        target_window.file_table_controller = FileTableController(target_window)
        target_window.transfer_ui_controller = TransferUiController(target_window)

    def _bind_widgets(self):
        """UI 파일 내 위젯 객체들을 바인딩"""
        # setupUi(self)를 통해 위젯들이 self에 생성되었으므로 w는 self를 가리킵니다.
        w = self
        win = self.window if self.window is not None else self

        win.main_splitter = self.main_splitter = w.findChild(QSplitter, "main_splitter")
        win.top_splitter = self.top_splitter = w.findChild(QSplitter, "top_splitter")
        win.config_group_box = self.config_group_box = w.findChild(QGroupBox, "config_group_box")

        self.group_box = w.findChild(QGroupBox, "group_box")
        self.qr_group_box = w.findChild(QGroupBox, "qr_group_box")
        self.zone_group_box = w.findChild(QGroupBox, "zone_group_box")
        self.print_job_group_box = w.findChild(QGroupBox, "print_job_group_box")
        self.bottom_group_box = w.findChild(QGroupBox, "bottom_group_box")

        win.folder_input = w.findChild(QLineEdit, "folder_input")
        win.folder_btn = w.findChild(QPushButton, "folder_btn")
        win.nic_combo = w.findChild(QComboBox, "nic_combo")
        win.rescan_nic_btn = w.findChild(QPushButton, "rescan_nic_btn")
        win.save_tab_combo = w.findChild(QComboBox, "save_tab_combo")

        win.zone_combo = w.findChild(QComboBox, "zone_combo")
        win.zone_input = w.findChild(QLineEdit, "zone_input")
        win.zone_buttons_widget = w.findChild(QWidget, "zone_buttons_widget")

        win.qr_label = w.findChild(QLabel, "qr_label")
        win.url_label = w.findChild(QLabel, "url_label")

        win.completed_only_checkbox = w.findChild(QCheckBox, "completed_only_checkbox")
        win.transfer_period_combo = w.findChild(QComboBox, "transfer_period_combo")
        win.transfer_start_date = w.findChild(QDateEdit, "transfer_start_date")
        win.transfer_end_date = w.findChild(QDateEdit, "transfer_end_date")
        self.transfer_filter_layout = w.findChild(QWidget, "transfer_filter_layout")

        win.tab_widget = w.findChild(QTabWidget, "tab_widget")
        win.print_job_table = w.findChild(QTableWidget, "print_job_table")

    def _apply_styles(self):
        """GroupBox 및 Label 스타일 적용"""
        gb_style = "QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }"
        for gb in [self.group_box, self.qr_group_box, self.zone_group_box, self.bottom_group_box]:
            if gb:
                gb.setStyleSheet(gb_style)

        if self.print_job_group_box:
            self.print_job_group_box.setStyleSheet("QGroupBox { border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 6px; }")

        win = self.window if self.window is not None else self
        if hasattr(win, 'qr_label') and win.qr_label:
            win.qr_label.setAlignment(Qt.AlignCenter)
            win.qr_label.setMinimumSize(210, 210)
            win.qr_label.setStyleSheet("border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 5px;")

        if hasattr(win, 'url_label') and win.url_label:
            win.url_label.setAlignment(Qt.AlignCenter)
            win.url_label.setWordWrap(True)
            win.url_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #007BFF; margin-top: 8px;")

    def _setup_folder_input(self):
        win = self.window if self.window is not None else self
        win.folder_input.setReadOnly(True)
        if hasattr(win, 'select_save_folder'):
            win.folder_btn.clicked.connect(win.select_save_folder)
        else:
            def default_select_folder():
                folder = QFileDialog.getExistingDirectory(win, "저장 폴더 선택", win.folder_input.text())
                if folder:
                    win.folder_input.setText(folder)
                    if hasattr(win, 'persist_settings'):
                        win.persist_settings()
            win.folder_btn.clicked.connect(default_select_folder)

    def _setup_network_controls(self):
        win = self.window if self.window is not None else self
        win.ip_data_map = {}
        if hasattr(win, 'on_nic_index_changed'):
            win.nic_combo.currentIndexChanged.connect(win.on_nic_index_changed)
        if hasattr(win, 'rescan_network_interfaces'):
            win.rescan_nic_btn.clicked.connect(win.rescan_network_interfaces)

        if hasattr(win, 'update_save_tab_combo_items'):
            win.update_save_tab_combo_items()
        if hasattr(win, 'on_save_tab_changed'):
            win.save_tab_combo.currentTextChanged.connect(win.on_save_tab_changed)

    def _setup_zone_controls(self):
        win = self.window if self.window is not None else self
        if hasattr(win, 'update_zone_combo_items'):
            win.update_zone_combo_items()
        if hasattr(win, 'on_zone_changed'):
            win.zone_combo.currentTextChanged.connect(win.on_zone_changed)

        win.zone_input.setEnabled(False)
        if hasattr(win, 'update_qr_code'):
            win.zone_input.textChanged.connect(win.update_qr_code)

        win.zone_buttons_layout = win.zone_buttons_widget.layout()
        if win.zone_buttons_layout is None:
            win.zone_buttons_layout = QGridLayout(win.zone_buttons_widget)
            win.zone_buttons_layout.setContentsMargins(0, 0, 0, 0)

        if hasattr(win, 'update_zone_buttons'):
            win.update_zone_buttons()

    def _setup_splitters(self):
        win = self.window if self.window is not None else self
        splitter_style = """
            QSplitter::handle {
                background-color: #3498db;
                margin: 2px;
                border-radius: 3px;
            }
            QSplitter::handle:hover {
                background-color: #2ecc71;
            }
        """

        if win.main_splitter:
            win.main_splitter.setHandleWidth(8)
            win.main_splitter.setChildrenCollapsible(False)
            win.main_splitter.setStyleSheet(splitter_style)
            win.main_splitter.setSizes(getattr(win, 'main_splitter_sizes', [400, 350]))
            
            win.main_splitter_save_timer = QTimer(win)
            win.main_splitter_save_timer.setSingleShot(True)
            win.main_splitter_save_timer.setInterval(250)
            win.main_splitter.splitterMoved.connect(lambda _pos, _index: win.main_splitter_save_timer.start())
            if hasattr(win, 'persist_settings'):
                win.main_splitter_save_timer.timeout.connect(win.persist_settings)

        if win.top_splitter:
            win.top_splitter.setHandleWidth(8)
            win.top_splitter.setChildrenCollapsible(False)
            win.top_splitter.setStyleSheet(splitter_style)
            win.top_splitter.setSizes(getattr(win, 'top_splitter_sizes', [350, 250, 350]))
            
            win.top_splitter_save_timer = QTimer(win)
            win.top_splitter_save_timer.setSingleShot(True)
            win.top_splitter_save_timer.setInterval(250)
            win.top_splitter.splitterMoved.connect(lambda _pos, _index: win.top_splitter_save_timer.start())
            if hasattr(win, 'persist_settings'):
                win.top_splitter_save_timer.timeout.connect(win.persist_settings)

        if win.config_group_box:
            def on_config_toggled(checked):
                win.top_splitter.setVisible(checked)
                if checked:
                    win.config_group_box.setMaximumHeight(16777215)
                    win.main_splitter.setSizes([400, 350])
                else:
                    win.config_group_box.setMaximumHeight(35)
                    win.main_splitter.setSizes([35, 715])
            win.config_group_box.toggled.connect(on_config_toggled)

    def _setup_bottom_area(self):
        win = self.window if self.window is not None else self
        win.completed_only_checkbox.setChecked(getattr(win, 'transfer_show_completed', True))

        win.transfer_period_combo.addItems(["All", "Today", "This month", "Custom"])
        saved_period = getattr(win, 'transfer_period', 'All')
        if saved_period in ("All", "Today", "This month", "Custom"):
            win.transfer_period_combo.setCurrentText(saved_period)

        start_date_edit = getattr(win, 'transfer_start_date', None)
        if start_date_edit and hasattr(start_date_edit, 'date'):
            date_str = start_date_edit.date().toString('yyyy-MM-dd')
            start_date = QDate.fromString(date_str, 'yyyy-MM-dd')
        else:
            start_date = QDate.currentDate() # 혹은 기본값 처리

        end_date_edit = getattr(win, 'transfer_end_date', None)
        if end_date_edit and hasattr(end_date_edit, 'date'):
            date_str = end_date_edit.date().toString('yyyy-MM-dd')
            end_date = QDate.fromString(date_str, 'yyyy-MM-dd')
        else:
            end_date = QDate.currentDate() # 혹은 기본값 처리


        # start_date = QDate.fromString(getattr(win, 'transfer_start_date', ''), 'yyyy-MM-dd')
        # end_date = QDate.fromString(getattr(win, 'transfer_end_date', ''), 'yyyy-MM-dd')
        
        win.transfer_start_date.setDate(start_date if start_date.isValid() else QDate.currentDate())
        win.transfer_start_date.setCalendarPopup(True)

        win.transfer_end_date.setDate(end_date if end_date.isValid() else QDate.currentDate())
        win.transfer_end_date.setCalendarPopup(True)

        if os.environ.get('MODE', '').strip().lower() == 'development':
            win.log_print_checkbox = QCheckBox('log_print')
            win.print_detect_checkbox = QCheckBox('print_detect')
            win.log_print_checkbox.setChecked(getattr(win, 'log_print_enabled', True))
            win.print_detect_checkbox.setChecked(getattr(win, 'print_detect_enabled', True))
            
            if hasattr(win, 'update_print_log_outputs'):
                win.log_print_checkbox.toggled.connect(win.update_print_log_outputs)
                win.print_detect_checkbox.toggled.connect(win.update_print_log_outputs)
            if hasattr(win, 'open_print_log_viewer'):
                win.log_print_checkbox.clicked.connect(lambda checked: checked and win.open_print_log_viewer('print'))
                win.print_detect_checkbox.clicked.connect(lambda checked: checked and win.open_print_log_viewer('print_detect'))
                
            if self.transfer_filter_layout:
                self.transfer_filter_layout.addWidget(win.log_print_checkbox)
                self.transfer_filter_layout.addWidget(win.print_detect_checkbox)
                
        if self.transfer_filter_layout:
            self.transfer_filter_layout.addStretch()

        if hasattr(win, 'apply_transfer_tab_filter'):
            win.transfer_period_combo.currentTextChanged.connect(win.apply_transfer_tab_filter)
            win.transfer_start_date.dateChanged.connect(win.apply_transfer_tab_filter)
            win.transfer_end_date.dateChanged.connect(win.apply_transfer_tab_filter)
            win.completed_only_checkbox.stateChanged.connect(win.apply_transfer_tab_filter)
        
        if hasattr(win, 'persist_settings'):
            win.completed_only_checkbox.stateChanged.connect(win.persist_settings)
            win.transfer_period_combo.currentTextChanged.connect(win.persist_settings)
            win.transfer_start_date.dateChanged.connect(win.persist_settings)
            win.transfer_end_date.dateChanged.connect(win.persist_settings)

        if hasattr(win, 'update_transfer_tab_colors'):
            win.tab_widget.currentChanged.connect(win.update_transfer_tab_colors)
        if hasattr(win, 'show_tab_context_menu'):
            win.tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
            win.tab_widget.tabBar().customContextMenuRequested.connect(win.show_tab_context_menu)
        win.tab_widget.setTabsClosable(True)
        if hasattr(win, 'close_tab'):
            win.tab_widget.tabCloseRequested.connect(win.close_tab)

        win.print_job_table.setHorizontalHeaderLabels(
            ['Printer', 'File Name', 'Job ID', 'Status', 'Tag', 'Output Path', 'Detected Time']
        )
        win.print_job_table.setSelectionBehavior(QTableWidget.SelectRows)
        win.print_job_table.setEditTriggers(QTableWidget.NoEditTriggers)
        win.print_job_table.horizontalHeader().setStretchLastSection(True)

    def register_tab(self, tab_widget, content_widget):
        return tab_widget.addTab(content_widget, self.title)

    def update_print_log_outputs(self, set_print_logging_enabled_func):
        return controller_update_print_log_outputs(self.window if self.window is not None else self, set_print_logging_enabled_func)

    def handle_print_request(self, request, order_service_inst):
        from LinkBox.printer_job_controller import handle_print_request as render_print_request
        return render_print_request(self.window if self.window is not None else self, request, order_service_inst)