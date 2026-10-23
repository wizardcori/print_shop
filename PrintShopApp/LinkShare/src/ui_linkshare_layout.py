from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QGroupBox, QSplitter, QTabWidget, QHeaderView, QPushButton, QComboBox, QLineEdit, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QPixmap
from .ui_linkshare_tab import register_tab

class CollapsibleStatusLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent); self._full_text=str(text or ''); self._expanded=False; self.setCursor(Qt.PointingHandCursor); self.setWordWrap(True)
    def setText(self, text): self._full_text=str(text or ''); self._refresh_display()
    def _refresh_display(self): super().setText(self._full_text if self._expanded else self._full_text.split(' | ', 1)[0])
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self._expanded=not self._expanded; self._refresh_display()
        super().mousePressEvent(event)
class AutoFitTextLabel(QLabel):
    def __init__(self, text='', point_size=11, parent=None): super().__init__(text,parent); self._base_point_size=point_size; self.setWordWrap(False)
    def resizeEvent(self, event): self._fit_font(); super().resizeEvent(event)
    def _fit_font(self):
        font=self.font(); font.setBold(True); font.setPointSize(self._base_point_size); metrics=QFontMetrics(font)
        while font.pointSize()>7 and metrics.horizontalAdvance(self.text()) > max(60,self.width()-8): font.setPointSize(font.pointSize()-1)
        self.setFont(font)

