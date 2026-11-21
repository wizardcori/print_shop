# update_client_tab.py
import subprocess
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFormLayout, QMessageBox, QGridLayout,
    QTextEdit, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt

from Common.settings_registry import register_settings_tab
from Common.print_shop_update_client import updater_client
from Protocol.update_service_protocol import (
    Cmd,
    ResponseCode,
)


class UpdateClientTab(QWidget):
    """업데이터 서비스 상태 확인, GitHub 설정 및 UDP 커맨드 진단을 수행하는 설정 탭 UI"""

    # 커맨드별 (인자1 힌트, 인자2 힌트, 필수 텍스트 인자 수 [0/1/2], 옵션 사용 여부)
    CLIENT_CMD_SPECS = {
        "HEARTBEAT": ("counter (필수, 예: 10)", "time_val (필수, Unix 초 예: 1732000000)", 2, False),
        "GET_STATUS": ("인자 불필요", "인자 불필요", 0, False),
        "GET_VERSIONS": ("인자 불필요", "인자 불필요", 0, False),
        "GET_PATHS": ("인자 불필요", "인자 불필요", 0, False),
        "GET_HEARTBEAT": ("인자 불필요", "인자 불필요", 0, False),
        "CONFIG_AND_TEST": ("repo_url (필수, 예: https://github.com/user/repo)", "json_url (필수, 예: https://raw.githubusercontent.com/.../version.json)", 2, False),
        "APPLY_UPDATE": ("target_version (필수, 예: 3.4.9)", "인자 1개만 사용하는 명령입니다", 1, True),
        "ROLLBACK": ("target_version (필수, 예: 3.4.8)", "인자 1개만 사용하는 명령입니다", 1, True),
        "SET_RESTART_FUNCTION": ("1 또는 0 (필수, 활성: 1 / 비활성: 0)", "인자 1개만 사용하는 명령입니다", 1, True),
        "GET_RESTART_FUNCTION": ("인자 불필요", "인자 불필요", 0, False),
        "SET_GITHUB_CONFIG": ("repo_url (필수, 예: https://github.com/user/repo)", "json_url (필수, 예: https://raw.githubusercontent.com/.../version.json)", 2, False),
        "GET_GITHUB_CONFIG": ("인자 불필요", "인자 불필요", 0, False),
        "GITHUB_TEST": ("repo_url (선택, 미입력 시 저장값 사용)", "json_url (선택, 미입력 시 저장값 사용)", 0, False),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_cmd = "GET_STATUS"
        self.init_ui()
        self._apply_cmd_arg_state(self._selected_cmd)
        self.refresh_service_info()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        title_label = QLabel("<h3>Update Service Status & UDP Client Diagnostics</h3>")
        title_label.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(title_label)

        # ---------------------------------------------------------
        # 1. 백그라운드 업데이터 서비스 & GitHub 설정 상태 그룹
        # ---------------------------------------------------------
        status_group = QGroupBox("Background Update Service & GitHub Config Status")
        status_form = QFormLayout(status_group)
        status_form.setContentsMargins(6, 12, 6, 6)
        status_form.setLabelAlignment(Qt.AlignRight)
        status_form.setHorizontalSpacing(6)
        status_form.setVerticalSpacing(4)

        self.lbl_service_status = QLabel("-")
        self.lbl_service_status.setStyleSheet("font-weight: bold;")

        self.lbl_comm_status = QLabel("-")

        self.lbl_tracked_main_path = QLabel("-")
        self.lbl_tracked_main_path.setStyleSheet("color: #9CDCFE; font-size: 9pt;")
        self.lbl_tracked_main_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.lbl_updater_actual_path = QLabel("-")
        self.lbl_updater_actual_path.setStyleSheet("color: #9CDCFE; font-size: 9pt;")
        self.lbl_updater_actual_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.lbl_github_json_url = QLabel("-")
        self.lbl_github_json_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_github_json_url.setStyleSheet("color: #9CDCFE; font-size: 9pt;")

        status_form.addRow("Windows 서비스 상태:", self.lbl_service_status)
        status_form.addRow("업데이터 통신(UDP) 상태:", self.lbl_comm_status)
        status_form.addRow("업데이터가 인지한 메인앱 경로:", self.lbl_tracked_main_path)
        status_form.addRow("업데이터 프로세스 실행 경로:", self.lbl_updater_actual_path)
        status_form.addRow("설정된 GitHub JSON URL:", self.lbl_github_json_url)

        main_layout.addWidget(status_group)

        # ---------------------------------------------------------
        # 2. UDP 명령어 통신 테스트 그룹
        # ---------------------------------------------------------
        udp_test_group = QGroupBox("Updater UDP Command Test & Diagnostics")
        udp_layout = QVBoxLayout(udp_test_group)
        udp_layout.setContentsMargins(5, 13, 5, 5)
        udp_layout.setSpacing(4)

        client_cmd_group = QGroupBox("UpdateClient 전송 커맨드 (13개) 실행 그룹")
        client_cmd_layout = QVBoxLayout(client_cmd_group)
        client_cmd_layout.setContentsMargins(4, 12, 4, 4)
        client_cmd_layout.setSpacing(4)

        param_layout = QGridLayout()
        param_layout.setContentsMargins(0, 0, 0, 0)
        param_layout.setHorizontalSpacing(4)
        param_layout.setVerticalSpacing(3)

        self.txt_cmd_param1 = QLineEdit()
        self.txt_cmd_param1.setPlaceholderText("인자 1")
        self.txt_cmd_param1.returnPressed.connect(self._on_param_input_submitted)

        self.txt_cmd_param2 = QLineEdit()
        self.txt_cmd_param2.setPlaceholderText("인자 2")
        self.txt_cmd_param2.returnPressed.connect(self._on_param_input_submitted)

        self.cmb_cmd_bool = QComboBox()
        self.cmb_cmd_bool.addItems(["True (1 / SELF)", "False (0 / SERVICE)"])

        param_layout.addWidget(QLabel("인자 1:"), 0, 0)
        param_layout.addWidget(self.txt_cmd_param1, 0, 1)
        param_layout.addWidget(QLabel("인자 2:"), 0, 2)
        param_layout.addWidget(self.txt_cmd_param2, 0, 3)
        param_layout.addWidget(QLabel("옵션:"), 0, 4)
        param_layout.addWidget(self.cmb_cmd_bool, 0, 5)
        client_cmd_layout.addLayout(param_layout)

        self.lbl_cmd_arg_guide = QLabel("[명령 선택 시 인자 안내가 표시됩니다]")
        self.lbl_cmd_arg_guide.setStyleSheet("color: #9CDCFE; font-size: 9pt;")
        client_cmd_layout.addWidget(self.lbl_cmd_arg_guide)

        all_commands = [
            "HEARTBEAT",
            "GET_STATUS",
            "GET_VERSIONS",
            "GET_PATHS",
            "GET_HEARTBEAT",
            "CONFIG_AND_TEST",
            "APPLY_UPDATE",
            "ROLLBACK",
            "SET_RESTART_FUNCTION",
            "GET_RESTART_FUNCTION",
            "SET_GITHUB_CONFIG",
            "GET_GITHUB_CONFIG",
            "GITHUB_TEST",
        ]

        cmd_grid = QGridLayout()
        cmd_grid.setContentsMargins(0, 0, 0, 0)
        cmd_grid.setHorizontalSpacing(4)
        cmd_grid.setVerticalSpacing(3)
        self.cmd_buttons: dict[str, QPushButton] = {}

        cols = 2
        for idx, cmd_name in enumerate(all_commands):
            btn = QPushButton(cmd_name)
            btn.setMinimumHeight(28)
            spec = self.CLIENT_CMD_SPECS.get(cmd_name)
            if spec:
                btn.setToolTip(f"필수 인자 수: {spec[2]} | 인자1: {spec[0]} | 인자2: {spec[1]}")
            if cmd_name == "GET_HEARTBEAT":
                btn.setStyleSheet("font-weight: bold; color: #4EC9B0;")
            btn.clicked.connect(lambda checked=False, c=cmd_name: self._on_cmd_button_clicked(c))
            cmd_grid.addWidget(btn, idx // cols, idx % cols)
            self.cmd_buttons[cmd_name] = btn

        client_cmd_layout.addLayout(cmd_grid)
        udp_layout.addWidget(client_cmd_group)

        packet_group = QGroupBox("패킷 송수신 (Request / Response)")
        packet_layout = QHBoxLayout(packet_group)
        packet_layout.setContentsMargins(4, 13, 4, 4)
        packet_layout.setSpacing(4)

        req_group = QGroupBox("요청 패킷 (Request)")
        req_vbox = QVBoxLayout(req_group)
        req_vbox.setContentsMargins(3, 12, 3, 3)
        req_vbox.setSpacing(2)
        self.txt_req_packet = QTextEdit()
        self.txt_req_packet.setMinimumHeight(100)
        self.txt_req_packet.setReadOnly(True)
        self.txt_req_packet.setStyleSheet("font-family: Consolas; color: #CE9178; background-color: #1E1E1E;")
        req_vbox.addWidget(self.txt_req_packet)
        packet_layout.addWidget(req_group, stretch=1)

        res_group = QGroupBox("응답 패킷 (Response / 날짜 변환 포함)")
        res_vbox = QVBoxLayout(res_group)
        res_vbox.setContentsMargins(3, 12, 3, 3)
        res_vbox.setSpacing(2)
        self.txt_res_packet = QTextEdit()
        self.txt_res_packet.setMinimumHeight(100)
        self.txt_res_packet.setReadOnly(True)
        self.txt_res_packet.setStyleSheet("font-family: Consolas; color: #4EC9B0; background-color: #1E1E1E;")
        res_vbox.addWidget(self.txt_res_packet)
        packet_layout.addWidget(res_group, stretch=1)

        udp_layout.addWidget(packet_group, stretch=1)
        main_layout.addWidget(udp_test_group, stretch=1)

        # ---------------------------------------------------------
        # 3. 하단 제어 버튼 영역
        # ---------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)

        self.btn_refresh = QPushButton("🔄 서비스 상태 새로고침")
        self.btn_refresh.setMinimumHeight(32)
        self.btn_refresh.clicked.connect(self.refresh_service_info)
        btn_layout.addWidget(self.btn_refresh)

        self.btn_github_assist = QPushButton("🌐 GitHub 업데이트 저장소 가이드 (Assist)")
        self.btn_github_assist.setMinimumHeight(32)
        self.btn_github_assist.setStyleSheet("font-weight: bold; color: #CE9178;")
        self.btn_github_assist.clicked.connect(self.open_github_assist_dialog)
        btn_layout.addWidget(self.btn_github_assist)

        btn_layout.addStretch()

        self.btn_clear_packets = QPushButton("🧹 패킷 로그 지우기")
        self.btn_clear_packets.setMinimumHeight(32)
        self.btn_clear_packets.clicked.connect(self._on_clear_packets)
        btn_layout.addWidget(self.btn_clear_packets)

        main_layout.addLayout(btn_layout)

    def _on_clear_packets(self):
        self.txt_req_packet.clear()
        self.txt_res_packet.clear()

    def refresh_service_info(self):
        """Windows 서비스 상태, UDP 상세 상태, 경로 및 레지스트리 설정 동기화"""
        status_text, color = self._check_windows_service_status("PrintShopUpdateService")
        self.lbl_service_status.setText(status_text)
        self.lbl_service_status.setStyleSheet(f"font-weight: bold; color: {color};")

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

    def _load_service_config_from_registry(self) -> str:
        """Windows 레지스트리에서 설정된 JsonUrl 불러오기"""
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\PrintShopUpdateService", 0, winreg.KEY_READ)
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
                self.refresh_service_info()
            except Exception as e:
                QMessageBox.critical(self, "오류", "GitHub 어시스트 창을 여는 중 오류가 발생했습니다:\n" + str(e))
        else:
            QMessageBox.warning(self, "경고", "UpdateClient 객체를 찾을 수 없습니다.")

    def _apply_cmd_arg_state(self, cmd: str):
        """선택한 명령의 인자 개수에 따라 입력 위젯 활성화 및 힌트 갱신"""
        cmd_key = cmd.strip().upper()
        hint1, hint2, arg_count, use_option = self.CLIENT_CMD_SPECS.get(
            cmd_key, ("인자 1", "인자 2", 2, True)
        )

        enable_p1 = arg_count >= 1
        self.txt_cmd_param1.setEnabled(enable_p1)
        self.txt_cmd_param1.setPlaceholderText(hint1)
        self.txt_cmd_param1.setToolTip(hint1)
        if not enable_p1:
            self.txt_cmd_param1.clear()

        enable_p2 = arg_count >= 2
        self.txt_cmd_param2.setEnabled(enable_p2)
        self.txt_cmd_param2.setPlaceholderText(hint2)
        self.txt_cmd_param2.setToolTip(hint2)
        if not enable_p2:
            self.txt_cmd_param2.clear()

        self.cmb_cmd_bool.setEnabled(use_option)

        if hasattr(self, "lbl_cmd_arg_guide"):
            if arg_count == 0 and not use_option:
                guide = f"[{cmd_key}] 인자 없음 -> 클릭 시 즉시 전송"
            elif arg_count == 0 and use_option:
                guide = f"[{cmd_key}] 옵션 선택 후 클릭 시 즉시 전송"
            elif arg_count == 1:
                guide = f"[{cmd_key}] 인자 1개 필수 ({hint1}) -> 입력 후 전송" + (" + 옵션" if use_option else "")
            else:
                guide = f"[{cmd_key}] 인자 2개 필수 (1: {hint1} / 2: {hint2}) -> 입력 후 전송"
            self.lbl_cmd_arg_guide.setText(guide)

    def _set_request_packet_error(self, cmd: str, reason: str):
        """요청 패킷 생성/검증 오류 표시"""
        self.txt_req_packet.setText(f"[요청 패킷 에러] {cmd} -> {reason}")
        self.txt_res_packet.setText(f"요청 패킷 에러: {reason}")

    def _validate_and_build_packet(self, cmd: str):
        """명령별 필수 인자 충족 여부 확인 및 요청 패킷 생성. (ok, pkt_or_err_msg)"""
        cmd_key = cmd.strip().upper()
        spec = self.CLIENT_CMD_SPECS.get(cmd_key)
        if not spec:
            return False, f"지원하지 않는 커맨드입니다: {cmd_key}"

        _, _, req_arg_count, _ = spec
        p1 = self.txt_cmd_param1.text().strip() if self.txt_cmd_param1.isEnabled() else ""
        p2 = self.txt_cmd_param2.text().strip() if self.txt_cmd_param2.isEnabled() else ""
        flag = self.cmb_cmd_bool.currentIndex() == 0

        if req_arg_count >= 1 and not p1:
            return False, "인자 1이 비어 있습니다. 인자를 입력한 뒤 전송하세요."
        if req_arg_count >= 2 and not p2:
            return False, "인자 2가 비어 있습니다. 인자를 모두 입력한 뒤 전송하세요."

        builder = updater_client.packet_builder

        if cmd_key == "HEARTBEAT":
            if not p1.isdigit() or not p2.isdigit():
                return False, "HEARTBEAT 인자(counter, time_val)는 정수여야 합니다."
            pkt = builder.req_heartbeat(int(p1), int(p2))
        elif cmd_key == "GET_STATUS":
            pkt = builder.req_get_status()
        elif cmd_key == "GET_VERSIONS":
            pkt = builder.req_get_versions()
        elif cmd_key == "GET_PATHS":
            pkt = builder.req_get_paths()
        elif cmd_key == "GET_HEARTBEAT":
            pkt = builder.req_get_heartbeat()
        elif cmd_key == "CONFIG_AND_TEST":
            pkt = builder.req_config_and_test(repo_url=p1, json_url=p2)
        elif cmd_key == "APPLY_UPDATE":
            pkt = builder.req_apply_update(target_version=p1, self_shutdown=flag)
        elif cmd_key == "ROLLBACK":
            pkt = builder.req_rollback(target_version=p1, self_shutdown=flag)
        elif cmd_key == "SET_RESTART_FUNCTION":
            if p1 in ("1", "0"):
                enabled = (p1 == "1")
            elif p1.lower() in ("true", "on", "yes", "enable", "enabled"):
                enabled = True
            elif p1.lower() in ("false", "off", "no", "disable", "disabled"):
                enabled = False
            else:
                return False, "SET_RESTART_FUNCTION 인자는 1 또는 0이어야 합니다."
            pkt = builder.req_set_restart_function(enabled=enabled)
        elif cmd_key == "GET_RESTART_FUNCTION":
            pkt = builder.req_get_restart_function()
        elif cmd_key == "SET_GITHUB_CONFIG":
            pkt = builder.req_set_github_config(repo_url=p1, json_url=p2)
        elif cmd_key == "GET_GITHUB_CONFIG":
            pkt = builder.req_get_github_config()
        elif cmd_key == "GITHUB_TEST":
            p1_opt = self.txt_cmd_param1.text().strip()
            p2_opt = self.txt_cmd_param2.text().strip()
            pkt = builder.req_github_test(repo_url=p1_opt, json_url=p2_opt)
        else:
            return False, f"지원하지 않는 커맨드입니다: {cmd_key}"

        encoded_str = pkt.to_str(True, True)
        if not encoded_str or getattr(pkt, "cmd", 0) == 0:
            return False, f"유효하지 않은 패킷이 생성되었습니다: {encoded_str}"

        return True, pkt

    def _on_cmd_button_clicked(self, cmd: str):
        """버튼 클릭 시: 인자 없는 명령은 즉시 전송, 인자 있는 명령은 인자가 채워졌을 때 전송"""
        cmd_key = cmd.strip().upper()
        self._selected_cmd = cmd_key
        self._apply_cmd_arg_state(cmd_key)

        spec = self.CLIENT_CMD_SPECS.get(cmd_key)
        req_arg_count = spec[2] if spec else 0

        if req_arg_count > 0:
            p1 = self.txt_cmd_param1.text().strip() if self.txt_cmd_param1.isEnabled() else ""
            p2 = self.txt_cmd_param2.text().strip() if self.txt_cmd_param2.isEnabled() else ""
            if (req_arg_count >= 1 and not p1) or (req_arg_count >= 2 and not p2):
                self._set_request_packet_error(
                    cmd_key,
                    f"필수 인자 {req_arg_count}개가 채워지지 않았습니다. 인자 입력 후 전송하세요."
                )
                self.txt_cmd_param1.setFocus()
                return

        self.on_send_specific_udp(cmd_key)

    def _on_param_input_submitted(self):
        """인자 입력창에서 Enter 입력 시 인자가 채워진 상태면 바로 전송"""
        cmd_key = getattr(self, "_selected_cmd", "")
        if not cmd_key:
            return
        spec = self.CLIENT_CMD_SPECS.get(cmd_key)
        if not spec or spec[2] <= 0:
            return
        self.on_send_specific_udp(cmd_key)

    def _get_timeout_for_cmd(self, cmd: str) -> float:
        """커맨드 성격에 따른 UDP 수신 타임아웃 반환"""
        cmd_key = cmd.strip().upper()
        if cmd_key in ("CONFIG_AND_TEST", "APPLY_UPDATE", "ROLLBACK"):
            return 5.0
        if cmd_key == "HEARTBEAT":
            return 1.0
        return 3.0

    def on_send_specific_udp(self, cmd: str):
        """검증된 요청 패킷을 UDP로 전송하고 응답을 UI에 반영"""
        if not updater_client:
            self._set_request_packet_error(cmd, "UpdateClient 모듈을 사용할 수 없습니다.")
            return

        cmd_key = cmd.strip().upper()
        try:
            ok, result = self._validate_and_build_packet(cmd_key)
        except Exception as e:
            self._set_request_packet_error(cmd_key, f"패킷 생성 예외: {e}")
            return

        if not ok:
            self._set_request_packet_error(cmd_key, result)
            return

        req_pkt = result
        raw_req_num = req_pkt.to_str(use_numeric_node=True, use_numeric_cmd=True)
        raw_req_str = req_pkt.to_str(use_numeric_node=False, use_numeric_cmd=False)
        self.txt_req_packet.setText(f"{cmd_key}\n[숫자] {raw_req_num}\n[문자] {raw_req_str}")
        self.txt_res_packet.setText("전송 중...")

        try:
            timeout = self._get_timeout_for_cmd(cmd_key)
            res_pkt = updater_client._send_udp_packet(req_pkt, timeout=timeout)
            if not res_pkt:
                self.txt_req_packet.setText(f"[요청 패킷 에러 / 무응답] {cmd_key} -> {raw_req_str}")
                self.txt_res_packet.setText("(응답 없음 또는 타임아웃)")
                return

            raw_res_num = res_pkt.to_str(use_numeric_node=True, use_numeric_cmd=True)
            raw_res_str = res_pkt.to_str(use_numeric_node=False, use_numeric_cmd=False)
            raw_payload = res_pkt.payload or ""

            # 상단 경고 및 패킷 요약 구성
            header_lines = []
            if res_pkt.cmd != Cmd.RES_FAIL and res_pkt.base_cmd != req_pkt.base_cmd:
                header_lines.append(
                    f"⚠️ [커맨드 불일치] 요청={req_pkt.cmd_name}({req_pkt.base_cmd}) / "
                    f"응답={res_pkt.cmd_name}({res_pkt.base_cmd})"
                )

            header_lines.append(cmd_key)
            header_lines.append(f"[숫자] {raw_res_num}")
            header_lines.append(f"[문자] {raw_res_str}")

            # RES_FAIL인 경우 ResponseCode 문자열 변환 표시
            if res_pkt.cmd == Cmd.RES_FAIL:
                code_int = ResponseCode.to_int(raw_payload)
                code_str = ResponseCode.to_str(code_int)
                display_text = f"❌ [실패 응답] {code_str} (code={raw_payload or code_int})"
            else:
                parsed_json = None
                if raw_payload:
                    try:
                        parsed_json = json.loads(raw_payload)
                    except Exception:
                        parsed_json = None

                if cmd_key == "GET_PATHS" and isinstance(parsed_json, dict):
                    self.lbl_tracked_main_path.setText(parsed_json.get("main_exe_path", "-"))
                    self.lbl_updater_actual_path.setText(parsed_json.get("updater_exe_path", "-"))

                if cmd_key == "GET_HEARTBEAT" and isinstance(parsed_json, dict):
                    for key in ("first_time", "last_time"):
                        if parsed_json.get(key) is not None:
                            try:
                                ts = int(parsed_json[key])
                                parsed_json[f"{key}_formatted"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                pass

                if parsed_json is not None:
                    display_text = (
                        f"[파싱 결과 - {res_pkt.cmd_full_name}]\n"
                        f"{json.dumps(parsed_json, indent=2, ensure_ascii=False)}"
                    )
                elif raw_payload:
                    display_text = f"[응답 데이터] {raw_payload}"
                else:
                    display_text = "[응답 데이터] (비어 있음)"

            self.txt_res_packet.setText("\n".join(header_lines) + "\n\n" + display_text)

        except Exception as e:
            self.txt_req_packet.setText(f"[요청 패킷 에러] {cmd_key} -> {raw_req_str}")
            self.txt_res_packet.setText(f"전송 오류 발생: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_service_info()


register_settings_tab('update_client', 'UpdateClient', UpdateClientTab, order=100)