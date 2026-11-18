"""
========================================================================================
[프로젝트 파일 구조 및 모듈 아키텍처]
========================================================================================
C:/1print_shop/PrintShopApp/
│
├── data/
│   └── github_config.ini            # GitHub 저장소 및 시스템 설정 INI 파일
│
└── src/
    ├── UpdateManager/
    │   ├── upload_progress_dialog.py        # 모달리스 진행 상태 다이얼로그
    │   ├── prio_worker_queue.py             # 우선순위 기반 공용 워커 큐 모듈
    │   ├── github_config_manager.py         # INI 설정 관리 클래스
    │   ├── github_update_sync_manager.py    # GitHub 싱크 관리 클래스
    │   ├── settings_dialog.py               # 환경 설정 다이얼로그 클래스
    │   ├── main_app.py                      # 애플리케이션 실행 진입점 (분리됨)
    │   └── printshop_update_manager_github.py  # [본 파일] 메인 UI 및 매니저 클래스
    │
    └── Common/
        └── Version/
            └── exe_version_crypto.py           # .exe 파일 EOF 암호화 버전 토큰 주입/추출
========================================================================================
"""

import os
import sys
import re
import json
import base64
import zipfile
import shutil
from packaging import version

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QFileDialog, QInputDialog, QProgressBar, QTabWidget, 
    QWidget, QTextEdit
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QBrush

# 경로 동적 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

common_version_dir = os.path.join(parent_dir, 'Common', 'Version')
if common_version_dir not in sys.path:
    sys.path.insert(0, common_version_dir)

common_dir = os.path.join(parent_dir, 'Common')
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

from Common.log import logd, loge

# 모듈 임포트
from upload_progress_dialog import UploadProgressDialog
from UpdateManager.update_manager_config import GitHubConfigManager, DEF_VERSION_DIR
from github_update_sync_manager import GitHubUpdateSyncManager
from UpdateManager.update_manager_settings_dialog import UpdateManagerSettingsDialog
from Common.Version.exe_version_crypto import extract_version_from_exe

from Common.prio_worker_queue import TaskManager, TaskPriority


