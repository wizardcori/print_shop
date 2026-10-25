from curses import window
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QGroupBox, QSplitter, QTabWidget, QHeaderView, QPushButton, 
    QComboBox, QLineEdit, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtUiTools import QUiLoader

class CollapsibleStatusLabel(QLabel):
    def __init__(self, text='', parent=None):
        # QUiLoader가 부모 위젯을 첫 번째 인자(text)로 전달하는 경우 예외 처리
        if isinstance(text, QWidget):
            parent = text
            text = ''
            
        if parent is not None:
            super().__init__(parent)
        else:
            super().__init__()
            
        self._full_text = str(text or '')
        self._expanded = False
        self.setCursor(Qt.PointingHandCursor)
        self.setWordWrap(True)
        if text:
            self.setText(text)

    def setText(self, text):
        self._full_text = str(text or '')
        self._refresh_display()

    def _refresh_display(self):
        super().setText(self._full_text if self._expanded else self._full_text.split(' | ', 1)[0])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._refresh_display()
        super().mousePressEvent(event)

class AutoFitTextLabel(QLabel):
    def __init__(self, text='', point_size=11, parent=None):
        super().__init__(text, parent)
        self._base_point_size = point_size
        self.setWordWrap(False)

    def resizeEvent(self, event):
        self._fit_font()
        super().resizeEvent(event)

    def _fit_font(self):
        font = self.font()
        font.setBold(True)
        font.setPointSize(self._base_point_size)
        metrics = QFontMetrics(font)
        while font.pointSize() > 7 and metrics.horizontalAdvance(self.text()) > max(60, self.width() - 8):
            font.setPointSize(font.pointSize() - 1)
        self.setFont(font)


