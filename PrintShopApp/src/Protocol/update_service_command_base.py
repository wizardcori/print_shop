# service_command_standard.py
from abc import ABC, abstractmethod
from typing import Any

from Protocol.update_service_protocol import (
    Cmd,
    UpdateServicePacket,
    UpdateServiceToUpdateClientPacketBuilder,
)


class UpdateServiceCommandBase(ABC):
    """
    UpdateService가 구현해야 하는 커맨드별 가상함수 표준 계약.
    새 커맨드 추가 시 이곳에 추상 메서드를 정의하면 상속 클래스에서 구현이 강제됩니다.
    """

    def __init__(self, packet_builder: UpdateServiceToUpdateClientPacketBuilder):
        self.packet_builder = packet_builder

    @abstractmethod
    def on_cmd_get_status(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_get_versions(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_get_paths(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_get_heartbeat(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_set_github_config(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_get_github_config(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_github_test(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_config_and_test(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_set_restart_function(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    @abstractmethod
    def on_cmd_get_restart_function(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        raise NotImplementedError

    # --- 공통 응답 조립 헬퍼 ---
    def ok(self, cmd_val: int, data: Any = "") -> UpdateServicePacket:
        return self.packet_builder.res_ok(data, req_cmd=cmd_val)

    def fail(self, reason_code: int | str) -> UpdateServicePacket:
        return self.packet_builder.res_fail(reason_code)


# 프로토콜 CMD와 표준 가상함수 이름 간 매핑
CMD_STANDARD_METHOD_MAP: dict[int, str] = {
    Cmd.GET_STATUS: "on_cmd_get_status",
    Cmd.GET_VERSIONS: "on_cmd_get_versions",
    Cmd.GET_PATHS: "on_cmd_get_paths",
    Cmd.GET_HEARTBEAT: "on_cmd_get_heartbeat",
    Cmd.SET_GITHUB_CONFIG: "on_cmd_set_github_config",
    Cmd.GET_GITHUB_CONFIG: "on_cmd_get_github_config",
    Cmd.GITHUB_TEST: "on_cmd_github_test",
    Cmd.CONFIG_AND_TEST: "on_cmd_config_and_test",
    Cmd.SET_RESTART_FUNCTION: "on_cmd_set_restart_function",
    Cmd.GET_RESTART_FUNCTION: "on_cmd_get_restart_function",
}
