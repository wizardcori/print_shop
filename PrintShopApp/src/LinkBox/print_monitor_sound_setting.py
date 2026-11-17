import os

from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QLabel, QFileDialog
from PySide6.QtUiTools import QUiLoader

import Common.paths as paths
from Common.globals import load_ui_safely
from Common.config import FileConfigManager, ConfigType
from Common.settings_registry import register_settings_tab

from .print_log_writer import write_system_log


class PrintMonitorSoundConfig(FileConfigManager):
        section = "PrintMonitorSoundConfig"
        section_order = 10
        #auto_save = False  # 수동 저장 모드
        schema = {
            'detection_sound': {"default": os.path.join(paths.PRINT_MONITOR_SOUND_DIR, 'detect.wav'), "type": ConfigType.FULLPATH},
            'tree_sound': {"default": os.path.join(paths.PRINT_MONITOR_SOUND_DIR, 'insert.wav'), "type": ConfigType.FULLPATH},            
        }

class PrintMonitorSoundSettings(AutoGeometryWidget):
    SOUND_SETTINGS_SECTION = 'PrintMonitorSounds'

    def __init__(self, parent=None):
        super().__init__(parent)

        # 내부 변수
        self.widget_id = "print_monitor_sound_settings"
        self.widget_title = "프린트 모니터 사운드 설정"
        self.config = PrintMonitorSoundConfig()

        # .ui 파일 로드

        loader = QUiLoader()

        ui_file_path = paths.get_ui_file_path(__file__, "ui", "print_monitor_sound_settings.ui")
        self.ui = paths.load_ui_smart(loader, ui_file_path, "print_monitor_sound_settings.ui",caller_file=__file__)

        # current_dir = os.path.dirname(os.path.abspath(__file__))
        # ui_path = os.path.join(current_dir, "ui", "print_monitor_sound_settings.ui")
        # write_system_log('WARNING', f"UI 파일 경로: {ui_path}")
        # logd(f"UI 파일 경로: {ui_path}")  # 디버그용 출력

        # try:
        #     # 안전한 로딩 함수 호출
        #     self.ui = load_ui_safely(ui_path, self)
        # except Exception as e:
        #     logd(e)
        #     write_system_log('ERROR', f"UI 파일 경로 로드 실패 ({ui_path}): {e}")

        # 위젯 참조
        self.detection_edit   = self.ui.findChild(QLineEdit, "detectionEdit")
        self.detection_browse = self.ui.findChild(QPushButton, "detectionBrowse")
        self.detection_test   = self.ui.findChild(QPushButton, "detectionTest")

        self.tree_edit   = self.ui.findChild(QLineEdit, "treeEdit")
        self.tree_browse = self.ui.findChild(QPushButton, "treeBrowse")
        self.tree_test   = self.ui.findChild(QPushButton, "treeTest")

        self.save_button  = self.ui.findChild(QPushButton, "saveButton")
        self.status_label = self.ui.findChild(QLabel, "statusLabel")

        # 시그널 연결
        self.detection_browse.clicked.connect(self.select_detection_sound)
        self.detection_test.clicked.connect(lambda: self.test_sound(self.detection_edit.text()))

        self.tree_browse.clicked.connect(self.select_tree_sound)
        self.tree_test.clicked.connect(lambda: self.test_sound(self.tree_edit.text()))

        self.save_button.clicked.connect(self.save_settings)

        self.load_settings()
    
    def load_settings(self):
        """사운드 설정 로드 및 UI 반영"""
        
        # UI 입력 필드에 값 채우기
        if self.detection_edit:
            self.detection_edit.setText(self.config.get('detection_sound'))
        if self.tree_edit:
            self.tree_edit.setText(self.config.get('tree_sound'))
        
    def save_settings(self):
        """사운드 설정을 설정 파일에 저장하고 상태를 표시합니다."""
        detection_sound = self.detection_edit.text() if self.detection_edit else ""
        tree_sound = self.tree_edit.text() if self.tree_edit else ""

        self.config.set('detection_sound', detection_sound)
        self.config.set('tree_sound', tree_sound)

        if self.status_label:
            self.status_label.setText("저장되었습니다.")

    def select_detection_sound(self):
        path, _ = QFileDialog.getOpenFileName(self, "WAV 선택", "", "WAV (*.wav)")
        if path:
            self.detection_edit.setText(path)

    def select_tree_sound(self):
        path, _ = QFileDialog.getOpenFileName(self, "WAV 선택", "", "WAV (*.wav)")
        if path:
            self.tree_edit.setText(path)

    def test_sound(self, file_path):
        if file_path:
            from .print_log_writer import play_notification_sound
            play_notification_sound(file_path.strip())

register_settings_tab(
    'linkbox.printer-monitor-sounds', 'Printer Monitor Sounds',
    PrintMonitorSoundSettings, order=65,
)