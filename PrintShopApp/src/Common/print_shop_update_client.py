# 메인 애플리케이션 및 어시스트 다이얼로그 (print_shop_update_manager.py)
import socket
import threading
import time
import json
import sys
import requests
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QListWidget, QPushButton, QMessageBox, QProgressBar, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush

class UpdateClient:
    def __init__(self, host="127.0.0.1", port=54321, heartbeat_interval=10):
        self.host = host
        self.port = port
        self.heartbeat_interval = heartbeat_interval
        self._running = False
        self._heartbeat_thread = None
        
        # 💡 [HEARTBEAT 전송용 카운터 및 시간 변수]
        self._counter = 0

    def info(self, stage: str, details: str):
        print(f"📌 [UpdateManager Info] Stage: {stage} | Details: {details}")

    def start_heartbeat(self):
        if self._running: return
        self._running = True
        self._counter = 0  # 시작 시 0으로 초기화
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self):
        while self._running:
            # 💡 메인앱 시작 시점부터 0으로 초기화되어 10씩 증가하는 카운터 및 4바이트 시간 변수(타임스탬프 등) 생성
            current_time_val = int(time.time())
            packet_msg = f"HEARTBEAT:{self._counter}:{current_time_val}"
            
            self._send_udp(packet_msg, timeout=1.0)
            
            # 다음 전송을 위해 10 증가 (최대값 한계 도달 시 관리 또는 무한 증가)
            self._counter += 10
            
            time.sleep(self.heartbeat_interval)

    def _send_udp(self, command: str, timeout=3.0) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                s.sendto(command.encode('utf-8'), (self.host, self.port))
                data, _ = s.recvfrom(4096)
                return data.decode('utf-8')
        except Exception:
            return ""

    def get_detailed_status(self) -> dict:
        res = self._send_udp("GET_STATUS", timeout=2.0)
        if res.startswith("OK:"):
            try: return json.loads(res.split("OK:", 1)[1])
            except Exception: pass
        return {"phase": "UNKNOWN", "progress": 0, "message": "대기 중..."}

    def get_service_paths(self) -> dict:
        """업데이터 서비스에 UDP로 경로 정보 요청"""
        try:
            res = self._send_udp("GET_PATHS", timeout=2.0)
            if res.startswith("OK:"):
                return json.loads(res.split("OK:", 1)[1])
        except Exception:
            pass
        return {}    

    def get_heartbeat_status(self) -> dict:
        """업데이터 서비스에 하트비트 통계 상태 조회 (GET_HEARTBEAT, 5초 쿨다운)"""
        try:
            res = self._send_udp("GET_HEARTBEAT", timeout=2.0)
            if res.startswith("OK:"):
                return json.loads(res.split("OK:", 1)[1])
        except Exception:
            pass
        return {}

    def send_config_and_test_download(self, repo_url: str, json_url: str) -> bool:
        config_data = {"repo_url": repo_url, "json_url": json_url}
        res = self._send_udp(f"CONFIG_AND_TEST:{json.dumps(config_data)}", timeout=5.0)
        return res == "OK:TEST_SUCCESS"

    def request_apply_update(self, self_shutdown: bool = True) -> bool:
        return self._send_udp(f"APPLY_UPDATE:{'SELF' if self_shutdown else 'SERVICE'}", timeout=5.0) == "OK"

    def request_rollback(self, target_version: str, self_shutdown: bool = True) -> bool:
        return self._send_udp(f"ROLLBACK:{target_version}:{'SELF' if self_shutdown else 'SERVICE'}", timeout=5.0) == "OK"

    def get_available_versions(self) -> list:
        res = self._send_udp("GET_VERSIONS", timeout=3.0)
        if res.startswith("OK:"):
            try: return json.loads(res.split("OK:", 1)[1])
            except Exception: pass
        return []

    def show_github_assist_dialog(self, parent=None):
        dialog = GitHubAssistModelessDialog(self, parent)
        dialog.show()


