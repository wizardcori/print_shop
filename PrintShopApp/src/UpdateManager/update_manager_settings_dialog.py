import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox, QFileDialog, 
    QTabWidget, QWidget, QCheckBox
)

# 정의된 상수 임포트
from github_config_manager import (
    DEF_REPO_OWNER, DEF_REPO_NAME, DEF_GITHUB_TOKEN,
    DEF_LOCAL_VERSION_DIR, DEF_BACKUP_DIR, DEF_OVERWRITE_RELEASE
)

from Common.log import logd, loge
from Common.log_settings_tab import LogSettingsTab


class UpdateManagerSettingsDialog(QDialog):
    """환경 설정 및 로그 설정 다이얼로그"""
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("환경 설정 및 로그 관리")
        self.resize(650, 550)
        logd("SettingsDialog 초기화 시작")
        
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)
        
        tab_general = QWidget()
        gen_layout = QVBoxLayout(tab_general)
        
        form_layout = QVBoxLayout()
        form_layout.addWidget(QLabel("GitHub 계정 소유자 (Repo Owner):"))
        self.owner_input = QLineEdit(self)
        form_layout.addWidget(self.owner_input)
        
        form_layout.addWidget(QLabel("GitHub 저장소 이름 (Repo Name):"))
        self.repo_input = QLineEdit(self)
        form_layout.addWidget(self.repo_input)
        
        form_layout.addWidget(QLabel("GitHub 개인 액세스 토큰 (Token):"))
        self.token_input = QLineEdit(self)
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.token_input)
        
        form_layout.addWidget(QLabel("로컬 버전 저장 디렉토리:"))
        dir_hbox = QHBoxLayout()
        self.dir_input = QLineEdit(self)
        dir_hbox.addWidget(self.dir_input)
        self.btn_browse_ver = QPushButton("폴더 선택...", self)
        self.btn_browse_ver.clicked.connect(lambda: self.select_directory(self.dir_input))
        dir_hbox.addWidget(self.btn_browse_ver)
        form_layout.addLayout(dir_hbox)
        
        form_layout.addWidget(QLabel("백업 저장 디렉토리:"))
        backup_hbox = QHBoxLayout()
        self.backup_dir_input = QLineEdit(self)
        backup_hbox.addWidget(self.backup_dir_input)
        self.btn_browse_bak = QPushButton("폴더 선택...", self)
        self.btn_browse_bak.clicked.connect(lambda: self.select_directory(self.backup_dir_input))
        backup_hbox.addWidget(self.btn_browse_bak)
        form_layout.addLayout(backup_hbox)
        
        self.cb_overwrite = QCheckBox("이미 존재하는 GitHub 릴리스 자동 덮어쓰기 (Overwrite Existing Release)", self)
        form_layout.addWidget(self.cb_overwrite)

        gen_layout.addLayout(form_layout)
        
        # 하단 버튼 레이아웃 (기본값 복원 버튼 및 설정 저장 버튼 배치)
        btn_layout = QHBoxLayout()
        
        self.btn_default = QPushButton("기본값 복원 (Default)", self)
        self.btn_default.setStyleSheet("color: #9CDCFE;")
        self.btn_default.clicked.connect(self.restore_defaults)
        btn_layout.addWidget(self.btn_default)
        
        btn_layout.addStretch()
        
        self.btn_save = QPushButton("설정 저장 (Save)", self)
        self.btn_save.setStyleSheet("font-weight: bold; color: #D7BA7D;")
        self.btn_save.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.btn_save)
        
        gen_layout.addLayout(btn_layout)
        
        self.tabs.addTab(tab_general, "⚙️ 기본 설정")
        
        if LogSettingsTab is not None:
            self.tab_log_settings = LogSettingsTab(self)
            self.tabs.addTab(self.tab_log_settings, "📝 로그 상세 설정")
        
        self.load_values_to_ui()

    def select_directory(self, target_line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "디렉토리 선택", target_line_edit.text() or os.getcwd())
        if path:
            norm_path = os.path.normpath(path)
            target_line_edit.setText(norm_path)
            logd(f"설정 다이얼로그 디렉토리 선택됨: {norm_path}")

    def load_values_to_ui(self):
        logd("설정 다이얼로그 UI에 INI 값 바인딩 중...")
        config = self.config_manager.load_config()
        self.owner_input.setText(config.get("repo_owner", DEF_REPO_OWNER))
        self.repo_input.setText(config.get("repo_name", DEF_REPO_NAME))
        self.token_input.setText(config.get("github_token", DEF_GITHUB_TOKEN))
        self.dir_input.setText(config.get("version_dir", DEF_LOCAL_VERSION_DIR))
        self.backup_dir_input.setText(config.get("backup_dir", DEF_BACKUP_DIR))
        self.cb_overwrite.setChecked(bool(config.get("overwrite_release", DEF_OVERWRITE_RELEASE)))

    def save_settings(self):
        settings = {
            "repo_owner": self.owner_input.text().strip(),
            "repo_name": self.repo_input.text().strip(),
            "github_token": self.token_input.text().strip(),
            "version_dir": self.dir_input.text().strip(),
            "backup_dir": self.backup_dir_input.text().strip(),
            "overwrite_release": self.cb_overwrite.isChecked(),
            "udp_port": 54321
        }
        if not settings["repo_owner"] or not settings["repo_name"] or not settings["version_dir"]:
            loge("설정 저장 실패: 필수 입력 항목(Owner, Repo, Version Dir)이 누락되었습니다.")
            QMessageBox.warning(self, "경고", "필수 항목을 입력해주세요.")
            return
            
        if self.config_manager.save_config(settings):
            logd("설정 다이얼로그 저장 성공 및 창 닫기(accept)")
            QMessageBox.information(self, "성공", "설정이 INI 파일에 저장되었습니다.")
            self.accept()
        else:
            loge("설정 다이얼로그 저장 실패: config_manager.save_config()가 False를 반환함")
            QMessageBox.critical(self, "실패", "설정 저장 중 오류가 발생했습니다.")
            
    def restore_defaults(self):
        logd("설정 기본값 복원 요청")
        reply = QMessageBox.question(
            self, "기본값 복원", 
            "모든 설정 값을 기본값으로 되돌리시겠습니까?\n(저장을 누르기 전까지는 파일에 반영되지 않습니다.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.owner_input.setText(DEF_REPO_OWNER)
            self.repo_input.setText(DEF_REPO_NAME)
            self.token_input.setText(DEF_GITHUB_TOKEN)
            self.dir_input.setText(DEF_LOCAL_VERSION_DIR)
            self.backup_dir_input.setText(DEF_BACKUP_DIR)
            self.cb_overwrite.setChecked(DEF_OVERWRITE_RELEASE)
            logd("설정 기본값으로 UI 필드 복원 완료")
            QMessageBox.information(self, "안내", "기본값으로 복원되었습니다. 적용하려면 [설정 저장] 버튼을 눌러주세요.")
