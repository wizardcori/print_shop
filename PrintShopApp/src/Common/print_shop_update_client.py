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

from Protocol.update_service_protocol import (
    DEFAULT_PORT, UpdateClientToUpdateServicePacketBuilder,
    parse_server_response, ResponseCode
)

class UpdateClient:
    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, heartbeat_interval=10):
        self.host = host
        self.port = port
        self.heartbeat_interval = heartbeat_interval
        self._running = False
        self._heartbeat_thread = None
        
        self._counter = 0
        
        # 패킷 빌더 초기화 (UpdateClient -> UpdateService)
        self.packet_builder = UpdateClientToUpdateServicePacketBuilder()

    def info(self, stage: str, details: str):
        print(f"📌 [UpdateManager Info] Stage: {stage} | Details: {details}")

    def start_heartbeat(self):
        if self._running: return
        self._running = True
        self._counter = 0
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self):
        while self._running:
            current_time_val = int(time.time())
            # 패킷 빌더 활용한 하트비트 패킷 생성 및 인코딩
            pkt = self.packet_builder.req_heartbeat(self._counter, current_time_val)
            self._send_udp_packet(pkt, timeout=1.0)
            
            self._counter += 10
            time.sleep(self.heartbeat_interval)

    def _send_udp_packet(self, pkt, timeout=3.0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                s.sendto(pkt.encode(), (self.host, self.port))
                data, _ = s.recvfrom(4096)
                is_valid, res_pkt, err = parse_server_response(data)
                if is_valid and res_pkt:
                    return res_pkt
        except Exception:
            pass
        return None

    def _send_raw_command(self, pkt, timeout=3.0) -> str:
        res_pkt = self._send_udp_packet(pkt, timeout=timeout)
        if res_pkt:
            return res_pkt.to_str(True, True)
        return ""

    def get_detailed_status(self) -> dict:
        pkt = self.packet_builder.req_get_status()
        res_pkt = self._send_udp_packet(pkt, timeout=2.0)
        if res_pkt and res_pkt.payload:
            try: return json.loads(res_pkt.payload)
            except Exception: pass
        return {"phase": "UNKNOWN", "progress": 0, "message": "대기 중..."}

    def get_service_paths(self) -> dict:
        pkt = self.packet_builder.req_get_paths()
        res_pkt = self._send_udp_packet(pkt, timeout=2.0)
        if res_pkt and res_pkt.payload:
            try: return json.loads(res_pkt.payload)
            except Exception: pass
        return {}    

    def get_heartbeat_status(self) -> dict:
        pkt = self.packet_builder.req_get_heartbeat()
        res_pkt = self._send_udp_packet(pkt, timeout=2.0)
        if res_pkt and res_pkt.payload:
            try: return json.loads(res_pkt.payload)
            except Exception: pass
        return {}

    def send_config_and_test_download(self, repo_url: str, json_url: str) -> bool:
        pkt = self.packet_builder.req_config_and_test(repo_url, json_url)
        res_pkt = self._send_udp_packet(pkt, timeout=5.0)
        if res_pkt:
            # res_ok payload가 TEST_SUCCESS이거나 payload가 비어있지 않은 경우 체크
            return res_pkt.payload == ResponseCode.to_str(ResponseCode.TEST_SUCCESS) or res_pkt.payload == str(ResponseCode.TEST_SUCCESS)
        return False

    def request_apply_update(self, target_version: str = "", self_shutdown: bool = True) -> bool:
        pkt = self.packet_builder.req_apply_update(target_version, self_shutdown)
        res_pkt = self._send_udp_packet(pkt, timeout=5.0)
        return res_pkt is not None

    def request_rollback(self, target_version: str, self_shutdown: bool = True) -> bool:
        pkt = self.packet_builder.req_rollback(target_version, self_shutdown)
        res_pkt = self._send_udp_packet(pkt, timeout=5.0)
        return res_pkt is not None

    def request_set_restart_function(self, enabled: bool) -> bool:
        pkt = self.packet_builder.req_set_restart_function(enabled)
        res_pkt = self._send_udp_packet(pkt, timeout=2.0)
        return res_pkt is not None

    def request_get_restart_function(self) -> bool:
        pkt = self.packet_builder.req_get_restart_function()
        res_pkt = self._send_udp_packet(pkt, timeout=2.0)
        if res_pkt and res_pkt.payload:
            return res_pkt.payload in ("1", "true", "True")
        return True

    def get_available_versions(self) -> list:
        pkt = self.packet_builder.req_get_versions()
        res_pkt = self._send_udp_packet(pkt, timeout=3.0)
        if res_pkt and res_pkt.payload:
            try: return json.loads(res_pkt.payload)
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
            self.steps_data[3]["pass"] = release_ok
        except Exception:
            self.steps_data[3]["pass"] = False

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


updater_client = UpdateClient(port=DEFAULT_PORT)
updater_client.start_heartbeat()