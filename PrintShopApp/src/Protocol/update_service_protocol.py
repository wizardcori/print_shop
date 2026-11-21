# update_protocol.py
"""
PrintShop Update Service & Client 공통 통신 프로토콜 모듈
- src / dst 노드 식별: 숫자(int)만 엄격히 지원 (NodeId / Src / Dst 클래스)
- cmd 명령어 상수 (숫자 코드 <-> 문자열 변환 지원, 요청: +0 / 응답: +10000 오프셋 적용)
- ResponseCode 상수 (숫자 코드 <-> 문자열 변환 지원)
- ProtocolPacket 상속 기반 방향별 패킷 클래스 및 빌더 클래스 적용
  (UpdateClientToUpdateServicePacketBuilder, UpdateServiceToUpdateClientPacketBuilder)
- GET_RESTART_FUNCTION 및 SET_RESTART_FUNCTION 지원
"""
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional, Tuple


# ==============================================================================
# 1. 네트워크 및 기본 통신 설정 상수
# ==============================================================================
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 54321
BUFFER_SIZE = 4096
ENCODING = "utf-8"
DELIMITER = ":"

CMD_REQ_OFFSET = 0
CMD_RES_OFFSET = 10000


# ==============================================================================
# 2. SRC / DST 노드 상수 정의 (정수형 전용 지원: UpdateClient=1, UpdateService=2)
# ==============================================================================
class NodeId(IntEnum):
    UNKNOWN = 0
    UPDATE_CLIENT = 1   # 메인 애플리케이션 클라이언트 (UpdateClient)
    UPDATE_SERVICE = 2  # 백그라운드 업데이트 & Watchdog 서비스 (UpdateService)


class Src:
    UNKNOWN = int(NodeId.UNKNOWN)
    UPDATE_CLIENT = int(NodeId.UPDATE_CLIENT)
    UPDATE_SERVICE = int(NodeId.UPDATE_SERVICE)

    STR_UNKNOWN = "UNKNOWN"
    STR_UPDATE_CLIENT = "UpdateClient"
    STR_UPDATE_SERVICE = "UpdateService"

    _STR_MAP = {
        int(NodeId.UNKNOWN): STR_UNKNOWN,
        int(NodeId.UPDATE_CLIENT): STR_UPDATE_CLIENT,
        int(NodeId.UPDATE_SERVICE): STR_UPDATE_SERVICE,
    }
    _NUM_MAP = {
        "UNKNOWN": int(NodeId.UNKNOWN),
        "UPDATECLIENT": int(NodeId.UPDATE_CLIENT),
        "UPDATE_CLIENT": int(NodeId.UPDATE_CLIENT),
        "UPDATESERVICE": int(NodeId.UPDATE_SERVICE),
        "UPDATE_SERVICE": int(NodeId.UPDATE_SERVICE),
    }

    @classmethod
    def to_str(cls, val: int) -> str:
        return cls._STR_MAP.get(int(val), cls.STR_UNKNOWN)

    @classmethod
    def to_int(cls, val: int | str) -> int:
        if isinstance(val, int):
            num = int(val)
            return num if num in cls._STR_MAP else cls.UNKNOWN
        text = str(val).strip()
        if text.isdigit():
            num = int(text)
            return num if num in cls._STR_MAP else cls.UNKNOWN
        return cls._NUM_MAP.get(text.upper(), cls.UNKNOWN)


class Dst(Src):
    pass


# ==============================================================================
# 3. CMD 상수 정의 (요청: +0, 응답: +10000 오프셋 적용 및 상호 변환)
# ==============================================================================
class CmdId(IntEnum):
    UNKNOWN = 0
    HEARTBEAT = 1
    GET_STATUS = 2
    GET_VERSIONS = 3
    GET_PATHS = 4
    GET_HEARTBEAT = 5
    CONFIG_AND_TEST = 6
    APPLY_UPDATE = 7
    ROLLBACK = 8
    OK = 9
    FAIL = 10
    SET_RESTART_FUNCTION = 11
    GET_RESTART_FUNCTION = 12  # 메인 프로그램 자동 재실행(launch_main_app) 설정 상태 조회
    SET_GITHUB_CONFIG = 13
    GET_GITHUB_CONFIG = 14
    GITHUB_TEST = 15


