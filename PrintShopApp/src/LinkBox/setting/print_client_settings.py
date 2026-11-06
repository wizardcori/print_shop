import os
from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QLabel, QFileDialog, QVBoxLayout, QFormLayout

from Common.globals import load_ui_safely
from Common.paths import PRINT_REQUEST_QRCODE_FULLPATH, PRINT_REQUEST_ADDED_SOUND
from Common.config import FileConfigManager, ConfigType
from Common.settings_registry import register_settings_tab


class PrintClientConfig(FileConfigManager):
    section = "PrintClientSettings"
    section_order = 21

    schema = {
        'service_ip': {"default": '127.0.0.1', "type": ConfigType.STRING},
        'qr_save_folder': {"default": os.path.join(PRINT_REQUEST_QRCODE_FULLPATH, 'insert.wav'), "type": ConfigType.FULLPATH},
        'completion_sound': {"default": os.path.join(PRINT_REQUEST_ADDED_SOUND, 'complete.wav'), "type": ConfigType.FULLPATH}
    }


class PrintClientSettingTab(AutoGeometryWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.widget_id = "print_client_setting"
        self.widget_title = "프린트 클라이언트 설정"
        self.config = PrintClientConfig()

        # .ui 파일 로드 시도 (UI 파일이 없을 경우 코드로 레이아웃 대체 가능하도록 예외 처리 구조 유지)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(current_dir, "ui", "print_client_setting.ui")

        try:
            self.ui = load_ui_safely(ui_path, self)
            # 위젯 참조
            self.service_ip_edit = self.ui.findChild(QLineEdit, "ipEdit")
            self.qr_save_folder_edit = self.ui.findChild(QLineEdit, "qrFolderEdit")
            self.qr_folder_browse = self.ui.findChild(QPushButton, "qrFolderBrowse")
            self.completion_sound_edit = self.ui.findChild(QLineEdit, "soundEdit")
            self.sound_browse = self.ui.findChild(QPushButton, "soundBrowse")
            self.save_button = self.ui.findChild(QPushButton, "saveButton")
            self.status_label = self.ui.findChild(QLabel, "statusLabel")

            # 시그널 연결
            if self.qr_folder_browse:
                self.qr_folder_browse.clicked.connect(self.select_qr_folder)
            if self.sound_browse:
                self.sound_browse.clicked.connect(self.select_sound_file)
            if self.save_button:
                self.save_button.clicked.connect(self.save_settings)
        except Exception as e:
            logd(f"UI 파일 로드 실패 또는 생략 ({ui_path}): {e}")
            self.init_fallback_ui()

        self.load_settings()

    def init_fallback_ui(self):
        """UI 파일이 없을 때를 대비한 기본 폼 레이아웃 구성"""
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.service_ip_edit = QLineEdit()
        self.qr_save_folder_edit = QLineEdit()
        self.completion_sound_edit = QLineEdit()

        form_layout.addRow("서비스 IP:", self.service_ip_edit)
        form_layout.addRow("QR 저장 폴더:", self.qr_save_folder_edit)
        form_layout.addRow("완료 사운드:", self.completion_sound_edit)

        layout.addLayout(form_layout)
        
        self.save_button = QPushButton("저장")
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def load_settings(self):
        """설정 로드 및 UI 반영"""
        if self.service_ip_edit:
            self.service_ip_edit.setText(self.config.get('service_ip'))
        if self.qr_save_folder_edit:
            self.qr_save_folder_edit.setText(self.config.get('qr_save_folder'))
        if self.completion_sound_edit:
            self.completion_sound_edit.setText(self.config.get('completion_sound'))
        
    def save_settings(self):
        """설정을 설정 파일에 저장하고 상태를 표시합니다."""
        if self.service_ip_edit:
            self.config.set('service_ip', self.service_ip_edit.text())
        if self.qr_save_folder_edit:
            self.config.set('qr_save_folder', self.qr_save_folder_edit.text())
        if self.completion_sound_edit:
            self.config.set('completion_sound', self.completion_sound_edit.text())

        if self.status_label:
            self.status_label.setText("저장되었습니다.")

    def select_qr_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "QR 코드 저장 폴더 선택")
        if dir_path:
            self.qr_save_folder_edit.setText(dir_path)

    def select_sound_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "사운드 파일 선택", "", "Audio Files (*.wav *.mp3)")
        if path:
            self.completion_sound_edit.setText(path)


# 설정 탭으로 자동 등록 (general_settings 스타일 반영)
register_settings_tab(
    'linkbox.print-client-setting', 'Print Client',
    PrintClientSettingTab, order=21.0,
)