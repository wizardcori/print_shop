# service_protocol_handler.py
import socket
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from Protocol.update_service_command_base import (
    CMD_STANDARD_METHOD_MAP,
    UpdateServiceCommandBase,
)
from Protocol.update_service_protocol import (
    BUFFER_SIZE,
    COMMAND_COOLDOWN_MAP,
    DEFAULT_HOST,
    DEFAULT_PORT,
    HEARTBEAT_INTERVAL_SEC,
    HEARTBEAT_LOG_BURST_COUNT,
    HEARTBEAT_MISSING_THRESHOLD,
    HEARTBEAT_RESET_COUNTER_THRESHOLD,
    HEARTBEAT_TIMEOUT_SEC,
    Cmd,
    ResponseCode,
    ShutdownMode,
    UpdateClientPacket,
    UpdateServicePacket,
    UpdateServiceToUpdateClientPacketBuilder,
    parse_client_request,
)
from UpdateService.update_service_commands import UpdateServiceCommands


class UpdateServiceProtocolHandler:
    """UpdateService 측 UDP 수신, 프로토콜 검증, 하트비트/쿨다운 관리 및 명령 라우팅 전담 클래스"""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        log_fn: Optional[Callable[[str, int, str], None]] = None,
        command_impl: Optional[UpdateServiceCommandBase] = None,
        on_get_status: Optional[Callable[[], dict]] = None,
        on_get_versions: Optional[Callable[[], list]] = None,
        on_get_paths: Optional[Callable[[], dict]] = None,
        on_set_github_config: Optional[Callable[[str, str], tuple[int, dict]]] = None,
        on_get_github_config: Optional[Callable[[], dict]] = None,
        on_github_test: Optional[Callable[[str, str], tuple[int, dict]]] = None,
        on_set_restart_function: Optional[Callable[[bool], None]] = None,
        on_get_restart_function: Optional[Callable[[], bool]] = None,
        on_apply_update: Optional[Callable[[str, bool], None]] = None,
        on_rollback: Optional[Callable[[str, bool], None]] = None,
    ):
        self.host = host
        self.port = port
        self._log = log_fn or (lambda phase, progress, msg: None)

        self.on_apply_update = on_apply_update
        self.on_rollback = on_rollback

        self.packet_builder = UpdateServiceToUpdateClientPacketBuilder()
        self._sock: Optional[socket.socket] = None
        self._running = False

        # 하트비트 및 Watchdog 상태
        now = time.time()
        self.last_heartbeat = now
        self.heartbeat_timeout_limit = HEARTBEAT_TIMEOUT_SEC
        self.hb_missing_count = 0
        self.hb_log_remaining = 0
        self.last_hb_received_time = now

        self.hb_first_time = None
        self.hb_first_server_time = None
        self.hb_first_counter = None
        self.hb_last_time = None
        self.hb_last_server_time = None
        self.hb_last_counter = None
        self.hb_total_count = 0

        # 쿨다운 및 무거운 작업 락
        self.command_last_called_time: dict[int, float] = {}
        self.is_heavy_task_running = False
        self.heavy_task_lock = threading.Lock()

        # 커맨드 가상함수 구현체 (외부 상속 구현체 주입 가능)
        self.command_impl: UpdateServiceCommandBase = command_impl or UpdateServiceCommands(
            packet_builder=self.packet_builder,
            on_get_status=on_get_status or (lambda: {}),
            on_get_versions=on_get_versions or (lambda: []),
            on_get_paths=on_get_paths or (lambda: {}),
            on_get_heartbeat=self.get_heartbeat_status,
            on_set_github_config=on_set_github_config or (lambda r, j: (ResponseCode.UNKNOWN_CMD, {})),
            on_get_github_config=on_get_github_config or (lambda: {}),
            on_github_test=on_github_test or (lambda r, j: (ResponseCode.UNKNOWN_CMD, {})),
            on_set_restart_function=on_set_restart_function or (lambda enabled: None),
            on_get_restart_function=on_get_restart_function or (lambda: True),
        )

    def get_heartbeat_status(self) -> dict:
        return {
            "first_time": self.hb_first_time,
            "first_server_time": self.hb_first_server_time,
            "first_counter": self.hb_first_counter,
            "last_time": self.hb_last_time,
            "last_server_time": self.hb_last_server_time,
            "last_counter": self.hb_last_counter,
            "total_count": self.hb_total_count,
        }

    def notify_app_launched(self):
        now = time.time()
        self.last_heartbeat = now
        self.hb_missing_count = HEARTBEAT_MISSING_THRESHOLD
        self.hb_log_remaining = HEARTBEAT_LOG_BURST_COUNT
        self.last_hb_received_time = now

    def check_heartbeat_health(self, current_time: float, is_app_running: bool) -> bool:
        if current_time - self.last_hb_received_time > HEARTBEAT_INTERVAL_SEC:
            self.hb_missing_count += 1
            self.last_hb_received_time = current_time

        if is_app_running and (current_time - self.last_heartbeat > self.heartbeat_timeout_limit):
            self.last_heartbeat = current_time
            return True
        return False

    def start_server(self) -> bool:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((self.host, self.port))
            self._sock.settimeout(1.0)
            self._running = True
            return True
        except Exception as e:
            self._log("ERROR", 0, f"UDP 소켓 바인드 실패: {e}")
            return False

    def stop_server(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def poll_once(self):
        if not self._sock or not self._running:
            return
        try:
            data_bytes, addr = self._sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            return
        except Exception:
            return

        current_time = time.time()
        is_valid, pkt, err_code = parse_client_request(data_bytes)
        if not is_valid:
            if pkt is not None:
                fail_pkt = self.packet_builder.res_fail(err_code)
                self._sock.sendto(fail_pkt.encode(), addr)
            return

        res_pkt = self.dispatch_packet(pkt, current_time)
        if res_pkt is not None:
            self._sock.sendto(res_pkt.encode(), addr)

    def dispatch_packet(self, pkt: UpdateClientPacket, current_time: float) -> UpdateServicePacket:
        cmd_val = pkt.cmd
        base_cmd_val = pkt.base_cmd
        payload = pkt.payload

        # 1. 무거운 비동기 작업(APPLY_UPDATE / ROLLBACK)
        if base_cmd_val in (Cmd.APPLY_UPDATE, Cmd.ROLLBACK):
            with self.heavy_task_lock:
                if self.is_heavy_task_running:
                    self._log(
                        "UDP_REJECT",
                        0,
                        f"요청 거부 ({ResponseCode.to_str(ResponseCode.HEAVY_TASK_ALREADY_RUNNING)}): Cmd={pkt.cmd_full_name}",
                    )
                    return self.packet_builder.res_fail(ResponseCode.HEAVY_TASK_ALREADY_RUNNING)

                cooldown = COMMAND_COOLDOWN_MAP.get(base_cmd_val, 30.0)
                max_last_time = max(
                    self.command_last_called_time.get(Cmd.APPLY_UPDATE, 0.0),
                    self.command_last_called_time.get(Cmd.ROLLBACK, 0.0),
                )
                if current_time - max_last_time < cooldown:
                    self._log(
                        "UDP_REJECT",
                        0,
                        f"요청 거부 ({ResponseCode.to_str(ResponseCode.FREQUENT_REQUEST_THROTTLED)}): Cmd={pkt.cmd_full_name}",
                    )
                    return self.packet_builder.res_fail(ResponseCode.FREQUENT_REQUEST_THROTTLED)

                self.command_last_called_time[base_cmd_val] = current_time
                self.is_heavy_task_running = True

            threading.Thread(
                target=self._run_heavy_task_wrapper,
                args=(base_cmd_val, payload),
                daemon=True,
            ).start()
            return self.packet_builder.res_ok(ResponseCode.PROCESSING, req_cmd=cmd_val)

        # 2. 일반 명령 쿨다운 체크
        if base_cmd_val in COMMAND_COOLDOWN_MAP:
            cooldown = COMMAND_COOLDOWN_MAP[base_cmd_val]
            last_called = self.command_last_called_time.get(base_cmd_val, 0.0)
            if current_time - last_called < cooldown:
                self._log(
                    "UDP_REJECT",
                    0,
                    f"요청 거부 ({ResponseCode.to_str(ResponseCode.FREQUENT_REQUEST_THROTTLED)}): {pkt.cmd_full_name}",
                )
                return self.packet_builder.res_fail(ResponseCode.FREQUENT_REQUEST_THROTTLED)
            self.command_last_called_time[base_cmd_val] = current_time

        # 3. HEARTBEAT 처리
        if base_cmd_val == Cmd.HEARTBEAT:
            return self._handle_heartbeat(pkt, current_time)

        # 4. 표준 가상함수 공통 호출
        if base_cmd_val != Cmd.GET_HEARTBEAT:
            self._log("UDP_REQUEST", 0, f"수신된 요청: {pkt.cmd_full_name}")

        method_name = CMD_STANDARD_METHOD_MAP.get(base_cmd_val)
        handler_fn = getattr(self.command_impl, method_name, None) if method_name else None
        if callable(handler_fn):
            res_pkt = handler_fn(cmd_val, payload)
        else:
            res_pkt = self.packet_builder.res_fail(ResponseCode.UNKNOWN_CMD)

        self._log("UDP_RESPONSE", 0, f"반환 응답: {res_pkt.cmd_full_name}")
        return res_pkt

    def _handle_heartbeat(self, pkt: UpdateClientPacket, current_time: float) -> UpdateServicePacket:
        self.last_heartbeat = current_time
        try:
            parts = pkt.payload.split(":") if pkt.payload else []
            current_counter = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
            current_time_val = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else int(time.time())
        except Exception:
            current_counter = 0
            current_time_val = int(time.time())

        server_measured_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        is_reset_condition = (
            self.hb_first_counter is None
            or (
                self.hb_last_counter is not None
                and current_counter < self.hb_last_counter
                and current_counter <= HEARTBEAT_RESET_COUNTER_THRESHOLD
            )
        )

        if is_reset_condition:
            self.hb_first_time = current_time_val
            self.hb_first_server_time = server_measured_time
            self.hb_first_counter = current_counter
            self.hb_total_count = 1
            self.command_last_called_time.clear()
            self._log("HEARTBEAT_RESET", 0, "메인 앱 재시작(세션 리셋) 감지: 모든 명령어 쿨다운 타이머가 초기화되었습니다.")
        else:
            self.hb_total_count += 1

        self.hb_last_time = current_time_val
        self.hb_last_server_time = server_measured_time
        self.hb_last_counter = current_counter

        if self.hb_missing_count >= HEARTBEAT_MISSING_THRESHOLD:
            self.hb_log_remaining = HEARTBEAT_LOG_BURST_COUNT

        self.hb_missing_count = 0
        self.last_hb_received_time = current_time

        res_pkt = self.packet_builder.res_ok("", req_cmd=pkt.cmd)
        if self.hb_log_remaining > 0:
            self._log(
                "UDP_REQUEST",
                0,
                f"수신된 요청: {pkt.cmd_full_name} (서버수신시간: {server_measured_time}, 누적: {self.hb_total_count})",
            )
            self._log("UDP_RESPONSE", 0, f"반환 응답: {res_pkt.cmd_full_name}")
            self.hb_log_remaining -= 1
        return res_pkt

    def _run_heavy_task_wrapper(self, base_cmd_val: int, payload: str):
        self._log("HEAVY_CMD_START", 0, f"무거운 백그라운드 작업 시작: Cmd={base_cmd_val}")
        try:
            parts = payload.split(":") if payload else []
            if base_cmd_val == Cmd.APPLY_UPDATE and self.on_apply_update:
                target_ver = parts[0] if len(parts) > 0 and "." in parts[0] else ""
                self_shutdown = True
                if len(parts) > 1 and parts[1] == ShutdownMode.SERVICE:
                    self_shutdown = False
                elif len(parts) == 1 and parts[0] == ShutdownMode.SERVICE:
                    self_shutdown = False
                    target_ver = ""
                self.on_apply_update(target_ver, self_shutdown)
            elif base_cmd_val == Cmd.ROLLBACK and self.on_rollback:
                target_ver = parts[0] if len(parts) > 0 else ""
                self_shutdown = True
                if len(parts) > 1 and parts[1] == ShutdownMode.SERVICE:
                    self_shutdown = False
                self.on_rollback(target_ver, self_shutdown)
        finally:
            with self.heavy_task_lock:
                self.is_heavy_task_running = False
            self._log("HEAVY_CMD_END", 0, f"무거운 백그라운드 작업 종료 및 락 해제 완료: Cmd={base_cmd_val}")
