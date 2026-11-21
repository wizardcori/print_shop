# version_tab.py
import os
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFormLayout, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt

from Common.settings_registry import register_settings_tab
from .version_manager import vm_inst, VersionManager
from .exe_version_crypto import get_runtime_decrypted_version, extract_version_from_exe


class VersionTab(QWidget):
    """애플리케이션 및 업데이터의 버전 정보를 표시하고 관리하는 설정 탭 UI"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_version_managers()
        self.init_ui()
        self.refresh_version_info()

    def _setup_version_managers(self):
        """메인 앱 및 업데이터의 경로를 탐색하여 VersionManager 설정"""
        if getattr(sys, 'frozen', False):
            app_root = os.path.dirname(os.path.abspath(sys.executable))
            updater_dir = app_root
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(current_dir)
            app_root = os.path.dirname(src_dir)
            updater_dir = os.path.join(src_dir, "UpdateService")

        self.app_root = app_root
        self.updater_dir = updater_dir

        self.main_vm = vm_inst
        self.main_vm.set_base_dir(app_root)
        self.main_vm.app_name = "PrintShopApp"

        self.updater_vm = VersionManager(
            base_dir=updater_dir,
            version_filename="version.txt",
            default_version="1.2.0",
            app_name="PrintShopUpdateService"
        )

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        title_label = QLabel("<h3>Application & Service Version Info</h3>")
        title_label.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(title_label)

        # ---------------------------------------------------------
        # 1. 메인 애플리케이션 버전 정보 그룹
        # ---------------------------------------------------------
        app_group = QGroupBox("Main Application (PrintShopApp)")
        app_form = QFormLayout(app_group)
        app_form.setContentsMargins(6, 12, 6, 6)
        app_form.setLabelAlignment(Qt.AlignRight)
        app_form.setHorizontalSpacing(6)
        app_form.setVerticalSpacing(4)

        self.lbl_app_name = QLabel("-")
        self.lbl_app_name.setStyleSheet("font-weight: bold; font-size: 11pt;")

        self.lbl_app_version = QLabel("-")
        self.lbl_app_version.setStyleSheet("font-weight: bold; font-size: 12pt; color: #4EC9B0;")

        self.lbl_app_eof_version = QLabel("-")
        self.lbl_app_eof_version.setStyleSheet("font-weight: bold; font-size: 10pt; color: #DCDCAA;")

        self.lbl_app_path = QLabel("-")
        self.lbl_app_path.setStyleSheet("color: #858585; font-size: 9pt;")
        self.lbl_app_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        app_form.addRow("프로그램명 (Name):", self.lbl_app_name)
        app_form.addRow("현재 버전 (File):", self.lbl_app_version)
        app_form.addRow("바이너리 무결성 버전 (EOF):", self.lbl_app_eof_version)
        app_form.addRow("버전 파일 경로:", self.lbl_app_path)

        main_layout.addWidget(app_group)

        # ---------------------------------------------------------
        # 2. 업데이터 서비스 버전 정보 그룹
        # ---------------------------------------------------------
        updater_group = QGroupBox("Update Service (PrintShopUpdateService)")
        updater_form = QFormLayout(updater_group)
        updater_form.setContentsMargins(6, 12, 6, 6)
        updater_form.setLabelAlignment(Qt.AlignRight)
        updater_form.setHorizontalSpacing(6)
        updater_form.setVerticalSpacing(4)

        self.lbl_updater_name = QLabel("-")
        self.lbl_updater_name.setStyleSheet("font-weight: bold; font-size: 11pt;")

        self.lbl_updater_version = QLabel("-")
        self.lbl_updater_version.setStyleSheet("font-weight: bold; font-size: 12pt; color: #569CD6;")

        self.lbl_updater_eof_version = QLabel("-")
        self.lbl_updater_eof_version.setStyleSheet("font-weight: bold; font-size: 10pt; color: #DCDCAA;")

        self.lbl_updater_path = QLabel("-")
        self.lbl_updater_path.setStyleSheet("color: #858585; font-size: 9pt;")
        self.lbl_updater_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        updater_form.addRow("서비스명 (Name):", self.lbl_updater_name)
        updater_form.addRow("서비스 버전 (File):", self.lbl_updater_version)
        updater_form.addRow("서비스 바이너리 버전 (EOF):", self.lbl_updater_eof_version)
        updater_form.addRow("버전 파일 경로:", self.lbl_updater_path)

        main_layout.addWidget(updater_group)

        # ---------------------------------------------------------
        # 3. 하단 버전 제어 버튼 영역
        # ---------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)

        self.btn_refresh = QPushButton("🔄 버전 새로고침")
        self.btn_refresh.setMinimumHeight(32)
        self.btn_refresh.clicked.connect(self.refresh_version_info)
        btn_layout.addWidget(self.btn_refresh)

        self.btn_verify_exe = QPushButton("🔍 EXE 암호화 버전 검사")
        self.btn_verify_exe.setMinimumHeight(32)
        self.btn_verify_exe.clicked.connect(self.on_verify_external_exe)
        btn_layout.addWidget(self.btn_verify_exe)

        btn_layout.addStretch()

        self.btn_bump_app = QPushButton("⬆️ 메인 앱 패치 버전 증가 (+0.0.1)")
        self.btn_bump_app.setMinimumHeight(32)
        self.btn_bump_app.clicked.connect(self.on_bump_app_version)
        btn_layout.addWidget(self.btn_bump_app)

        main_layout.addLayout(btn_layout)
        main_layout.addStretch()

    def refresh_version_info(self):
        """디스크 버전 파일 및 EXE EOF 암호화 버전 동기화"""
        self.lbl_app_name.setText(self.main_vm.app_name)
        self.lbl_app_path.setText(self.main_vm.txt_path)
        app_ver = "1.2.0"
        try:
            app_ver = self.main_vm.get_current_version()
            self.lbl_app_version.setText(f"v{app_ver}")
        except Exception as e:
            self.lbl_app_version.setText(f"오류 ({e})")

        eof_ver = get_runtime_decrypted_version(fallback_version=app_ver)
        self.lbl_app_eof_version.setText(eof_ver)

        self.lbl_updater_name.setText(self.updater_vm.app_name)
        self.lbl_updater_path.setText(self.updater_vm.txt_path)
        try:
            if os.path.exists(self.updater_vm.txt_path):
                updater_ver = self.updater_vm.get_current_version()
                self.lbl_updater_version.setText(f"v{updater_ver}")
            else:
                self.lbl_updater_version.setText("파일 없음 (미설치 또는 경로 확인)")
        except Exception as e:
            self.lbl_updater_version.setText(f"오류 ({e})")

        updater_exe_path = os.path.join(self.updater_dir, "PSUpdateService.exe")
        if not os.path.exists(updater_exe_path):
            updater_exe_path = os.path.join(self.updater_dir, "PrintShopUpdateService.exe")
        if os.path.exists(updater_exe_path):
            self.lbl_updater_eof_version.setText(extract_version_from_exe(updater_exe_path))
        else:
            self.lbl_updater_eof_version.setText("실행 파일 없음 (개발 환경)")

    def on_verify_external_exe(self):
        """사용자가 선택한 .exe 파일의 EOF 암호화 버전을 복호화하여 검증"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "암호화 버전을 검사할 실행 파일 선택", self.app_root, "Executable Files (*.exe)"
        )
        if not file_path:
            return
        extracted = extract_version_from_exe(file_path)
        QMessageBox.information(
            self,
            "EXE 암호화 버전 검증 결과",
            f"📁 대상 파일: {os.path.basename(file_path)}\n"
            f"🔐 복호화된 버전 정보: {extracted}"
        )

    def on_bump_app_version(self):
        """메인 앱의 패치 버전을 1 증가시키고 UI를 갱신"""
        try:
            new_ver = self.main_vm.bump_version("patch")
            self.refresh_version_info()
            QMessageBox.information(
                self, "버전 업데이트 완료",
                f"메인 애플리케이션 버전이 v{new_ver}(으)로 업데이트되었습니다.\n"
                f"(version.txt, version.py 및 version_info.txt 동기화 완료)"
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", "버전 증가 중 오류가 발생했습니다:\n" + str(e))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_version_info()


register_settings_tab('version', 'Version', VersionTab, order=99)