import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QComboBox, QGroupBox, 
    QTabWidget, QHeaderView, QSplitter, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap, QAction, QFontMetrics


class CollapsibleStatusLabel(QLabel):
    """A status label that toggles between a compact summary and full details."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._expanded = False
        self.setCursor(Qt.PointingHandCursor)
        self.setWordWrap(True)
        self.setText(text)

    def setText(self, text):
        self._full_text = str(text or "")
        self._refresh_display()

    def _refresh_display(self):
        if self._expanded:
            display_text = f"{self._full_text}  (축약하려면 클릭)"
        else:
            summary = self._full_text.split(" | ", 1)[0]
            suffix = "  … (상세 보기)" if summary != self._full_text else ""
            display_text = summary + suffix
        super().setText(display_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._refresh_display()
        super().mousePressEvent(event)


class AutoFitTextLabel(QLabel):
    """Keep a label on one line by shrinking its font when needed."""

    def __init__(self, text="", point_size=11, parent=None):
        super().__init__(parent)
        self._base_point_size = point_size
        self.setWordWrap(False)
        self.setText(text)

    def resizeEvent(self, event):
        self._fit_font()
        super().resizeEvent(event)

    def setText(self, text):
        super().setText(text)
        self._fit_font()

    def _fit_font(self):
        font = self.font()
        font.setBold(True)
        font.setPointSize(self._base_point_size)
        available_width = max(60, self.width() - 8)
        metrics = QFontMetrics(font)
        while font.pointSize() > 7 and metrics.horizontalAdvance(self.text()) > available_width:
            font.setPointSize(font.pointSize() - 1)
        if self.font().pointSize() != font.pointSize():
            self.setFont(font)


def setup_integrated_ui(window, current_upload_folder, current_zones, current_save_tabs, interfaces,
                        current_ssid, internet_nic, hotspot_nic, hotspot_image,
                        hotspot_network, hotspot_gateway, max_connections,
                        current_main_tab="file_receiver"):
    settings_menu = window.menuBar().addMenu("Settings")
    window.settings_action = QAction("Open Settings", window)
    window.settings_action.triggered.connect(window.open_settings_dialog)
    settings_menu.addAction(window.settings_action)

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    
    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(10, 10, 10, 10)

    # Main Tab Widget (Tab 1: LinkBox, Tab 2: LinkShare)
    window.main_tabs = QTabWidget()
    window.main_tabs.currentChanged.connect(window.on_main_tab_changed)
    main_layout.addWidget(window.main_tabs)

    # ==========================================
    # [Tab 1] LinkBox (File Receiver & Manager)
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

    # 2. Right Area: [QR Location] + [QR Code]
    right_container = QWidget()
    right_container_layout = QHBoxLayout(right_container)

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

    right_container_layout.addWidget(zone_group_box)

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

    right_container_layout.addWidget(right_widget)
    window.top_splitter.addWidget(right_container)

    # 3. Bottom Area (Log Table)[cite: 1, 2]
    bottom_container = QWidget()
    bottom_layout = QVBoxLayout(bottom_container)
    bottom_layout.addWidget(QLabel("📂 LinkBox Received Transfer Log:"))
    
    window.tab_widget = QTabWidget()
    window.tab_widget.setTabsClosable(True)
    window.tab_widget.tabCloseRequested.connect(window.close_tab)
    bottom_layout.addWidget(window.tab_widget)
    
    window.main_splitter.addWidget(bottom_container)
    window.main_tabs.addTab(tab1_widget, "📦 File Receiver (LinkBox)")

    # ==========================================
    # [Tab 2] LinkShare (Wi-Fi & Internet Pass Manager)[cite: 4]
    # ==========================================
    tab2_widget = QWidget()
    tab2_layout = QVBoxLayout(tab2_widget)

    hotspot_info_group = QGroupBox(f"📶 Current Hotspot SSID: {current_ssid}")
    hotspot_info_layout = QHBoxLayout()

    hotspot_control_group = QGroupBox("Hotspot Control")
    hotspot_control_layout = QVBoxLayout()
    hotspot_control_layout.setSpacing(6)
    window.hotspot_control_layout = hotspot_control_layout
    hotspot_controls = QHBoxLayout()
    hotspot_controls.setSpacing(6)
    window.hotspot_status_btn = QLabel("상태 확인 중")
    window.hotspot_status_btn.setAlignment(Qt.AlignCenter)
    window.hotspot_status_btn.setMinimumHeight(32)
    window.hotspot_status_btn.setStyleSheet(
        "QLabel { background-color: #607d8b; color: white; font-weight: bold; "
        "border: 1px solid #455a64; border-radius: 4px; padding: 5px 10px; }"
    )
    hotspot_controls.addWidget(window.hotspot_status_btn)
    window.hotspot_on_btn = QPushButton("Hotspot 켜기")
    window.hotspot_on_btn.clicked.connect(lambda: window.set_hotspot_state(True))
    window.hotspot_on_btn.setMinimumHeight(32)
    window.hotspot_on_btn.setStyleSheet(
        "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
        "border: 1px solid #1b5e20; border-radius: 4px; padding: 5px 10px; }"
        "QPushButton:hover { background-color: #388e3c; }"
    )
    hotspot_controls.addWidget(window.hotspot_on_btn)
    window.hotspot_off_btn = QPushButton("Hotspot 끄기")
    window.hotspot_off_btn.clicked.connect(lambda: window.set_hotspot_state(False))
    window.hotspot_off_btn.setMinimumHeight(32)
    window.hotspot_off_btn.setStyleSheet(
        "QPushButton { background-color: #c62828; color: white; font-weight: bold; "
        "border: 1px solid #8e0000; border-radius: 4px; padding: 5px 10px; }"
        "QPushButton:hover { background-color: #d32f2f; }"
    )
    hotspot_controls.addWidget(window.hotspot_off_btn)
    window.hotspot_diagnose_btn = QPushButton("상태 진단 실행")
    window.hotspot_diagnose_btn.clicked.connect(window.diagnose_hotspot)
    window.hotspot_diagnose_btn.setMinimumHeight(32)
    window.hotspot_diagnose_btn.setStyleSheet(
        "QPushButton { background-color: #1565c0; color: white; font-weight: bold; "
        "border: 1px solid #0d47a1; border-radius: 4px; padding: 5px 10px; }"
        "QPushButton:hover { background-color: #1976d2; }"
    )
    hotspot_controls.addWidget(window.hotspot_diagnose_btn)
    hotspot_control_layout.addLayout(hotspot_controls)
    window.hotspot_name_label = QLabel(
        f"• Active Hotspot Name: <b>{current_ssid}</b> (Auto-started)"
    )
    hotspot_control_layout.addWidget(window.hotspot_name_label)
    window.hotspot_nic_label = QLabel(f"• Hotspot NIC: <b>{hotspot_nic.get('display', 'Not selected')}</b>")
    hotspot_control_layout.addWidget(window.hotspot_nic_label)
    window.hotspot_network_label = QLabel(f"• Hotspot IP range: <b>{hotspot_network}</b> / gateway: <b>{hotspot_gateway}</b>")
    hotspot_control_layout.addWidget(window.hotspot_network_label)
    window.captive_portal_status_label = CollapsibleStatusLabel("Captive Portal: starting...")
    hotspot_control_layout.addWidget(window.captive_portal_status_label)
    window.hotspot_status_label = CollapsibleStatusLabel("Hotspot status: checking...")
    hotspot_control_layout.addWidget(window.hotspot_status_label)
    window.hotspot_image_label = QLabel()
    window.hotspot_image_label.setAlignment(Qt.AlignCenter)
    window.hotspot_image_label.setMinimumHeight(0)
    window.hotspot_image_label.setMaximumHeight(140)
    if hotspot_image and os.path.exists(hotspot_image):
        pixmap = QPixmap(hotspot_image)
        if not pixmap.isNull():
            window.hotspot_image_label.setPixmap(pixmap.scaled(320, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    else:
        window.hotspot_image_label.clear()
    hotspot_control_layout.addWidget(window.hotspot_image_label)
    hotspot_control_group.setLayout(hotspot_control_layout)
    hotspot_info_layout.addWidget(hotspot_control_group, 1)

    qr_group = QGroupBox("Internet Sharing QR Code")
    qr_layout = QVBoxLayout(qr_group)
    qr_layout.setContentsMargins(1, 1, 1, 1)
    qr_layout.setSpacing(0)
    window.qr_layout = qr_layout
    qr_pair_layout = QHBoxLayout()
    network_group = QGroupBox("Network Connection")
    network_group.setStyleSheet(
        "QGroupBox { color: #1565c0; font-weight: bold; background: #e3f2fd; "
        "border: 2px solid #64b5f6; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
    )
    network_layout = QHBoxLayout(network_group)
    window.hotspot_network_qr_label = QLabel()
    window.hotspot_network_qr_label.setAlignment(Qt.AlignCenter)
    window.hotspot_network_qr_label.setMinimumSize(0, 0)
    window.hotspot_network_qr_label.setMaximumSize(220, 220)
    window.hotspot_network_qr_label.setStyleSheet(
        "border: 1px solid #64b5f6; background-color: #ffffff; border-radius: 5px;"
    )
    network_layout.addWidget(window.hotspot_network_qr_label, 0, Qt.AlignCenter)
    network_info_layout = QVBoxLayout()
    network_print_btn = QPushButton("PRINT")
    network_print_btn.setFixedSize(84, 30)
    network_print_btn.setStyleSheet(
        "QPushButton { color: #0d47a1; background-color: #e3f2fd; "
        "border: 1px solid #64b5f6; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold; }"
        "QPushButton:hover { background-color: #bbdefb; }"
    )
    network_print_btn.clicked.connect(window.show_network_qr_print_dialog)
    window.hotspot_network_info_label = QLabel("SSID: -\nPassword: -")
    window.hotspot_network_info_label.setAlignment(Qt.AlignCenter)
    window.hotspot_network_info_label.setStyleSheet("font-size: 9px; color: #263238;")
    network_info_layout.addWidget(window.hotspot_network_info_label)
    network_info_layout.addWidget(network_print_btn, 0, Qt.AlignHCenter)
    network_layout.addLayout(network_info_layout)
    captive_group = QGroupBox("Captive Portal")
    captive_group.setStyleSheet(
        "QGroupBox { color: #2e7d32; font-weight: bold; background: #e8f5e9; "
        "border: 2px solid #81c784; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
    )
    captive_layout = QHBoxLayout(captive_group)
    window.hotspot_qr_label = QLabel()
    window.hotspot_qr_label.setAlignment(Qt.AlignCenter)
    window.hotspot_qr_label.setMinimumSize(0, 0)
    window.hotspot_qr_label.setMaximumSize(220, 220)
    window.hotspot_qr_label.setStyleSheet("border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 5px;")
    window.hotspot_qr_caption = QLabel("이 QR 코드는 인터넷 사용신청용입니다.")
    window.hotspot_qr_caption.setAlignment(Qt.AlignCenter)
    window.hotspot_qr_caption.setStyleSheet("font-size: 9px; font-weight: bold; color: #16803c; margin: 0;")
    window.hotspot_url_label = QLabel("Generated URL: ")
    window.hotspot_url_label.setAlignment(Qt.AlignCenter)
    window.hotspot_url_label.setWordWrap(True)
    window.hotspot_url_label.setStyleSheet("font-size: 9px; font-weight: bold; color: #007BFF; margin: 0;")

    captive_layout.addWidget(window.hotspot_qr_label, 0, Qt.AlignCenter)
    captive_info_layout = QVBoxLayout()
    captive_print_btn = QPushButton("PRINT")
    captive_print_btn.setFixedSize(84, 30)
    captive_print_btn.setStyleSheet(
        "QPushButton { color: #1b5e20; background-color: #e8f5e9; "
        "border: 1px solid #81c784; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold; }"
        "QPushButton:hover { background-color: #c8e6c9; }"
    )
    captive_print_btn.clicked.connect(window.show_captive_qr_print_dialog)
    captive_info_layout.addWidget(window.hotspot_qr_caption)
    captive_info_layout.addWidget(window.hotspot_url_label)
    captive_info_layout.addWidget(captive_print_btn, 0, Qt.AlignHCenter)
    captive_layout.addLayout(captive_info_layout)
    qr_pair_layout.addWidget(network_group)
    qr_pair_layout.addWidget(captive_group)
    qr_layout.addLayout(qr_pair_layout)
    hotspot_info_layout.addWidget(qr_group, 1)

    card_style = (
        "QGroupBox { background-color: #ffffff; color: #17324d; border: 2px solid #90a4ae; "
        "border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }"
        " QGroupBox::title { color: #0d47a1; subcontrol-origin: margin; left: 12px; padding: 0 5px; }"
        " QLabel { color: #263238; font-weight: normal; }"
    )
    hotspot_info_group.setStyleSheet(card_style)
    hotspot_control_group.setStyleSheet(card_style)
    qr_group.setStyleSheet(card_style)
    hotspot_info_group.setLayout(hotspot_info_layout)

    window.status_group = QGroupBox()
    window.status_layout = QHBoxLayout()
    window.status_layout.setSpacing(12)
    window.status_title_label = AutoFitTextLabel("Currently Connected Clients Summary", 11)
    window.status_layout.addWidget(window.status_title_label, 1)
    window.status_label = AutoFitTextLabel(f"Devices connected: 0 of {max_connections}", 12)
    window.status_layout.addWidget(window.status_label)
    window.windows_hotspot_clients_label = AutoFitTextLabel(
        "Windows Mobile Hotspot: checking actual client limit...", 10
    )
    window.status_layout.addWidget(window.windows_hotspot_clients_label, 2)
    window.status_group.setLayout(window.status_layout)
    window.status_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    window.status_group.setMaximumHeight(72)
    window.status_group.setStyleSheet(card_style)
    window.status_title_label.setStyleSheet("color: #0d47a1; font-weight: bold;")
    window.status_label.setStyleSheet("color: #1565c0; font-weight: bold;")
    window.windows_hotspot_clients_label.setStyleSheet("color: #455a64; font-weight: bold;")

    window.usage_history_tabs = QTabWidget()
    window.usage_history_tables = {}
    usage_tabs = {
        "연결상태": ["연결상태", "요청시간", "시작시간", "종료시간", "남은시간", "IP 주소"],
        "사용요청": ["사용요청", "요청시간", "IP 주소"],
        "사용허가": ["사용허가", "승인시간", "시작시간", "종료시간", "남은시간", "IP 주소"],
    }
    connection_tab_name = next(iter(usage_tabs))
    usage_tabs[connection_tab_name] = ["연결상태", "사용승인", "인터넷연결", "요청시간", "시작시간", "종료시간", "총사용요청시간", "남은시간", "IP 주소"]
    approval_tab_name = list(usage_tabs)[2]
    usage_tabs[approval_tab_name] = ["사용허가", "승인시간", "요청사용시간", "IP 주소"]
    for tab_name, headers in usage_tabs.items():
        headers = headers + ["사용자정보"]
        usage_tab = QWidget()
        usage_tab_layout = QVBoxLayout(usage_tab)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setStyleSheet(
            "QTableWidget { background-color: #ffffff; color: #263238; "
            "gridline-color: #b0bec5; }"
            " QHeaderView::section { background-color: #1565c0; color: white; "
            "font-weight: bold; padding: 4px; }"
        )
        usage_tab_layout.addWidget(table)
        window.usage_history_tables[tab_name] = table
        window.usage_history_tabs.addTab(usage_tab, tab_name)

    history_tab = QWidget()
    history_layout = QVBoxLayout(history_tab)
    history_filter_layout = QHBoxLayout()
    window.usage_history_filter = QComboBox()
    window.usage_history_filter.addItems(["전체", "오늘", "이번 달", "기간"])
    window.usage_history_start = QLineEdit()
    window.usage_history_start.setPlaceholderText("시작일 YYYY-MM-DD")
    window.usage_history_end = QLineEdit()
    window.usage_history_end.setPlaceholderText("종료일 YYYY-MM-DD")
    history_filter_layout.addWidget(window.usage_history_filter)
    history_filter_layout.addWidget(window.usage_history_start)
    history_filter_layout.addWidget(window.usage_history_end)
    history_layout.addLayout(history_filter_layout)
    window.usage_history_total_label = QLabel("사용시간 누적: 0분                         금액 누적: 0 PHP")
    history_layout.addWidget(window.usage_history_total_label)
    history_table = QTableWidget(0, 5)
    history_table.setHorizontalHeaderLabels(["요청시간", "승인시간", "사용시간", "금액", "사용자정보"])
    history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    history_table.horizontalHeader().setStretchLastSection(True)
    history_table.setEditTriggers(QTableWidget.NoEditTriggers)
    history_layout.addWidget(history_table)
    window.usage_history_tables["사용내역"] = history_table
    window.usage_history_tabs.addTab(history_tab, "사용내역")
    window.usage_history_filter.currentIndexChanged.connect(window.update_usage_history_tables)
    window.usage_history_start.textChanged.connect(window.update_usage_history_tables)
    window.usage_history_end.textChanged.connect(window.update_usage_history_tables)
    window.usage_history_tabs.currentChanged.connect(window.on_usage_history_tab_changed)

    status_panel = QWidget()
    status_panel_layout = QVBoxLayout(status_panel)
    status_panel_layout.setContentsMargins(0, 0, 0, 0)
    status_panel_layout.setSpacing(4)
    status_panel_layout.addWidget(window.status_group, 0)
    status_panel_layout.addWidget(window.usage_history_tabs, 1)

    window.linkshare_splitter = QSplitter(Qt.Vertical)
    window.linkshare_splitter.setOpaqueResize(True)
    window.linkshare_splitter.setChildrenCollapsible(False)
    window.linkshare_splitter.setHandleWidth(8)
    window.linkshare_splitter.addWidget(hotspot_info_group)
    window.linkshare_splitter.addWidget(status_panel)
    hotspot_info_group.setMinimumHeight(120)
    status_panel.setMinimumHeight(100)
    window.linkshare_splitter.setStretchFactor(0, 3)
    window.linkshare_splitter.setStretchFactor(1, 2)
    window.linkshare_splitter.setSizes(getattr(window, 'linkshare_splitter_sizes', [520, 260]))
    window.linkshare_splitter.splitterMoved.connect(window.handle_linkshare_splitter_moved)
    window.linkshare_splitter_save_timer = QTimer(window)
    window.linkshare_splitter_save_timer.setSingleShot(True)
    window.linkshare_splitter_save_timer.setInterval(250)
    window.linkshare_splitter_save_timer.timeout.connect(window.persist_settings)
    tab2_layout.addWidget(window.linkshare_splitter)
    QTimer.singleShot(0, window.adjust_linkshare_spacing)

    window.main_tabs.addTab(tab2_widget, "🌐 Wi-Fi Pass Manager (LinkShare)")
    window.main_tabs.setCurrentIndex(1 if current_main_tab == "wifi_pass" else 0)
