# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'linkshare_layout.ui'
##
## Created by: Qt User Interface Compiler version 6.12.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSplitter, QTabWidget, QVBoxLayout, QWidget)

from LinkShare.linkshare import (AutoFitTextLabel, CollapsibleStatusLabel)

class Ui_LinkShareLayout(object):
    def setupUi(self, LinkShareLayout):
        if not LinkShareLayout.objectName():
            LinkShareLayout.setObjectName(u"LinkShareLayout")
        LinkShareLayout.resize(1180, 800)
        self.main_vertical_layout = QVBoxLayout(LinkShareLayout)
        self.main_vertical_layout.setObjectName(u"main_vertical_layout")
        self.main_vertical_layout.setContentsMargins(0, 0, 0, 0)
        self.linkshare_splitter = QSplitter(LinkShareLayout)
        self.linkshare_splitter.setObjectName(u"linkshare_splitter")
        self.linkshare_splitter.setOrientation(Qt.Vertical)
        self.top_container = QWidget(self.linkshare_splitter)
        self.top_container.setObjectName(u"top_container")
        self.top_container_layout = QVBoxLayout(self.top_container)
        self.top_container_layout.setObjectName(u"top_container_layout")
        self.top_container_layout.setContentsMargins(0, 0, 0, 0)
        self.qr_group_box = QGroupBox(self.top_container)
        self.qr_group_box.setObjectName(u"qr_group_box")
        self.qr_group_box_layout = QVBoxLayout(self.qr_group_box)
        self.qr_group_box_layout.setSpacing(4)
        self.qr_group_box_layout.setObjectName(u"qr_group_box_layout")
        self.qr_group_box_layout.setContentsMargins(4, 4, 4, 4)
        self.qr_pair_layout = QHBoxLayout()
        self.qr_pair_layout.setSpacing(6)
        self.qr_pair_layout.setObjectName(u"qr_pair_layout")
        self.network_qr_box = QGroupBox(self.qr_group_box)
        self.network_qr_box.setObjectName(u"network_qr_box")
        self.network_qr_box.setStyleSheet(u"QGroupBox { color: #1565c0; font-weight: bold; background: #e3f2fd; border: 2px solid #64b5f6; border-radius: 6px; margin-top: 8px; padding-top: 8px; }")
        self.network_qr_box_layout = QVBoxLayout(self.network_qr_box)
        self.network_qr_box_layout.setSpacing(4)
        self.network_qr_box_layout.setObjectName(u"network_qr_box_layout")
        self.network_qr_box_layout.setContentsMargins(6, -1, 6, 6)
        self.hotspot_network_qr_label = QLabel(self.network_qr_box)
        self.hotspot_network_qr_label.setObjectName(u"hotspot_network_qr_label")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.hotspot_network_qr_label.sizePolicy().hasHeightForWidth())
        self.hotspot_network_qr_label.setSizePolicy(sizePolicy)
        self.hotspot_network_qr_label.setStyleSheet(u"border: 1px solid #64b5f6; background-color: #ffffff; border-radius: 5px;")
        self.hotspot_network_qr_label.setAlignment(Qt.AlignCenter)

        self.network_qr_box_layout.addWidget(self.hotspot_network_qr_label)

        self.network_bottom_layout = QHBoxLayout()
        self.network_bottom_layout.setObjectName(u"network_bottom_layout")
        self.hotspot_network_info_label = QLabel(self.network_qr_box)
        self.hotspot_network_info_label.setObjectName(u"hotspot_network_info_label")
        self.hotspot_network_info_label.setStyleSheet(u"font-size: 11px; font-weight: bold; color: #263238;")
        self.hotspot_network_info_label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)

        self.network_bottom_layout.addWidget(self.hotspot_network_info_label)

        self.network_print_btn = QPushButton(self.network_qr_box)
        self.network_print_btn.setObjectName(u"network_print_btn")
        self.network_print_btn.setFixedSize(QSize(84, 28))
        self.network_print_btn.setStyleSheet(u"QPushButton { color: #0d47a1; background-color: #e3f2fd; border: 1px solid #64b5f6; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold; }\n"
"QPushButton:hover { background-color: #bbdefb; }")

        self.network_bottom_layout.addWidget(self.network_print_btn, 0, Qt.AlignRight)


        self.network_qr_box_layout.addLayout(self.network_bottom_layout)


        self.qr_pair_layout.addWidget(self.network_qr_box)

        self.captive_qr_box = QGroupBox(self.qr_group_box)
        self.captive_qr_box.setObjectName(u"captive_qr_box")
        self.captive_qr_box.setStyleSheet(u"QGroupBox { color: #2e7d32; font-weight: bold; background: #e8f5e9; border: 2px solid #81c784; border-radius: 6px; margin-top: 8px; padding-top: 8px; }")
        self.captive_qr_box_layout = QVBoxLayout(self.captive_qr_box)
        self.captive_qr_box_layout.setSpacing(4)
        self.captive_qr_box_layout.setObjectName(u"captive_qr_box_layout")
        self.captive_qr_box_layout.setContentsMargins(6, -1, 6, 6)
        self.hotspot_qr_label = QLabel(self.captive_qr_box)
        self.hotspot_qr_label.setObjectName(u"hotspot_qr_label")
        sizePolicy.setHeightForWidth(self.hotspot_qr_label.sizePolicy().hasHeightForWidth())
        self.hotspot_qr_label.setSizePolicy(sizePolicy)
        self.hotspot_qr_label.setStyleSheet(u"border: 1px solid #ccc; background-color: #f9f9f9; border-radius: 5px;")
        self.hotspot_qr_label.setAlignment(Qt.AlignCenter)

        self.captive_qr_box_layout.addWidget(self.hotspot_qr_label)

        self.captive_single_line_layout = QHBoxLayout()
        self.captive_single_line_layout.setSpacing(8)
        self.captive_single_line_layout.setObjectName(u"captive_single_line_layout")
        self.hotspot_qr_caption = QLabel(self.captive_qr_box)
        self.hotspot_qr_caption.setObjectName(u"hotspot_qr_caption")
        self.hotspot_qr_caption.setStyleSheet(u"font-size: 9px; font-weight: bold; color: #16803c;")
        self.hotspot_qr_caption.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)

        self.captive_single_line_layout.addWidget(self.hotspot_qr_caption)

        self.hotspot_url_label = QLabel(self.captive_qr_box)
        self.hotspot_url_label.setObjectName(u"hotspot_url_label")
        self.hotspot_url_label.setStyleSheet(u"font-size: 9px; font-weight: bold; color: #007BFF;")
        self.hotspot_url_label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        self.hotspot_url_label.setWordWrap(False)

        self.captive_single_line_layout.addWidget(self.hotspot_url_label)

        self.captive_print_btn = QPushButton(self.captive_qr_box)
        self.captive_print_btn.setObjectName(u"captive_print_btn")
        self.captive_print_btn.setFixedSize(QSize(84, 28))
        self.captive_print_btn.setStyleSheet(u"QPushButton { color: #1b5e20; background-color: #e8f5e9; border: 1px solid #81c784; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold; }\n"
"QPushButton:hover { background-color: #c8e6c9; }")

        self.captive_single_line_layout.addWidget(self.captive_print_btn, 0, Qt.AlignRight)


        self.captive_qr_box_layout.addLayout(self.captive_single_line_layout)


        self.qr_pair_layout.addWidget(self.captive_qr_box)


        self.qr_group_box_layout.addLayout(self.qr_pair_layout)


        self.top_container_layout.addWidget(self.qr_group_box)

        self.linkshare_splitter.addWidget(self.top_container)
        self.bottom_container = QWidget(self.linkshare_splitter)
        self.bottom_container.setObjectName(u"bottom_container")
        self.bottom_container_layout = QVBoxLayout(self.bottom_container)
        self.bottom_container_layout.setObjectName(u"bottom_container_layout")
        self.bottom_container_layout.setContentsMargins(0, 0, 0, 0)
        self.status_group = QGroupBox(self.bottom_container)
        self.status_group.setObjectName(u"status_group")
        self.status_group.setMaximumSize(QSize(16777215, 72))
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.status_group.sizePolicy().hasHeightForWidth())
        self.status_group.setSizePolicy(sizePolicy1)
        self.status_group.setStyleSheet(u"QGroupBox { background-color: #ffffff; color: #17324d; border: 2px solid #90a4ae; border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }\n"
"QGroupBox::title { color: #0d47a1; background-color: #ffffff; subcontrol-origin: margin; left: 12px; padding: 0 8px; }")
        self.status_layout = QHBoxLayout(self.status_group)
        self.status_layout.setSpacing(12)
        self.status_layout.setObjectName(u"status_layout")
        self.status_title_label = AutoFitTextLabel(self.status_group)
        self.status_title_label.setObjectName(u"status_title_label")
        self.status_title_label.setStyleSheet(u"color: #0d47a1; font-weight: bold;")

        self.status_layout.addWidget(self.status_title_label)

        self.status_label = AutoFitTextLabel(self.status_group)
        self.status_label.setObjectName(u"status_label")
        self.status_label.setStyleSheet(u"color: #1565c0; font-weight: bold;")

        self.status_layout.addWidget(self.status_label)

        self.windows_hotspot_clients_label = AutoFitTextLabel(self.status_group)
        self.windows_hotspot_clients_label.setObjectName(u"windows_hotspot_clients_label")
        self.windows_hotspot_clients_label.setStyleSheet(u"color: #455a64; font-weight: bold;")

        self.status_layout.addWidget(self.windows_hotspot_clients_label)


        self.bottom_container_layout.addWidget(self.status_group)

        self.linkshare_filter_group = QGroupBox(self.bottom_container)
        self.linkshare_filter_group.setObjectName(u"linkshare_filter_group")
        self.linkshare_filter_group.setMinimumSize(QSize(0, 75))
        sizePolicy1.setHeightForWidth(self.linkshare_filter_group.sizePolicy().hasHeightForWidth())
        self.linkshare_filter_group.setSizePolicy(sizePolicy1)
        self.linkshare_filter_group.setStyleSheet(u"QGroupBox { background-color: #ffffff; color: #17324d; border: 2px solid #90a4ae; border-radius: 8px; margin-top: 8px; padding-top: 12px; font-weight: bold; }\n"
"QGroupBox::title { color: #0d47a1; background-color: #ffffff; subcontrol-origin: margin; left: 12px; padding: 0 8px; }\n"
"QLineEdit { color: #263238; background-color: #ffffff; border: 1px solid #90a4ae; border-radius: 4px; padding: 4px; }\n"
"QComboBox { color: #263238; background-color: #ffffff; border: 1px solid #90a4ae; border-radius: 4px; padding: 4px; }")
        self.filter_layout = QHBoxLayout(self.linkshare_filter_group)
        self.filter_layout.setObjectName(u"filter_layout")
        self.filter_label = QLabel(self.linkshare_filter_group)
        self.filter_label.setObjectName(u"filter_label")

        self.filter_layout.addWidget(self.filter_label)

        self.internet_share_filter = QComboBox(self.linkshare_filter_group)
        self.internet_share_filter.setObjectName(u"internet_share_filter")

        self.filter_layout.addWidget(self.internet_share_filter)

        self.internet_share_start = QLineEdit(self.linkshare_filter_group)
        self.internet_share_start.setObjectName(u"internet_share_start")

        self.filter_layout.addWidget(self.internet_share_start)

        self.tilde_label = QLabel(self.linkshare_filter_group)
        self.tilde_label.setObjectName(u"tilde_label")

        self.filter_layout.addWidget(self.tilde_label)

        self.internet_share_end = QLineEdit(self.linkshare_filter_group)
        self.internet_share_end.setObjectName(u"internet_share_end")

        self.filter_layout.addWidget(self.internet_share_end)

        self.internet_share_total_label = QLabel(self.linkshare_filter_group)
        self.internet_share_total_label.setObjectName(u"internet_share_total_label")

        self.filter_layout.addWidget(self.internet_share_total_label)

        self.show_approval_btn = QPushButton(self.linkshare_filter_group)
        self.show_approval_btn.setObjectName(u"show_approval_btn")
        self.show_approval_btn.setStyleSheet(u"QPushButton { color: white; background-color: #1565c0; border: 1px solid #0d47a1; border-radius: 4px; padding: 4px 12px; font-weight: bold; } QPushButton:hover { background-color: #0d47a1; }")

        self.filter_layout.addWidget(self.show_approval_btn)


        self.bottom_container_layout.addWidget(self.linkshare_filter_group)

        self.internet_share_tabs = QTabWidget(self.bottom_container)
        self.internet_share_tabs.setObjectName(u"internet_share_tabs")
        self.internet_share_tabs.setStyleSheet(u"QTabWidget::pane { border: 1px solid #90a4ae; background: #ffffff; border-radius: 4px; }\n"
"QTabBar::tab { background: #eceff1; color: #37474f; padding: 6px 12px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }\n"
"QTabBar::tab:selected { background: #1565c0; color: white; }\n"
"QTabBar::tab:hover { background: #cfd8dc; color: #263238; }")

        self.bottom_container_layout.addWidget(self.internet_share_tabs)

        self.linkshare_splitter.addWidget(self.bottom_container)

        self.main_vertical_layout.addWidget(self.linkshare_splitter)


        self.retranslateUi(LinkShareLayout)

        QMetaObject.connectSlotsByName(LinkShareLayout)
    # setupUi

    def retranslateUi(self, LinkShareLayout):
        LinkShareLayout.setWindowTitle(QCoreApplication.translate("LinkShareLayout", u"Form", None))
        self.qr_group_box.setTitle(QCoreApplication.translate("LinkShareLayout", u"Wi-Fi & Portal QR Codes", None))
        self.network_qr_box.setTitle(QCoreApplication.translate("LinkShareLayout", u"Network Connection", None))
        self.hotspot_network_info_label.setText(QCoreApplication.translate("LinkShareLayout", u"SSID: - | Password: -", None))
        self.network_print_btn.setText(QCoreApplication.translate("LinkShareLayout", u"PRINT", None))
        self.captive_qr_box.setTitle(QCoreApplication.translate("LinkShareLayout", u"Captive Portal", None))
        self.hotspot_qr_caption.setText(QCoreApplication.translate("LinkShareLayout", u"This QR code is for Internet access requests.", None))
        self.hotspot_url_label.setText(QCoreApplication.translate("LinkShareLayout", u"Generated URL: ", None))
        self.captive_print_btn.setText(QCoreApplication.translate("LinkShareLayout", u"PRINT", None))
        self.status_group.setTitle(QCoreApplication.translate("LinkShareLayout", u"Client Connection Summary", None))
        self.status_title_label.setText(QCoreApplication.translate("LinkShareLayout", u"Currently Connected Clients Summary", None))
        self.status_label.setText(QCoreApplication.translate("LinkShareLayout", u"Devices connected: 0 of 8", None))
        self.windows_hotspot_clients_label.setText(QCoreApplication.translate("LinkShareLayout", u"Windows Mobile Hotspot: checking actual client limit...", None))
        self.linkshare_filter_group.setTitle(QCoreApplication.translate("LinkShareLayout", u"Filter & Quick Controls", None))
        self.filter_label.setText(QCoreApplication.translate("LinkShareLayout", u"Date Filter:", None))
        self.internet_share_start.setPlaceholderText(QCoreApplication.translate("LinkShareLayout", u"YYYY-MM-DD", None))
        self.tilde_label.setText(QCoreApplication.translate("LinkShareLayout", u"~", None))
        self.internet_share_end.setPlaceholderText(QCoreApplication.translate("LinkShareLayout", u"YYYY-MM-DD", None))
        self.internet_share_total_label.setText(QCoreApplication.translate("LinkShareLayout", u"Total: 0", None))
        self.show_approval_btn.setText(QCoreApplication.translate("LinkShareLayout", u"Show Approval", None))
    # retranslateUi

