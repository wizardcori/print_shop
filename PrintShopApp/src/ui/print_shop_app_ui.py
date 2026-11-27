# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'print_shop_app.ui'
##
## Created by: Qt User Interface Compiler version 6.12.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QMainWindow, QMenuBar, QSizePolicy,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget)

class Ui_PrintShopApp(object):
    def setupUi(self, PrintShopApp):
        if not PrintShopApp.objectName():
            PrintShopApp.setObjectName(u"PrintShopApp")
        PrintShopApp.resize(1150, 750)
        self.actionSetting = QAction(PrintShopApp)
        self.actionSetting.setObjectName(u"actionSetting")
        self.centralwidget = QWidget(PrintShopApp)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(10, 10, 10, 10)
        self.main_tabs = QTabWidget(self.centralwidget)
        self.main_tabs.setObjectName(u"main_tabs")
        self.main_tabs.setStyleSheet(u"\n"
"        QTabWidget::pane {\n"
"            border: 1px solid #444444;\n"
"            background-color: #1e1e1e;\n"
"        }\n"
"        QTabBar::tab {\n"
"            background-color: #2d2d2d;\n"
"            color: #888888;\n"
"            padding: 8px 16px;\n"
"            margin-right: 2px;\n"
"            border-top-left-radius: 4px;\n"
"            border-top-right-radius: 4px;\n"
"            border: 1px solid #3f3f3f;\n"
"        }\n"
"        QTabBar::tab:selected {\n"
"            background-color: #007acc;\n"
"            color: #ffffff;\n"
"            font-weight: bold;\n"
"            border-color: #007acc;\n"
"        }\n"
"        QTabBar::tab:hover:not(:selected) {\n"
"            background-color: #3d3d3d;\n"
"            color: #cccccc;\n"
"        }\n"
"       ")

        self.verticalLayout.addWidget(self.main_tabs)

        PrintShopApp.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(PrintShopApp)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1150, 33))
        PrintShopApp.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(PrintShopApp)
        self.statusbar.setObjectName(u"statusbar")
        PrintShopApp.setStatusBar(self.statusbar)

        self.menubar.addAction(self.actionSetting)

        self.retranslateUi(PrintShopApp)

        self.main_tabs.setCurrentIndex(-1)


        QMetaObject.connectSlotsByName(PrintShopApp)
    # setupUi

    def retranslateUi(self, PrintShopApp):
        PrintShopApp.setWindowTitle(QCoreApplication.translate("PrintShopApp", u"PrintShop Integrated Manager (HTTPS)", None))
        self.actionSetting.setText(QCoreApplication.translate("PrintShopApp", u"setting", None))
    # retranslateUi

