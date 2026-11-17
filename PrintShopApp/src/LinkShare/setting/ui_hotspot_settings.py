# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'hotspot_settings.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QSpinBox,
    QVBoxLayout, QWidget)
class Ui_HotspotSettingsWidget(object):
    def setupUi(self, HotspotSettingsWidget):
        if not HotspotSettingsWidget.objectName():
            HotspotSettingsWidget.setObjectName(u"HotspotSettingsWidget")
        HotspotSettingsWidget.resize(1200, 950)
        self.main_layout = QVBoxLayout(HotspotSettingsWidget)
        self.main_layout.setObjectName(u"main_layout")
        self.hotspot_control_group = QGroupBox(HotspotSettingsWidget)
        self.hotspot_control_group.setObjectName(u"hotspot_control_group")
        self.hotspot_control_layout = QVBoxLayout(self.hotspot_control_group)
        self.hotspot_control_layout.setObjectName(u"hotspot_control_layout")
        self.hotspot_controls_layout = QHBoxLayout()
        self.hotspot_controls_layout.setObjectName(u"hotspot_controls_layout")
        self.hotspot_status_btn = QLabel(self.hotspot_control_group)
        self.hotspot_status_btn.setObjectName(u"hotspot_status_btn")
        self.hotspot_status_btn.setAlignment(Qt.AlignCenter)

        self.hotspot_controls_layout.addWidget(self.hotspot_status_btn)

        self.hotspot_on_btn = QPushButton(self.hotspot_control_group)
        self.hotspot_on_btn.setObjectName(u"hotspot_on_btn")

        self.hotspot_controls_layout.addWidget(self.hotspot_on_btn)

        self.hotspot_off_btn = QPushButton(self.hotspot_control_group)
        self.hotspot_off_btn.setObjectName(u"hotspot_off_btn")

        self.hotspot_controls_layout.addWidget(self.hotspot_off_btn)

        self.hotspot_diagnose_btn = QPushButton(self.hotspot_control_group)
        self.hotspot_diagnose_btn.setObjectName(u"hotspot_diagnose_btn")

        self.hotspot_controls_layout.addWidget(self.hotspot_diagnose_btn)


        self.hotspot_control_layout.addLayout(self.hotspot_controls_layout)

        self.active_info_layout = QHBoxLayout()
        self.active_info_layout.setObjectName(u"active_info_layout")
        self.active_name_label = QLabel(self.hotspot_control_group)
        self.active_name_label.setObjectName(u"active_name_label")

        self.active_info_layout.addWidget(self.active_name_label)

        self.active_nic_label = QLabel(self.hotspot_control_group)
        self.active_nic_label.setObjectName(u"active_nic_label")

        self.active_info_layout.addWidget(self.active_nic_label)

        self.active_range_label = QLabel(self.hotspot_control_group)
        self.active_range_label.setObjectName(u"active_range_label")

        self.active_info_layout.addWidget(self.active_range_label)


        self.hotspot_control_layout.addLayout(self.active_info_layout)


        self.main_layout.addWidget(self.hotspot_control_group)

        self.qr_group = QGroupBox(HotspotSettingsWidget)
        self.qr_group.setObjectName(u"qr_group")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.qr_group.sizePolicy().hasHeightForWidth())
        self.qr_group.setSizePolicy(sizePolicy)
        self.qr_outer_layout = QVBoxLayout(self.qr_group)
        self.qr_outer_layout.setObjectName(u"qr_outer_layout")
        self.qr_layout = QHBoxLayout()
        self.qr_layout.setObjectName(u"qr_layout")
        self.network_group = QGroupBox(self.qr_group)
        self.network_group.setObjectName(u"network_group")
        self.network_layout = QVBoxLayout(self.network_group)
        self.network_layout.setObjectName(u"network_layout")
        self.hotspot_network_qr_label = QLabel(self.network_group)
        self.hotspot_network_qr_label.setObjectName(u"hotspot_network_qr_label")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.hotspot_network_qr_label.sizePolicy().hasHeightForWidth())
        self.hotspot_network_qr_label.setSizePolicy(sizePolicy1)
        self.hotspot_network_qr_label.setAlignment(Qt.AlignCenter)
        self.hotspot_network_qr_label.setScaledContents(False)

        self.network_layout.addWidget(self.hotspot_network_qr_label)

        self.net_bottom_container = QWidget(self.network_group)
        self.net_bottom_container.setObjectName(u"net_bottom_container")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.net_bottom_container.sizePolicy().hasHeightForWidth())
        self.net_bottom_container.setSizePolicy(sizePolicy2)
        self.net_bottom_group_layout = QVBoxLayout(self.net_bottom_container)
        self.net_bottom_group_layout.setSpacing(4)
        self.net_bottom_group_layout.setObjectName(u"net_bottom_group_layout")
        self.net_bottom_group_layout.setContentsMargins(0, 0, 0, 0)
        self.hotspot_network_info_label = QLabel(self.net_bottom_container)
        self.hotspot_network_info_label.setObjectName(u"hotspot_network_info_label")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.hotspot_network_info_label.sizePolicy().hasHeightForWidth())
        self.hotspot_network_info_label.setSizePolicy(sizePolicy3)

        self.net_bottom_group_layout.addWidget(self.hotspot_network_info_label)

        self.net_btn_layout = QHBoxLayout()
        self.net_btn_layout.setObjectName(u"net_btn_layout")
        self.network_print_btn = QPushButton(self.net_bottom_container)
        self.network_print_btn.setObjectName(u"network_print_btn")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(1)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.network_print_btn.sizePolicy().hasHeightForWidth())
        self.network_print_btn.setSizePolicy(sizePolicy4)

        self.net_btn_layout.addWidget(self.network_print_btn)

        self.network_folder_btn = QPushButton(self.net_bottom_container)
        self.network_folder_btn.setObjectName(u"network_folder_btn")
        sizePolicy4.setHeightForWidth(self.network_folder_btn.sizePolicy().hasHeightForWidth())
        self.network_folder_btn.setSizePolicy(sizePolicy4)

        self.net_btn_layout.addWidget(self.network_folder_btn)


        self.net_bottom_group_layout.addLayout(self.net_btn_layout)


        self.network_layout.addWidget(self.net_bottom_container)


        self.qr_layout.addWidget(self.network_group)

        self.captive_group = QGroupBox(self.qr_group)
        self.captive_group.setObjectName(u"captive_group")
        self.captive_layout = QVBoxLayout(self.captive_group)
        self.captive_layout.setObjectName(u"captive_layout")
        self.hotspot_qr_label = QLabel(self.captive_group)
        self.hotspot_qr_label.setObjectName(u"hotspot_qr_label")
        sizePolicy1.setHeightForWidth(self.hotspot_qr_label.sizePolicy().hasHeightForWidth())
        self.hotspot_qr_label.setSizePolicy(sizePolicy1)
        self.hotspot_qr_label.setAlignment(Qt.AlignCenter)
        self.hotspot_qr_label.setScaledContents(False)

        self.captive_layout.addWidget(self.hotspot_qr_label)

        self.cap_bottom_container = QWidget(self.captive_group)
        self.cap_bottom_container.setObjectName(u"cap_bottom_container")
        sizePolicy2.setHeightForWidth(self.cap_bottom_container.sizePolicy().hasHeightForWidth())
        self.cap_bottom_container.setSizePolicy(sizePolicy2)
        self.cap_bottom_group_layout = QVBoxLayout(self.cap_bottom_container)
        self.cap_bottom_group_layout.setSpacing(4)
        self.cap_bottom_group_layout.setObjectName(u"cap_bottom_group_layout")
        self.cap_bottom_group_layout.setContentsMargins(0, 0, 0, 0)
        self.qr_caption = QLabel(self.cap_bottom_container)
        self.qr_caption.setObjectName(u"qr_caption")
        sizePolicy3.setHeightForWidth(self.qr_caption.sizePolicy().hasHeightForWidth())
        self.qr_caption.setSizePolicy(sizePolicy3)

        self.cap_bottom_group_layout.addWidget(self.qr_caption)

        self.cap_btn_layout = QHBoxLayout()
        self.cap_btn_layout.setObjectName(u"cap_btn_layout")
        self.captive_print_btn = QPushButton(self.cap_bottom_container)
        self.captive_print_btn.setObjectName(u"captive_print_btn")
        sizePolicy4.setHeightForWidth(self.captive_print_btn.sizePolicy().hasHeightForWidth())
        self.captive_print_btn.setSizePolicy(sizePolicy4)

        self.cap_btn_layout.addWidget(self.captive_print_btn)

        self.captive_folder_btn = QPushButton(self.cap_bottom_container)
        self.captive_folder_btn.setObjectName(u"captive_folder_btn")
        sizePolicy4.setHeightForWidth(self.captive_folder_btn.sizePolicy().hasHeightForWidth())
        self.captive_folder_btn.setSizePolicy(sizePolicy4)

        self.cap_btn_layout.addWidget(self.captive_folder_btn)


        self.cap_bottom_group_layout.addLayout(self.cap_btn_layout)


        self.captive_layout.addWidget(self.cap_bottom_container)


        self.qr_layout.addWidget(self.captive_group)


        self.qr_outer_layout.addLayout(self.qr_layout)

        self.basic_settings_group = QGroupBox(self.qr_group)
        self.basic_settings_group.setObjectName(u"basic_settings_group")
        self.basic_settings_grid = QGridLayout(self.basic_settings_group)
        self.basic_settings_grid.setObjectName(u"basic_settings_grid")
        self.ssid_row_layout = QHBoxLayout()
        self.ssid_row_layout.setObjectName(u"ssid_row_layout")
        self.lbl_ssid = QLabel(self.basic_settings_group)
        self.lbl_ssid.setObjectName(u"lbl_ssid")

        self.ssid_row_layout.addWidget(self.lbl_ssid)

        self.ssid_input = QLineEdit(self.basic_settings_group)
        self.ssid_input.setObjectName(u"ssid_input")

        self.ssid_row_layout.addWidget(self.ssid_input)


        self.basic_settings_grid.addLayout(self.ssid_row_layout, 0, 0, 1, 3)

        self.startup_checkbox = QCheckBox(self.basic_settings_group)
        self.startup_checkbox.setObjectName(u"startup_checkbox")

        self.basic_settings_grid.addWidget(self.startup_checkbox, 1, 0, 1, 1)

        self.file_transfer_internet_checkbox = QCheckBox(self.basic_settings_group)
        self.file_transfer_internet_checkbox.setObjectName(u"file_transfer_internet_checkbox")

        self.basic_settings_grid.addWidget(self.file_transfer_internet_checkbox, 1, 1, 1, 1)

        self.max_conn_layout = QHBoxLayout()
        self.max_conn_layout.setObjectName(u"max_conn_layout")
        self.lbl_max_conn = QLabel(self.basic_settings_group)
        self.lbl_max_conn.setObjectName(u"lbl_max_conn")

        self.max_conn_layout.addWidget(self.lbl_max_conn)

        self.max_connections_input = QSpinBox(self.basic_settings_group)
        self.max_connections_input.setObjectName(u"max_connections_input")

        self.max_conn_layout.addWidget(self.max_connections_input)


        self.basic_settings_grid.addLayout(self.max_conn_layout, 1, 2, 1, 1)

        self.lbl_password = QLabel(self.basic_settings_group)
        self.lbl_password.setObjectName(u"lbl_password")

        self.basic_settings_grid.addWidget(self.lbl_password, 2, 0, 1, 1)

        self.password_input = QLineEdit(self.basic_settings_group)
        self.password_input.setObjectName(u"password_input")
        self.password_input.setEchoMode(QLineEdit.Password)

        self.basic_settings_grid.addWidget(self.password_input, 2, 1, 1, 1)

        self.pwd_btn_layout = QHBoxLayout()
        self.pwd_btn_layout.setObjectName(u"pwd_btn_layout")
        self.show_password_btn = QPushButton(self.basic_settings_group)
        self.show_password_btn.setObjectName(u"show_password_btn")
        self.show_password_btn.setCheckable(True)

        self.pwd_btn_layout.addWidget(self.show_password_btn)

        self.default_password_btn = QPushButton(self.basic_settings_group)
        self.default_password_btn.setObjectName(u"default_password_btn")

        self.pwd_btn_layout.addWidget(self.default_password_btn)

        self.random_password_btn = QPushButton(self.basic_settings_group)
        self.random_password_btn.setObjectName(u"random_password_btn")

        self.pwd_btn_layout.addWidget(self.random_password_btn)


        self.basic_settings_grid.addLayout(self.pwd_btn_layout, 2, 2, 1, 1)

        self.lbl_win_limit = QLabel(self.basic_settings_group)
        self.lbl_win_limit.setObjectName(u"lbl_win_limit")

        self.basic_settings_grid.addWidget(self.lbl_win_limit, 3, 0, 1, 1)

        self.windows_hotspot_limit_input = QSpinBox(self.basic_settings_group)
        self.windows_hotspot_limit_input.setObjectName(u"windows_hotspot_limit_input")

        self.basic_settings_grid.addWidget(self.windows_hotspot_limit_input, 3, 1, 1, 1)

        self.apply_windows_limit_btn = QPushButton(self.basic_settings_group)
        self.apply_windows_limit_btn.setObjectName(u"apply_windows_limit_btn")

        self.basic_settings_grid.addWidget(self.apply_windows_limit_btn, 3, 2, 1, 1)


        self.qr_outer_layout.addWidget(self.basic_settings_group)


        self.main_layout.addWidget(self.qr_group)

        self.net_group = QGroupBox(HotspotSettingsWidget)
        self.net_group.setObjectName(u"net_group")
        self.net_grid_layout = QGridLayout(self.net_group)
        self.net_grid_layout.setObjectName(u"net_grid_layout")
        self.auto_detect_btn = QPushButton(self.net_group)
        self.auto_detect_btn.setObjectName(u"auto_detect_btn")

        self.net_grid_layout.addWidget(self.auto_detect_btn, 0, 0, 1, 2)

        self.lbl_internet_nic = QLabel(self.net_group)
        self.lbl_internet_nic.setObjectName(u"lbl_internet_nic")

        self.net_grid_layout.addWidget(self.lbl_internet_nic, 1, 0, 1, 1)

        self.internet_nic_combo = QComboBox(self.net_group)
        self.internet_nic_combo.setObjectName(u"internet_nic_combo")

        self.net_grid_layout.addWidget(self.internet_nic_combo, 2, 0, 1, 1)

        self.lbl_hotspot_nic = QLabel(self.net_group)
        self.lbl_hotspot_nic.setObjectName(u"lbl_hotspot_nic")

        self.net_grid_layout.addWidget(self.lbl_hotspot_nic, 1, 1, 1, 1)

        self.hotspot_nic_combo = QComboBox(self.net_group)
        self.hotspot_nic_combo.setObjectName(u"hotspot_nic_combo")

        self.net_grid_layout.addWidget(self.hotspot_nic_combo, 2, 1, 1, 1)

        self.lbl_hotspot_gw = QLabel(self.net_group)
        self.lbl_hotspot_gw.setObjectName(u"lbl_hotspot_gw")

        self.net_grid_layout.addWidget(self.lbl_hotspot_gw, 3, 0, 1, 1)

        self.hotspot_gateway_input = QLineEdit(self.net_group)
        self.hotspot_gateway_input.setObjectName(u"hotspot_gateway_input")

        self.net_grid_layout.addWidget(self.hotspot_gateway_input, 4, 0, 1, 1)

        self.lbl_hotspot_cidr = QLabel(self.net_group)
        self.lbl_hotspot_cidr.setObjectName(u"lbl_hotspot_cidr")

        self.net_grid_layout.addWidget(self.lbl_hotspot_cidr, 3, 1, 1, 1)

        self.hotspot_network_input = QLineEdit(self.net_group)
        self.hotspot_network_input.setObjectName(u"hotspot_network_input")

        self.net_grid_layout.addWidget(self.hotspot_network_input, 4, 1, 1, 1)


        self.main_layout.addWidget(self.net_group)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.main_layout.addItem(self.verticalSpacer)


        self.retranslateUi(HotspotSettingsWidget)

        QMetaObject.connectSlotsByName(HotspotSettingsWidget)
    # setupUi

    def retranslateUi(self, HotspotSettingsWidget):
        self.hotspot_control_group.setTitle(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot Control", None))
        self.hotspot_status_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Checking status", None))
        self.hotspot_on_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Turn Hotspot On", None))
        self.hotspot_off_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Turn Hotspot Off", None))
        self.hotspot_diagnose_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Run Diagnostics", None))
        self.active_name_label.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Active Hotspot Name: -", None))
        self.active_nic_label.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot NIC: -", None))
        self.active_range_label.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot IP range: -", None))
        self.qr_group.setTitle(QCoreApplication.translate("HotspotSettingsWidget", u"Internet Sharing QR Code & Configuration", None))
        self.network_group.setTitle(QCoreApplication.translate("HotspotSettingsWidget", u"Network Connection", None))
        self.hotspot_network_info_label.setText(QCoreApplication.translate("HotspotSettingsWidget", u"SSID: -   |   Password: -", None))
        self.network_print_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"PRINT", None))
        self.network_folder_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"\ud3f4\ub354", None))
        self.captive_group.setTitle(QCoreApplication.translate("HotspotSettingsWidget", u"Captive Portal", None))
        self.qr_caption.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Internet access requests   |   http://192.168.137.1:5000/scan", None))
        self.captive_print_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"PRINT", None))
        self.captive_folder_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"\ud3f4\ub354", None))
        self.basic_settings_group.setTitle(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot Basic Configuration", None))
        self.lbl_ssid.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot SSID (Name):", None))
        self.startup_checkbox.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Register at Windows startup", None))
        self.file_transfer_internet_checkbox.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Allow Internet during transfer", None))
        self.lbl_max_conn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Max conn:", None))
        self.lbl_password.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot password:", None))
        self.show_password_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Show", None))
        self.default_password_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Default", None))
        self.random_password_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Random", None))
        self.lbl_win_limit.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Win Hotspot Limit:", None))
        self.apply_windows_limit_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Apply Windows limit (registry)", None))
        self.net_group.setTitle(QCoreApplication.translate("HotspotSettingsWidget", u"Network Interface & IP Configuration", None))
        self.auto_detect_btn.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Auto (Re-detect Network Adapters)", None))
        self.lbl_internet_nic.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Internet NIC (internet line):", None))
        self.lbl_hotspot_nic.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot NIC (wireless adapter):", None))
        self.lbl_hotspot_gw.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot gateway IP:", None))
        self.hotspot_gateway_input.setPlaceholderText(QCoreApplication.translate("HotspotSettingsWidget", u"192.168.137.1", None))
        self.lbl_hotspot_cidr.setText(QCoreApplication.translate("HotspotSettingsWidget", u"Hotspot IPv4 range (CIDR):", None))
        self.hotspot_network_input.setPlaceholderText(QCoreApplication.translate("HotspotSettingsWidget", u"192.168.137.0/24", None))
        pass
    # retranslateUi