class Cmd:
    REQ_OFFSET = CMD_REQ_OFFSET
    RES_OFFSET = CMD_RES_OFFSET

    UNKNOWN = int(CmdId.UNKNOWN)
    HEARTBEAT = int(CmdId.HEARTBEAT)
    GET_STATUS = int(CmdId.GET_STATUS)
    GET_VERSIONS = int(CmdId.GET_VERSIONS)
    GET_PATHS = int(CmdId.GET_PATHS)
    GET_HEARTBEAT = int(CmdId.GET_HEARTBEAT)
    CONFIG_AND_TEST = int(CmdId.CONFIG_AND_TEST)
    APPLY_UPDATE = int(CmdId.APPLY_UPDATE)
    ROLLBACK = int(CmdId.ROLLBACK)
    OK = int(CmdId.OK)
    FAIL = int(CmdId.FAIL)
    SET_RESTART_FUNCTION = int(CmdId.SET_RESTART_FUNCTION)
    GET_RESTART_FUNCTION = int(CmdId.GET_RESTART_FUNCTION)
    SET_GITHUB_CONFIG = int(CmdId.SET_GITHUB_CONFIG)
    GET_GITHUB_CONFIG = int(CmdId.GET_GITHUB_CONFIG)
    GITHUB_TEST = int(CmdId.GITHUB_TEST)

    # 요청 전용 상수 (+0)
    REQ_HEARTBEAT = HEARTBEAT + REQ_OFFSET
    REQ_GET_STATUS = GET_STATUS + REQ_OFFSET
    REQ_GET_VERSIONS = GET_VERSIONS + REQ_OFFSET
    REQ_GET_PATHS = GET_PATHS + REQ_OFFSET
    REQ_GET_HEARTBEAT = GET_HEARTBEAT + REQ_OFFSET
    REQ_CONFIG_AND_TEST = CONFIG_AND_TEST + REQ_OFFSET
    REQ_APPLY_UPDATE = APPLY_UPDATE + REQ_OFFSET
    REQ_ROLLBACK = ROLLBACK + REQ_OFFSET
    REQ_SET_RESTART_FUNCTION = SET_RESTART_FUNCTION + REQ_OFFSET
    REQ_GET_RESTART_FUNCTION = GET_RESTART_FUNCTION + REQ_OFFSET
    REQ_SET_GITHUB_CONFIG = SET_GITHUB_CONFIG + REQ_OFFSET
    REQ_GET_GITHUB_CONFIG = GET_GITHUB_CONFIG + REQ_OFFSET
    REQ_GITHUB_TEST = GITHUB_TEST + REQ_OFFSET

    # 응답 전용 상수 (+10000)
    RES_HEARTBEAT = HEARTBEAT + RES_OFFSET
    RES_GET_STATUS = GET_STATUS + RES_OFFSET
    RES_GET_VERSIONS = GET_VERSIONS + RES_OFFSET
    RES_GET_PATHS = GET_PATHS + RES_OFFSET
    RES_GET_HEARTBEAT = GET_HEARTBEAT + RES_OFFSET
    RES_CONFIG_AND_TEST = CONFIG_AND_TEST + RES_OFFSET
    RES_APPLY_UPDATE = APPLY_UPDATE + RES_OFFSET
    RES_ROLLBACK = ROLLBACK + RES_OFFSET
    RES_OK = OK + RES_OFFSET
    RES_FAIL = FAIL + RES_OFFSET
    RES_SET_RESTART_FUNCTION = SET_RESTART_FUNCTION + RES_OFFSET
    RES_GET_RESTART_FUNCTION = GET_RESTART_FUNCTION + RES_OFFSET
    RES_SET_GITHUB_CONFIG = SET_GITHUB_CONFIG + RES_OFFSET
    RES_GET_GITHUB_CONFIG = GET_GITHUB_CONFIG + RES_OFFSET
    RES_GITHUB_TEST = GITHUB_TEST + RES_OFFSET

    STR_UNKNOWN = "UNKNOWN"
    STR_HEARTBEAT = "HEARTBEAT"
    STR_GET_STATUS = "GET_STATUS"
    STR_GET_VERSIONS = "GET_VERSIONS"
    STR_GET_PATHS = "GET_PATHS"
    STR_GET_HEARTBEAT = "GET_HEARTBEAT"
    STR_CONFIG_AND_TEST = "CONFIG_AND_TEST"
    STR_APPLY_UPDATE = "APPLY_UPDATE"
    STR_ROLLBACK = "ROLLBACK"
    STR_OK = "OK"
    STR_FAIL = "FAIL"
    STR_SET_RESTART_FUNCTION = "SET_RESTART_FUNCTION"
    STR_GET_RESTART_FUNCTION = "GET_RESTART_FUNCTION"
    STR_SET_GITHUB_CONFIG = "SET_GITHUB_CONFIG"
    STR_GET_GITHUB_CONFIG = "GET_GITHUB_CONFIG"
    STR_GITHUB_TEST = "GITHUB_TEST"

    _BASE_STR_MAP = {
        int(CmdId.UNKNOWN): STR_UNKNOWN,
        int(CmdId.HEARTBEAT): STR_HEARTBEAT,
        int(CmdId.GET_STATUS): STR_GET_STATUS,
        int(CmdId.GET_VERSIONS): STR_GET_VERSIONS,
        int(CmdId.GET_PATHS): STR_GET_PATHS,
        int(CmdId.GET_HEARTBEAT): STR_GET_HEARTBEAT,
        int(CmdId.CONFIG_AND_TEST): STR_CONFIG_AND_TEST,
        int(CmdId.APPLY_UPDATE): STR_APPLY_UPDATE,
        int(CmdId.ROLLBACK): STR_ROLLBACK,
        int(CmdId.OK): STR_OK,
        int(CmdId.FAIL): STR_FAIL,
        int(CmdId.SET_RESTART_FUNCTION): STR_SET_RESTART_FUNCTION,
        int(CmdId.GET_RESTART_FUNCTION): STR_GET_RESTART_FUNCTION,
        int(CmdId.SET_GITHUB_CONFIG): STR_SET_GITHUB_CONFIG,
        int(CmdId.GET_GITHUB_CONFIG): STR_GET_GITHUB_CONFIG,
        int(CmdId.GITHUB_TEST): STR_GITHUB_TEST,
    }
    _NUM_MAP = {v: k for k, v in _BASE_STR_MAP.items()}

    @classmethod
    def is_response(cls, cmd_val: int) -> bool:
        return int(cmd_val) >= cls.RES_OFFSET

    @classmethod
    def base_code(cls, cmd_val: int) -> int:
        num = int(cmd_val)
        return num - cls.RES_OFFSET if num >= cls.RES_OFFSET else num

    @classmethod
    def to_req(cls, val: int | str) -> int:
        base = cls.base_code(cls.to_int(val))
        return base + cls.REQ_OFFSET if base != cls.UNKNOWN else cls.UNKNOWN

    @classmethod
    def to_res(cls, val: int | str) -> int:
        base = cls.base_code(cls.to_int(val))
        return base + cls.RES_OFFSET if base != cls.UNKNOWN else cls.UNKNOWN

    @classmethod
    def to_str(cls, val: int | str, include_dir_prefix: bool = False) -> str:
        if isinstance(val, int):
            num = int(val)
            is_res = num >= cls.RES_OFFSET
            base = cls.base_code(num)
            name = cls._BASE_STR_MAP.get(base, cls.STR_UNKNOWN)
            if include_dir_prefix and name != cls.STR_UNKNOWN:
                return f"{'RES' if is_res else 'REQ'}_{name}"
            return name

        text = str(val).strip().upper()
        if text.isdigit():
            return cls.to_str(int(text), include_dir_prefix=include_dir_prefix)

        is_res = False
        if text.startswith("RES_"):
            is_res = True
            text = text[4:]
        elif text.startswith("REQ_"):
            text = text[4:]

        name = text if text in cls._NUM_MAP else cls.STR_UNKNOWN
        if include_dir_prefix and name != cls.STR_UNKNOWN:
            return f"{'RES' if is_res else 'REQ'}_{name}"
        return name

    @classmethod
    def to_int(cls, val: int | str, is_response: bool = False) -> int:
        if isinstance(val, int):
            num = int(val)
            if num >= cls.RES_OFFSET:
                base = num - cls.RES_OFFSET
                return (base + cls.RES_OFFSET) if base in cls._BASE_STR_MAP else cls.UNKNOWN
            if num in cls._BASE_STR_MAP:
                if num == cls.UNKNOWN:
                    return cls.UNKNOWN
                return num + (cls.RES_OFFSET if is_response else cls.REQ_OFFSET)
            return cls.UNKNOWN

        text = str(val).strip().upper()
        if text.isdigit():
            return cls.to_int(int(text), is_response=is_response)

        if text.startswith("RES_"):
            is_response = True
            text = text[4:]
        elif text.startswith("REQ_"):
            is_response = False
            text = text[4:]

        base = cls._NUM_MAP.get(text, cls.UNKNOWN)
        if base == cls.UNKNOWN:
            return cls.UNKNOWN
        return base + (cls.RES_OFFSET if is_response else cls.REQ_OFFSET)


