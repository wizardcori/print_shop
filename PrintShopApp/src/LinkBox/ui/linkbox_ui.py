# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'linkbox.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_Tab1Widget(object):
    def setupUi(self, Tab1Widget):
        if not Tab1Widget.objectName():
            Tab1Widget.setObjectName(u"Tab1Widget")
        Tab1Widget.resize(950, 750)
        self.verticalLayout = QVBoxLayout(Tab1Widget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.main_splitter = QSplitter(Tab1Widget)
        self.main_splitter.setObjectName(u"main_splitter")
        self.main_splitter.setOrientation(Qt.Vertical)
        self.config_group_box = QGroupBox(self.main_splitter)
        self.config_group_box.setObjectName(u"config_group_box")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.config_group_box.sizePolicy().hasHeightForWidth())
        self.config_group_box.setSizePolicy(sizePolicy)
        self.config_group_box.setCheckable(True)
        self.config_group_box.setChecked(True)
        self.config_layout = QVBoxLayout(self.config_group_box)
        self.config_layout.setObjectName(u"config_layout")
        self.top_splitter = QSplitter(self.config_group_box)
        self.top_splitter.setObjectName(u"top_splitter")
        self.top_splitter.setOrientation(Qt.Horizontal)
        self.group_box = QGroupBox(self.top_splitter)
        self.group_box.setObjectName(u"group_box")
        self.left_layout = QVBoxLayout(self.group_box)
        self.left_layout.setObjectName(u"left_layout")
        self.folder_layout = QHBoxLayout()
        self.folder_layout.setObjectName(u"folder_layout")
        self.label_folder = QLabel(self.group_box)
        self.label_folder.setObjectName(u"label_folder")

        self.folder_layout.addWidget(self.label_folder)

        self.folder_input = QLineEdit(self.group_box)
        self.folder_input.setObjectName(u"folder_input")
        self.folder_input.setReadOnly(True)

        self.folder_layout.addWidget(self.folder_input)

        self.folder_btn = QPushButton(self.group_box)
        self.folder_btn.setObjectName(u"folder_btn")

        self.folder_layout.addWidget(self.folder_btn)


        self.left_layout.addLayout(self.folder_layout)

        self.nic_layout = QHBoxLayout()
        self.nic_layout.setObjectName(u"nic_layout")
        self.label_nic = QLabel(self.group_box)
        self.label_nic.setObjectName(u"label_nic")

        self.nic_layout.addWidget(self.label_nic)

        self.nic_combo = QComboBox(self.group_box)
        self.nic_combo.setObjectName(u"nic_combo")

        self.nic_layout.addWidget(self.nic_combo)

        self.rescan_nic_btn = QPushButton(self.group_box)
        self.rescan_nic_btn.setObjectName(u"rescan_nic_btn")

        self.nic_layout.addWidget(self.rescan_nic_btn)


        self.left_layout.addLayout(self.nic_layout)

        self.save_tab_layout = QHBoxLayout()
        self.save_tab_layout.setObjectName(u"save_tab_layout")
        self.label_save_tab = QLabel(self.group_box)
        self.label_save_tab.setObjectName(u"label_save_tab")

        self.save_tab_layout.addWidget(self.label_save_tab)

        self.save_tab_combo = QComboBox(self.group_box)
        self.save_tab_combo.setObjectName(u"save_tab_combo")

        self.save_tab_layout.addWidget(self.save_tab_combo)


        self.left_layout.addLayout(self.save_tab_layout)

        self.top_splitter.addWidget(self.group_box)
        self.qr_group_box = QGroupBox(self.top_splitter)
        self.qr_group_box.setObjectName(u"qr_group_box")
        self.qr_layout = QVBoxLayout(self.qr_group_box)
        self.qr_layout.setObjectName(u"qr_layout")
        self.qr_label = QLabel(self.qr_group_box)
        self.qr_label.setObjectName(u"qr_label")
        self.qr_label.setMinimumSize(QSize(210, 210))
        self.qr_label.setAlignment(Qt.AlignCenter)

        self.qr_layout.addWidget(self.qr_label)

        self.url_label = QLabel(self.qr_group_box)
        self.url_label.setObjectName(u"url_label")
        self.url_label.setAlignment(Qt.AlignCenter)

        self.qr_layout.addWidget(self.url_label)

        self.top_splitter.addWidget(self.qr_group_box)
        self.zone_group_box = QGroupBox(self.top_splitter)
        self.zone_group_box.setObjectName(u"zone_group_box")
        self.zone_group_layout = QVBoxLayout(self.zone_group_box)
        self.zone_group_layout.setObjectName(u"zone_group_layout")
        self.top_zone_layout = QHBoxLayout()
        self.top_zone_layout.setObjectName(u"top_zone_layout")
        self.label_location = QLabel(self.zone_group_box)
        self.label_location.setObjectName(u"label_location")

        self.top_zone_layout.addWidget(self.label_location)

        self.zone_combo = QComboBox(self.zone_group_box)
        self.zone_combo.setObjectName(u"zone_combo")

        self.top_zone_layout.addWidget(self.zone_combo)

        self.zone_input = QLineEdit(self.zone_group_box)
        self.zone_input.setObjectName(u"zone_input")
        self.zone_input.setEnabled(False)

        self.top_zone_layout.addWidget(self.zone_input)


        self.zone_group_layout.addLayout(self.top_zone_layout)

        self.zone_buttons_widget = QWidget(self.zone_group_box)
        self.zone_buttons_widget.setObjectName(u"zone_buttons_widget")
        self.zone_buttons_layout = QGridLayout(self.zone_buttons_widget)
        self.zone_buttons_layout.setObjectName(u"zone_buttons_layout")
        self.zone_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.zone_group_layout.addWidget(self.zone_buttons_widget)

        self.top_splitter.addWidget(self.zone_group_box)

        self.config_layout.addWidget(self.top_splitter)

        self.main_splitter.addWidget(self.config_group_box)
        self.bottom_group_box = QGroupBox(self.main_splitter)
        self.bottom_group_box.setObjectName(u"bottom_group_box")
        self.bottom_group_layout = QVBoxLayout(self.bottom_group_box)
        self.bottom_group_layout.setObjectName(u"bottom_group_layout")
        self.print_job_group_box = QGroupBox(self.bottom_group_box)
        self.print_job_group_box.setObjectName(u"print_job_group_box")
        self.print_job_group_layout = QVBoxLayout(self.print_job_group_box)
        self.print_job_group_layout.setObjectName(u"print_job_group_layout")
        self.transfer_filter_layout = QHBoxLayout()
        self.transfer_filter_layout.setObjectName(u"transfer_filter_layout")
        self.completed_only_checkbox = QCheckBox(self.print_job_group_box)
        self.completed_only_checkbox.setObjectName(u"completed_only_checkbox")

        self.transfer_filter_layout.addWidget(self.completed_only_checkbox)

        self.label_period = QLabel(self.print_job_group_box)
        self.label_period.setObjectName(u"label_period")

        self.transfer_filter_layout.addWidget(self.label_period)

        self.transfer_period_combo = QComboBox(self.print_job_group_box)
        self.transfer_period_combo.setObjectName(u"transfer_period_combo")

        self.transfer_filter_layout.addWidget(self.transfer_period_combo)

        self.transfer_start_date = QDateEdit(self.print_job_group_box)
        self.transfer_start_date.setObjectName(u"transfer_start_date")
        self.transfer_start_date.setCalendarPopup(True)

        self.transfer_filter_layout.addWidget(self.transfer_start_date)

        self.label_tilde = QLabel(self.print_job_group_box)
        self.label_tilde.setObjectName(u"label_tilde")

        self.transfer_filter_layout.addWidget(self.label_tilde)

        self.transfer_end_date = QDateEdit(self.print_job_group_box)
        self.transfer_end_date.setObjectName(u"transfer_end_date")
        self.transfer_end_date.setCalendarPopup(True)

        self.transfer_filter_layout.addWidget(self.transfer_end_date)


        self.print_job_group_layout.addLayout(self.transfer_filter_layout)


        self.bottom_group_layout.addWidget(self.print_job_group_box)

        self.tab_widget = QTabWidget(self.bottom_group_box)
        self.tab_widget.setObjectName(u"tab_widget")
        self.print_jobs_tab = QWidget()
        self.print_jobs_tab.setObjectName(u"print_jobs_tab")
        self.print_jobs_layout = QVBoxLayout(self.print_jobs_tab)
        self.print_jobs_layout.setObjectName(u"print_jobs_layout")
        self.print_job_table = QTableWidget(self.print_jobs_tab)
        if (self.print_job_table.columnCount() < 7):
            self.print_job_table.setColumnCount(7)
        __qtablewidgetitem = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.print_job_table.setHorizontalHeaderItem(6, __qtablewidgetitem6)
        self.print_job_table.setObjectName(u"print_job_table")

        self.print_jobs_layout.addWidget(self.print_job_table)

        self.tab_widget.addTab(self.print_jobs_tab, "")

        self.bottom_group_layout.addWidget(self.tab_widget)

        self.main_splitter.addWidget(self.bottom_group_box)

        self.verticalLayout.addWidget(self.main_splitter)


        self.retranslateUi(Tab1Widget)
        self.config_group_box.toggled.connect(self.top_splitter.setVisible)

        QMetaObject.connectSlotsByName(Tab1Widget)
    # setupUi

    def retranslateUi(self, Tab1Widget):
        self.config_group_box.setTitle(QCoreApplication.translate("Tab1Widget", u"Server & Location Configuration", None))
        self.group_box.setTitle(QCoreApplication.translate("Tab1Widget", u"Server & Connection Settings", None))
        self.label_folder.setText(QCoreApplication.translate("Tab1Widget", u"Save Location:", None))
        self.folder_btn.setText(QCoreApplication.translate("Tab1Widget", u"Browse...", None))
        self.label_nic.setText(QCoreApplication.translate("Tab1Widget", u"Internet NIC:", None))
        self.rescan_nic_btn.setText(QCoreApplication.translate("Tab1Widget", u"Rescan NIC", None))
        self.label_save_tab.setText(QCoreApplication.translate("Tab1Widget", u"Save Tab:", None))
        self.qr_group_box.setTitle(QCoreApplication.translate("Tab1Widget", u"QR Code & URL", None))
        self.url_label.setText(QCoreApplication.translate("Tab1Widget", u"Generated URL: ", None))
        self.zone_group_box.setTitle(QCoreApplication.translate("Tab1Widget", u"QR Location & Table Selection", None))
        self.label_location.setText(QCoreApplication.translate("Tab1Widget", u"Location:", None))
        self.bottom_group_box.setTitle(QCoreApplication.translate("Tab1Widget", u"Print Jobs Management", None))
        self.print_job_group_box.setTitle("")
        self.completed_only_checkbox.setText(QCoreApplication.translate("Tab1Widget", u"Show completed too", None))
        self.label_period.setText(QCoreApplication.translate("Tab1Widget", u"Display period:", None))
        self.label_tilde.setText(QCoreApplication.translate("Tab1Widget", u"~", None))
        ___qtablewidgetitem = self.print_job_table.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("Tab1Widget", u"Printer", None))
        ___qtablewidgetitem1 = self.print_job_table.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("Tab1Widget", u"File Name", None))
        ___qtablewidgetitem2 = self.print_job_table.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("Tab1Widget", u"Job ID", None))
        ___qtablewidgetitem3 = self.print_job_table.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("Tab1Widget", u"Status", None))
        ___qtablewidgetitem4 = self.print_job_table.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("Tab1Widget", u"Tag", None))
        ___qtablewidgetitem5 = self.print_job_table.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("Tab1Widget", u"Output Path", None))
        ___qtablewidgetitem6 = self.print_job_table.horizontalHeaderItem(6)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("Tab1Widget", u"Detected Time", None))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.print_jobs_tab), QCoreApplication.translate("Tab1Widget", u"Print Jobs", None))
        pass
    # retranslateUi