def create_tab(window, current_ssid, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections, current_main_tab='file_receiver'):
# ==========================================
    # [Tab 2] LinkShare (Wi-Fi & Internet Pass Manager)[cite: 4]
    # ==========================================
    tab2_widget = QWidget()
    tab2_layout = QVBoxLayout(tab2_widget)

    hotspot_info_group = QGroupBox(f"Current Hotspot SSID: {current_ssid}")
    hotspot_info_layout = QHBoxLayout()

    hotspot_control_group = QGroupBox("Hotspot Control")
    hotspot_control_layout = QVBoxLayout()
    hotspot_control_layout.setSpacing(6)
    window.hotspot_control_layout = hotspot_control_layout
    hotspot_controls = QHBoxLayout()
    hotspot_controls.setSpacing(6)
    window.hotspot_status_btn = QLabel("Checking status")
    window.hotspot_status_btn.setAlignment(Qt.AlignCenter)
    window.hotspot_status_btn.setMinimumHeight(32)
    window.hotspot_status_btn.setStyleSheet(
        "QLabel { background-color: #607d8b; color: white; font-weight: bold; "
        "border: 1px solid #455a64; border-radius: 4px; padding: 5px 10px; }"
    )
    hotspot_controls.addWidget(window.hotspot_status_btn)
    window.hotspot_on_btn = QPushButton("Turn Hotspot On")
    window.hotspot_on_btn.clicked.connect(lambda: window.set_hotspot_state(True))
    window.hotspot_on_btn.setMinimumHeight(32)
    window.hotspot_on_btn.setStyleSheet(
        "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; "
        "border: 1px solid #1b5e20; border-radius: 4px; padding: 5px 10px; }"
        "QPushButton:hover { background-color: #388e3c; }"
    )
    hotspot_controls.addWidget(window.hotspot_on_btn)
    window.hotspot_off_btn = QPushButton("Turn Hotspot Off")
    window.hotspot_off_btn.clicked.connect(lambda: window.set_hotspot_state(False))
    window.hotspot_off_btn.setMinimumHeight(32)
    window.hotspot_off_btn.setStyleSheet(
        "QPushButton { background-color: #c62828; color: white; font-weight: bold; "
        "border: 1px solid #8e0000; border-radius: 4px; padding: 5px 10px; }"
        "QPushButton:hover { background-color: #d32f2f; }"
    )
    hotspot_controls.addWidget(window.hotspot_off_btn)
    window.hotspot_diagnose_btn = QPushButton("Run Diagnostics")
    window.hotspot_diagnose_btn.clicked.connect(window.diagnose_hotspot)
    window.hotspot_diagnose_btn.setMinimumHeight(32)
    window.hotspot_diagnose_btn.setStyleSheet(
        "QPushButton { background-color: #1565c0; color: white; font-weight: bold; "
        "border: 1px solid #0d47a1; border-radius: 4px; padding: 5px 10px; }"
        "QPushButton:hover { background-color: #1976d2; }"
    )
    hotspot_controls.addWidget(window.hotspot_diagnose_btn)
    for control in (
        window.hotspot_status_btn,
        window.hotspot_on_btn,
        window.hotspot_off_btn,
        window.hotspot_diagnose_btn,
    ):
        control.setMinimumWidth(0)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    for index in range(4):
        hotspot_controls.setStretch(index, 1)
    hotspot_control_layout.addLayout(hotspot_controls)
    window.hotspot_name_label = QLabel(
        f"Active Hotspot Name: <b>{current_ssid}</b> (Auto-started)"
    )
    hotspot_control_layout.addWidget(window.hotspot_name_label)
    window.hotspot_nic_label = QLabel(f"Hotspot NIC: <b>{hotspot_nic.get('display', 'Not selected')}</b>")
    hotspot_control_layout.addWidget(window.hotspot_nic_label)
    window.hotspot_network_label = QLabel(f"Hotspot IP range: <b>{hotspot_network}</b> / gateway: <b>{hotspot_gateway}</b>")
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
    window.hotspot_horizontal_splitter = QSplitter(Qt.Horizontal)
    window.hotspot_horizontal_splitter.setOpaqueResize(True)
    window.hotspot_horizontal_splitter.setChildrenCollapsible(False)
    window.hotspot_horizontal_splitter.setHandleWidth(12)
    window.hotspot_horizontal_splitter.setStyleSheet(
        "QSplitter::handle { background-color: #90a4ae; }"
        " QSplitter::handle:hover { background-color: #1976d2; }"
    )
    window.hotspot_horizontal_splitter.addWidget(hotspot_control_group)

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
    window.hotspot_qr_caption = QLabel("This QR code is for Internet access requests.")
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
    window.hotspot_horizontal_splitter.addWidget(qr_group)
    window.hotspot_horizontal_splitter.setStretchFactor(0, 1)
    window.hotspot_horizontal_splitter.setStretchFactor(1, 3)
    window.hotspot_horizontal_splitter.setSizes([280, 900])
    hotspot_info_layout.addWidget(window.hotspot_horizontal_splitter)

    card_style = (
        "QGroupBox { background-color: #ffffff; color: #17324d; border: 2px solid #90a4ae; "
        "border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }"
        " QGroupBox::title { color: #0d47a1; background-color: #ffffff; "
        "subcontrol-origin: margin; left: 12px; padding: 0 8px; }"
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
        "Connection Status": ["Connection Status", "Request Time", "Start Time", "End Time", "Remaining", "IP Address"],
        "Usage Requests": ["Usage Request", "Request Time", "IP Address"],
        "Usage Approvals": ["Usage Approval", "Approval Time", "Start Time", "End Time", "Remaining", "IP Address"],
    }
    connection_tab_name = next(iter(usage_tabs))
    usage_tabs[connection_tab_name] = ["Connection Status", "Usage Approval", "Internet Connection", "Request Time", "Start Time", "End Time", "Total Requested", "Remaining", "IP Address"]
    approval_tab_name = list(usage_tabs)[2]
    usage_tabs[approval_tab_name] = ["Usage Approval", "Approval Time", "Requested Usage Time", "IP Address"]
    for tab_name, headers in usage_tabs.items():
        headers = headers + ["Cookie", "User Info"]
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
    window.usage_history_filter.addItems(["All", "Today", "This month", "Custom"])
    window.usage_history_start = QLineEdit()
    window.usage_history_start.setPlaceholderText("Start date YYYY-MM-DD")
    window.usage_history_end = QLineEdit()
    window.usage_history_end.setPlaceholderText("End date YYYY-MM-DD")
    history_filter_layout.addWidget(window.usage_history_filter)
    history_filter_layout.addWidget(window.usage_history_start)
    history_filter_layout.addWidget(window.usage_history_end)
    history_layout.addLayout(history_filter_layout)
    window.usage_history_total_label = QLabel("Total usage: 0 min                         Total amount: 0 PHP")
    history_layout.addWidget(window.usage_history_total_label)
    history_table = QTableWidget(0, 6)
    history_table.setHorizontalHeaderLabels(["Request Time", "Approval Time", "Usage Time", "Amount", "Cookie", "User Info"])
    history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    history_table.horizontalHeader().setStretchLastSection(True)
    history_table.setEditTriggers(QTableWidget.NoEditTriggers)
    history_layout.addWidget(history_table)
    window.usage_history_tables["Usage History"] = history_table
    window.usage_history_tabs.addTab(history_tab, "Usage History")
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
    window.linkshare_splitter.setHandleWidth(12)
    window.linkshare_splitter.setStyleSheet(
        "QSplitter::handle { background-color: #90a4ae; }"
        " QSplitter::handle:hover { background-color: #1976d2; }"
    )
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

    window.main_tabs.addTab(tab2_widget, "Wi-Fi Pass Manager (LinkShare)")
    window.main_tabs.setCurrentIndex(1 if current_main_tab == "wifi_pass" else 0)
    return tab2_widget
def update_captive_portal_status(window, text):
    label = getattr(window, 'captive_portal_status_label', None)
    if label is not None:
        label.setText(text)