# ==============================================================================
# 4. RESPONSE CODE 상수 정의
# ==============================================================================
class ResponseCodeId(IntEnum):
    UNKNOWN = 0
    PROCESSING = 1
    TEST_SUCCESS = 2
    TEST_FAILED = 3
    EXCEPTION = 4
    UNKNOWN_CMD = 5
    INVALID_PACKET = 6
    INVALID_DIRECTION = 7
    FREQUENT_REQUEST_THROTTLED = 8
    HEAVY_TASK_ALREADY_RUNNING = 9


class ResponseCode:
    UNKNOWN = int(ResponseCodeId.UNKNOWN)
    PROCESSING = int(ResponseCodeId.PROCESSING)
    TEST_SUCCESS = int(ResponseCodeId.TEST_SUCCESS)
    TEST_FAILED = int(ResponseCodeId.TEST_FAILED)
    EXCEPTION = int(ResponseCodeId.EXCEPTION)
    UNKNOWN_CMD = int(ResponseCodeId.UNKNOWN_CMD)
    INVALID_PACKET = int(ResponseCodeId.INVALID_PACKET)
    INVALID_DIRECTION = int(ResponseCodeId.INVALID_DIRECTION)
    FREQUENT_REQUEST_THROTTLED = int(ResponseCodeId.FREQUENT_REQUEST_THROTTLED)
    HEAVY_TASK_ALREADY_RUNNING = int(ResponseCodeId.HEAVY_TASK_ALREADY_RUNNING)

    STR_UNKNOWN = "UNKNOWN"
    STR_PROCESSING = "PROCESSING"
    STR_TEST_SUCCESS = "TEST_SUCCESS"
    STR_TEST_FAILED = "TEST_FAILED"
    STR_EXCEPTION = "EXCEPTION"
    STR_UNKNOWN_CMD = "UNKNOWN_CMD"
    STR_INVALID_PACKET = "INVALID_PACKET"
    STR_INVALID_DIRECTION = "INVALID_DIRECTION"
    STR_FREQUENT_REQUEST_THROTTLED = "FREQUENT_REQUEST_THROTTLED"
    STR_HEAVY_TASK_ALREADY_RUNNING = "HEAVY_TASK_ALREADY_RUNNING"

    _STR_MAP = {
        int(ResponseCodeId.UNKNOWN): STR_UNKNOWN,
        int(ResponseCodeId.PROCESSING): STR_PROCESSING,
        int(ResponseCodeId.TEST_SUCCESS): STR_TEST_SUCCESS,
        int(ResponseCodeId.TEST_FAILED): STR_TEST_FAILED,
        int(ResponseCodeId.EXCEPTION): STR_EXCEPTION,
        int(ResponseCodeId.UNKNOWN_CMD): STR_UNKNOWN_CMD,
        int(ResponseCodeId.INVALID_PACKET): STR_INVALID_PACKET,
        int(ResponseCodeId.INVALID_DIRECTION): STR_INVALID_DIRECTION,
        int(ResponseCodeId.FREQUENT_REQUEST_THROTTLED): STR_FREQUENT_REQUEST_THROTTLED,
        int(ResponseCodeId.HEAVY_TASK_ALREADY_RUNNING): STR_HEAVY_TASK_ALREADY_RUNNING,
    }
    _NUM_MAP = {v: k for k, v in _STR_MAP.items()}

    @classmethod
    def to_str(cls, val: int) -> str:
        return cls._STR_MAP.get(int(val), cls.STR_UNKNOWN)

    @classmethod
    def to_int(cls, val: int | str) -> int:
        if isinstance(val, int):
            num = int(val)
            return num if num in cls._STR_MAP else cls.UNKNOWN
        text = str(val).strip().upper()
        if text.isdigit():
            num = int(text)
            return num if num in cls._STR_MAP else cls.UNKNOWN
        return cls._NUM_MAP.get(text, cls.UNKNOWN)


