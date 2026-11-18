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
    │   ├── github_update_sync_manager.py    # GitHub 싱크 관리 클래스 (LocalVersionMap 포함)
    │   ├── settings_dialog.py               # 환경 설정 다이얼로그 클래스
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

from upload_progress_dialog import UploadProgressDialog
from UpdateManager.update_manager_config import GitHubConfigManager, DEF_VERSION_DIR
from github_update_sync_manager import GitHubUpdateSyncManager, LocalVersionMap, LocalVersionInfo
from UpdateManager.update_manager_settings_dialog import UpdateManagerSettingsDialog
from Common.Version.exe_version_crypto import extract_version_from_exe, encrypt_and_append_version

from Common.prio_worker_queue import TaskManager, TaskPriority


class UpdateManagerWindow(QMainWindow):
    """메인 윈도우 UI (QMainWindow 기반 및 우선순위 큐 시스템 연동)"""
    def __init__(self, config_manager: GitHubConfigManager, parent=None):
        super().__init__(parent)
        
        self.window_id = "GITHUB_SETTINGS_WIN"
        self.config_manager = config_manager
        self.setWindowTitle("GitHub 및 업데이트 시스템 통합 매니저 (Priority Queue)")
        self.resize(900, 700)

        worker = TaskManager().get_worker()
        worker.task_progress.connect(self._handle_global_progress)
        worker.task_finished.connect(self._handle_global_finished)
        worker.queue_updated.connect(self._handle_global_queue)
        worker.current_task_changed.connect(self._handle_global_current)

        self.last_selected_dir = os.getcwd()
        logd("GitHubSettingsDialog 메인 윈도우 초기화 시작")
        
        self.current_sync_data = []
        self.cached_remote_sha = None
        self.active_task_keys = []
        self._batch_progress_map = {}
        
        # 데이터 클래스 기반 맵 객체 캐시 초기화
        self.cached_local_version_map = {}
        
        self.upload_progress_dialog = UploadProgressDialog(self)
        self.upload_progress_dialog.cancel_all_signal.connect(self.on_cancel_all)
        self.upload_progress_dialog.cancel_item_signal.connect(self.on_cancel_item)
        
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

        inject_layout = QHBoxLayout()
        self.btn_inject_version_upload = QPushButton("✏️ 신규 업데이트 버전 주입 & 업로드", self)
        self.btn_inject_version_upload.setStyleSheet("background-color: #388A34; font-weight: bold; color: white;")
        self.btn_inject_version_upload.clicked.connect(self.handle_inject_version_and_upload)
        inject_layout.addWidget(self.btn_inject_version_upload)        

        self.btn_force_inject = QPushButton("⚡ 버전 강제주입", self)
        self.btn_force_inject.setStyleSheet("background-color: #C586C0; font-weight: bold; color: white;")
        self.btn_force_inject.clicked.connect(self.handle_force_inject_queue)
        inject_layout.addWidget(self.btn_force_inject)
        
        layout.addLayout(inject_layout)
        
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
        
        self.btn_check_local_versions = QPushButton("🔍 로컬버전 체크", self)
        self.btn_check_local_versions.setStyleSheet("font-weight: bold; color: #4EC9B0; background-color: #2D2D2D;")
        self.btn_check_local_versions.clicked.connect(self.handle_local_version_check)
        btn_layout.addWidget(self.btn_check_local_versions)

        # 🔍 버튼 이름 변경 반영 (버전 싱크 상태 확인 -> 원격버전 체크)
        self.btn_sync_check = QPushButton("🔍 원격버전 체크", self)
        self.btn_sync_check.setStyleSheet("font-weight: bold; color: #569CD6; background-color: #2D2D2D;")
        self.btn_sync_check.clicked.connect(self.handle_remote_version_check)
        btn_layout.addWidget(self.btn_sync_check)
        layout.addLayout(btn_layout)

        self.btn_auto_sync_json = QPushButton("🔄 원격 version.json 자동 정렬", self)
        self.btn_auto_sync_json.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.btn_auto_sync_json.clicked.connect(self.auto_sync_remote_json_action)
        btn_layout.addWidget(self.btn_auto_sync_json)        

        self.table = QTableWidget(self)
        self.table.setColumnCount(7)  # 컬럼 수 7개로 확장
        self.table.setHorizontalHeaderLabels([
            "순서", "선택", "Local 버전", "싱크 상태", "로컬/GitHub 유무", "GitHub 버전", "원격 릴리스 관리"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive) # Local 버전
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive) # 싱크 상태
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)     # 로컬/GitHub 유무
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive) # GitHub 버전 (새로 추가)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # 원격 릴리스 관리
        
        
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
            QMessageBox.warning(self, "경고", "환경 설정에 GitHub 소유자(Owner) 또는 리포지토리(Repo) 이름이 설정되어 있지 않습니다.")
            return
            
        url = f"https://github.com/{owner}/{repo}"
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"브라우저를 실행할 수 없습니다:\n{e}")

    def open_settings_dialog(self):
        dlg = UpdateManagerSettingsDialog(self.config_manager, self)
        if dlg.exec():
            self.handle_remote_version_check()

    @Slot(int, int)
    def on_table_cell_double_clicked(self, row: int, column: int):
        if column == 2 and row < len(self.current_sync_data):
            stat = self.current_sync_data[row]
            version_str = stat.get("version", "")
            local_path = stat.get("local_path")
            
            if local_path and os.path.exists(local_path):
                os.system(f'explorer /select,"{os.path.normpath(local_path)}"')
            else:
                config = self.config_manager.load_config()
                version_dir = config.get("version_dir", DEF_VERSION_DIR)
                if os.path.exists(version_dir):
                    os.startfile(os.path.normpath(version_dir))
                else:
                    QMessageBox.information(
                        self, "알림", 
                        f"버전 v{version_str}의 로컬 파일이 존재하지 않습니다."
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
        for key in list(self.active_task_keys):
            TaskManager().cancel(key)
        self.upload_progress_dialog.update_total_progress(0, "⚠️ 사용자에 의해 전체 큐 작업이 취소되었습니다.")

    def on_cancel_item(self, version_str: str):
        for key in list(self.active_task_keys):
            if version_str in key:
                TaskManager().cancel(key)
        self.upload_progress_dialog.update_item_progress(version_str, 0, "취소됨", f"⚠️ 버전 v{version_str} 작업이 취소되었습니다.")

    def delete_remote_release_action(self, version_str: str):
        # 1. 현재 화면(또는 캐시)에서 해당 버전의 유무 상태(O/X) 정보 탐색
        target_stat = None
        for stat in self.current_sync_data:
            if stat.get("version") == version_str:
                target_stat = stat
                break
        
        if not target_stat and hasattr(self, "cached_local_version_map"):
            for fname, info in self.cached_local_version_map.items():
                if info.version == version_str or info.inner_version == version_str:
                    target_stat = info.to_dict()
                    break

        # 2. 'O'로 존재하는 항목들만 골라내어 리스트로 구성
        existing_items = []
        if target_stat:
            if target_stat.get("has_release", False):
                existing_items.append("Release")
            if target_stat.get("has_zip", False):
                existing_items.append("ZIP 에셋")
            if target_stat.get("has_tag", False):
                existing_items.append("Tag")
        
        items_str = ", ".join(existing_items) if existing_items else "릴리스 및 태그"

        # 3. 상세히 표시되는 삭제 확인 메시지 박스 호출
        reply = QMessageBox.question(
            self, "원격 릴리스 삭제 확인",
            f"GitHub에 있는 버전 v{version_str}의 다음 항목을 정말 삭제하시겠습니까?\n\n"
            f"📍 감지된 항목: [ {items_str} ]",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            manager = self.get_sync_manager()
            success = manager.delete_github_release(version_str)
            if success:
                QMessageBox.information(self, "성공", f"✅ v{version_str} 원격 항목이 삭제되었습니다.")
                self.handle_remote_version_check()
            else:
                QMessageBox.critical(self, "실패", f"❌ v{version_str} 원격 항목 삭제에 실패했습니다.")

    def fetch_remote_json_action(self):
        manager = self.get_sync_manager()
        self.progress_bar.show()
        
        task_key = f"{self.window_id}_FETCH_JSON_{int(os.times()[4]*1000)}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")
            content, sha = manager.fetch_remote_version_json_raw()
            return {"content": content, "sha": sha}

        TaskManager().enqueue(TaskPriority.NORMAL, task_key, self.window_id, "원격 version.json 조회", task_func)

    def force_update_remote_json_action(self):
        target_ver = self.input_force_ver.text().strip()
        if not target_ver:
            QMessageBox.warning(self, "경고", "강제 적용할 버전을 입력해주세요.")
            return
        if not self.cached_remote_sha:
            self.fetch_remote_json_action()
            return
            
        manager = self.get_sync_manager()
        custom_url = self.input_force_url.text().strip() or None
        self.progress_bar.show()
        
        task_key = f"{self.window_id}_FORCE_JSON_{target_ver}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")
            return manager.force_update_remote_json_manual(target_ver, self.cached_remote_sha, custom_url)

        TaskManager().enqueue(TaskPriority.NORMAL, task_key, self.window_id, f"원격 version.json 강제 수정 (v{target_ver})", task_func)

    def auto_sync_remote_json_action(self):
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

        TaskManager().enqueue(TaskPriority.NORMAL, task_key, self.window_id, "원격 version.json 자동 정렬", task_func)

    # 1. [로컬 전용 영역] 로컬 영역만 스캔하여 LocalVersionMap 생성 및 갱신
    def handle_local_version_check(self):
        config = self.config_manager.load_config()
        version_dir = config["version_dir"]

        if not os.path.exists(version_dir):
            QMessageBox.warning(self, "경고", f"로컬 버전 디렉토리가 존재하지 않습니다:\n{version_dir}")
            return

        self.btn_check_local_versions.setEnabled(False)
        self.progress_bar.show()

        task_key = f"{self.window_id}_LOCAL_ONLY_CHECK_{int(os.times()[4]*1000)}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")

            if progress_cb:
                progress_cb(20, "로컬 파일 스캔 및 .exe 버전 매치 검사 중...")

            version_map_mgr = LocalVersionMap(version_dir)
            local_map_result = version_map_mgr.scan_and_build()
            
            # 메인 윈도우 캐시에 LocalVersionMap 보관
            self.cached_local_version_map = local_map_result  
            local_check_results = [info.to_dict() for info in local_map_result.values()]

            if progress_cb:
                progress_cb(100, "로컬버전 체크 완료")

            return local_check_results

        TaskManager().enqueue(TaskPriority.HIGH, task_key, self.window_id, "로컬버전 체크", task_func)

    # 2. [원격 전용 영역] GitHub 원격만 조회하여 LocalVersionMap 업데이트 및 갱신
    def handle_remote_version_check(self):
        config = self.config_manager.load_config()
        if not config["github_token"]:
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return

        self.btn_sync_check.setEnabled(False)
        self.progress_bar.show()

        task_key = f"{self.window_id}_REMOTE_ONLY_CHECK_{int(os.times()[4]*1000)}"
        self.active_task_keys.append(task_key)

        sync_manager = self.get_sync_manager()

        def task_func(progress_cb=None, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")

            if progress_cb:
                progress_cb(20, "GitHub 원격 릴리스 및 태그 정보 조회 중...")

            # 로컬 맵이 아직 없으면 먼저 빈 로컬 맵 생성
            if not hasattr(self, "cached_local_version_map") or not self.cached_local_version_map:
                version_map_mgr = LocalVersionMap(config["version_dir"])
                self.cached_local_version_map = version_map_mgr.scan_and_build()

            if progress_cb:
                progress_cb(60, "LocalVersionMap에 원격 상태 업데이트 중...")

            # 원격 정보만 맵에 반영
            updated_map = sync_manager.update_remote_status_to_map(self.cached_local_version_map)
            self.cached_local_version_map = updated_map

            remote_check_results = [info.to_dict() for info in updated_map.values()]

            if progress_cb:
                progress_cb(100, "원격버전 체크 완료")

            return remote_check_results

        TaskManager().enqueue(TaskPriority.HIGH, task_key, self.window_id, "원격버전 체크", task_func)

    def select_and_register_update_file(self):
        config = self.config_manager.load_config()
        version_dir = config["version_dir"]

        file_path, _ = QFileDialog.getOpenFileName(
            self, "신규 업데이트 파일 선택", self.last_selected_dir, 
            "업데이트 파일 (*.zip *.exe);;ZIP 파일 (*.zip);;실행 파일 (*.exe);;모든 파일 (*.*)"
        )
        if not file_path:
            return

        self.last_selected_dir = os.path.dirname(file_path)
        sync_manager = self.get_sync_manager()
        target_file_for_register = file_path
        detected_version = "0.0.0"

        if file_path.lower().endswith(".exe"):
            raw_ver = extract_version_from_exe(file_path)
            match = re.search(r"v?(\d+\.\d+\.\d+)", raw_ver)
            if match:
                detected_version = match.group(1)
            else:
                input_ver, ok = QInputDialog.getText(self, "버전 입력", "버전을 입력하세요 (예: 1.3.0):")
                if ok and input_ver.strip():
                    clean_match = re.search(r"v?(\d+\.\d+\.\d+)", input_ver.strip())
                    if clean_match:
                        detected_version = clean_match.group(1)

            if detected_version == "0.0.0":
                QMessageBox.critical(self, "오류", "유효한 버전을 감지하지 못했습니다.")
                return

            reply = QMessageBox.question(
                self, "ZIP 패키징 안내",
                f"감지된 버전: v{detected_version}\n.zip 파일로 자동 압축하여 등록하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.makedirs(version_dir, exist_ok=True)
                temp_zip_name = os.path.join(version_dir, f"update_v{detected_version}.zip")
                with zipfile.ZipFile(temp_zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(file_path, arcname=os.path.basename(file_path))
                target_file_for_register = temp_zip_name
            else:
                return
        else:
            filename = os.path.basename(file_path)
            match = re.search(r"v?(\d+\.\d+\.\d+)", filename)
            if match:
                detected_version = match.group(1)
            else:
                input_ver, ok = QInputDialog.getText(self, "버전 입력", "버전을 입력하세요 (예: 1.3.0):")
                if ok and input_ver.strip():
                    clean_match = re.search(r"v?(\d+\.\d+\.\d+)", input_ver.strip())
                    if clean_match:
                        detected_version = clean_match.group(1)

        if detected_version == "0.0.0":
            QMessageBox.critical(self, "오류", "유효한 버전을 확인할 수 없습니다.")
            return

        reply = QMessageBox.question(
            self, "신규 업로드 확인",
            f"버전 v{detected_version} 파일을 로컬 등록하고 큐에 넣어 GitHub에 업로드하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.makedirs(version_dir, exist_ok=True)
                dest_path = os.path.join(version_dir, f"update_v{detected_version}.zip")
                if os.path.abspath(target_file_for_register) != os.path.abspath(dest_path):
                    shutil.copy2(target_file_for_register, dest_path)
                
                item_info = {"version": detected_version, "local_path": dest_path, "name": os.path.basename(dest_path)}
                self.upload_progress_dialog.init_tasks([item_info])
                self._update_dialog_title_and_total("신규 업로드", [item_info])
                self.upload_progress_dialog.show()
                self.upload_progress_dialog.raise_()
                
                if config["github_token"]:
                    self.enqueue_upload_task(sync_manager, item_info)
                else:
                    sync_manager.update_local_version_json(detected_version, dest_path)
                    QMessageBox.warning(self, "알림", "토큰이 없어 로컬에만 등록되었습니다.")
                self.handle_remote_version_check()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"등록 중 예외 발생: {e}")


    def handle_inject_version_and_upload(self):
        config = self.config_manager.load_config()
        version_dir = config["version_dir"]

        file_path, _ = QFileDialog.getOpenFileName(
            self, "업데이트 패키지 선택", self.last_selected_dir, "Update Packages (*.zip *.exe)"
        )
        if not file_path:
            return
            
        self.last_selected_dir = os.path.dirname(file_path)
        version_str, ok = QInputDialog.getText(
            self, "버전 주입 및 업로드", "업로드할 버전을 입력하세요 (예: 1.2.1):", QLineEdit.Normal, "1.2.1"
        )
        
        if not ok or not version_str.strip():
            return
            
        version_str = version_str.strip().lstrip('v')

        reply = QMessageBox.question(
            self, "신규 버전 주입 업로드 확인",
            f"입력한 버전 v{version_str}를 실행파일에 주입하고 압축하여 GitHub에 업로드하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            os.makedirs(version_dir, exist_ok=True)
            dest_path = os.path.join(version_dir, f"update_v{version_str}.zip")
            
            target_exe_path = None
            
            # 1. 파일 형식별 버전 암호화 주입 수행
            if file_path.lower().endswith('.exe'):
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    temp_exe = os.path.join(tmpdir, os.path.basename(file_path))
                    shutil.copy2(file_path, temp_exe)
                    
                    # 실행파일에 버전 토큰 암호화 주입
                    encrypt_and_append_version(temp_exe, f"v{version_str}")
                    target_exe_path = temp_exe
                    
                    with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.write(temp_exe, arcname=os.path.basename(file_path))
            elif file_path.lower().endswith('.zip'):
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.extractall(tmpdir)
                    
                    exe_found = None
                    for root, dirs, files in os.walk(tmpdir):
                        for f in files:
                            if f.lower().endswith('.exe'):
                                exe_found = os.path.join(root, f)
                                break
                        if exe_found:
                            break
                            
                    if exe_found:
                        encrypt_and_append_version(exe_found, f"v{version_str}")
                        target_exe_path = exe_found
                    else:
                        QMessageBox.warning(self, "경고", "ZIP 파일 내에 .exe 실행파일이 존재하지 않습니다.")
                        return
                        
                    with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for root, dirs, files in os.walk(tmpdir):
                            for f in files:
                                abs_f = os.path.join(root, f)
                                arc_name = os.path.relpath(abs_f, tmpdir)
                                zf.write(abs_f, arcname=arc_name)
            else:
                QMessageBox.critical(self, "오류", "지원하지 않는 파일 형식입니다.")
                return

            # 2. 🔍 주입 후 즉시 검증 (Verification) 수행
            if target_exe_path and os.path.exists(target_exe_path):
                extracted_raw_ver = extract_version_from_exe(target_exe_path)
                match = re.search(r"v?(\d+\.\d+\.\d+)", extracted_raw_ver)
                extracted_ver = match.group(1) if match else ""
                
                if extracted_ver != version_str:
                    QMessageBox.critical(
                        self, "검증 실패", 
                        f"❌ 버전 주입 검증 실패!\n\n입력한 버전: v{version_str}\n추출된 버전: {extracted_raw_ver}\n\n주입된 토큰이 일치하지 않습니다."
                    )
                    return
                else:
                    logd(f"✅ [주입 검증 성공] 실행파일 내부 버전이 v{extracted_ver}로 완벽히 확인되었습니다.")

            # 3. 업로드 큐 등록 및 진행
            sync_manager = self.get_sync_manager()
            item_info = {"version": version_str, "local_path": dest_path, "name": os.path.basename(dest_path)}
            self.upload_progress_dialog.init_tasks([item_info])
            self._update_dialog_title_and_total("버전 주입 및 업로드", [item_info])
            self.upload_progress_dialog.show()
            self.upload_progress_dialog.raise_()

            if config["github_token"]:
                self.enqueue_upload_task(sync_manager, item_info)
            else:
                sync_manager.update_local_version_json(version_str, dest_path)
                QMessageBox.warning(self, "알림", "토큰이 없어 로컬에만 등록되었습니다.")
            self.handle_remote_version_check()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"주입 및 등록 중 예외 발생: {e}")

    def handle_force_inject_queue(self):
        selected_items = self.get_checked_items()
        if not selected_items:
            QMessageBox.warning(self, "경고", "버전을 강제주입할 대상 로컬 파일(체크박스)을 선택해주세요.")
            return

        task_items = [
            {
                "version": item["version"],
                "local_path": item["local_path"],
                "name": os.path.basename(item["local_path"])
            }
            for item in selected_items
            if item.get("local_path") and os.path.exists(item["local_path"])
        ]

        if not task_items:
            QMessageBox.warning(self, "경고", "선택된 항목 중 유효한 로컬 파일이 없습니다.")
            return

        self.last_injected_versions = [item["version"] for item in task_items]

        reply = QMessageBox.question(
            self, "로컬 버전 강제주입 큐 실행 확인",
            f"선택된 {len(task_items)}개의 로컬 파일에 대해 버전 강제주입 큐 작업을 시작하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        sync_manager = self.get_sync_manager()

        self.upload_progress_dialog.init_tasks(task_items)
        self._update_dialog_title_and_total("로컬 버전 강제주입", task_items)
        self.upload_progress_dialog.show()
        self.upload_progress_dialog.raise_()

        for item in task_items:
            self.enqueue_force_inject_task(sync_manager, item)


    def enqueue_force_inject_task(self, sync_manager, item):
        ver = item["version"]
        path = item["local_path"]
        task_key = f"{self.window_id}_FORCE_INJECT_LOCAL_{ver}"
        self.active_task_keys.append(task_key)

        def task_func(progress_cb=None, cancel_event=None):
            def report(pct, msg):
                if progress_cb:
                    progress_cb(pct, msg)

            if cancel_event and cancel_event.is_set():
                raise InterruptedError("작업이 취소되었습니다.")

            report(20, f"v{ver} 로컬 파일 버전 강제주입 분석 중...")

            is_zip = path.lower().endswith('.zip')
            extracted_dir = None
            target_exe_path = None

            try:
                if is_zip:
                    import tempfile
                    extracted_dir = tempfile.mkdtemp()
                    with zipfile.ZipFile(path, 'r') as zf:
                        zf.extractall(extracted_dir)
                    
                    for root, dirs, files in os.walk(extracted_dir):
                        for f in files:
                            if f.lower().endswith('.exe'):
                                target_exe_path = os.path.join(root, f)
                                break
                        if target_exe_path:
                            break

                    if not target_exe_path:
                        raise FileNotFoundError("ZIP 파일 내에 .exe 실행파일이 존재하지 않습니다.")

                    report(50, f"v{ver} ZIP 내부 실행파일 버전 강제 주입 중...")
                    encrypt_and_append_version(target_exe_path, f"v{ver}")
                    
                    # 🔍 주입 직후 내부 실행파일 검증
                    extracted_raw_ver = extract_version_from_exe(target_exe_path)
                    if f"v{ver}" not in extracted_raw_ver and ver not in extracted_raw_ver:
                        raise ValueError(f"버전 주입 검증 실패: 예상(v{ver}), 추출된 버전({extracted_raw_ver})")

                    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for root, dirs, files in os.walk(extracted_dir):
                            for f in files:
                                abs_f = os.path.join(root, f)
                                arc_name = os.path.relpath(abs_f, extracted_dir)
                                zf.write(abs_f, arcname=arc_name)

                elif path.lower().endswith('.exe'):
                    report(50, f"v{ver} 실행파일 버전 강제 주입 중...")
                    encrypt_and_append_version(path, f"v{ver}")
                    target_exe_path = path

                    # 🔍 주입 직후 실행파일 검증
                    extracted_raw_ver = extract_version_from_exe(target_exe_path)
                    if f"v{ver}" not in extracted_raw_ver and ver not in extracted_raw_ver:
                        raise ValueError(f"버전 주입 검증 실패: 예상(v{ver}), 추출된 버전({extracted_raw_ver})")

                report(80, f"v{ver} 로컬 version.json 반영 중...")
                sync_manager.update_local_version_json(ver, path)
                logd(f"✅ [강제주입 성공 및 검증 완료] 버전 v{ver} (대상: {os.path.basename(path)})")

            finally:
                if extracted_dir and os.path.exists(extracted_dir):
                    shutil.rmtree(extracted_dir, ignore_errors=True)

            report(100, f"v{ver} 로컬 버전 강제주입이 완료되었습니다.")
            return True

        TaskManager().enqueue(
            TaskPriority.HIGH,
            task_key,
            self.window_id,
            f"로컬 버전 v{ver} 강제주입",
            task_func
        )

    def upload_selected_versions(self):
        selected = self.get_checked_items()
        if not selected:
            QMessageBox.warning(self, "경고", "업로드할 버전을 선택해주세요.")
            return
        config = self.config_manager.load_config()
        if not config["github_token"]:
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return
            
        sync_manager = self.get_sync_manager()
        task_items = [{"version": item["version"], "local_path": item["local_path"], "name": os.path.basename(item["local_path"]) if item["local_path"] else ""} for item in selected]
        
        self.upload_progress_dialog.init_tasks(task_items)
        self._update_dialog_title_and_total("원격 GitHub 업로드", task_items)
        self.upload_progress_dialog.show()
        self.upload_progress_dialog.raise_()
        
        for item in task_items:
            self.enqueue_upload_task(sync_manager, item)

    def download_selected_versions(self):
        selected = self.get_checked_items()
        if not selected:
            QMessageBox.warning(self, "경고", "다운로드할 버전을 선택해주세요.")
            return
        config = self.config_manager.load_config()
        if not config["github_token"]:
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return
            
        sync_manager = self.get_sync_manager()
        task_items = [{"version": item["version"], "github_info": item["github_info"], "name": item["github_info"].get("name", "") if item["github_info"] else ""} for item in selected]
        
        self.upload_progress_dialog.init_tasks(task_items)
        self._update_dialog_title_and_total("로컬 다운로드", task_items)
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

            def check_cancel():
                return cancel_event and cancel_event.is_set()

            success, err_msg = sync_manager.upload_to_github_with_progress(
                ver, path, progress_callback=cb, cancel_check=check_cancel
            )
            if not success:
                raise Exception(err_msg)
            return success

        TaskManager().enqueue(TaskPriority.NORMAL, task_key, self.window_id, f"버전 v{ver} 업로드", task_func)

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

            def check_cancel():
                return cancel_event and cancel_event.is_set()

            success, err_msg = sync_manager.download_from_github_with_progress(
                ver, download_url, progress_callback=cb, cancel_check=check_cancel
            )
            if not success:
                raise Exception(err_msg)
            return success

        TaskManager().enqueue(TaskPriority.NORMAL, task_key, self.window_id, f"버전 v{ver} 다운로드", task_func)

    def get_checked_items(self) -> list:
        checked_items = []
        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 1)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                if row < len(self.current_sync_data):
                    checked_items.append(self.current_sync_data[row])
        return checked_items

    def _update_dialog_title_and_total(self, title_suffix: str, items: list):
        self.upload_progress_dialog.setWindowTitle(f"작업 진행 상황 ({title_suffix})")
        self._batch_progress_map = {item["version"]: 0 for item in items}
        self.upload_progress_dialog.update_total_progress(0, f"[{title_suffix}] 작업 준비 중...")

    def _report_item_and_total_progress(self, ver: str, pct: int, status_text: str, msg: str):
        self.upload_progress_dialog.update_item_progress(ver, pct, status_text, msg)
        if hasattr(self, "_batch_progress_map") and ver in self._batch_progress_map:
            self._batch_progress_map[ver] = pct
            total_count = len(self._batch_progress_map)
            if total_count > 0:
                total_pct = int(sum(self._batch_progress_map.values()) / total_count)
                self.upload_progress_dialog.update_total_progress(total_pct)

    def on_task_progress(self, task_name, percent, message):
        for ver in getattr(self, "_batch_progress_map", {}):
            if ver in task_name or f"v{ver}" in task_name:
                status_str = "완료" if percent == 100 else "진행 중"
                self._report_item_and_total_progress(ver, percent, status_str, message)
                break

    def on_task_finished(self, task_name, status, data):
        self.progress_bar.hide()
        self.btn_sync_check.setEnabled(True)
        self.btn_check_local_versions.setEnabled(True)

        if status == "SUCCESS":
            for ver in getattr(self, "_batch_progress_map", {}):
                if ver in task_name or f"v{ver}" in task_name:
                    self._report_item_and_total_progress(ver, 100, "완료", f"v{ver} 작업 완료")

            if ("로컬버전 체크" in task_name or "원격버전 체크" in task_name) and isinstance(data, list):
                self.apply_sync_table_data(data)
                pass
                # if "로컬버전 체크" in task_name:
                #     QMessageBox.information(self, "완료", "✅ 로컬버전 체크가 완료되었습니다.")
                # elif "원격버전 체크" in task_name:
                #     QMessageBox.information(self, "완료", "✅ 원격버전 체크가 완료되었습니다.")
            elif "원격 version.json 조회" in task_name and isinstance(data, dict):
                content = data.get("content")
                sha = data.get("sha")
                self.cached_remote_sha = sha
                self.txt_remote_content.setPlainText(f"--- [SHA 값]: {sha} ---\n\n{content}")
                logd("조회 성공 : 원격 version.json 조회가 완료되었습니다.")
            elif "원격 version.json 강제 수정" in task_name:
                logd("수정 성공 : 원격 version.json이 강제 갱신되었습니다.")
                self.fetch_remote_json_action()
            elif "원격 version.json 자동 정렬" in task_name:
                self.btn_auto_sync_json.setEnabled(True)
                logd("동기화 성공 : ✅ 실제 최신 릴리스에 맞게 원격 version.json이 자동 정렬되었습니다.")
                self.handle_remote_version_check()
            elif "강제주입" in task_name:
                self.handle_local_version_check()
                pass
                # self.handle_remote_version_check()
        elif status != "CANCELLED":
            if "자동 정렬" in task_name:
                self.btn_auto_sync_json.setEnabled(True)
            else:
                QMessageBox.critical(self, "작업 오류", f"작업 실패:\n{data}")

    def on_queue_updated(self, task_names):
        pass

    def on_current_task_changed(self, owner_id, task_name):
        pass

    def apply_sync_table_data(self, result: list):
        # [요청 반영] 버전이 큰 버전이 위로 오도록 내림차순 정렬 (SemVer 기준)
        try:
            result = sorted(
                result, 
                key=lambda x: version.parse(x.get('version', '0.0.0')), 
                reverse=True
            )
        except Exception as e:
            loge(f"버전 정렬 중 오류 발생: {e}")

        self.current_sync_data = result
        self.table.setRowCount(len(result))
        
        target_checked = getattr(self, "last_injected_versions", [])

        for row, stat in enumerate(result):
            # 0: 순서
            seq_item = QTableWidgetItem(str(row + 1))
            seq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            seq_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, seq_item)

            # 1: 선택 체크박스
            chk_item = QTableWidgetItem()
            has_local_file = stat.get('in_local', False) and stat.get('local_path') and os.path.exists(stat['local_path'])
            if has_local_file:
                chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
            else:
                chk_item.setFlags(Qt.ItemFlag.NoItemFlags)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                chk_item.setForeground(QBrush(QColor("gray")))
            self.table.setItem(row, 1, chk_item)
            
            # 2: Local 버전
            ver_text = f"v{stat['version']}"
            ver_item = QTableWidgetItem(ver_text)
            if stat.get("version_mismatch"):
                inner_v = stat.get("inner_version", "알 수 없음")
                ver_item.setText(f"⚠️ {ver_text} (내부: v{inner_v})")
                ver_item.setForeground(QBrush(QColor("#F44747")))
            self.table.setItem(row, 2, ver_item)
            
            # 3: 싱크 상태
            status_text = stat['sync_status']
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QBrush(QColor("green" if stat['sync_status'] == "SYNCED" else "orange")))
            self.table.setItem(row, 3, status_item)
            
            # 4: 로컬/GitHub 유무
            loc_s = 'O' if has_local_file else 'X'
            rel_s = 'O' if stat['has_release'] else 'X'
            zip_s = 'O' if stat['has_zip'] else 'X'
            tag_s = 'O' if stat['has_tag'] else 'X'
            detail_str = f"Local: {loc_s} / Release: {rel_s} / ZIP: {zip_s} / Tag: {tag_s}"
            self.table.setItem(row, 4, QTableWidgetItem(detail_str))

            # 5: 🌐 GitHub 버전 컬럼 추가 배치
            gh_ver_text = stat.get("github_version", "-")
            gh_ver_item = QTableWidgetItem(gh_ver_text)
            gh_ver_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if gh_ver_text != "-":
                gh_ver_item.setForeground(QBrush(QColor("#569CD6")))
            else:
                gh_ver_item.setForeground(QBrush(QColor("gray")))
            self.table.setItem(row, 5, gh_ver_item)
            
            # 6: 원격 릴리스 관리 버튼
            if stat['has_release'] or stat['has_tag']:
                btn_del_remote = QPushButton("🗑️ 원격 릴리스/태그 제거")
                btn_del_remote.setStyleSheet("color: #F44747; font-weight: bold;")
                btn_del_remote.clicked.connect(lambda checked=False, v=stat['version']: self.delete_remote_release_action(v))
                self.table.setCellWidget(row, 6, btn_del_remote)
            else:
                lbl_none = QLabel("-")
                lbl_none.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setCellWidget(row, 6, lbl_none)

        if hasattr(self, "last_injected_versions"):
            delattr(self, "last_injected_versions")