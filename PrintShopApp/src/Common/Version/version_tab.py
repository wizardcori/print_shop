# version_tab.py
import os
import sys
import subprocess
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QPushButton, QFormLayout, QMessageBox, QFileDialog, QGridLayout, QTextEdit
)
from PySide6.QtCore import Qt

from Common.settings_registry import register_settings_tab
from .version_manager import vm_inst, VersionManager
from Common.print_shop_update_client import updater_client
# EXE 암호화 버전 추출 유틸리티 임포트
from .exe_version_crypto import get_runtime_decrypted_version, extract_version_from_exe


class VersionTab(QWidget):
    """애플리케이션 및 업데이터 서비스의 버전 정보를 표시하고 관리하는 설정 탭 UI"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_version_managers()
        self.init_ui()
        self.refresh_version_info()

    def _setup_version_managers(self):
        """메인 앱 및 업데이터 서비스의 경로를 탐색하여 VersionManager 설정"""
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
            app_name="print_shop_update_service"
        )

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)

        title_label = QLabel("<h3>Application & Service Version & Update Status</h3>")
        main_layout.addWidget(title_label)

        # ---------------------------------------------------------
        # 1. 메인 애플리케이션 버전 정보 그룹
        # ---------------------------------------------------------
        app_group = QGroupBox("Main Application (PrintShopApp)")
        app_form = QFormLayout()
        app_form.setLabelAlignment(Qt.AlignRight)
        app_form.setVerticalSpacing(8)

        self.lbl_app_name = QLabel("-")
        self.lbl_app_name.setStyleSheet("font-weight: bold; font-size: 11pt;")

        self.lbl_app_version = QLabel("-")
        self.lbl_app_version.setStyleSheet("font-weight: bold; font-size: 12pt; color: #4EC9B0;")

        # EXE EOF 암호화 무결성 버전 라벨
        self.lbl_app_eof_version = QLabel("-")
        self.lbl_app_eof_version.setStyleSheet("font-weight: bold; font-size: 10pt; color: #DCDCAA;")

        self.lbl_app_path = QLabel("-")
        self.lbl_app_path.setStyleSheet("color: #858585; font-size: 9pt;")
        self.lbl_app_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        app_form.addRow("프로그램명 (Name):", self.lbl_app_name)
        app_form.addRow("현재 버전 (File):", self.lbl_app_version)
        app_form.addRow("바이너리 무결성 버전 (EOF):", self.lbl_app_eof_version)
        app_form.addRow("버전 파일 경로:", self.lbl_app_path)

        app_group.setLayout(app_form)
        main_layout.addWidget(app_group)

        # ---------------------------------------------------------
        # 2. 업데이터 서비스 버전 및 설정 상태 그룹
        # ---------------------------------------------------------
        updater_group = QGroupBox("Background Update Service & GitHub Config Status")
        updater_form = QFormLayout()
        updater_form.setLabelAlignment(Qt.AlignRight)
        updater_form.setVerticalSpacing(8)

        self.lbl_updater_name = QLabel("-")
        self.lbl_updater_name.setStyleSheet("font-weight: bold; font-size: 11pt;")

        self.lbl_updater_version = QLabel("-")
        self.lbl_updater_version.setStyleSheet("font-weight: bold; font-size: 12pt; color: #569CD6;")

        # 업데이터 EXE EOF 암호화 버전 라벨
        self.lbl_updater_eof_version = QLabel("-")
        self.lbl_updater_eof_version.setStyleSheet("font-weight: bold; font-size: 10pt; color: #DCDCAA;")

        self.lbl_service_status = QLabel("-")
        self.lbl_service_status.setStyleSheet("font-weight: bold;")

        self.lbl_comm_status = QLabel("-")
        
        # 업데이터가 인지한 메인앱 경로 및 업데이터 실제 실행 경로 라벨
        self.lbl_tracked_main_path = QLabel("-")
        self.lbl_tracked_main_path.setStyleSheet("color: #9CDCFE; font-size: 9pt;")
        self.lbl_tracked_main_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.lbl_updater_actual_path = QLabel("-")
        self.lbl_updater_actual_path.setStyleSheet("color: #9CDCFE; font-size: 9pt;")
        self.lbl_updater_actual_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.lbl_github_json_url = QLabel("-")
        self.lbl_github_json_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_github_json_url.setStyleSheet("color: #9CDCFE; font-size: 9pt;")

        self.lbl_updater_path = QLabel("-")
        self.lbl_updater_path.setStyleSheet("color: #858585; font-size: 9pt;")
        self.lbl_updater_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        updater_form.addRow("서비스명 (Name):", self.lbl_updater_name)
        updater_form.addRow("서비스 버전 (File):", self.lbl_updater_version)
        updater_form.addRow("서비스 바이너리 버전 (EOF):", self.lbl_updater_eof_version)
        updater_form.addRow("Windows 서비스 상태:", self.lbl_service_status)
        updater_form.addRow("업데이터 통신(UDP) 상태:", self.lbl_comm_status)
        updater_form.addRow("업데이터가 인지한 메인앱 경로:", self.lbl_tracked_main_path)
        updater_form.addRow("업데이터 프로세스 실행 경로:", self.lbl_updater_actual_path)
        updater_form.addRow("설정된 GitHub JSON URL:", self.lbl_github_json_url)
        updater_form.addRow("버전 파일 경로:", self.lbl_updater_path)

        updater_group.setLayout(updater_form)
        main_layout.addWidget(updater_group)

        # ---------------------------------------------------------
        # 3. UDP 명령어 통신 테스트 그룹 (버튼형 배치 및 영역 확장)
        # ---------------------------------------------------------
        udp_test_group = QGroupBox("Updater UDP Command Test & Diagnostics")
        udp_layout = QVBoxLayout()
        udp_layout.setSpacing(8)

        # 상단: 개별 커맨드 테스트 버튼들을 그리드 형태로 배치
        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)

        self.btn_cmd_status = QPushButton("GET_STATUS")
        self.btn_cmd_status.setMinimumHeight(32)
        self.btn_cmd_status.clicked.connect(lambda: self.on_send_specific_udp("GET_STATUS"))
        btn_grid.addWidget(self.btn_cmd_status, 0, 0)

        self.btn_cmd_versions = QPushButton("GET_VERSIONS")
        self.btn_cmd_versions.setMinimumHeight(32)
        self.btn_cmd_versions.clicked.connect(lambda: self.on_send_specific_udp("GET_VERSIONS"))
        btn_grid.addWidget(self.btn_cmd_versions, 0, 1)

        self.btn_cmd_paths = QPushButton("GET_PATHS")
        self.btn_cmd_paths.setMinimumHeight(32)
        self.btn_cmd_paths.clicked.connect(lambda: self.on_send_specific_udp("GET_PATHS"))
        btn_grid.addWidget(self.btn_cmd_paths, 1, 0)

        self.btn_cmd_heartbeat = QPushButton("GET_HEARTBEAT")
        self.btn_cmd_heartbeat.setMinimumHeight(32)
        self.btn_cmd_heartbeat.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        self.btn_cmd_heartbeat.clicked.connect(lambda: self.on_send_specific_udp("GET_HEARTBEAT"))
        btn_grid.addWidget(self.btn_cmd_heartbeat, 1, 1)

        udp_layout.addLayout(btn_grid)

        # 하단: 요청 패킷 및 응답 패킷 영역 (가독성을 위한 QTextEdit 상하/좌우 분리 배치)
        packet_layout = QHBoxLayout()

        # 요청 패킷 박스
        req_vbox = QVBoxLayout()
        req_vbox.addWidget(QLabel("<b>요청 패킷 (Request):</b>"))
        self.txt_req_packet = QTextEdit()
        self.txt_req_packet.setMaximumHeight(70)
        self.txt_req_packet.setReadOnly(True)
        self.txt_req_packet.setStyleSheet("font-family: Consolas; color: #CE9178; background-color: #1E1E1E;")
        req_vbox.addWidget(self.txt_req_packet)
        packet_layout.addLayout(req_vbox)

        # 응답 패킷 박스 (날짜 타임스탬프 자동 변환 포함)
        res_vbox = QVBoxLayout()
        res_vbox.addWidget(QLabel("<b>응답 패킷 (Response / 날짜 변환 포함):</b>"))
        self.txt_res_packet = QTextEdit()
        self.txt_res_packet.setMaximumHeight(120)
        self.txt_res_packet.setReadOnly(True)
        self.txt_res_packet.setStyleSheet("font-family: Consolas; color: #4EC9B0; background-color: #1E1E1E;")
        res_vbox.addWidget(self.txt_res_packet)
        packet_layout.addLayout(res_vbox)

        udp_layout.addLayout(packet_layout)
        udp_test_group.setLayout(udp_layout)
        main_layout.addWidget(udp_test_group)

        # ---------------------------------------------------------
        # 4. 하단 제어 버튼 영역
        # ---------------------------------------------------------
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton("🔄 정보 새로고침")
        self.btn_refresh.setMinimumHeight(34)
        self.btn_refresh.clicked.connect(self.refresh_version_info)
        btn_layout.addWidget(self.btn_refresh)

        self.btn_github_assist = QPushButton("🌐 GitHub 업데이트 저장소 가이드 (Assist)")
        self.btn_github_assist.setMinimumHeight(34)
        self.btn_github_assist.setStyleSheet("font-weight: bold; color: #CE9178;")
        self.btn_github_assist.clicked.connect(self.open_github_assist_dialog)
        btn_layout.addWidget(self.btn_github_assist)

        # 외부 EXE 파일 암호화 버전 검증 버튼
        self.btn_verify_exe = QPushButton("🔍 EXE 암호화 버전 검사")
        self.btn_verify_exe.setMinimumHeight(34)
        self.btn_verify_exe.clicked.connect(self.on_verify_external_exe)
        btn_layout.addWidget(self.btn_verify_exe)

        btn_layout.addStretch()

        self.btn_bump_app = QPushButton("⬆️ 메인 앱 패치 버전 증가 (+0.0.1)")
        self.btn_bump_app.setMinimumHeight(34)
        self.btn_bump_app.clicked.connect(self.on_bump_app_version)
        btn_layout.addWidget(self.btn_bump_app)

        main_layout.addLayout(btn_layout)
        main_layout.addStretch()

    def refresh_version_info(self):
        """디스크 버전, EXE EOF 암호화 버전, Windows 서비스 상태, UDP 상세 상태 및 경로 동기화"""
        # 1. 메인 앱 버전 조회
        self.lbl_app_name.setText(self.main_vm.app_name)
        self.lbl_app_path.setText(self.main_vm.txt_path)
        app_ver = "1.2.0"
        try:
            app_ver = self.main_vm.get_current_version()
            self.lbl_app_version.setText(f"v{app_ver}")
        except Exception as e:
            self.lbl_app_version.setText(f"오류 ({e})")

        # 메인 앱 실행 파일의 EOF 복호화 버전 조회
        eof_ver = get_runtime_decrypted_version(fallback_version=app_ver)
        self.lbl_app_eof_version.setText(eof_ver)

        # 2. 업데이터 서비스 버전 조회
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

        # 업데이터 서비스 EXE 파일의 EOF 복호화 버전 조회
        updater_exe_path = os.path.join(self.updater_dir, "PSUpdateService.exe")
        if not os.path.exists(updater_exe_path):
            updater_exe_path = os.path.join(self.updater_dir, "print_shop_update_service.exe")
        if os.path.exists(updater_exe_path):
            self.lbl_updater_eof_version.setText(extract_version_from_exe(updater_exe_path))
        else:
            self.lbl_updater_eof_version.setText("실행 파일 없음 (개발 환경)")

        # 3. Windows 서비스 상태 확인
        status_text, color = self._check_windows_service_status("PrintShopUpdateService")
        self.lbl_service_status.setText(status_text)
        self.lbl_service_status.setStyleSheet(f"font-weight: bold; color: {color};")

        # 4. 업데이터 서비스 설정 상태(GitHub URL 등) 및 UDP 프로토콜 경로 연동 조회
        if updater_client:
            try:
                detailed_status = updater_client.get_detailed_status()
                phase = detailed_status.get("phase", "UNKNOWN")
                msg = detailed_status.get("message", "응답 없음")
                
                if phase != "UNKNOWN":
                    self.lbl_comm_status.setText(f"● 정상 동작 중 [Phase: {phase}] - {msg}")
                    self.lbl_comm_status.setStyleSheet("font-weight: bold; color: #4EC9B0;")
                else:
                    self.lbl_comm_status.setText("○ 업데이터 서비스와 통신 응답 없음 (서비스 중지 상태일 수 있음)")
                    self.lbl_comm_status.setStyleSheet("font-weight: bold; color: #CE9178;")

                # 업데이터 서비스에 UDP로 경로 정보 요청 (GET_PATHS 프로토콜)
                paths_data = updater_client.get_service_paths() if hasattr(updater_client, 'get_service_paths') else {}
                if paths_data:
                    self.lbl_tracked_main_path.setText(paths_data.get("main_exe_path", "-"))
                    self.lbl_updater_actual_path.setText(paths_data.get("updater_exe_path", "-"))
                else:
                    self.lbl_tracked_main_path.setText("서비스 응답 없음 (UDP 연결 대기)")
                    self.lbl_updater_actual_path.setText("서비스 응답 없음 (UDP 연결 대기)")

                json_url_val = self._load_service_config_from_registry()
                if json_url_val:
                    self.lbl_github_json_url.setText(json_url_val)
                else:
                    self.lbl_github_json_url.setText("설정된 GitHub URL이 없습니다. (Assist를 통해 설정 필요)")
            except Exception as e:
                self.lbl_comm_status.setText(f"통신 오류: {e}")
                self.lbl_comm_status.setStyleSheet("font-weight: bold; color: #F44747;")
                self.lbl_tracked_main_path.setText("통신 오류")
                self.lbl_updater_actual_path.setText("통신 오류")
        else:
            self.lbl_comm_status.setText("updater_client 모듈을 불러올 수 없습니다.")
            self.lbl_comm_status.setStyleSheet("font-weight: bold; color: #F44747;")

    def on_send_specific_udp(self, cmd: str):
        """특정 UDP 커맨드를 전송하고 응답 패킷의 타임스탬프 날짜 변환 및 GET_PATHS 응답 시 상단 UI 경로 즉시 갱신"""
        if not updater_client:
            QMessageBox.warning(self, "경고", "UpdateClient 모듈을 사용할 수 없습니다.")
            return

        self.txt_req_packet.setText(cmd)
        self.txt_res_packet.setText("전송 중...")

        try:
            response = updater_client._send_udp(cmd, timeout=3.0)
            if not response:
                self.txt_res_packet.setText("(응답 없음 또는 타임아웃)")
                return

            display_text = response
            
            # 💡 1. GET_PATHS 응답이 정상일 때 상단 UI 경로 라벨 즉시 업데이트 연동
            if cmd == "GET_PATHS" and response.startswith("OK:"):
                try:
                    paths_json_str = response.split("OK:", 1)[1]
                    paths_data = json.loads(paths_json_str)
                    
                    # 상단 라벨 텍스트 동기화 갱신
                    self.lbl_tracked_main_path.setText(paths_data.get("main_exe_path", "-"))
                    self.lbl_updater_actual_path.setText(paths_data.get("updater_exe_path", "-"))
                    
                    display_text = f"OK (상단 UI 경로 정보가 동기화되었습니다):\n{json.dumps(paths_data, indent=2, ensure_ascii=False)}"
                except Exception as e:
                    display_text = f"{response}\n(경로 UI 파싱 오류: {e})"

            # 💡 2. GET_HEARTBEAT 응답일 때 타임스탬프를 읽기 쉬운 날짜로 포맷 변환
            elif cmd == "GET_HEARTBEAT" and response.startswith("OK:"):
                try:
                    json_str = response.split("OK:", 1)[1]
                    data = json.loads(json_str)
                    
                    for key in ["first_time", "last_time"]:
                        if data.get(key) is not None:
                            try:
                                ts = int(data[key])
                                dt_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                                data[f"{key}_formatted"] = dt_str
                            except Exception:
                                pass
                    
                    display_text = f"OK (포맷 변환됨):\n{json.dumps(data, indent=2, ensure_ascii=False)}"
                except Exception:
                    pass

            self.txt_res_packet.setText(display_text)
        except Exception as e:
            self.txt_res_packet.setText(f"전송 오류 발생: {e}")

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

    def _load_service_config_from_registry(self) -> str:
        """Windows 레지스트리에서 설정된 JsonUrl 불러오기"""
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\print_shop_update_service", 0, winreg.KEY_READ)
            json_url, _ = winreg.QueryValueEx(key, "JsonUrl")
            winreg.CloseKey(key)
            return json_url
        except Exception:
            return ""

    def _check_windows_service_status(self, service_name: str) -> tuple[str, str]:
        """sc query 명령으로 윈도우 백그라운드 서비스 상태 확인"""
        try:
            res = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = res.stdout.upper()
            if "RUNNING" in output:
                return "● 실행 중 (RUNNING)", "#4EC9B0"
            elif "STOPPED" in output:
                return "■ 중지됨 (STOPPED)", "#CE9178"
            elif "1060" in output or res.returncode != 0:
                return "○ 미등록 서비스 (Not Installed)", "#858585"
            return "상태 확인 불가", "#D4D4D4"
        except Exception:
            return "상태 조회 실패", "#F44747"

    def open_github_assist_dialog(self):
        """GitHub 업데이트 어시스트 다이얼로그 호출"""
        if updater_client:
            try:
                updater_client.show_github_assist_dialog(self)
            except Exception as e:
                QMessageBox.critical(self, "오류", "GitHub 어시스트 창을 여는 중 오류가 발생했습니다:\n" + str(e))
        else:
            QMessageBox.warning(self, "경고", "UpdateClient 객체를 찾을 수 없습니다.")

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
