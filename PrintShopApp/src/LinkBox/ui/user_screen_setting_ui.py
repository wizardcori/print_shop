# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'user_screen_setting.ui'
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
class Ui_UserScreenSetting(object):
    def setupUi(self, UserScreenSetting):
        if not UserScreenSetting.objectName():
            UserScreenSetting.setObjectName(u"UserScreenSetting")
        UserScreenSetting.resize(450, 280)
        self.verticalLayout = QVBoxLayout(UserScreenSetting)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.ipGroup = QGroupBox(UserScreenSetting)
        self.ipGroup.setObjectName(u"ipGroup")
        self.layoutIp = QHBoxLayout(self.ipGroup)
        self.layoutIp.setObjectName(u"layoutIp")
        self.ipEdit = QLineEdit(self.ipGroup)
        self.ipEdit.setObjectName(u"ipEdit")

        self.layoutIp.addWidget(self.ipEdit)


        self.verticalLayout.addWidget(self.ipGroup)

        self.qrFolderGroup = QGroupBox(UserScreenSetting)
        self.qrFolderGroup.setObjectName(u"qrFolderGroup")
        self.layoutQrFolder = QHBoxLayout(self.qrFolderGroup)
        self.layoutQrFolder.setObjectName(u"layoutQrFolder")
        self.qrFolderEdit = QLineEdit(self.qrFolderGroup)
        self.qrFolderEdit.setObjectName(u"qrFolderEdit")

        self.layoutQrFolder.addWidget(self.qrFolderEdit)

        self.qrFolderBrowse = QPushButton(self.qrFolderGroup)
        self.qrFolderBrowse.setObjectName(u"qrFolderBrowse")

        self.layoutQrFolder.addWidget(self.qrFolderBrowse)


        self.verticalLayout.addWidget(self.qrFolderGroup)

        self.soundGroup = QGroupBox(UserScreenSetting)
        self.soundGroup.setObjectName(u"soundGroup")
        self.layoutSound = QHBoxLayout(self.soundGroup)
        self.layoutSound.setObjectName(u"layoutSound")
        self.soundEdit = QLineEdit(self.soundGroup)
        self.soundEdit.setObjectName(u"soundEdit")

        self.layoutSound.addWidget(self.soundEdit)

        self.soundBrowse = QPushButton(self.soundGroup)
        self.soundBrowse.setObjectName(u"soundBrowse")

        self.layoutSound.addWidget(self.soundBrowse)


        self.verticalLayout.addWidget(self.soundGroup)

        self.saveButton = QPushButton(UserScreenSetting)
        self.saveButton.setObjectName(u"saveButton")

        self.verticalLayout.addWidget(self.saveButton)

        self.statusLabel = QLabel(UserScreenSetting)
        self.statusLabel.setObjectName(u"statusLabel")

        self.verticalLayout.addWidget(self.statusLabel)

        self.verticalSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.retranslateUi(UserScreenSetting)

        QMetaObject.connectSlotsByName(UserScreenSetting)
    # setupUi

    def retranslateUi(self, UserScreenSetting):
        self.ipGroup.setTitle(QCoreApplication.translate("UserScreenSetting", u"\uc11c\ube44\uc2a4 \uc544\uc774\ud53c \uc124\uc815", None))
        self.qrFolderGroup.setTitle(QCoreApplication.translate("UserScreenSetting", u"QR \ucf54\ub4dc \uc800\uc7a5 \ud3f4\ub354", None))
        self.qrFolderBrowse.setText(QCoreApplication.translate("UserScreenSetting", u"\ucc3e\uae30", None))
        self.soundGroup.setTitle(QCoreApplication.translate("UserScreenSetting", u"\ud30c\uc77c \uc804\uc1a1 \uc644\ub8cc \uc0ac\uc6b4\ub4dc \ud30c\uc77c \ud480\ud328\uc2a4", None))
        self.soundBrowse.setText(QCoreApplication.translate("UserScreenSetting", u"\ucc3e\uae30", None))
        self.saveButton.setText(QCoreApplication.translate("UserScreenSetting", u"\uc800\uc7a5", None))
        pass
    # retranslateUi

