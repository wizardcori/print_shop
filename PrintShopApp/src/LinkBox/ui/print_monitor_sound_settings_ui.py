# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'print_monitor_sound_settings.ui'
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
from PySide6.QtWidgets import (QApplication, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)
class Ui_PrintMonitorSoundSettings(object):
    def setupUi(self, PrintMonitorSoundSettings):
        if not PrintMonitorSoundSettings.objectName():
            PrintMonitorSoundSettings.setObjectName(u"PrintMonitorSoundSettings")
        PrintMonitorSoundSettings.resize(420, 220)
        self.verticalLayout = QVBoxLayout(PrintMonitorSoundSettings)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.detectionGroup = QGroupBox(PrintMonitorSoundSettings)
        self.detectionGroup.setObjectName(u"detectionGroup")
        self.layoutDetection = QHBoxLayout(self.detectionGroup)
        self.layoutDetection.setObjectName(u"layoutDetection")
        self.detectionEdit = QLineEdit(self.detectionGroup)
        self.detectionEdit.setObjectName(u"detectionEdit")

        self.layoutDetection.addWidget(self.detectionEdit)

        self.detectionBrowse = QPushButton(self.detectionGroup)
        self.detectionBrowse.setObjectName(u"detectionBrowse")

        self.layoutDetection.addWidget(self.detectionBrowse)

        self.detectionTest = QPushButton(self.detectionGroup)
        self.detectionTest.setObjectName(u"detectionTest")

        self.layoutDetection.addWidget(self.detectionTest)


        self.verticalLayout.addWidget(self.detectionGroup)

        self.treeGroup = QGroupBox(PrintMonitorSoundSettings)
        self.treeGroup.setObjectName(u"treeGroup")
        self.layoutTree = QHBoxLayout(self.treeGroup)
        self.layoutTree.setObjectName(u"layoutTree")
        self.treeEdit = QLineEdit(self.treeGroup)
        self.treeEdit.setObjectName(u"treeEdit")

        self.layoutTree.addWidget(self.treeEdit)

        self.treeBrowse = QPushButton(self.treeGroup)
        self.treeBrowse.setObjectName(u"treeBrowse")

        self.layoutTree.addWidget(self.treeBrowse)

        self.treeTest = QPushButton(self.treeGroup)
        self.treeTest.setObjectName(u"treeTest")

        self.layoutTree.addWidget(self.treeTest)


        self.verticalLayout.addWidget(self.treeGroup)

        self.saveButton = QPushButton(PrintMonitorSoundSettings)
        self.saveButton.setObjectName(u"saveButton")

        self.verticalLayout.addWidget(self.saveButton)

        self.statusLabel = QLabel(PrintMonitorSoundSettings)
        self.statusLabel.setObjectName(u"statusLabel")

        self.verticalLayout.addWidget(self.statusLabel)

        self.verticalSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.retranslateUi(PrintMonitorSoundSettings)

        QMetaObject.connectSlotsByName(PrintMonitorSoundSettings)
    # setupUi

    def retranslateUi(self, PrintMonitorSoundSettings):
        self.detectionGroup.setTitle(QCoreApplication.translate("PrintMonitorSoundSettings", u"\uac80\ucd9c \uc0ac\uc6b4\ub4dc", None))
        self.detectionBrowse.setText(QCoreApplication.translate("PrintMonitorSoundSettings", u"\ucc3e\uae30", None))
        self.detectionTest.setText(QCoreApplication.translate("PrintMonitorSoundSettings", u"\ud14c\uc2a4\ud2b8", None))
        self.treeGroup.setTitle(QCoreApplication.translate("PrintMonitorSoundSettings", u"\ud2b8\ub9ac \ucd94\uac00 \uc0ac\uc6b4\ub4dc", None))
        self.treeBrowse.setText(QCoreApplication.translate("PrintMonitorSoundSettings", u"\ucc3e\uae30", None))
        self.treeTest.setText(QCoreApplication.translate("PrintMonitorSoundSettings", u"\ud14c\uc2a4\ud2b8", None))
        self.saveButton.setText(QCoreApplication.translate("PrintMonitorSoundSettings", u"\uc800\uc7a5", None))
        pass
    # retranslateUi