class ShutdownMode:
    SELF = "SELF"
    SERVICE = "SERVICE"


COMMAND_COOLDOWN_MAP = {
    Cmd.GET_STATUS: 2.0,
    Cmd.GET_VERSIONS: 5.0,
    Cmd.GET_PATHS: 10.0,
    Cmd.CONFIG_AND_TEST: 5.0,
    Cmd.APPLY_UPDATE: 60.0,
    Cmd.ROLLBACK: 60.0,
    Cmd.GET_HEARTBEAT: 5.0,
    Cmd.SET_RESTART_FUNCTION: 2.0,
    Cmd.GET_RESTART_FUNCTION: 2.0,
    Cmd.SET_GITHUB_CONFIG: 2.0,
    Cmd.GET_GITHUB_CONFIG: 2.0,
    Cmd.GITHUB_TEST: 5.0,
}

HEARTBEAT_INTERVAL_SEC = 10.0
HEARTBEAT_TIMEOUT_SEC = 90.0
HEARTBEAT_LOG_BURST_COUNT = 5
HEARTBEAT_MISSING_THRESHOLD = 3
HEARTBEAT_RESET_COUNTER_THRESHOLD = 10


# ==============================================================================
# 5. 표준 패킷 베이스 클래스 및 방향별 패킷 클래스
# ==============================================================================
@dataclass
class ProtocolPacket:
    SRC: ClassVar[int] = Src.UNKNOWN

    dst: int
    cmd: int | str
    payload: str = ""
    src: int = field(init=False)

    def __post_init__(self):
        self.src = Src.to_int(self.__class__.SRC)
        self.dst = Src.to_int(self.dst)
        is_res = (self.src == Src.UPDATE_SERVICE)
        self.cmd = Cmd.to_int(self.cmd, is_response=is_res)

    @property
    def is_response(self) -> bool:
        return Cmd.is_response(self.cmd)

    @property
    def base_cmd(self) -> int:
        return Cmd.base_code(self.cmd)

    @property
    def src_name(self) -> str:
        return Src.to_str(self.src)

    @property
    def dst_name(self) -> str:
        return Dst.to_str(self.dst)

    @property
    def cmd_name(self) -> str:
        return Cmd.to_str(self.cmd, include_dir_prefix=False)

    @property
    def cmd_full_name(self) -> str:
        return Cmd.to_str(self.cmd, include_dir_prefix=True)

    def encode(self, use_numeric_node: bool = True, use_numeric_cmd: bool = True) -> bytes:
        src_field = str(int(self.src)) if use_numeric_node else self.src_name
        dst_field = str(int(self.dst)) if use_numeric_node else self.dst_name
        cmd_field = str(int(self.cmd)) if use_numeric_cmd else self.cmd_full_name
        base = f"{src_field}{DELIMITER}{dst_field}{DELIMITER}{cmd_field}"
        if self.payload != "":
            base = f"{base}{DELIMITER}{self.payload}"
        return base.encode(ENCODING)

    def to_str(self, use_numeric_node: bool = True, use_numeric_cmd: bool = True) -> str:
        return self.encode(use_numeric_node=use_numeric_node, use_numeric_cmd=use_numeric_cmd).decode(ENCODING)

    @classmethod
    def decode(cls, raw_data: bytes | str) -> "ProtocolPacket":
        text = raw_data.decode(ENCODING) if isinstance(raw_data, bytes) else raw_data
        parts = text.split(DELIMITER, 3)
        if len(parts) < 3:
            raise ValueError(f"유효하지 않은 패킷 형식입니다: {text}")

        src_val = Src.to_int(parts[0])
        dst_val = Dst.to_int(parts[1])
        is_res = (src_val == Src.UPDATE_SERVICE)
        cmd_val = Cmd.to_int(parts[2], is_response=is_res)
        payload = parts[3] if len(parts) > 3 else ""

        if cls is not ProtocolPacket:
            expected_src = Src.to_int(cls.SRC)
            if src_val != expected_src:
                raise ValueError(
                    f"SRC 불일치: {cls.__name__}는 SRC={Src.to_str(expected_src)}({expected_src})만 허용합니다."
                )
            return cls(dst=dst_val, cmd=cmd_val, payload=payload)

        target_cls = _SRC_SUBCLASS_MAP.get(src_val)
        if target_cls is not None:
            return target_cls(dst=dst_val, cmd=cmd_val, payload=payload)

        raise ValueError(f"알 수 없는 SRC 노드입니다: {parts[0]}")