def create_tab(window, current_ssid, hotspot_nic, hotspot_image, hotspot_network, hotspot_gateway, max_connections, current_main_tab='file_receiver'):
    # 1. QUiLoader를 이용해 .ui 파일 로드[cite: 1]
    loader = QUiLoader()
    loader.registerCustomWidget(CollapsibleStatusLabel)
    loader.registerCustomWidget(AutoFitTextLabel)

    ui_file_path = os.path.join(os.path.dirname(__file__), "ui", "linkshare_layout.ui")
    if os.path.exists(ui_file_path):
        tab2_widget = loader.load(ui_file_path, window)
    else:
        tab2_widget = QWidget()
        QVBoxLayout(tab2_widget)

    # 2. UI 객체 매핑 및 동적 컨트롤 생성[cite: 1, 2]
    window.hotspot_horizontal_splitter = tab2_widget.findChild(QSplitter, "hotspot_horizontal_splitter")
    window.linkshare_splitter = tab2_widget.findChild(QSplitter, "linkshare_splitter")
    
    hotspot_control_group = tab2_widget.findChild(QGroupBox, "hotspot_control_group")
    hotspot_control_layout = hotspot_control_group.layout()
    window.hotspot_control_layout = hotspot_control_layout

    # 상단 핫스팟 컨트롤 버튼 레이아웃 구성[cite: 1, 2]
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

    for control in (window.hotspot_status_btn, window.hotspot_on_btn, window.hotspot_off_btn, window.hotspot_diagnose_btn):
        control.setMinimumWidth(0)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    for index in range(4):
        hotspot_controls.setStretch(index, 1)
        
    hotspot_control_layout.insertLayout(0, hotspot_controls)

    # 텍스트 및 라벨 세팅[cite: 1, 2]
    window.hotspot_name_label = tab2_widget.findChild(QLabel, "hotspot_name_label")
    window.hotspot_name_label.setText(f"Active Hotspot Name: <b>{current_ssid}</b> (Auto-started)")

    window.hotspot_nic_label = tab2_widget.findChild(QLabel, "hotspot_nic_label")
    window.hotspot_nic_label.setText(f"Hotspot NIC: <b>{hotspot_nic.get('display', 'Not selected')}</b>")

    window.hotspot_network_label = tab2_widget.findChild(QLabel, "hotspot_network_label")
    window.hotspot_network_label.setText(f"Hotspot IP range: <b>{hotspot_network}</b> / gateway: <b>{hotspot_gateway}</b>")

    window.captive_portal_status_label = tab2_widget.findChild(CollapsibleStatusLabel, "captive_portal_status_label")
    if window.captive_portal_status_label is None:
        window.captive_portal_status_label = CollapsibleStatusLabel("Captive Portal: starting...", tab2_widget)

    window.hotspot_status_label = tab2_widget.findChild(CollapsibleStatusLabel, "hotspot_status_label")
    if window.hotspot_status_label is None:
        window.hotspot_status_label = CollapsibleStatusLabel("Hotspot status: checking...", tab2_widget)

    window.hotspot_image_label = tab2_widget.findChild(QLabel, "hotspot_image_label")
    window.hotspot_image_label.setMaximumHeight(140)

    if hotspot_image and os.path.exists(hotspot_image):
        pixmap = QPixmap(hotspot_image)
        if not pixmap.isNull():
            window.hotspot_image_label.setPixmap(pixmap.scaled(320, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    else:
        window.hotspot_image_label.clear()

    # QR 그룹 박스 구성[cite: 1, 2]
    qr_group = tab2_widget.findChild(QGroupBox, "qr_group")
    qr_layout = qr_group.layout()
    qr_layout.setContentsMargins(1, 1, 1, 1)
    qr_layout.setSpacing(0)
    window.qr_layout = qr_layout

    qr_pair_layout = QHBoxLayout()
    
    # 네트워크 연결 그룹[cite: 1, 2]
    network_group = QGroupBox("Network Connection")
    network_group.setStyleSheet(
        "QGroupBox { color: #1565c0; font-weight: bold; background: #e3f2fd; "
        "border: 2px solid #64b5f6; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
    )
    network_layout = QHBoxLayout(network_group)
    window.hotspot_network_qr_label = QLabel()
    window.hotspot_network_qr_label.setAlignment(Qt.AlignCenter)
    window.hotspot_network_qr_label.setMaximumSize(220, 220)
    window.hotspot_network_qr_label.setStyleSheet("border: 1px solid #64b5f6; background-color: #ffffff; border-radius: 5px;")
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

    # 캡티브 포털 그룹[cite: 1, 2]
    captive_group = QGroupBox("Captive Portal")
    captive_group.setStyleSheet(
        "QGroupBox { color: #2e7d32; font-weight: bold; background: #e8f5e9; "
        "border: 2px solid #81c784; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
    )
    captive_layout = QHBoxLayout(captive_group)
    window.hotspot_qr_label = QLabel()
    window.hotspot_qr_label.setAlignment(Qt.AlignCenter)
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

    # 스플리터 설정[cite: 1, 2]
    window.hotspot_horizontal_splitter.setStretchFactor(0, 1)
    window.hotspot_horizontal_splitter.setStretchFactor(1, 3)
    window.hotspot_horizontal_splitter.setSizes([280, 900])

    card_style = (
        "QGroupBox { background-color: #ffffff; color: #17324d; border: 2px solid #90a4ae; "
        "border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }"
        " QGroupBox::title { color: #0d47a1; background-color: #ffffff; "
        "subcontrol-origin: margin; left: 12px; padding: 0 8px; }"
        " QLabel { color: #263238; font-weight: normal; background-color: transparent; }"
        " QLineEdit { color: #263238; background-color: #ffffff; border: 1px solid #b0bec5; border-radius: 4px; padding: 2px; }"
        " QComboBox { color: #263238; background-color: #ffffff; border: 1px solid #b0bec5; border-radius: 4px; padding: 2px; }"
        " QComboBox QAbstractItemView { color: #263238; background-color: #ffffff; selection-background-color: #1565c0; selection-color: #ffffff; }"
    )
    
    hotspot_info_group = tab2_widget.findChild(QGroupBox, "hotspot_info_group")
    hotspot_info_group.setStyleSheet(card_style)
    
    session_monitor_group = tab2_widget.findChild(QGroupBox, "session_monitor_group")
    if session_monitor_group:
        session_monitor_group.setStyleSheet(card_style)

    # 필터 그룹박스 설정
    linkshare_filter_group = tab2_widget.findChild(QGroupBox, "linkshare_filter_group")
    linkshare_filter_group.setStyleSheet(
        card_style + 
        " QLineEdit { color: #263238; background-color: #ffffff; border: 1px solid #90a4ae; border-radius: 4px; padding: 4px; }"
        " QComboBox { color: #263238; background-color: #ffffff; border: 1px solid #90a4ae; border-radius: 4px; padding: 4px; }"
    )
    
    # 💡 필터 영역이 세로로 찌그러지지 않도록 최소 높이 및 고정 정책 설정
    linkshare_filter_group.setMinimumHeight(75)
    linkshare_filter_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # 필터 그룹박스 설정 부근에 최소 높이 및 SizePolicy 추가
    linkshare_filter_group = tab2_widget.findChild(QGroupBox, "linkshare_filter_group")
    linkshare_filter_group.setStyleSheet(card_style)
    

    hotspot_control_group.setStyleSheet(card_style)
    qr_group.setStyleSheet(card_style)

    # 하단 상태 요약 그룹 구성[cite: 1, 2]
    window.status_group = tab2_widget.findChild(QGroupBox, "status_group")
    window.status_layout = window.status_group.layout()
    window.status_layout.setSpacing(12)
    
    window.status_title_label = AutoFitTextLabel("Currently Connected Clients Summary", 11)
    window.status_layout.addWidget(window.status_title_label, 1)
    
    window.status_label = AutoFitTextLabel(f"Devices connected: 0 of {max_connections}", 12)
    window.status_layout.addWidget(window.status_label)
    
    window.windows_hotspot_clients_label = AutoFitTextLabel("Windows Mobile Hotspot: checking actual client limit...", 10)
    window.status_layout.addWidget(window.windows_hotspot_clients_label, 2)
    
    window.status_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    window.status_group.setMaximumHeight(72)
    window.status_group.setStyleSheet(card_style)
    window.status_title_label.setStyleSheet("color: #0d47a1; font-weight: bold;")
    window.status_label.setStyleSheet("color: #1565c0; font-weight: bold;")
    window.windows_hotspot_clients_label.setStyleSheet("color: #455a64; font-weight: bold;")




    # 💡 4개 탭(Connection Status, Usage Requests, Usage Approvals, Usage History) 전체 명시적 순서 지정
    window.usage_history_tabs = tab2_widget.findChild(QTabWidget, "usage_history_tabs")
    window.usage_history_tabs.setStyleSheet(
        "QTabWidget::pane { border: 1px solid #90a4ae; background: #ffffff; border-radius: 4px; }"
        " QTabBar::tab { background: #eceff1; color: #37474f; padding: 6px 12px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }"
        " QTabBar::tab:selected { background: #1565c0; color: white; }"
        " QTabBar::tab:hover { background: #cfd8dc; color: #263238; }"
    )
    
    window.usage_history_tables = {}
    
    # 1. 4개 탭 및 각각의 헤더 정의 (순서 유지)
    usage_tabs = {
        "Connection Status": ["Connection Status", "Usage Approval", "Internet Connection", "Request Time", "Start Time", "End Time", "Total Requested", "Remaining", "IP Address"],
        "Usage Requests": ["Usage Request", "Request Time", "IP Address"],
        "Usage Approvals": ["Usage Approval", "Approval Time", "Requested Usage Time", "IP Address"],
        "Usage History": ["Request Time", "Approval Time", "Usage Time", "Amount"]
    }

    # 2. UI 파일에 기본 포함된 기존 탭을 제거하여 중복 및 순서 꼬임 방지
    while window.usage_history_tabs.count() > 0:
        window.usage_history_tabs.removeTab(0)

    # 3. 정의된 순서대로 4개 탭을 반복문으로 일괄 생성 및 등록
    for tab_name, headers in usage_tabs.items]:
        headers = headers + ["Cookie", "User Info"]
        usage_tab = QWidget()
        usage_tab_layout = QVBoxLayout(usage_tab)
        
        # Usage History 탭의 경우 UI에 정의된 history_table을 재사용, 나머지는 새 테이블 생성
        if tab_name == "Usage History":
            table = tab2_widget.findChild(QTableWidget, "history_table")
            if table is None:
                table = QTableWidget(0, len(headers))
            table.setHorizontalHeaderLabels(headers)
        else:
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

    # UI 파일에 정의된 필터 요소를 findChild로 불러오기[cite: 1, 2]
    window.usage_history_filter = tab2_widget.findChild(QComboBox, "usage_history_filter")
    window.usage_history_filter.clear()
    window.usage_history_filter.addItems([
        "Today", "Yesterday", 
        "2 days ago", "3 days ago", "4 days ago", 
        "5 days ago", "6 days ago", "7 days ago", "Custom", "All" 
    ])

    # 💡 2. 탭별 필터 상태를 기억하기 위한 저장소 초기화
    if not hasattr(window, 'tab_filter_states'):
        window.tab_filter_states = {}
        for t_name in usage_tabs.keys():
            window.tab_filter_states[t_name] = {
                "combo_index": 0,
                "start": "",
                "end": ""
            }

    # 플래그: 프로그램적 값 변경 시 무한 루프/중복 시그널 방지
    window._is_updating_filter_ui = False

    window.usage_history_start = tab2_widget.findChild(QLineEdit, "usage_history_start")
    window.usage_history_end = tab2_widget.findChild(QLineEdit, "usage_history_end")
    
    window.usage_history_total_label = tab2_widget.findChild(QLabel, "usage_history_total_label")
    
    # 💡 [개선 반영] 누적 사용량/금액 라벨 가독성 및 컬러 명시[cite: 1, 2]
    window.usage_history_total_label.setStyleSheet(
        "QLabel { color: #0d47a1; background-color: #f5f5f5; font-weight: bold; padding: 6px; border-radius: 4px; border: 1px solid #cfd8dc; }"
    )
    
    history_table = tab2_widget.findChild(QTableWidget, "history_table")
    history_table.setHorizontalHeaderLabels(["Request Time", "Approval Time", "Usage Time", "Amount", "Cookie", "User Info"])
    history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    history_table.horizontalHeader().setStretchLastSection(True)
    history_table.setEditTriggers(QTableWidget.NoEditTriggers)
    history_table.setStyleSheet(
        "QTableWidget { background-color: #ffffff; color: #263238; "
        "gridline-color: #b0bec5; }"
        " QHeaderView::section { background-color: #1565c0; color: white; "
        "font-weight: bold; padding: 4px; }"
    )
    
    window.usage_history_tables["Usage History"] = history_table
    
    window.usage_history_filter.currentIndexChanged.connect(window.update_usage_history_tables)
    window.usage_history_start.textChanged.connect(window.update_usage_history_tables)
    window.usage_history_end.textChanged.connect(window.update_usage_history_tables)
    window.usage_history_tabs.currentChanged.connect(window.on_usage_history_tab_changed)

    status_panel = tab2_widget.findChild(QWidget, "status_panel")
    status_panel_layout = status_panel.layout()
    status_panel_layout.addWidget(window.status_group, 0)
    status_panel_layout.addWidget(window.usage_history_tabs, 1)
    
    hotspot_info_group.setMinimumHeight(120)
    status_panel.setMinimumHeight(100)
    
    # 세로 스플리터 영역 설정[cite: 1, 2]
    window.linkshare_splitter.setStretchFactor(0, 3)
    window.linkshare_splitter.setStretchFactor(1, 3)
    window.linkshare_splitter.setSizes(getattr(window, 'linkshare_splitter_sizes', [450, 450]))
    window.linkshare_splitter.splitterMoved.connect(window.handle_linkshare_splitter_moved)
    
    window.linkshare_splitter_save_timer = QTimer(window)
    window.linkshare_splitter_save_timer.setSingleShot(True)
    window.linkshare_splitter_save_timer.setInterval(250)
    window.linkshare_splitter_save_timer.timeout.connect(window.persist_settings)

    QTimer.singleShot(0, window.adjust_linkshare_spacing)

    window.main_tabs.addTab(tab2_widget, "Wi-Fi Pass Manager (LinkShare)")
    window.main_titles = getattr(window, 'main_titles', [])
    window.main_tabs.setCurrentIndex(1 if current_main_tab == "wifi_pass" else 0)
    return tab2_widget


def update_captive_portal_status(window, text):
    label = getattr(window, 'captive_portal_status_label', None)
    if label is not None:
        label.setText(text)


# 💡 3. 필터 콤보박스 변경 함수
def on_filter_combo_changed(index):
    if window._is_updating_filter_ui:
        return
        
    current_tab_idx = window.usage_history_tabs.currentIndex()
    current_tab_name = window.usage_history_tabs.tabText(current_tab_idx)
    
    combo_text = window.usage_history_filter.currentText()
    
    # 날짜 계산 로직 (오늘 기준)
    from datetime import datetime, timedelta
    today = datetime.now().date()
    
    start_date = ""
    end_date = ""
    
    if combo_text == "Today":
        start_date = end_date = today.strftime("%Y-%m-%d")
    elif combo_text == "Yesterday":
        d = today - timedelta(days=1)
        start_date = end_date = d.strftime("%Y-%m-%d")
    elif "days ago" in combo_text:
        # 예: "2 days ago" -> 숫자 추출
        days_num = int(combo_text.split()[0])
        d = today - timedelta(days=days_num)
        start_date = end_date = d.strftime("%Y-%m-%d")
    elif combo_text == "All":
        start_date = ""
        end_date = ""
        
    window._is_updating_filter_ui = True
    if combo_text != "Custom":
        window.usage_history_start.setText(start_date)
        window.usage_history_end.setText(end_date)
    window._is_updating_filter_ui = False
    
    # 현재 탭 상태에 저장
    window.tab_filter_states[current_tab_name] = {
        "combo_index": index,
        "start": window.usage_history_start.text(),
        "end": window.usage_history_end.text()
    }
    
    # 테이블 필터링 실행
    window.update_usage_history_tables()

# 💡 4. 날짜(Start/End) 변경 시그널 및 필터 날짜 변경 처리 함수
def on_date_field_changed():
    if window._is_updating_filter_ui:
        return
        
    current_tab_idx = window.usage_history_tabs.currentIndex()
    current_tab_name = window.usage_history_tabs.tabText(current_tab_idx)
    
    start_val = window.usage_history_start.text().strip()
    end_val = window.usage_history_end.text().strip()
    
    # 사용자가 직접 날짜를 수정했으므로 콤보박스를 'Custom'으로 변경 (Custom이 마지막 인덱스라 가정)
    if start_val or end_val:
        window._is_updating_filter_ui = True
        custom_idx = window.usage_history_filter.count() - 1
        window.usage_history_filter.setCurrentIndex(custom_idx)
        window._is_updating_filter_ui = False

    # 상태 기억 저장
    window.tab_filter_states[current_tab_name] = {
        "combo_index": window.usage_history_filter.currentIndex(),
        "start": start_val,
        "end": end_val
    }
    
    # 필터 날짜 변경 시그널 발생 및 현재 열린 탭에 적용하여 필터링
    window.update_usage_history_tables()

# 💡 5. 탭 전환 시 실행되는 함수
def custom_tab_changed(index):
    tab_name = window.usage_history_tabs.tabText(index)
    state = window.tab_filter_states.get(tab_name, {"combo_index": 0, "start": "", "end": ""})
    
    window._is_updating_filter_ui = True
    window.usage_history_filter.setCurrentIndex(state["combo_index"])
    window.usage_history_start.setText(state["start"])
    window.usage_history_end.setText(state["end"])
    window._is_updating_filter_ui = False
    
    # 기존 정의된 탭 변경 핸들러 호출 및 현재 탭 필터링 갱신
    if hasattr(window, 'on_usage_history_tab_changed'):
        window.on_usage_history_tab_changed(index)
    window.update_usage_history_tables()

# 시그널 연결
window.usage_history_filter.currentIndexChanged.connect(on_filter_combo_changed)
window.usage_history_start.textChanged.connect(on_date_field_changed)
window.usage_history_end.textChanged.connect(on_date_field_changed)
window.usage_history_tabs.currentChanged.connect(custom_tab_changed)        


TAB_TITLE = "🌐 Wi-Fi Pass Manager (LinkShare)"

def register_tab(tab_widget, content_widget):
    return tab_widget.addTab(content_widget, TAB_TITLE)