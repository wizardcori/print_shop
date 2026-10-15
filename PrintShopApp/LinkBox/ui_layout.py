import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QComboBox, QGroupBox, 
    QTabWidget, QGridLayout, QHeaderView, QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

def setup_ui(window, current_upload_folder, current_zones, current_save_tabs, interfaces):
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    
    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(10, 10, 10, 10)

    window.main_splitter = QSplitter(Qt.Vertical)
    window.main_splitter.setStyleSheet(
        "QSplitter::handle { background-color: #007BFF; height: 6px; border-radius: 3px; }"
        "QSplitter::handle:hover { background-color: #0056b3; }"
    )
    main_layout.addWidget(window.main_splitter)

    window.top_splitter = QSplitter(Qt.Horizontal)
    window.top_splitter.setStyleSheet(
        "QSplitter::handle { background-color: #007BFF; width: 6px; border-radius: 3px; }"
        "QSplitter::handle:hover { background-color: #0056b3; }"
    )
    window.main_splitter.addWidget(window.top_splitter)

    # 1. 왼쪽 그룹박스: Server & Connection Settings
    group_box = QGroupBox("Server & Connection Settings")
    group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
    left_layout = QVBoxLayout(group_box)

    folder_layout = QHBoxLayout()
    folder_layout.addWidget(QLabel("Save Location:"))
    window.folder_input = QLineEdit(current_upload_folder)
    window.folder_input.setReadOnly(True)
    folder_layout.addWidget(window.folder_input)
    
    window.folder_btn = QPushButton("Browse...")
    window.folder_btn.clicked.connect(window.select_save_folder)
    folder_layout.addWidget(window.folder_btn)
    
    window.settings_btn = QPushButton("⚙ Settings")
    window.settings_btn.clicked.connect(window.open_settings_dialog)
    folder_layout.addWidget(window.settings_btn)
    left_layout.addLayout(folder_layout)

    nic_layout = QHBoxLayout()
    nic_layout.addWidget(QLabel("Network Adapter:"))
    window.nic_combo = QComboBox()
    
    window.ip_data_map = {}
    for display_name, ip, is_connected in interfaces:
        window.nic_combo.addItem(display_name, ip)
        window.ip_data_map[display_name] = ip
        
        index = window.nic_combo.count() - 1
        window.nic_combo.setItemData(index, is_connected, Qt.UserRole + 1)
        color = QColor(0, 180, 0) if is_connected else QColor(220, 0, 0)
        window.nic_combo.setItemData(index, color, Qt.ForegroundRole)
        
    window.nic_combo.currentIndexChanged.connect(window.on_nic_index_changed)
    nic_layout.addWidget(window.nic_combo)
    left_layout.addLayout(nic_layout)

    save_tab_layout = QHBoxLayout()
    save_tab_layout.addWidget(QLabel("Save Tab:"))
    window.save_tab_combo = QComboBox()
    window.update_save_tab_combo_items()
    window.save_tab_combo.currentTextChanged.connect(window.on_save_tab_changed)
    save_tab_layout.addWidget(window.save_tab_combo)
    left_layout.addLayout(save_tab_layout)

    window.top_splitter.addWidget(group_box)

    # 2. 오른쪽 영역: [QR Location & Table Selection] + [QR 코드]
    right_container = QWidget()
    right_container_layout = QHBoxLayout(right_container)
    right_container_layout.setContentsMargins(0, 0, 0, 0)

    zone_group_box = QGroupBox("QR Location & Table Selection")
    zone_group_box.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #ccc; border-radius: 6px; margin-top: 6px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
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
    window.zone_buttons_layout.setContentsMargins(0, 5, 0, 5)
    window.update_zone_buttons()
    zone_group_layout.addWidget(window.zone_buttons_widget)

    right_container_layout.addWidget(zone_group_box)

    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)
    right_layout.setContentsMargins(10, 0, 0, 0)
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
    window.top_splitter.setSizes(window.initial_top_sizes if hasattr(window, 'initial_top_sizes') else [450, 450])

    # 3. 하단 영역 (로그 테이블)
    bottom_container = QWidget()
    bottom_layout = QVBoxLayout(bottom_container)
    bottom_layout.setContentsMargins(0, 0, 0, 0)
    
    bottom_layout.addWidget(QLabel("📂 LinkBox Received Transfer Log (Double click or Right click to open/delete):"))
    
    window.tab_widget = QTabWidget()
    window.tab_widget.setTabsClosable(True)
    window.tab_widget.tabCloseRequested.connect(window.close_tab)
    bottom_layout.addWidget(window.tab_widget)
    
    window.main_splitter.addWidget(bottom_container)
    window.main_splitter.setSizes(window.initial_main_sizes if hasattr(window, 'initial_main_sizes') else [450, 250])

def create_table_widget(window, identity):
    table = QTableWidget()
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels(["Name", "Zone", "File Name", "Size", "Time", "Status"])
    
    # 선택된 행(레코드)의 가시성을 극대화하기 위해 선명한 파란색 배경과 흰색 글씨로 강조
    table.setStyleSheet("""
        QTableWidget {
            font-size: 12px;
            color: #111111;
            background-color: #ffffff;
            gridline-color: #ced4da;
            selection-background-color: #0d6efd;
            selection-color: #ffffff;
        }
        QHeaderView::section {
            background-color: #e9ecef;
            padding: 6px;
            border: 1px solid #ced4da;
            font-weight: bold;
            font-size: 12px;
            color: #212529;
        }
    """)
    
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setStretchLastSection(True)
    
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    
    table.cellDoubleClicked.connect(window.on_row_double_clicked)
    table.setContextMenuPolicy(Qt.CustomContextMenu)
    table.customContextMenuRequested.connect(lambda pos, t=table: window.show_context_menu(pos, t))
    
    return table