class GitHubAssistModelessDialog(QDialog):
    def __init__(self, update_client: UpdateClient, parent=None):
        super().__init__(parent)
        self.update_client = update_client
        self.setWindowTitle("GitHub 업데이트 저장소 구축 어시스트")
        self.resize(650, 600)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>[단계별 가이드]</b> GitHub 계정과 저장소 이름만 입력하면 자동으로 링크를 조합하여 검증합니다."))
        
        # 1. 입력 필드 레이아웃 (계정명, 저장소명 분리 입력)
        input_layout = QHBoxLayout()
        
        self.user_input = QLineEdit(self)
        self.user_input.setPlaceholderText("GitHub 계정명 (예: wizardcori)")
        self.user_input.setText("wizardcori")
        input_layout.addWidget(QLabel("계정:"))
        input_layout.addWidget(self.user_input)
        
        self.repo_input = QLineEdit(self)
        self.repo_input.setPlaceholderText("저장소 이름 (예: printshop_update)")
        self.repo_input.setText("printshop_update")
        input_layout.addWidget(QLabel("저장소:"))
        input_layout.addWidget(self.repo_input)
        
        layout.addLayout(input_layout)
        
        # 2. 상태 테이블
        self.table = QTableWidget(self)
        self.table.setRowCount(4)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["단계", "작업 내용 및 가이드", "상태 (Pass/Fail)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        self.steps_data = [
            {"title": "1. GitHub 계정", "desc": "GitHub 공식 홈페이지 가입 및 프로필 확인", "pass": False},
            {"title": "2. Public 리포지토리", "desc": "공개(Public) 리포지토리 생성 및 접속 확인", "pass": False},
            {"title": "3. version.json 업로드", "desc": "저장소 내 version.json 파일 존재 및 구조 확인", "pass": False},
            {"title": "4. 빌드 .zip 파일 업로드", "desc": "Releases에 최신 빌드 .zip 파일 등록 확인", "pass": False}
        ]
        self.populate_table()
        layout.addWidget(self.table)
        
        # 3. 버튼 영역
        btn_layout = QHBoxLayout()
        self.btn_recheck = QPushButton("모든 단계 자동 재점검 (Re-check)", self)
        self.btn_recheck.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.btn_recheck.clicked.connect(self.run_recheck)
        btn_layout.addWidget(self.btn_recheck)
        
        self.btn_submit_test = QPushButton("업데이터 전송 및 다운로드 테스트", self)
        self.btn_submit_test.setEnabled(False)
        self.btn_submit_test.clicked.connect(self.run_download_test)
        btn_layout.addWidget(self.btn_submit_test)
        layout.addLayout(btn_layout)
        
        self.result_label = QLabel("", self)
        layout.addWidget(self.result_label)

    def populate_table(self):
        for row, step in enumerate(self.steps_data):
            self.table.setItem(row, 0, QTableWidgetItem(step["title"]))
            self.table.setItem(row, 1, QTableWidgetItem(step["desc"]))
            item_status = QTableWidgetItem("🟢 PASS" if step["pass"] else "🔴 FAIL")
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setForeground(QBrush(QColor("green" if step["pass"] else "red")))
            self.table.setItem(row, 2, item_status)

    def run_recheck(self):
        username = self.user_input.text().strip()
        repo = self.repo_input.text().strip()
        
        if not username or not repo:
            QMessageBox.warning(self, "경고", "GitHub 계정명과 저장소 이름을 모두 입력해주세요.")
            return

        try:
            user_res = requests.get(f"https://api.github.com/users/{username}", timeout=3)
            self.steps_data[0]["pass"] = (user_res.status_code == 200)
        except Exception:
            self.steps_data[0]["pass"] = False

        try:
            repo_res = requests.get(f"https://api.github.com/repos/{username}/{repo}", timeout=3)
            self.steps_data[1]["pass"] = (repo_res.status_code == 200)
        except Exception:
            self.steps_data[1]["pass"] = False

        json_found = False
        valid_json_url = ""
        for branch in ["main", "master"]:
            test_url = f"https://raw.githubusercontent.com/{username}/{repo}/{branch}/version.json"
            try:
                res = requests.get(test_url, timeout=3)
                if res.status_code == 200:
                    data = res.json()
                    if "version" in data and "download_url" in data:
                        json_found = True
                        valid_json_url = test_url
                        break
            except Exception:
                continue
        
        self.steps_data[2]["pass"] = json_found
        self.stored_json_url = valid_json_url

        release_ok = False
        try:
            releases_res = requests.get(f"https://api.github.com/repos/{username}/{repo}/releases/latest", timeout=3)
            if releases_res.status_code == 200:
                release_data = releases_res.json()
                assets = release_data.get("assets", [])
                if any(asset.get("name", "").endswith(".zip") for asset in assets):
                    release_ok = True
        except Exception:
            pass
        
        self.steps_data[3]["pass"] = release_ok

        self.populate_table()
        
        if all(step["pass"] for step in self.steps_data):
            self.btn_submit_test.setEnabled(True)
            self.result_label.setText(f"✨ 모든 검증 통과! [URL: {self.stored_json_url}]")
            self.result_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.btn_submit_test.setEnabled(False)
            self.result_label.setText("⚠️ 일부 단계가 충족되지 않았습니다. 가이드를 확인하세요.")
            self.result_label.setStyleSheet("color: red;")

    def run_download_test(self):
        if hasattr(self, 'stored_json_url') and self.stored_json_url:
            if self.update_client.send_config_and_test_download(repo_url=self.stored_json_url, json_url=self.stored_json_url):
                QMessageBox.information(self, "성공", "✅ 업데이터 서비스가 다운로드 테스트를 성공적으로 통과했습니다!")
                self.close()
            else:
                QMessageBox.critical(self, "실패", "❌ 업데이터 서비스의 다운로드 테스트 중 오류가 발생했습니다.")
        else:
            QMessageBox.warning(self, "경고", "먼저 모든 단계 재점검을 완료해주세요.")


updater_client = UpdateClient(port=54321)
updater_client.start_heartbeat()
