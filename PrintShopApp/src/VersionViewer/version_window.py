import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QScrollArea
)
from PySide6.QtCore import Qt

# 공통 모듈 및 설정 임포트 (exe_version_crypto의 extract_version_from_exe 활용)
from Common.Version.exe_version_crypto import extract_version_from_exe
from Common.log import setup_global_log, logd
from Common.config import FileConfigManager, ConfigType
from Common.path_mgr import PathMgr
from Common.log_settings_tab import LogSettingsTab


# ==========================================
# 1. VersionViewer 전용 설정 매니저 정의
# ==========================================
class VersionViewerConfig(FileConfigManager):
    file_dir: str = PathMgr.CONFIG_DIR
    file_name: str = "version_viewer_config.ini"
    section: str = "VersionViewer"
    schema = {
        "last_path": {"type": ConfigType.STRING, "default": ""},
        "window_width": {"type": ConfigType.INTEGER, "default": 950},
        "window_height": {"type": ConfigType.INTEGER, "default": 550}
    }


viewer_config_instance = VersionViewerConfig()


# ==========================================
# 2. 로그 환경 설정 다이얼로그
# ==========================================
class LogConfigDialog(QDialog):
    """로그 환경 설정 팝업 다이얼로그 (스크롤 영역 및 LogSettingsTab 탑재)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그 환경 설정")
        self.resize(700, 600)
        
        layout = QVBoxLayout(self)
        
        # 스크롤 영역 추가 (설정 항목이 많으므로 화면 넘침 방지)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # 로그 설정 탭 위젯 탑재
        self.log_settings_widget = LogSettingsTab(self)
        scroll.setWidget(self.log_settings_widget)
        
        layout.addWidget(scroll)
        
        # 하단 닫기 버튼
        btn_layout = QHBoxLayout()
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


# ==========================================
# 3. 메인 윈도우 클래스
# ==========================================
class VersionViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        setup_global_log(module_name="VersionViewer")
        logd("VersionViewerWindow initialized successfully.")

        self.config = viewer_config_instance

        self.setWindowTitle("PrintShopApp - 버전 뷰어 및 하위 검색기")
        
        # 저장된 윈도우 크기 불러오기
        w = self.config.get("window_width")
        h = self.config.get("window_height")
        self.resize(w, h)

        self.init_ui()

        # 저장된 마지막 경로 복원 및 자동 스캔 수행
        last_path = self.config.get("last_path")
        if last_path and os.path.exists(last_path):
            self.path_label.setText(f"선택된 경로: {last_path}")
            logd(f"Restoring last path from config: {last_path}")
            is_dir = os.path.isdir(last_path)
            self.scan_and_extract(last_path, is_dir=is_dir)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()
        
        self.path_label = QLabel("선택된 경로: 없음")
        self.path_label.setStyleSheet("font-weight: bold; color: #333;")
        
        btn_select_dir = QPushButton("📁 폴더 선택")
        btn_select_dir.clicked.connect(self.select_directory)
        
        btn_select_file = QPushButton("📄 파일 선택")
        btn_select_file.clicked.connect(self.select_file)

        btn_log_config = QPushButton("⚙️ 로그 설정")
        btn_log_config.clicked.connect(self.open_log_config_dialog)

        top_layout.addWidget(self.path_label, 1)
        top_layout.addWidget(btn_select_dir)
        top_layout.addWidget(btn_select_file)
        top_layout.addWidget(btn_log_config)
        layout.addLayout(top_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["No", "파일명 (Executable)", "버전 정보 (Version)"])
        
        header = self.table.horizontalHeader()
        # 컬럼 크기 자유 조절 가능 (Interactive)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)

        layout.addWidget(self.table)

    def open_log_config_dialog(self):
        dialog = LogConfigDialog(self)
        dialog.exec()

    def select_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택")
        if dir_path:
            self.path_label.setText(f"선택된 경로: {dir_path}")
            self.config.set("last_path", dir_path)  
            logd(f"Directory selected and saved: {dir_path}")
            self.scan_and_extract(dir_path, is_dir=True)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "확인할 실행 파일 선택", "", "Executable Files (*.exe)")
        if file_path:
            self.path_label.setText(f"선택된 경로: {file_path}")
            self.config.set("last_path", file_path)  
            logd(f"File selected and saved: {file_path}")
            self.scan_and_extract(file_path, is_dir=False)

    def scan_and_extract(self, path: str, is_dir: bool):
        exe_files = []
        if is_dir:
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith(".exe"):
                        exe_files.append(os.path.join(root, file))
        else:
            if path.lower().endswith(".exe"):
                exe_files.append(path)

        if not exe_files:
            QMessageBox.information(self, "안내", "탐색된 실행(.exe) 파일이 없습니다.")
            logd("No executable files found during scan.")
            self.table.setRowCount(0)
            return

        logd(f"Found {len(exe_files)} executable files. Starting version extraction...")
        self.table.setRowCount(len(exe_files))
        for idx, exe_path in enumerate(exe_files):
            item_no = QTableWidgetItem(str(idx + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            
            item_name = QTableWidgetItem(exe_path)
            item_name.setToolTip(exe_path) 
            
            # 외부 extract_version_from_exe 함수 활용
            version = extract_version_from_exe(exe_path)
            item_version = QTableWidgetItem(version if version else "추출 실패 / 정보 없음")
            item_version.setTextAlignment(Qt.AlignCenter)
            
            if not version or "오류" in version or "미적용" in version or "부족" in version or "없음" in version:
                item_version.setForeground(Qt.red)
            else:
                item_version.setForeground(Qt.darkGreen)
                logd(f"Extracted version for {os.path.basename(exe_path)}: {version}")

            self.table.setItem(idx, 0, item_no)
            self.table.setItem(idx, 1, item_name)
            self.table.setItem(idx, 2, item_version)

    def on_item_double_clicked(self, item):
        if item.column() == 1:
            file_path = item.text()
            if os.path.exists(file_path):
                norm_path = os.path.normpath(file_path)
                logd(f"Opening explorer for: {norm_path}")
                subprocess.run(['explorer.exe', '/select,', norm_path])
            else:
                QMessageBox.warning(self, "경고", f"파일을 찾을 수 없습니다:\n{file_path}")

    def closeEvent(self, event):
        """프로그램 종료 시 윈도우 크기 및 상태 저장"""
        self.config.set("window_width", self.width())
        self.config.set("window_height", self.height())
        logd("VersionViewer window size and settings saved.")
        super().closeEvent(event)