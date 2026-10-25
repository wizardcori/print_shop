import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QComboBox, QGroupBox, QTabWidget, 
    QSplitter, QGridLayout, QDateEdit, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, QDate, QFile
from PySide6.QtGui import QColor
from PySide6.QtUiTools import QUiLoader
from Common.ui_order_dashboard import create_order_dashboard

def create_tab(window, current_upload_folder, current_zones, current_save_tabs, interfaces, current_ssid, internet_nic, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections):
    # ==========================================
    # 1. QUiLoader를 이용해 .ui 파일 로드
    # ==========================================
    loader = QUiLoader()
    ui_path = os.path.join(os.path.dirname(__file__), "ui","linkbox.ui")
    file = QFile(ui_path)
    if not file.open(QFile.ReadOnly):
        raise FileNotFoundError(f"UI 파일을 찾을 수 없습니다: {ui_path}")
    
    tab1_widget = loader.load(file, window)
    file.close()

    # ==========================================
    # 2. 위젯 객체 매핑 및 초기화
    # ==========================================
    window.main_splitter = tab1_widget.findChild(QSplitter, "main_splitter")
    window.top_splitter = tab1_widget.findChild(QSplitter, "top_splitter")
    window.config_group_box = tab1_widget.findChild(QGroupBox, "config_group_box")

    # GroupBox 스타일 설정
    group_box = tab1_widget.findChild(QGroupBox, "group_box")
    if group_box:
        group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")

    qr_group_box = tab1_widget.findChild(QGroupBox, "qr_group_box")
    if qr_group_box:
        qr_group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")

    zone_group_box = tab1_widget.findChild(QGroupBox, "zone_group_box")
    if zone_group_box:
        zone_group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")

    print_job_group_box = tab1_widget.findChild(QGroupBox, "print_job_group_box")
    if print_job_group_box:
        print_job_group_box.setStyleSheet("QGroupBox { border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 6px; }")

    bottom_group_box = tab1_widget.findChild(QGroupBox, "bottom_group_box")
    if bottom_group_box:
        bottom_group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")

    # Save Location
    window.folder_input = tab1_widget.findChild(QLineEdit, "folder_input")
    window.folder_input.setText(current_upload_folder)
    window.folder_input.setReadOnly(True)

    window.folder_btn = tab1_widget.findChild(QPushButton, "folder_btn")
    window.folder_btn.clicked.connect(window.select_save_folder)

    # Internet NIC Selection ComboBox
    window.nic_combo = tab1_widget.findChild(QComboBox, "nic_combo")
    window.ip_data_map = {}
    for display_name, ip, is_connected, is_wireless in interfaces:
        window.nic_combo.addItem(display_name, ip)
        window.ip_data_map[display_name] = ip
        
        index = window.nic_combo.count() - 1
        window.nic_combo.setItemData(index, is_connected, Qt.UserRole + 1)
        color = QColor(0, 180, 0) if is_connected else QColor(220, 0, 0)
        window.nic_combo.setItemData(index, color, Qt.ForegroundRole)

        if ip == internet_nic.get('ip') or display_name == internet_nic.get('display'):
            window.nic_combo.setCurrentIndex(index)
    
    window.nic_combo.currentIndexChanged.connect(window.on_nic_index_changed)
    
    window.rescan_nic_btn = tab1_widget.findChild(QPushButton, "rescan_nic_btn")
    window.rescan_nic_btn.clicked.connect(window.rescan_network_interfaces)

    # Save Tab ComboBox
    window.save_tab_combo = tab1_widget.findChild(QComboBox, "save_tab_combo")
    window.update_save_tab_combo_items()
    window.save_tab_combo.currentTextChanged.connect(window.on_save_tab_changed)

    # Zone ComboBox & Input
    window.zone_combo = tab1_widget.findChild(QComboBox, "zone_combo")
    window.update_zone_combo_items()
    window.zone_combo.currentTextChanged.connect(window.on_zone_changed)

    window.zone_input = tab1_widget.findChild(QLineEdit, "zone_input")
    window.zone_input.setText(current_zones[0] if current_zones else "Table01")
    window.zone_input.setEnabled(False)
    window.zone_input.textChanged.connect(window.update_qr_code)

    window.zone_buttons_widget = tab1_widget.findChild(QWidget, "zone_buttons_widget")
    window.zone_buttons_layout = QGridLayout(window.zone_buttons_widget)
    window.update_zone_buttons()

    # QR Label & URL Label
    window.qr_label = tab1_widget.findChild(QLabel, "qr_label")
    window.qr_label.setAlignment(Qt.AlignCenter)
    window.qr_label.setMinimumSize(210, 210)
    window.qr_label.setStyleSheet("border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 5px;")

    window.url_label = tab1_widget.findChild(QLabel, "url_label")
    window.url_label.setAlignment(Qt.AlignCenter)
    window.url_label.setWordWrap(True)
    window.url_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #007BFF; margin-top: 8px;")

    # Splitter Configuration & Visibility Connection (시인성이 좋은 색상 적용 및 체크 해제 시 높이 축소)
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

    if window.main_splitter:
        window.main_splitter.setHandleWidth(8)
        window.main_splitter.setChildrenCollapsible(False)
        window.main_splitter.setStyleSheet(splitter_style)
        window.main_splitter.setSizes(getattr(window, 'main_splitter_sizes', [400, 350]))
        
        window.main_splitter_save_timer = QTimer(window)
        window.main_splitter_save_timer.setSingleShot(True)
        window.main_splitter_save_timer.setInterval(250)
        window.main_splitter.splitterMoved.connect(lambda _pos, _index: window.main_splitter_save_timer.start())
        window.main_splitter_save_timer.timeout.connect(window.persist_settings)

    if window.top_splitter:
        window.top_splitter.setHandleWidth(8)
        window.top_splitter.setChildrenCollapsible(False)
        window.top_splitter.setStyleSheet(splitter_style)
        window.top_splitter.setSizes(getattr(window, 'top_splitter_sizes', [350, 250, 350]))
        
        window.top_splitter_save_timer = QTimer(window)
        window.top_splitter_save_timer.setSingleShot(True)
        window.top_splitter_save_timer.setInterval(250)
        window.top_splitter.splitterMoved.connect(lambda _pos, _index: window.top_splitter_save_timer.start())
        window.top_splitter_save_timer.timeout.connect(window.persist_settings)

    if window.config_group_box:
        def on_config_toggled(checked):
            window.top_splitter.setVisible(checked)
            if checked:
                window.config_group_box.setMaximumHeight(16777215) # QWIDGETSIZE_MAX
                window.main_splitter.setSizes([400, 350])
            else:
                window.config_group_box.setMaximumHeight(35) # 타이틀바 높이만큼 줄임
                window.main_splitter.setSizes([35, 715])
        window.config_group_box.toggled.connect(on_config_toggled)

    # ==========================================
    # 3. Bottom Area (Log Table & Filters)
    # ==========================================
    window.completed_only_checkbox = tab1_widget.findChild(QCheckBox, "completed_only_checkbox")
    window.completed_only_checkbox.setChecked(getattr(window, 'transfer_show_completed', True))

    window.transfer_period_combo = tab1_widget.findChild(QComboBox, "transfer_period_combo")
    window.transfer_period_combo.addItems(["All", "Today", "This month", "Custom"])
    saved_period = getattr(window, 'transfer_period', 'All')
    if saved_period in ("All", "Today", "This month", "Custom"):
        window.transfer_period_combo.setCurrentText(saved_period)

    start_date = QDate.fromString(getattr(window, 'transfer_start_date', ''), 'yyyy-MM-dd')
    end_date = QDate.fromString(getattr(window, 'transfer_end_date', ''), 'yyyy-MM-dd')
    
    window.transfer_start_date = tab1_widget.findChild(QDateEdit, "transfer_start_date")
    window.transfer_start_date.setDate(start_date if start_date.isValid() else QDate.currentDate())
    window.transfer_start_date.setCalendarPopup(True)

    window.transfer_end_date = tab1_widget.findChild(QDateEdit, "transfer_end_date")
    window.transfer_end_date.setDate(end_date if end_date.isValid() else QDate.currentDate())
    window.transfer_end_date.setCalendarPopup(True)

    transfer_filter_layout = tab1_widget.findChild(QHBoxLayout, "transfer_filter_layout")
    if os.environ.get('MODE', '').strip().lower() == 'development':
        window.log_print_checkbox = QCheckBox('log_print')
        window.print_detect_checkbox = QCheckBox('print_detect')
        window.log_print_checkbox.setChecked(getattr(window, 'log_print_enabled', True))
        window.print_detect_checkbox.setChecked(getattr(window, 'print_detect_enabled', True))
        window.log_print_checkbox.toggled.connect(window.update_print_log_outputs)
        window.print_detect_checkbox.toggled.connect(window.update_print_log_outputs)
        window.log_print_checkbox.clicked.connect(lambda checked: checked and window.open_print_log_viewer('print'))
        window.print_detect_checkbox.clicked.connect(lambda checked: checked and window.open_print_log_viewer('print_detect'))
        if transfer_filter_layout:
            transfer_filter_layout.addWidget(window.log_print_checkbox)
            transfer_filter_layout.addWidget(window.print_detect_checkbox)
            
    if transfer_filter_layout:
        transfer_filter_layout.addStretch()

    # Filter & Setting Connects
    window.transfer_period_combo.currentTextChanged.connect(window.apply_transfer_tab_filter)
    window.transfer_start_date.dateChanged.connect(window.apply_transfer_tab_filter)
    window.transfer_end_date.dateChanged.connect(window.apply_transfer_tab_filter)
    window.completed_only_checkbox.stateChanged.connect(window.apply_transfer_tab_filter)
    
    window.completed_only_checkbox.stateChanged.connect(window.persist_settings)
    window.transfer_period_combo.currentTextChanged.connect(window.persist_settings)
    window.transfer_start_date.dateChanged.connect(window.persist_settings)
    window.transfer_end_date.dateChanged.connect(window.persist_settings)

    # Tab Widget & Table
    window.tab_widget = tab1_widget.findChild(QTabWidget, "tab_widget")
    window.tab_widget.currentChanged.connect(window.update_transfer_tab_colors)
    window.tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
    window.tab_widget.tabBar().customContextMenuRequested.connect(window.show_tab_context_menu)
    window.tab_widget.setTabsClosable(True)
    window.tab_widget.tabCloseRequested.connect(window.close_tab)

    window.print_job_table = tab1_widget.findChild(QTableWidget, "print_job_table")
    window.print_job_table.setHorizontalHeaderLabels(
        ['Printer', 'File Name', 'Job ID', 'Status', 'Tag', 'Output Path', 'Detected Time']
    )
    window.print_job_table.setSelectionBehavior(QTableWidget.SelectRows)
    window.print_job_table.setEditTriggers(QTableWidget.NoEditTriggers)
    window.print_job_table.horizontalHeader().setStretchLastSection(True)

    # Order Dashboard Integration
    bottom_group_box = tab1_widget.findChild(QGroupBox, "bottom_group_box")
    bottom_layout = bottom_group_box.layout() if bottom_group_box else None
    
    window.order_dashboard = create_order_dashboard(window)
    if bottom_layout:
        bottom_layout.addWidget(window.order_dashboard)
    
    window.main_tabs.addTab(tab1_widget, "File Receiver (LinkBox)")

    # ==========================================
    return tab1_widget


"""Integrated LinkBox main-tab registration."""

TAB_TITLE = "📦 File Receiver (LinkBox)"


def register_tab(tab_widget, content_widget):
    """Register LinkBox content in the integrated PrintShopApp tabs."""
    return tab_widget.addTab(content_widget, TAB_TITLE)
