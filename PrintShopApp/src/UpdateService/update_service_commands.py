# UpdateService/update_service_commands.py
import json
from typing import Any, Callable, Optional, Tuple

from Protocol.update_service_command_base import UpdateServiceCommandBase
from Protocol.update_service_protocol import (
    ResponseCode,
    UpdateServicePacket,
    UpdateServiceToUpdateClientPacketBuilder,
    parse_bool_payload,
)


class UpdateServiceCommands(UpdateServiceCommandBase):
    """UpdateServiceCommandBase를 상속한 UpdateService 기본 커맨드 가상함수 구현체"""

    def __init__(
        self,
        packet_builder: UpdateServiceToUpdateClientPacketBuilder,
        on_get_status: Callable[[], dict],
        on_get_versions: Callable[[], list],
        on_get_paths: Callable[[], dict],
        on_get_heartbeat: Callable[[], dict],
        on_set_github_config: Callable[[str, str], Tuple[int, dict]],
        on_get_github_config: Callable[[], dict],
        on_github_test: Callable[[str, str], Tuple[int, dict]],
        on_set_restart_function: Callable[[bool], Any],
        on_get_restart_function: Callable[[], bool],
        on_config_and_test: Optional[Callable[[str, str], Tuple[int, dict]]] = None,
    ):
        super().__init__(packet_builder)
        self._on_get_status = on_get_status
        self._on_get_versions = on_get_versions
        self._on_get_paths = on_get_paths
        self._on_get_heartbeat = on_get_heartbeat
        self._on_set_github_config = on_set_github_config
        self._on_get_github_config = on_get_github_config
        self._on_github_test = on_github_test
        self._on_set_restart_function = on_set_restart_function
        self._on_get_restart_function = on_get_restart_function
        self._on_config_and_test = on_config_and_test

    def on_cmd_get_status(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            return self.ok(cmd_val, self._on_get_status())
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_get_versions(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            return self.ok(cmd_val, self._on_get_versions())
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_get_paths(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            return self.ok(cmd_val, self._on_get_paths())
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_get_heartbeat(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            return self.ok(cmd_val, self._on_get_heartbeat())
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_set_github_config(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            cfg = json.loads(payload) if payload else {}
            code, result_data = self._on_set_github_config(
                str(cfg.get("repo_url", "")).strip(),
                str(cfg.get("json_url", "")).strip(),
            )
            if code == ResponseCode.TEST_SUCCESS:
                return self.ok(cmd_val, result_data)
            return self.fail(code)
        except Exception:
            return self.fail(ResponseCode.INVALID_PACKET)

    def on_cmd_get_github_config(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            return self.ok(cmd_val, self._on_get_github_config())
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_github_test(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            cfg = json.loads(payload) if payload else {}
            code, result_data = self._on_github_test(
                str(cfg.get("repo_url", "")).strip(),
                str(cfg.get("json_url", "")).strip(),
            )
            if code == ResponseCode.TEST_SUCCESS:
                return self.ok(cmd_val, result_data)
            return self.fail(code)
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_config_and_test(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            cfg = json.loads(payload) if payload else {}
            repo_url = str(cfg.get("repo_url", "")).strip()
            json_url = str(cfg.get("json_url", "")).strip()

            if callable(self._on_config_and_test):
                code, result_data = self._on_config_and_test(repo_url, json_url)
                if code == ResponseCode.TEST_SUCCESS:
                    return self.ok(cmd_val, result_data)
                return self.fail(code)

            set_code, _ = self._on_set_github_config(repo_url, json_url)
            if set_code != ResponseCode.TEST_SUCCESS:
                return self.fail(set_code)

            test_code, test_data = self._on_github_test(repo_url, json_url)
            if test_code == ResponseCode.TEST_SUCCESS:
                return self.ok(cmd_val, test_data)
            return self.fail(test_code)
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_set_restart_function(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            enabled = parse_bool_payload(payload)
            self._on_set_restart_function(enabled)
            return self.ok(cmd_val, "1" if enabled else "0")
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)

    def on_cmd_get_restart_function(self, cmd_val: int, payload: str) -> UpdateServicePacket:
        try:
            enabled = bool(self._on_get_restart_function())
            return self.ok(cmd_val, "1" if enabled else "0")
        except Exception:
            return self.fail(ResponseCode.EXCEPTION)
