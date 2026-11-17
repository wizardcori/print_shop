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
    │   ├── update_queue_worker.py           # 큐 기반 비동기 워커 모듈
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
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QFileDialog, QInputDialog, QProgressBar, QTabWidget, 
    QWidget, QTextEdit
)
from PySide6.QtCore import Qt
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
from UpdateManager.um_work_queue import UpdateManagerWorkQueue
from github_config_manager import GitHubConfigManager, DEF_LOCAL_VERSION_DIR
from github_update_sync_manager import GitHubUpdateSyncManager
from UpdateManager.update_manager_settings_dialog import UpdateManagerSettingsDialog
from Common.Version.exe_version_crypto import extract_version_from_exe


class GitHubSettingsDialog(QDialog):
    """메인 UI 다이얼로그 (분리된 모듈 및 큐 시스템 연동)"""
    def __init__(self, config_manager: GitHubConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("GitHub 및 업데이트 시스템 통합 매니저 (Queue)")
        self.resize(850, 700)
        logd("GitHubSettingsDialog 메인 UI 초기화 시작")
        
        self.worker = None
        self.current_sync_data = []
        self.cached_remote_sha = None
        
        self.upload_progress_dialog = UploadProgressDialog(self)
        self.upload_progress_dialog.cancel_all_signal.connect(self.on_cancel_all)
        self.upload_progress_dialog.cancel_item_signal.connect(self.on_cancel_item)
        
        main_layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget(self)
        main_layout.addWidget(self.tabs)
        
        self.tab_sync = QWidget()
        self.init_sync_tab(self.tab_sync)
        self.tabs.addTab(self.tab_sync, "🚀 버전 싱크 및 배포 관리")
        
        self.tab_remote_json = QWidget()
        self.init_remote_json_tab(self.tab_remote_json)
        self.tabs.addTab(self.tab_remote_json, "🔍 원격 version.json 검증/수정")

    def init_sync_tab(self, tab: QWidget):
        layout = QVBoxLayout(tab)
        
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(QLabel("<b>[PrintShop 업데이트 관리자 - 큐 시스템]</b>"))
        top_bar_layout.addStretch()
        
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

        # 원격 version.json 자동 동기화 버튼
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

    def open_settings_dialog(self):
        logd("환경 및 로그 설정 다이얼로그 열기")
        dlg = UpdateManagerSettingsDialog(self.config_manager, self)
        if dlg.exec():
            logd("설정 변경 확인됨 -> 싱크 상태 재조회 실행")
            self.check_sync_status_async()

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
        logd("메인 UI: 전체 취소 시그널 수신")
        if self.worker and self.worker.isRunning():
            self.worker.cancel_all()
            self.upload_progress_dialog.update_total_progress(0, "⚠️ 사용자에 의해 전체 큐 작업이 취소되었습니다.")

    def on_cancel_item(self, version_str: str):
        logd(f"메인 UI: 개별 취소 시그널 수신 -> v{version_str}")
        if self.worker and self.worker.isRunning():
            self.worker.cancel_item(version_str)
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
        logd("원격 version.json 조회 액션 시작")
        manager = self.get_sync_manager()
        self.progress_bar.show()
        self.worker = UpdateManagerWorkQueue(manager)
        self.worker.add_task("FETCH_REMOTE_JSON", {})
        self.worker.finished_signal.connect(self.on_background_finished)
        self.worker.error_signal.connect(self.on_background_error)
        self.worker.start()

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
        logd(f"원격 version.json 강제 수정 액션 시작 (목표 버전: {target_ver}, SHA: {self.cached_remote_sha})")
        self.progress_bar.show()
        self.worker = UpdateManagerWorkQueue(manager)
        self.worker.add_task("FORCE_UPDATE_REMOTE_JSON", {"version": target_ver, "sha": self.cached_remote_sha, "url": custom_url})
        self.worker.finished_signal.connect(self.on_background_finished)
        self.worker.error_signal.connect(self.on_background_error)
        self.worker.start()

    def auto_sync_remote_json_action(self):
        logd("원격 version.json 자동 정렬/동기화 액션 시작")
        config = self.config_manager.load_config()
        if not config["github_token"]:
            QMessageBox.warning(self, "경고", "GitHub 토큰이 설정되지 않았습니다.")
            return

        manager = self.get_sync_manager()
        self.progress_bar.show()
        self.btn_auto_sync_json.setEnabled(False)
        
        self.worker = UpdateManagerWorkQueue(manager)
        self.worker.add_task("AUTO_SYNC_JSON", {})
        self.worker.finished_signal.connect(self.on_background_finished)
        self.worker.error_signal.connect(lambda v, err: self.on_background_error("AUTO_SYNC_JSON", err))
        self.worker.start()

    def select_and_register_update_file(self):
        logd("신규 업데이트 파일 선택 다이얼로그 호출")
        config = self.config_manager.load_config()
        version_dir = config["version_dir"]
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "신규 업데이트 파일 선택", os.getcwd(), 
            "업데이트 파일 (*.zip *.exe);;ZIP 파일 (*.zip);;실행 파일 (*.exe);;모든 파일 (*.*)"
        )
        if not file_path:
            logd("파일 선택 취소됨")
            return

        logd(f"선택된 업데이트 파일: {file_path}")
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
                logd(".exe 파일에서 자동 버전 감지 실패 -> 사용자 수동 입력 요청")
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
                logd(".zip 패키지에서 자동 버전 감지 실패 -> 사용자 수동 입력 요청")
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
                    
                    self.worker = UpdateManagerWorkQueue(sync_manager)
                    self.worker.add_task("UPLOAD", item_info)
                    self.worker.progress_signal.connect(self.upload_progress_dialog.update_item_progress)
                    self.worker.total_progress_signal.connect(self.upload_progress_dialog.update_total_progress)
                    self.worker.error_signal.connect(lambda v, err: self.upload_progress_dialog.append_error(v, err))
                    self.worker.finished_signal.connect(self.on_background_finished)
                    self.worker.start()
                else:
                    logd(f"토큰이 없어 로컬 version.json만 업데이트함: v{detected_version}")
                    sync_manager.update_local_version_json(detected_version, dest_path)
                    QMessageBox.warning(self, "알림", "토큰이 없어 로컬에만 등록되었습니다.")
                self.check_sync_status_async()
            except Exception as e:
                loge(f"신규 파일 등록 및 업로드 준비 중 예외 발생: {e}")
                QMessageBox.critical(self, "오류", f"등록 중 예외 발생: {e}")

    def check_sync_status_async(self):
        logd("비동기 버전 싱크 상태 확인 요청 시작")
        config = self.config_manager.load_config()
        sync_manager = self.get_sync_manager()
        self.btn_sync_check.setEnabled(False)
        self.progress_bar.show()
        
        self.worker = UpdateManagerWorkQueue(sync_manager)
        self.worker.add_task("CHECK_SYNC", {"version_dir": config["version_dir"]})
        self.worker.finished_signal.connect(self.on_background_finished)
        self.worker.error_signal.connect(lambda v, err: self.on_background_error("CHECK_SYNC", err))
        self.worker.start()

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
        
        self.worker = UpdateManagerWorkQueue(sync_manager)
        for item in task_items:
            self.worker.add_task("UPLOAD", item)
            
        self.worker.progress_signal.connect(self.upload_progress_dialog.update_item_progress)
        self.worker.total_progress_signal.connect(self.upload_progress_dialog.update_total_progress)
        self.worker.error_signal.connect(lambda v, err: self.upload_progress_dialog.append_error(v, err))
        self.worker.finished_signal.connect(self.on_background_finished)
        self.worker.start()

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
        
        self.worker = UpdateManagerWorkQueue(sync_manager)
        for item in task_items:
            self.worker.add_task("DOWNLOAD", item)
            
        self.worker.progress_signal.connect(self.upload_progress_dialog.update_item_progress)
        self.worker.total_progress_signal.connect(self.upload_progress_dialog.update_total_progress)
        self.worker.error_signal.connect(lambda v, err: self.upload_progress_dialog.append_error(v, err))
        self.worker.finished_signal.connect(self.on_background_finished)
        self.worker.start()

    def get_checked_items(self) -> list:
        checked_items = []
        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                if row < len(self.current_sync_data):
                    checked_items.append(self.current_sync_data[row])
        logd(f"테이블 체크박스 선택 항목 조회: {len(checked_items)}개 선택됨")
        return checked_items

    def on_background_finished(self, task_type: str, result):
        self.progress_bar.hide()
        self.btn_sync_check.setEnabled(True)
        logd(f"백그라운드 작업 완료 시그널 수신: [{task_type}]")

        if task_type == "CHECK_SYNC":
            self.current_sync_data = result
            self.table.setRowCount(len(result))
            for row, stat in enumerate(result):
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(row, 0, chk_item)
                
                self.table.setItem(row, 1, QTableWidgetItem(f"v{stat['version']}"))
                
                status_item = QTableWidgetItem(stat['sync_status'])
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_item.setForeground(QBrush(QColor("green" if stat['sync_status'] == "SYNCED" else "orange")))
                self.table.setItem(row, 2, status_item)
                
                loc_s = 'O' if stat['in_local'] else 'X'
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
                    
        elif task_type == "QUEUE_FINISHED":
            logd(f"큐 배치 작업 완료 안내 (성공 건수: {result}건)")
            self.upload_progress_dialog.update_total_progress(100, "🎉 큐에 담긴 모든 동기화 작업이 완료되었습니다!")
            QMessageBox.information(self, "완료", f"큐 작업이 완료되었습니다! (성공: {result}건)")
            self.check_sync_status_async()

        elif task_type == "FETCH_REMOTE_JSON":
            content = result.get("content")
            sha = result.get("sha")
            self.cached_remote_sha = sha
            logd(f"원격 version.json UI 반영 완료 (SHA: {sha})")
            self.txt_remote_content.setPlainText(f"--- [SHA 값]: {sha} ---\n\n{content}")
            QMessageBox.information(self, "조회 성공", "원격 version.json 조회가 완료되었습니다.")

        elif task_type == "FORCE_UPDATE_REMOTE_JSON":
            if result:
                logd("원격 version.json 강제 수정 성공 확인 -> 재조회 실행")
                QMessageBox.information(self, "수정 성공", "원격 version.json이 강제 갱신되었습니다.")
                self.fetch_remote_json_action()
            else:
                loge("원격 version.json 강제 수정 실패 결과 반환됨")
                QMessageBox.critical(self, "수정 실패", "원격 version.json 강제 갱신 실패")
        
        elif task_type == "AUTO_SYNC_JSON":
            self.progress_bar.hide()
            self.btn_auto_sync_json.setEnabled(True)
            if result:
                logd("원격 version.json 자동 동기화 성공 -> 싱크 상태 재조회 실행")
                QMessageBox.information(self, "동기화 성공", "✅ 실제 최신 릴리스에 맞게 원격 version.json이 자동 정렬되었습니다.")
                self.check_sync_status_async()
            else:
                loge("원격 version.json 자동 동기화 실패 또는 변경 사항 없음")
                QMessageBox.warning(self, "알림", "동기화할 유효한 릴리스가 없거나 이미 일치합니다.")

    def on_background_error(self, task_type: str, error_msg: str):
        self.progress_bar.hide()
        self.btn_sync_check.setEnabled(True)
        loge(f"백그라운드 작업 오류 발생 [{task_type}]: {error_msg}")
        QMessageBox.critical(self, "백그라운드 오류", f"작업({task_type}) 오류:\n{error_msg}")