class UpdateManagerWindow(QMainWindow):
    """메인 윈도우 UI (QMainWindow 기반 및 우선순위 큐 시스템 연동)"""
    def __init__(self, config_manager: GitHubConfigManager, parent=None):
        super().__init__(parent)
        
        self.window_id = "GITHUB_SETTINGS_WIN"
        self.config_manager = config_manager
        self.setWindowTitle("GitHub 및 업데이트 시스템 통합 매니저 (Priority Queue)")
        self.resize(850, 700)

        # 큐 워커 전역 시그널 연결
        worker = TaskManager().get_worker()
        worker.task_progress.connect(self._handle_global_progress)
        worker.task_finished.connect(self._handle_global_finished)
        worker.queue_updated.connect(self._handle_global_queue)
        worker.current_task_changed.connect(self._handle_global_current)

        # 마지막으로 선택한 폴더 경로 기억할 변수 초기화
        self.last_selected_dir = os.getcwd()
        logd("GitHubSettingsDialog 메인 윈도우 초기화 시작")
        
        self.current_sync_data = []
        self.cached_remote_sha = None
        self.active_task_keys = []  # 현재 실행 또는 대기 중인 task_key 추적용
        
        self.upload_progress_dialog = UploadProgressDialog(self)
        self.upload_progress_dialog.cancel_all_signal.connect(self.on_cancel_all)
        self.upload_progress_dialog.cancel_item_signal.connect(self.on_cancel_item)
        
        # QMainWindow Central Widget 구성
        container = QWidget(self)
        main_layout = QVBoxLayout(container)
        
        self.tabs = QTabWidget(self)
        main_layout.addWidget(self.tabs)
        
        self.tab_sync = QWidget()
        self.init_sync_tab(self.tab_sync)
        self.tabs.addTab(self.tab_sync, "🚀 버전 싱크 및 배포 관리")
        
        self.tab_remote_json = QWidget()
        self.init_remote_json_tab(self.tab_remote_json)
        self.tabs.addTab(self.tab_remote_json, "🔍 원격 version.json 검증/수정")

        self.setCentralWidget(container)

    # ==========================================
    # Priority Queue 글로벌 시그널 핸들러 및 라우팅
    # ==========================================
    @Slot(str, str, int, str)
    def _handle_global_progress(self, owner_id, task_name, percent, message):
        if owner_id == self.window_id: 
            self.on_task_progress(task_name, percent, message)

    @Slot(str, str, tuple)
    def _handle_global_finished(self, owner_id, task_name, response):
        if owner_id == self.window_id:
            status, data = response
            self.on_task_finished(task_name, status, data)

    @Slot(list)
    def _handle_global_queue(self, task_names): 
        self.on_queue_updated(task_names)

    @Slot(str, str)
    def _handle_global_current(self, owner_id, task_name):
        if owner_id == self.window_id or owner_id == "": 
            self.on_current_task_changed(owner_id, task_name)

    def init_sync_tab(self, tab: QWidget):
        layout = QVBoxLayout(tab)
        
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(QLabel("<b>[PrintShop 업데이트 관리자 - 우선순위 큐 시스템]</b>"))
        top_bar_layout.addStretch()

        self.btn_open_github = QPushButton("🌐 GitHub 열기", self)
        self.btn_open_github.setStyleSheet("font-weight: bold; color: #569CD6; background-color: #2D2D2D;")
        self.btn_open_github.clicked.connect(self.open_github_repo_in_browser)
        top_bar_layout.addWidget(self.btn_open_github)
        
        self.btn_open_settings = QPushButton("⚙️ 환경 및 로그 설정...", self)
        self.btn_open_settings.setStyleSheet("font-weight: bold; color: #D7BA7D; background-color: #2D2D2D;")
        self.btn_open_settings.clicked.connect(self.open_settings_dialog)
        top_bar_layout.addWidget(self.btn_open_settings)
        layout.addLayout(top_bar_layout)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        file_action_layout = QHBoxLayout()
        self.btn_add_update_file = QPushButton("📁 신규 업데이트 파일(.zip/.exe) 선택 및 큐 등록 (업로드)", self)
        self.btn_add_update_file.setStyleSheet("font-weight: bold; color: #DCDCAA; background-color: #2D2D2D;")
        self.btn_add_update_file.clicked.connect(self.select_and_register_update_file)
        file_action_layout.addWidget(self.btn_add_update_file)
        layout.addLayout(file_action_layout)

        self.btn_inject_version_upload = QPushButton("✏️ 신규 업데이트 버전 주입 & 업로드", self)
        self.btn_inject_version_upload.setStyleSheet("background-color: #388A34; font-weight: bold; color: white;")
        self.btn_inject_version_upload.clicked.connect(self.handle_inject_version_and_upload)
        file_action_layout.addWidget(self.btn_inject_version_upload)        
        
        sync_action_layout = QHBoxLayout()
        self.btn_upload_selected = QPushButton("🚀 선택 버전을 큐에 담아 원격 업로드", self)
        self.btn_upload_selected.setStyleSheet("font-weight: bold; color: #4EC9B0; background-color: #1E1E1E;")
        self.btn_upload_selected.clicked.connect(self.upload_selected_versions)
        sync_action_layout.addWidget(self.btn_upload_selected)
        
        self.btn_open_upload_dlg = QPushButton("📊 진행 상태 창 열기", self)
        self.btn_open_upload_dlg.setStyleSheet("font-weight: bold; color: #D7BA7D; background-color: #1E1E1E;")
        self.btn_open_upload_dlg.clicked.connect(self.upload_progress_dialog.show)
        sync_action_layout.addWidget(self.btn_open_upload_dlg)
        
        self.btn_download_selected = QPushButton("⬇️ 선택 버전을 큐에 담아 로컬 다운로드", self)
        self.btn_download_selected.setStyleSheet("font-weight: bold; color: #569CD6; background-color: #1E1E1E;")
        self.btn_download_selected.clicked.connect(self.download_selected_versions)
        sync_action_layout.addWidget(self.btn_download_selected)
        layout.addLayout(sync_action_layout)
        
        btn_layout = QHBoxLayout()
        self.btn_sync_check = QPushButton("버전 싱크 상태 확인", self)
        self.btn_sync_check.clicked.connect(self.check_sync_status_async)
        btn_layout.addWidget(self.btn_sync_check)
        layout.addLayout(btn_layout)

        self.btn_auto_sync_json = QPushButton("🔄 원격 version.json 자동 정렬", self)
        self.btn_auto_sync_json.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.btn_auto_sync_json.clicked.connect(self.auto_sync_remote_json_action)
        btn_layout.addWidget(self.btn_auto_sync_json)        
        
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["선택", "버전", "싱크 상태", "로컬/GitHub 유무", "원격 릴리스 관리"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table.cellDoubleClicked.connect(self.on_table_cell_double_clicked)

        layout.addWidget(self.table)

    def init_remote_json_tab(self, tab: QWidget):
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("<b>[원격 저장소 version.json 검증 및 수동 제어]</b>"))
        
        self.txt_remote_content = QTextEdit(self)
        self.txt_remote_content.setPlaceholderText("상단의 [원격 조회 및 검증] 버튼을 누르면 내용이 표시됩니다.")
        layout.addWidget(self.txt_remote_content)
        
        edit_form = QVBoxLayout()
        edit_form.addWidget(QLabel("강제 적용할 목표 버전 (예: 1.3.0):"))
        self.input_force_ver = QLineEdit(self)
        edit_form.addWidget(self.input_force_ver)
        
        edit_form.addWidget(QLabel("강제 적용할 다운로드 URL (비워두면 자동 조합):"))
        self.input_force_url = QLineEdit(self)
        edit_form.addWidget(self.input_force_url)
        layout.addLayout(edit_form)
        
        action_hbox = QHBoxLayout()
        self.btn_fetch_remote = QPushButton("📥 1) 원격 조회 및 검증", self)
        self.btn_fetch_remote.setStyleSheet("font-weight: bold; color: #569CD6;")
        self.btn_fetch_remote.clicked.connect(self.fetch_remote_json_action)
        action_hbox.addWidget(self.btn_fetch_remote)
        
        self.btn_force_update = QPushButton("📤 2) 원격 version.json 강제 수정", self)
        self.btn_force_update.setStyleSheet("font-weight: bold; color: #D7BA7D;")
        self.btn_force_update.clicked.connect(self.force_update_remote_json_action)
        action_hbox.addWidget(self.btn_force_update)
        layout.addLayout(action_hbox)

    def open_github_repo_in_browser(self):
        config = self.config_manager.load_config()
        owner = config.get("repo_owner", "").strip()
        repo = config.get("repo_name", "").strip()
        
        if not owner or not repo:
            loge("GitHub 열기 실패: owner 또는 repo 설정 누락")
            QMessageBox.warning(self, "경고", "환경 설정에 GitHub 소유자(Owner) 또는 리포지토리(Repo) 이름이 설정되어 있지 않습니다.")
            return
            
        url = f"https://github.com/{owner}/{repo}"
        logd(f"GitHub 리포지토리 브라우저로 열기: {url}")
        
        try:
            import webbrowser
            opened = False
            try:
                chrome = webbrowser.get('chrome')
                if chrome:
                    chrome.open(url)
                    opened = True
            except Exception:
                pass
                
            if not opened:
                webbrowser.open(url)
                
        except Exception as e:
            loge(f"GitHub 페이지 열기 중 예외 발생: {e}")
            QMessageBox.critical(self, "오류", f"브라우저를 실행할 수 없습니다:\n{e}")

    def open_settings_dialog(self):
        logd("환경 및 로그 설정 다이얼로그 열기")
        dlg = UpdateManagerSettingsDialog(self.config_manager, self)
        if dlg.exec():
            logd("설정 변경 확인됨 -> 싱크 상태 재조회 실행")
            self.check_sync_status_async()

    @Slot(int, int)
    def on_table_cell_double_clicked(self, row: int, column: int):
        """테이블 셀 더블클릭 시 버전 컬럼인 경우 파일 위치 탐색기 열기"""
        # 1은 버전 컬럼 인덱스
        if column == 1:
            if row < len(self.current_sync_data):
                stat = self.current_sync_data[row]
                version_str = stat.get("version", "")
                local_path = stat.get("local_path")
                
                # 1) 로컬 파일 경로가 존재하고 실제 파일이 있는 경우
                if local_path and os.path.exists(local_path):
                    logd(f"로컬 파일 위치 탐색기로 열기: {local_path}")
                    # 윈도우 탐색기에서 해당 파일 선택 상태로 열기
                    os.system(f'explorer /select,"{os.path.normpath(local_path)}"')
                else:
                    # 2) 파일은 없지만 해당 버전의 폴더(versions_printshop/vX.X.X)가 있는 경우
                    config = self.config_manager.load_config()
                    version_dir = config.get("version_dir", DEF_VERSION_DIR)
                    target_folder = os.path.join(version_dir, f"v{version_str}")
                    
                    if os.path.exists(target_folder):
                        logd(f"로컬 버전 폴더 탐색기로 열기: {target_folder}")
                        os.startfile(os.path.normpath(target_folder))
                    else:
                        QMessageBox.information(
                            self, "알림", 
                            f"버전 v{version_str}의 로컬 파일이나 디렉토리가 존재하지 않습니다.\n(먼저 다운로드하거나 파일을 등록해주세요.)"
                        )            

    def get_sync_manager(self) -> GitHubUpdateSyncManager:
        cfg = self.config_manager.load_config()
        return GitHubUpdateSyncManager(
            repo_owner=cfg["repo_owner"],
            repo_name=cfg["repo_name"],
            github_token=cfg["github_token"],
            local_versions_dir=cfg["version_dir"],
            overwrite_release=cfg["overwrite_release"]
        )

    def on_cancel_all(self):
        logd("메인 윈도우: 전체 취소 요청")
        for key in list(self.active_task_keys):
            TaskManager().cancel(key)
        self.upload_progress_dialog.update_total_progress(0, "⚠️ 사용자에 의해 전체 큐 작업이 취소되었습니다.")

    def on_cancel_item(self, version_str: str):
        logd(f"메인 윈도우: 개별 취소 요청 -> v{version_str}")
        for key in list(self.active_task_keys):
            if version_str in key:
                TaskManager().cancel(key)
        self.upload_progress_dialog.update_item_progress(version_str, 0, "취소됨", f"⚠️ 버전 v{version_str} 작업이 취소되었습니다.")

    def delete_remote_release_action(self, version_str: str):
        logd(f"원격 릴리스 삭제 버튼 클릭됨: v{version_str}")
        reply = QMessageBox.question(
            self, "원격 릴리스 삭제 확인",
            f"GitHub에 있는 버전 v{version_str} 릴리스와 에셋을 정말 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            manager = self.get_sync_manager()
            success = manager.delete_github_release(version_str)
            if success:
                logd(f"원격 릴리스 삭제 완료: v{version_str}")
                QMessageBox.information(self, "성공", f"✅ v{version_str} 원격 릴리스가 삭제되었습니다.")
                self.check_sync_status_async()
            else:
                loge(f"원격 릴리스 삭제 실패: v{version_str}")
                QMessageBox.critical(self, "실패", f"❌ v{version_str} 원격 릴리스 삭제에 실패했습니다.")

    def fetch_remote_json_action(self):
        logd("원격 version.json 조회 액션 시작 (Priority Queue)")
        manager = self.get_sync_manager()
        self.progress_bar.show()
        
        task_key = f"{self.window_id}_FETCH_JSON_{int(os.times()[4]*1000)}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")
            content, sha = manager.fetch_remote_version_json_raw()
            return {"content": content, "sha": sha}

        TaskManager().enqueue(
            TaskPriority.NORMAL, task_key, self.window_id, 
            "원격 version.json 조회", task_func
        )

    def force_update_remote_json_action(self):
        target_ver = self.input_force_ver.text().strip()
        if not target_ver:
            loge("원격 version.json 강제 수정 중단: 목표 버전 미입력")
            QMessageBox.warning(self, "경고", "강제 적용할 버전을 입력해주세요.")
            return
        if not self.cached_remote_sha:
            logd("캐시된 원격 SHA가 없어 원격 version.json 선행 조회 실행")
            self.fetch_remote_json_action()
            return
            
        manager = self.get_sync_manager()
        custom_url = self.input_force_url.text().strip() or None
        logd(f"원격 version.json 강제 수정 액션 시작 (목표 버전: {target_ver})")
        self.progress_bar.show()
        
        task_key = f"{self.window_id}_FORCE_JSON_{target_ver}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")
            return manager.force_update_remote_json_manual(target_ver, self.cached_remote_sha, custom_url)

        TaskManager().enqueue(
            TaskPriority.NORMAL, task_key, self.window_id, 
            f"원격 version.json 강제 수정 (v{target_ver})", task_func
        )

    def auto_sync_remote_json_action(self):
        logd("원격 version.json 자동 정렬/동기화 액션 시작")
        config = self.config_manager.load_config()
        if not config["github_token"]:
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return

        manager = self.get_sync_manager()
        self.progress_bar.show()
        self.btn_auto_sync_json.setEnabled(False)
        
        task_key = f"{self.window_id}_AUTO_SYNC_JSON"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")
            return manager.auto_sync_remote_version_json()

        TaskManager().enqueue(
            TaskPriority.NORMAL, task_key, self.window_id, 
            "원격 version.json 자동 정렬", task_func
        )

    def check_sync_status_async(self):
        logd("비동기 버전 싱크 상태 확인 요청 시작 (Priority Queue)")
        config = self.config_manager.load_config()
        sync_manager = self.get_sync_manager()
        self.btn_sync_check.setEnabled(False)
        self.progress_bar.show()
        
        task_key = f"{self.window_id}_CHECK_SYNC_{int(os.times()[4]*1000)}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")
            return sync_manager.get_version_sync_status(config["version_dir"])

        TaskManager().enqueue(
            TaskPriority.HIGH, task_key, self.window_id, 
            "버전 싱크 상태 확인", task_func
        )

    def select_and_register_update_file(self):
        logd("신규 업데이트 파일 선택 다이얼로그 호출")
        config = self.config_manager.load_config()
        version_dir = config["version_dir"]

        file_path, _ = QFileDialog.getOpenFileName(
            self, "신규 업데이트 파일 선택", self.last_selected_dir, 
            "업데이트 파일 (*.zip *.exe);;ZIP 파일 (*.zip);;실행 파일 (*.exe);;모든 파일 (*.*)"
        )
        if not file_path:
            logd("파일 선택 취소됨")
            return

        self.last_selected_dir = os.path.dirname(file_path)
        logd(f"선택된 업데이트 파일: {file_path} (폴더 경로 기억: {self.last_selected_dir})")

        sync_manager = self.get_sync_manager()
        target_file_for_register = file_path
        detected_version = "0.0.0"

        if file_path.lower().endswith(".exe"):
            raw_ver = extract_version_from_exe(file_path)
            match = re.search(r"v?(\d+\.\d+\.\d+)", raw_ver)
            if match:
                detected_version = match.group(1)
                logd(f".exe 파일에서 버전 감지됨: {detected_version}")
            else:
                input_ver, ok = QInputDialog.getText(self, "버전 입력", "버전을 입력하세요 (예: 1.3.0):")
                if ok and input_ver.strip():
                    clean_match = re.search(r"v?(\d+\.\d+\.\d+)", input_ver.strip())
                    if clean_match:
                        detected_version = clean_match.group(1)

            if detected_version == "0.0.0":
                loge(f"유효한 버전을 감지하지 못해 파일 등록 중단: {file_path}")
                QMessageBox.critical(self, "오류", "유효한 버전을 감지하지 못했습니다.")
                return

            reply = QMessageBox.question(
                self, "ZIP 패키징 안내",
                f"감지된 버전: v{detected_version}\n.zip 파일로 자동 압축하여 등록하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                temp_zip_name = os.path.join(version_dir, f"update_v{detected_version}.zip")
                logd(f".exe 파일을 ZIP으로 자동 압축 중: {temp_zip_name}")
                with zipfile.ZipFile(temp_zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(file_path, arcname=os.path.basename(file_path))
                target_file_for_register = temp_zip_name
            else:
                logd("사용자가 ZIP 패키징을 취소함")
                return
        else:
            detected_version = sync_manager.extract_version_from_package(file_path)
            if detected_version == "0.0.0":
                input_ver, ok = QInputDialog.getText(self, "버전 입력", "버전을 입력하세요 (예: 1.3.0):")
                if ok and input_ver.strip():
                    clean_match = re.search(r"v?(\d+\.\d+\.\d+)", input_ver.strip())
                    if clean_match:
                        detected_version = clean_match.group(1)

        if detected_version == "0.0.0":
            loge("최종 버전 확인 실패로 등록 중단")
            QMessageBox.critical(self, "오류", "유효한 버전을 확인할 수 없습니다.")
            return

        reply = QMessageBox.question(
            self, "신규 업로드 확인",
            f"버전 v{detected_version} 파일을 로컬 등록하고 큐에 넣어 GitHub에 업로드하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                target_folder = os.path.join(version_dir, f"v{detected_version}")
                os.makedirs(target_folder, exist_ok=True)
                dest_path = os.path.join(target_folder, os.path.basename(target_file_for_register))
                if target_file_for_register != dest_path:
                    shutil.copy2(target_file_for_register, dest_path)
                    logd(f"로컬 버전 폴더로 파일 복사 완료: {dest_path}")
                
                if config["github_token"]:
                    item_info = {"version": detected_version, "local_path": dest_path, "name": os.path.basename(dest_path)}
                    logd(f"신규 파일 업로드 큐 등록 및 워커 시작: v{detected_version}")
                    
                    self.upload_progress_dialog.init_tasks([item_info])
                    self.upload_progress_dialog.show()
                    self.upload_progress_dialog.raise_()
                    
                    self.enqueue_upload_task(sync_manager, item_info)
                else:
                    logd(f"토큰이 없어 로컬 version.json만 업데이트함: v{detected_version}")
                    sync_manager.update_local_version_json(detected_version, dest_path)
                    QMessageBox.warning(self, "알림", "토큰이 없어 로컬에만 등록되었습니다.")
                self.check_sync_status_async()
            except Exception as e:
                loge(f"신규 파일 등록 및 업로드 준비 중 예외 발생: {e}")
                QMessageBox.critical(self, "오류", f"등록 중 예외 발생: {e}")

    def handle_inject_version_and_upload(self):
        config = self.config_manager.load_config()
        version_dir = config["version_dir"]

        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "업데이트 패키지 선택", 
            self.last_selected_dir, 
            "Update Packages (*.zip *.exe)"
        )
        
        if not file_path:
            logd("버전 주입 파일 선택 취소됨")
            return
            
        self.last_selected_dir = os.path.dirname(file_path)
        logd(f"선택된 업데이트 파일: {file_path} (폴더 경로 기억: {self.last_selected_dir})")
        
        default_ver = "1.2.1"
        version_str, ok = QInputDialog.getText(
            self, 
            "버전 주입 및 업로드", 
            "업로드할 버전을 입력하세요 (예: 1.2.1):", 
            QLineEdit.Normal, 
            default_ver
        )
        
        if not ok or not version_str.strip():
            logd("버전 주입 취소됨")
            return
            
        version_str = version_str.strip().lstrip('v')
        logd(f"사용자 직접 버전 주입 선택: v{version_str} (파일: {file_path})")

        target_file_for_register = file_path

        if file_path.lower().endswith(".exe"):
            reply = QMessageBox.question(
                self, "ZIP 패키징 안내",
                f"주입된 버전: v{version_str}\n.zip 파일로 자동 압축하여 등록하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.makedirs(version_dir, exist_ok=True)
                temp_zip_name = os.path.join(version_dir, f"update_v{version_str}.zip")
                logd(f".exe 파일을 ZIP으로 자동 압축 중: {temp_zip_name}")
                with zipfile.ZipFile(temp_zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(file_path, arcname=os.path.basename(file_path))
                target_file_for_register = temp_zip_name

        reply = QMessageBox.question(
            self, "신규 버전 주입 업로드 확인",
            f"주입된 버전 v{version_str}로 로컬 등록 후 GitHub에 업로드하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                target_folder = os.path.join(version_dir, f"v{version_str}")
                os.makedirs(target_folder, exist_ok=True)
                dest_path = os.path.join(target_folder, os.path.basename(target_file_for_register))
                
                if target_file_for_register != dest_path:
                    shutil.copy2(target_file_for_register, dest_path)
                    logd(f"로컬 버전 폴더로 파일 복사 완료: {dest_path}")
                
                sync_manager = self.get_sync_manager()
                if config["github_token"]:
                    item_info = {"version": version_str, "local_path": dest_path, "name": os.path.basename(dest_path)}
                    logd(f"주입된 버전 파일 업로드 큐 등록 및 워커 시작: v{version_str}")
                    
                    self.upload_progress_dialog.init_tasks([item_info])
                    self.upload_progress_dialog.show()
                    self.upload_progress_dialog.raise_()
                    
                    self.enqueue_upload_task(sync_manager, item_info)
                else:
                    logd(f"토큰이 없어 로컬 version.json만 업데이트함: v{version_str}")
                    sync_manager.update_local_version_json(version_str, dest_path)
                    QMessageBox.warning(self, "알림", "토큰이 없어 로컬에만 등록되었습니다.")
                    
                self.check_sync_status_async()
            except Exception as e:
                loge(f"버전 주입 파일 등록 및 업로드 준비 중 예외 발생: {e}")
                QMessageBox.critical(self, "오류", f"등록 중 예외 발생: {e}")

    def upload_selected_versions(self):
        selected = self.get_checked_items()
        if not selected:
            loge("원격 업로드 중단: 선택된 버전이 없음")
            QMessageBox.warning(self, "경고", "업로드할 버전을 선택해주세요.")
            return
        config = self.config_manager.load_config()
        if not config["github_token"]:
            loge("원격 업로드 중단: GitHub 토큰 미설정")
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return
            
        logd(f"선택된 {len(selected)}개 버전 원격 업로드 큐 시작")
        sync_manager = self.get_sync_manager()
        task_items = [{"version": item["version"], "local_path": item["local_path"], "name": os.path.basename(item["local_path"]) if item["local_path"] else ""} for item in selected]
        
        self.upload_progress_dialog.init_tasks(task_items)
        self.upload_progress_dialog.show()
        self.upload_progress_dialog.raise_()
        
        for item in task_items:
            self.enqueue_upload_task(sync_manager, item)

    def download_selected_versions(self):
        selected = self.get_checked_items()
        if not selected:
            loge("로컬 다운로드 중단: 선택된 버전이 없음")
            QMessageBox.warning(self, "경고", "다운로드할 버전을 선택해주세요.")
            return
        config = self.config_manager.load_config()
        if not config["github_token"]:
            loge("로컬 다운로드 중단: GitHub 토큰 미설정")
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return
            
        logd(f"선택된 {len(selected)}개 버전 로컬 다운로드 큐 시작")
        sync_manager = self.get_sync_manager()
        task_items = [{"version": item["version"], "github_info": item["github_info"], "name": item["github_info"].get("name", "") if item["github_info"] else ""} for item in selected]
        
        self.upload_progress_dialog.init_tasks(task_items)
        self.upload_progress_dialog.show()
        self.upload_progress_dialog.raise_()
        
        for item in task_items:
            self.enqueue_download_task(sync_manager, item)

    def enqueue_upload_task(self, sync_manager, item):
        ver = item["version"]
        path = item["local_path"]
        task_key = f"{self.window_id}_UPLOAD_{ver}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            def cb(pct, msg):
                if progress_cb:
                    progress_cb(pct, msg)
                self.upload_progress_dialog.update_item_progress(ver, pct, "업로드 중", msg)

            def check_cancel():
                return cancel_event and cancel_event.is_set()

            success, err_msg = sync_manager.upload_to_github_with_progress(
                ver, path, progress_callback=cb, cancel_check=check_cancel
            )
            if not success:
                raise Exception(err_msg)
            return success

        TaskManager().enqueue(
            TaskPriority.NORMAL, task_key, self.window_id, 
            f"버전 v{ver} 업로드", task_func
        )

    def enqueue_download_task(self, sync_manager, item):
        ver = item["version"]
        gh_info = item["github_info"]
        download_url = gh_info.get("download_url") if gh_info else None
        task_key = f"{self.window_id}_DOWNLOAD_{ver}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            def cb(pct, msg):
                if progress_cb:
                    progress_cb(pct, msg)
                self.upload_progress_dialog.update_item_progress(ver, pct, "다운로드 중", msg)

            def check_cancel():
                return cancel_event and cancel_event.is_set()

            success, err_msg = sync_manager.download_from_github_with_progress(
                ver, download_url, progress_callback=cb, cancel_check=check_cancel
            )
            if not success:
                raise Exception(err_msg)
            return success

        TaskManager().enqueue(
            TaskPriority.NORMAL, task_key, self.window_id, 
            f"버전 v{ver} 다운로드", task_func
        )

    def get_checked_items(self) -> list:
        checked_items = []
        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                if row < len(self.current_sync_data):
                    checked_items.append(self.current_sync_data[row])
        logd(f"테이블 체크박스 선택 항목 조회: {len(checked_items)}개 선택됨")
        return checked_items

    # ==========================================
    # QueueBaseWindow 호환 콜백 메서드들
    # ==========================================
    def on_task_progress(self, task_name, percent, message):
        logd(f"[진행] {task_name}: {percent}% - {message}")

    def on_task_finished(self, task_name, status, data):
        self.progress_bar.hide()
        self.btn_sync_check.setEnabled(True)
        logd(f"[완료] 작업 종료: {task_name} (상태: {status})")

        if status == "SUCCESS":
            if "버전 싱크 상태 확인" in task_name and isinstance(data, list):
                self.apply_sync_table_data(data)
            elif "원격 version.json 조회" in task_name and isinstance(data, dict):
                content = data.get("content")
                sha = data.get("sha")
                self.cached_remote_sha = sha
                self.txt_remote_content.setPlainText(f"--- [SHA 값]: {sha} ---\n\n{content}")
                QMessageBox.information(self, "조회 성공", "원격 version.json 조회가 완료되었습니다.")
            elif "원격 version.json 강제 수정" in task_name:
                QMessageBox.information(self, "수정 성공", "원격 version.json이 강제 갱신되었습니다.")
                self.fetch_remote_json_action()
            elif "원격 version.json 자동 정렬" in task_name:
                self.btn_auto_sync_json.setEnabled(True)
                QMessageBox.information(self, "동기화 성공", "✅ 실제 최신 릴리스에 맞게 원격 version.json이 자동 정렬되었습니다.")
                self.check_sync_status_async()
            elif "업로드" in task_name or "다운로드" in task_name:
                pass
        elif status == "CANCELLED":
            logd(f"[취소됨] {task_name}")
        else:
            loge(f"[에러] {task_name} 실패: {data}")
            if "자동 정렬" in task_name:
                self.btn_auto_sync_json.setEnabled(True)
            else:
                QMessageBox.critical(self, "작업 오류", f"작업 실패:\n{data}")

    def on_queue_updated(self, task_names):
        logd(f"우선순위 대기열 갱신: {task_names}")

    def on_current_task_changed(self, owner_id, task_name):
        if owner_id == self.window_id or owner_id == "":
            logd(f"현재 실행 중인 우선순위 작업: {task_name}")

    def apply_sync_table_data(self, result: list):
        self.current_sync_data = result
        self.table.setRowCount(len(result))
        for row, stat in enumerate(result):
            chk_item = QTableWidgetItem()
            has_local_file = stat.get('in_local', False) and stat.get('local_path') and os.path.exists(stat['local_path'])
            
            if has_local_file:
                chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
            else:
                chk_item.setFlags(Qt.ItemFlag.NoItemFlags)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                chk_item.setForeground(QBrush(QColor("gray")))

            self.table.setItem(row, 0, chk_item)
            self.table.setItem(row, 1, QTableWidgetItem(f"v{stat['version']}"))
            
            status_item = QTableWidgetItem(stat['sync_status'])
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QBrush(QColor("green" if stat['sync_status'] == "SYNCED" else "orange")))
            self.table.setItem(row, 2, status_item)
            
            loc_s = 'O' if has_local_file else 'X'
            rel_s = 'O' if stat['has_release'] else 'X'
            zip_s = 'O' if stat['has_zip'] else 'X'
            tag_s = 'O' if stat['has_tag'] else 'X'
            
            detail_str = f"Local: {loc_s} / Release: {rel_s} / ZIP: {zip_s} / Tag: {tag_s}"
            self.table.setItem(row, 3, QTableWidgetItem(detail_str))
            
            if stat['has_release'] or stat['has_tag']:
                btn_del_remote = QPushButton("🗑️ 원격 릴리스/태그 제거")
                btn_del_remote.setStyleSheet("color: #F44747; font-weight: bold;")
                btn_del_remote.clicked.connect(lambda checked=False, v=stat['version']: self.delete_remote_release_action(v))
                self.table.setCellWidget(row, 4, btn_del_remote)
            else:
                lbl_none = QLabel("-")
                lbl_none.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setCellWidget(row, 4, lbl_none)