@dataclass
class UpdateClientPacket(ProtocolPacket):
    SRC: ClassVar[int] = Src.UPDATE_CLIENT


@dataclass
class UpdateServicePacket(ProtocolPacket):
    SRC: ClassVar[int] = Src.UPDATE_SERVICE


_SRC_SUBCLASS_MAP: dict[int, type[ProtocolPacket]] = {
    Src.UPDATE_CLIENT: UpdateClientPacket,
    Src.UPDATE_SERVICE: UpdateServicePacket,
}


# ==============================================================================
# 6. 패킷 빌더 클래스 구현
# ==============================================================================
class PacketBuilder:
    DST: ClassVar[int] = Dst.UNKNOWN

    def __init__(self):
        pass


class UpdateClientToUpdateServicePacketBuilder(PacketBuilder):
    DST: ClassVar[int] = Dst.UPDATE_SERVICE

    def req_heartbeat(self, counter: int, time_val: int) -> UpdateClientPacket:
        return UpdateClientPacket(
            dst=self.DST,
            cmd=Cmd.REQ_HEARTBEAT,
            payload=f"{counter}{DELIMITER}{time_val}",
        )

    def req_get_status(self) -> UpdateClientPacket:
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GET_STATUS)

    def req_get_versions(self) -> UpdateClientPacket:
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GET_VERSIONS)

    def req_get_paths(self) -> UpdateClientPacket:
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GET_PATHS)

    def req_get_heartbeat(self) -> UpdateClientPacket:
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GET_HEARTBEAT)

    def req_config_and_test(self, repo_url: str, json_url: str) -> UpdateClientPacket:
        body = json.dumps({"repo_url": repo_url, "json_url": json_url}, ensure_ascii=False)
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_CONFIG_AND_TEST, payload=body)

    def req_apply_update(self, target_version: str, self_shutdown: bool = True) -> UpdateClientPacket:
        mode = ShutdownMode.SELF if self_shutdown else ShutdownMode.SERVICE
        payload = f"{target_version}{DELIMITER}{mode}" if target_version else mode
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_APPLY_UPDATE, payload=payload)

    def req_rollback(self, target_version: str, self_shutdown: bool = True) -> UpdateClientPacket:
        mode = ShutdownMode.SELF if self_shutdown else ShutdownMode.SERVICE
        return UpdateClientPacket(
            dst=self.DST,
            cmd=Cmd.REQ_ROLLBACK,
            payload=f"{target_version}{DELIMITER}{mode}",
        )

    def req_set_restart_function(self, enabled: bool) -> UpdateClientPacket:
        return UpdateClientPacket(
            dst=self.DST,
            cmd=Cmd.REQ_SET_RESTART_FUNCTION,
            payload="1" if enabled else "0",
        )

    def req_get_restart_function(self) -> UpdateClientPacket:
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GET_RESTART_FUNCTION)

    def req_set_github_config(self, repo_url: str, json_url: str) -> UpdateClientPacket:
        body = json.dumps({"repo_url": repo_url, "json_url": json_url}, ensure_ascii=False)
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_SET_GITHUB_CONFIG, payload=body)

    def req_get_github_config(self) -> UpdateClientPacket:
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GET_GITHUB_CONFIG)

    def req_github_test(self, repo_url: str = "", json_url: str = "") -> UpdateClientPacket:
        body = json.dumps({"repo_url": repo_url, "json_url": json_url}, ensure_ascii=False)
        return UpdateClientPacket(dst=self.DST, cmd=Cmd.REQ_GITHUB_TEST, payload=body)


