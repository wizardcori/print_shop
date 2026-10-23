import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QComboBox, QGroupBox, QTabWidget, QHeaderView, QSplitter, QGridLayout, QDateEdit, QCheckBox
from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QColor
from .ui_linkbox_tab import register_tab
from Common.ui_order_dashboard import create_order_dashboard

def create_tab(window, current_upload_folder, current_zones, current_save_tabs, interfaces, current_ssid, internet_nic, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections):
# ==========================================
    tab1_widget = QWidget()
    tab1_layout = QVBoxLayout(tab1_widget)

    window.main_splitter = QSplitter(Qt.Vertical)
    tab1_layout.addWidget(window.main_splitter)

    window.top_splitter = QSplitter(Qt.Horizontal)
    window.main_splitter.addWidget(window.top_splitter)

    # 1. Left GroupBox: Server & Connection Settings
    group_box = QGroupBox("Server & Connection Settings")
    group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")
    left_layout = QVBoxLayout(group_box)

    folder_layout = QHBoxLayout()
    folder_layout.addWidget(QLabel("Save Location:"))
    window.folder_input = QLineEdit(current_upload_folder)
    window.folder_input.setReadOnly(True)
    folder_layout.addWidget(window.folder_input)

    window.folder_btn = QPushButton("Browse...")
    window.folder_btn.clicked.connect(window.select_save_folder)
    folder_layout.addWidget(window.folder_btn)

    left_layout.addLayout(folder_layout)

    # NIC Selection ComboBox (Auto-search and Internet tested priority)[cite: 2]
    nic_layout = QHBoxLayout()
    nic_layout.addWidget(QLabel("Internet NIC:"))
    window.nic_combo = QComboBox()

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
    nic_layout.addWidget(window.nic_combo)
    window.rescan_nic_btn = QPushButton("Rescan NIC")
    window.rescan_nic_btn.clicked.connect(window.rescan_network_interfaces)
    nic_layout.addWidget(window.rescan_nic_btn)
    left_layout.addLayout(nic_layout)

    save_tab_layout = QHBoxLayout()
    save_tab_layout.addWidget(QLabel("Save Tab:"))
    window.save_tab_combo = QComboBox()
    window.update_save_tab_combo_items()
    window.save_tab_combo.currentTextChanged.connect(window.on_save_tab_changed)
    save_tab_layout.addWidget(window.save_tab_combo)
    left_layout.addLayout(save_tab_layout)

    window.top_splitter.addWidget(group_box)

    # 2. Right Area: [QR Code] | splitter | [QR Location & Table]
    zone_group_box = QGroupBox("QR Location & Table Selection")
    zone_group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")
    zone_group_layout = QVBoxLayout(zone_group_box)

    top_zone_layout = QHBoxLayout()
    top_zone_layout.addWidget(QLabel("Location:"))
    window.zone_combo = QComboBox()
    window.update_zone_combo_items()
    window.zone_combo.currentTextChanged.connect(window.on_zone_changed)
    top_zone_layout.addWidget(window.zone_combo)

    window.zone_input = QLineEdit(current_zones[0] if current_zones else "Table01")
    window.zone_input.setEnabled(False)
    window.zone_input.textChanged.connect(window.update_qr_code)
    top_zone_layout.addWidget(window.zone_input)
    zone_group_layout.addLayout(top_zone_layout)

    window.zone_buttons_widget = QWidget()
    window.zone_buttons_layout = QGridLayout(window.zone_buttons_widget)
    window.update_zone_buttons()
    zone_group_layout.addWidget(window.zone_buttons_widget)

    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)
    right_layout.setAlignment(Qt.AlignCenter)

    window.qr_label = QLabel()
    window.qr_label.setAlignment(Qt.AlignCenter)
    window.qr_label.setMinimumSize(210, 210)
    window.qr_label.setStyleSheet("border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 5px;")
    right_layout.addWidget(window.qr_label)

    window.url_label = QLabel("Generated URL: ")
    window.url_label.setAlignment(Qt.AlignCenter)
    window.url_label.setWordWrap(True)
    window.url_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #007BFF; margin-top: 8px;")
    right_layout.addWidget(window.url_label)

    window.qr_location_splitter = QSplitter(Qt.Horizontal)
    window.qr_location_splitter.setHandleWidth(8)
    window.qr_location_splitter.setChildrenCollapsible(False)
    window.qr_location_splitter.addWidget(right_widget)
    window.qr_location_splitter.addWidget(zone_group_box)
    window.qr_location_splitter.setSizes(
        getattr(window, 'qr_location_splitter_sizes', [260, 520])
    )
    window.qr_location_splitter_save_timer = QTimer(window)
    window.qr_location_splitter_save_timer.setSingleShot(True)
    window.qr_location_splitter_save_timer.setInterval(250)
    window.qr_location_splitter.splitterMoved.connect(
        lambda _pos, _index: window.qr_location_splitter_save_timer.start()
    )
    window.qr_location_splitter_save_timer.timeout.connect(window.persist_settings)
    window.top_splitter.addWidget(window.qr_location_splitter)
    window.top_splitter.setSizes(getattr(window, 'file_receiver_splitter_sizes', [520, 420]))
    window.file_receiver_splitter_save_timer = QTimer(window)
    window.file_receiver_splitter_save_timer.setSingleShot(True)
    window.file_receiver_splitter_save_timer.setInterval(250)
    window.top_splitter.splitterMoved.connect(
        lambda _pos, _index: window.file_receiver_splitter_save_timer.start()
    )
    window.file_receiver_splitter_save_timer.timeout.connect(window.persist_settings)

    # 3. Bottom Area (Log Table)[cite: 1, 2]
    bottom_container = QWidget()
    bottom_layout = QVBoxLayout(bottom_container)
    bottom_layout.addWidget(QLabel("PrintJobTree:"))

    transfer_filter_layout = QHBoxLayout()
    window.completed_only_checkbox = QCheckBox("Show completed too")
    # Show persisted transfer tabs on startup; users can uncheck this to hide
    # tabs that contain completed records only.
    window.completed_only_checkbox.setChecked(getattr(window, 'transfer_show_completed', True))
    transfer_filter_layout.addWidget(window.completed_only_checkbox)
    transfer_filter_layout.addWidget(QLabel("Display period:"))
    window.transfer_period_combo = QComboBox()
    window.transfer_period_combo.addItems(["All", "Today", "This month", "Custom"])
    saved_period = getattr(window, 'transfer_period', 'All')
    if saved_period in ("All", "Today", "This month", "Custom"):
        window.transfer_period_combo.setCurrentText(saved_period)
    transfer_filter_layout.addWidget(window.transfer_period_combo)
    start_date = QDate.fromString(getattr(window, 'transfer_start_date', ''), 'yyyy-MM-dd')
    end_date = QDate.fromString(getattr(window, 'transfer_end_date', ''), 'yyyy-MM-dd')
    window.transfer_start_date = QDateEdit(start_date if start_date.isValid() else QDate.currentDate())
    window.transfer_start_date.setCalendarPopup(True)
    window.transfer_end_date = QDateEdit(end_date if end_date.isValid() else QDate.currentDate())
    window.transfer_end_date.setCalendarPopup(True)
    transfer_filter_layout.addWidget(window.transfer_start_date)
    transfer_filter_layout.addWidget(QLabel("~"))
    transfer_filter_layout.addWidget(window.transfer_end_date)
    if os.environ.get('MODE', '').strip().lower() == 'development':
        window.log_print_checkbox = QCheckBox('log_print')
        window.print_detect_checkbox = QCheckBox('print_detect')
        window.log_print_checkbox.setChecked(getattr(window, 'log_print_enabled', True))
        window.print_detect_checkbox.setChecked(getattr(window, 'print_detect_enabled', True))
        window.log_print_checkbox.toggled.connect(window.update_print_log_outputs)
        window.print_detect_checkbox.toggled.connect(window.update_print_log_outputs)
        window.log_print_checkbox.clicked.connect(lambda checked: checked and window.open_print_log_viewer('print'))
        window.print_detect_checkbox.clicked.connect(lambda checked: checked and window.open_print_log_viewer('print_detect'))
        transfer_filter_layout.addWidget(window.log_print_checkbox)
        transfer_filter_layout.addWidget(window.print_detect_checkbox)
    transfer_filter_layout.addStretch()
    bottom_layout.addLayout(transfer_filter_layout)
    window.transfer_period_combo.currentTextChanged.connect(window.apply_transfer_tab_filter)
    window.transfer_start_date.dateChanged.connect(window.apply_transfer_tab_filter)
    window.transfer_end_date.dateChanged.connect(window.apply_transfer_tab_filter)
    window.completed_only_checkbox.stateChanged.connect(window.apply_transfer_tab_filter)
    window.completed_only_checkbox.stateChanged.connect(window.persist_settings)
    window.transfer_period_combo.currentTextChanged.connect(window.persist_settings)
    window.transfer_start_date.dateChanged.connect(window.persist_settings)
    window.transfer_end_date.dateChanged.connect(window.persist_settings)
    window.tab_widget = QTabWidget()
    window.tab_widget.currentChanged.connect(window.update_transfer_tab_colors)
    window.tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
    window.tab_widget.tabBar().customContextMenuRequested.connect(window.show_tab_context_menu)
    window.tab_widget.setTabsClosable(True)
    window.tab_widget.tabCloseRequested.connect(window.close_tab)
    window.print_job_table = QTableWidget(0, 7)
    window.print_job_table.setHorizontalHeaderLabels(
        ['Printer', 'File Name', 'Job ID', 'Status', 'Tag', 'Output Path', 'Detected Time']
    )
    window.print_job_table.setSelectionBehavior(QTableWidget.SelectRows)
    window.print_job_table.setEditTriggers(QTableWidget.NoEditTriggers)
    window.print_job_table.horizontalHeader().setStretchLastSection(True)
    window.tab_widget.addTab(window.print_job_table, 'Print Jobs')
    bottom_layout.addWidget(window.tab_widget)

    # Orders remain part of the LinkBox workflow: uploaded files and their
    # validation/state controls are shown directly below the received files.
    window.order_dashboard = create_order_dashboard(window)
    bottom_layout.addWidget(window.order_dashboard)

    window.main_splitter.addWidget(bottom_container)
    window.main_splitter.setSizes(getattr(window, 'main_splitter_sizes', [520, 420]))
    window.main_splitter_save_timer = QTimer(window)
    window.main_splitter_save_timer.setSingleShot(True)
    window.main_splitter_save_timer.setInterval(250)
    window.main_splitter.splitterMoved.connect(
        lambda _pos, _index: window.main_splitter_save_timer.start()
    )
    window.main_splitter_save_timer.timeout.connect(window.persist_settings)
    window.main_tabs.addTab(tab1_widget, "File Receiver (LinkBox)")

    # ==========================================
    return tab1_widget