class UpdateServiceToUpdateClientPacketBuilder(PacketBuilder):
    DST: ClassVar[int] = Dst.UPDATE_CLIENT

    def res_ok(self, data: Any = "", req_cmd: int | str | None = None) -> UpdateServicePacket:
        if isinstance(data, (dict, list)):
            payload = json.dumps(data, ensure_ascii=False)
        else:
            payload = str(data) if data is not None else ""
        target_cmd = Cmd.to_res(req_cmd) if req_cmd is not None else Cmd.RES_OK
        return UpdateServicePacket(dst=self.DST, cmd=target_cmd, payload=payload)

    def res_fail(self, reason_code: str | int) -> UpdateServicePacket:
        code_int = ResponseCode.to_int(reason_code)
        return UpdateServicePacket(dst=self.DST, cmd=Cmd.RES_FAIL, payload=str(code_int))


def parse_bool_payload(payload: str) -> bool:
    val = str(payload).strip().lower()
    if val in ("1", "true", "on", "yes", "y", "enable", "enabled"):
        return True
    if val in ("0", "false", "off", "no", "n", "disable", "disabled"):
        return False
    raise ValueError(f"유효하지 않은 boolean payload입니다: {payload}")


def parse_client_request(
    raw_data: bytes | str,
    expected_dst: int = Dst.UPDATE_SERVICE,
) -> Tuple[bool, Optional[UpdateClientPacket], int]:
    try:
        pkt = UpdateClientPacket.decode(raw_data)
    except ValueError:
        return False, None, ResponseCode.INVALID_PACKET

    if pkt.dst != int(expected_dst) or pkt.is_response:
        return False, pkt, ResponseCode.INVALID_DIRECTION

    return True, pkt, ResponseCode.UNKNOWN


def parse_server_response(
    raw_data: bytes | str,
    expected_dst: int = Dst.UPDATE_CLIENT,
) -> Tuple[bool, Optional[UpdateServicePacket], int]:
    try:
        pkt = UpdateServicePacket.decode(raw_data)
    except ValueError:
        return False, None, ResponseCode.INVALID_PACKET

    if pkt.dst != int(expected_dst) or not pkt.is_response:
        return False, pkt, ResponseCode.INVALID_DIRECTION

    return True, pkt, ResponseCode.UNKNOWN
