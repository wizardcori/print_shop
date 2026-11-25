from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    _HAS_PYSIDE6 = True
except Exception:  # pragma: no cover
    QTimer = None
    QApplication = None
    _HAS_PYSIDE6 = False

try:
    import win32con  # type: ignore
    import win32event  # type: ignore

    _HAS_WIN32_EVENT = True
except Exception:  # pragma: no cover
    win32con = None
    win32event = None
    _HAS_WIN32_EVENT = False

try:
    from Common.log import set_file_tag, logd as _common_logd, loge as _common_loge
    set_file_tag("APP_CONTROL")

except Exception:  # pragma: no cover
    _common_logd = None
    _common_loge = None


def _logd(msg: str) -> None:
    if callable(_common_logd):
        try:
            _common_logd(msg)
        except Exception:
            pass


def _loge(msg: str) -> None:
    if callable(_common_loge):
        try:
            _common_loge(msg)
        except Exception:
            pass


def _default_on_rejected(channel_label: str, reason: str) -> None:
    _loge(f"[CtrlReceiver] 신호 거부/차단 ({channel_label}): {reason}")


CTRL_SECRET_KEY: str = "printshop-ctrl-hmac-secret-2026"

__all__ = [
    "CTRL_SECRET_KEY",
    "ControlAction",
    "ControlSignalState",
    "SignedSignalVerifier",
    "AppControlSignalManager",
    "AppControlSender",
    "AppControlReceiver",
    "QtAppControlReceiver",
    "attach_control_signal",
    "send_stop_signal",
    "send_restart_signal",
]


class ControlAction(str, Enum):
    NONE = "none"
    STOP = "stop"
    RESTART = "restart"


@dataclass
class ControlSignalState:
    action: ControlAction = ControlAction.NONE
    source: str = ""  # "app" 또는 "all"
    triggered_at: float = 0.0
    verified: bool = True
    reason: str = ""
    sender_key: str = ""
    sender_pid: int | None = None
    sender_role: str = ""


class SignedSignalVerifier:
    """수신 시 HMAC 서명, 타임스탬프 유효성, 중복 Nonce 및 발신자 메타데이터를 검증합니다."""

    def __init__(
        self,
        secret_key: bytes | str,
        *,
        max_skew_sec: float = 5.0,
        nonce_ttl_sec: float = 30.0,
    ) -> None:
        self._key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
        self.max_skew_sec = float(max_skew_sec)
        self.nonce_ttl_sec = float(nonce_ttl_sec)
        self._seen_nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def sign_payload(
        self,
        action: ControlAction | str,
        app_key: str,
        nonce: str,
        ts: float | None = None,
        *,
        sender_key: str = "",
        sender_pid: int | None = None,
        sender_role: str = "",
    ) -> dict[str, Any]:
        act_str = action.value if isinstance(action, ControlAction) else str(action)
        timestamp = float(time.time() if ts is None else ts)
        resolved_pid = int(os.getpid() if sender_pid is None else sender_pid)
        payload: dict[str, Any] = {
            "action": act_str,
            "app_key": app_key,
            "nonce": nonce,
            "ts": timestamp,
            "sender_key": str(sender_key or ""),
            "sender_pid": resolved_pid,
            "sender_role": str(sender_role or ""),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["sig"] = hmac.new(self._key, canonical, hashlib.sha256).hexdigest()
        return payload

    def verify_payload(
        self,
        payload: dict[str, Any],
        expected_app_key: str,
    ) -> tuple[bool, str]:
        now = time.time()
        with self._lock:
            expired = [k for k, exp in self._seen_nonces.items() if exp <= now]
            for k in expired:
                del self._seen_nonces[k]

            sig = str(payload.get("sig") or "")
            nonce = str(payload.get("nonce") or "")
            action = str(payload.get("action") or "")
            app_key = str(payload.get("app_key") or "")
            raw_ts = payload.get("ts")
            sender_key = str(payload.get("sender_key") or "")
            raw_sender_pid = payload.get("sender_pid")
            sender_role = str(payload.get("sender_role") or "")

            if not sig or not nonce or action not in (ControlAction.STOP.value, ControlAction.RESTART.value):
                return False, "필수 필드 누락 또는 잘못된 액션"

            if app_key not in (expected_app_key, "ALL"):
                return False, "대상 앱 불일치"

            try:
                ts = float(raw_ts)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False, "잘못된 타임스탬프"

            if abs(now - ts) > self.max_skew_sec:
                return False, "신호 유효 시간 만료"

            if nonce in self._seen_nonces:
                return False, "중복 Nonce(재전송 의심)"

            sender_pid: int | None
            if raw_sender_pid is None or raw_sender_pid == "":
                sender_pid = None
            else:
                try:
                    sender_pid = int(raw_sender_pid)
                except (TypeError, ValueError):
                    return False, "잘못된 발신자 PID"

            unsigned = {
                "action": action,
                "app_key": app_key,
                "nonce": nonce,
                "ts": ts,
                "sender_key": sender_key,
                "sender_pid": sender_pid,
                "sender_role": sender_role,
            }
            canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
            expected_sig = hmac.new(self._key, canonical, hashlib.sha256).hexdigest()

            if not hmac.compare_digest(sig, expected_sig):
                return False, "HMAC 서명 불일치"

            self._seen_nonces[nonce] = now + self.nonce_ttl_sec
            return True, "검증 성공"


class AppControlSignalManager:
    """
    앱별 전용 신호 및 전체 공통 신호를 수신/발송하고,
    종료(STOP) 및 재시작(RESTART) 흐름을 관리하는 클래스.
    """

    def __init__(
        self,
        app_key: str,
        *,
        prefix: str = "PrintShopApp_Ctrl",
        namespace: str = "Local",
        poll_interval_sec: float = 0.2,
        fallback_dir: str | Path | None = None,
        secret_key: bytes | str | None = None,
        max_skew_sec: float = 5.0,
        nonce_ttl_sec: float = 30.0,
        debounce_sec: float = 1.0,
        sender_role: str = "app",
        ignore_self_signals: bool = False,
        ignore_self_restart: bool = True,
        on_stop: Callable[[ControlSignalState], None] | None = None,
        on_restart: Callable[[ControlSignalState], None] | None = None,
        on_rejected: Callable[[str, str], None] | None = None,
        restart_cmd: list[str] | None = None,
        restart_cwd: str | Path | None = None,
    ) -> None:
        if not app_key or not str(app_key).strip():
            raise ValueError("app_key는 비어 있을 수 없습니다.")

        self.app_key = str(app_key).strip()
        self.safe_key = self._sanitize_key(self.app_key)
        self.prefix = self._sanitize_key(prefix)
        self.namespace = namespace.strip("\\") if namespace else "Local"
        self.poll_interval_sec = max(0.05, float(poll_interval_sec))
        self.debounce_sec = max(0.0, float(debounce_sec))
        self.sender_role = str(sender_role or "app")
        self.ignore_self_signals = bool(ignore_self_signals)
        self.ignore_self_restart = bool(ignore_self_restart)

        effective_secret = secret_key if secret_key is not None else CTRL_SECRET_KEY
        self.verifier = (
            SignedSignalVerifier(
                secret_key=effective_secret,
                max_skew_sec=max_skew_sec,
                nonce_ttl_sec=nonce_ttl_sec,
            )
            if effective_secret
            else None
        )

        self.on_stop = on_stop
        self.on_restart = on_restart
        self.on_rejected = on_rejected
        self.restart_cmd = list(restart_cmd) if restart_cmd else None
        self.restart_cwd = str(Path(restart_cwd).resolve()) if restart_cwd else None

        self._lock = threading.Lock()
        self._stop_watcher_event = threading.Event()
        self._signal_event = threading.Event()
        self._state = ControlSignalState()
        self._watcher_thread: threading.Thread | None = None
        self._last_accepted_at: float = 0.0

        base_fallback = (
            Path(fallback_dir).resolve()
            if fallback_dir
            else (Path(os.environ.get("TEMP", "/tmp")) / f"{self.prefix}_signals")
        )
        self._fallback_dir = base_fallback
        self._fallback_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_key(raw: str) -> str:
        return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in raw)

    def _event_name(self, action: ControlAction, scope: str) -> str:
        suffix = self.safe_key if scope == "app" else "ALL"
        name = f"{self.prefix}_{action.value.upper()}_{suffix}"
        if self.namespace:
            return f"{self.namespace}\\{name}"
        return name

    def _flag_file_path(self, action: ControlAction, scope: str) -> Path:
        suffix = self.safe_key if scope == "app" else "ALL"
        return self._fallback_dir / f"{self.prefix}_{action.value.upper()}_{suffix}.signal"

    @property
    def state(self) -> ControlSignalState:
        with self._lock:
            return ControlSignalState(
                action=self._state.action,
                source=self._state.source,
                triggered_at=self._state.triggered_at,
                verified=self._state.verified,
                reason=self._state.reason,
                sender_key=self._state.sender_key,
                sender_pid=self._state.sender_pid,
                sender_role=self._state.sender_role,
            )

    @property
    def is_triggered(self) -> bool:
        return self._signal_event.is_set()

    @property
    def is_stop_requested(self) -> bool:
        with self._lock:
            return self._state.action in (ControlAction.STOP, ControlAction.RESTART)

    @property
    def is_restart_requested(self) -> bool:
        with self._lock:
            return self._state.action == ControlAction.RESTART

    def start_listening(self) -> None:
        with self._lock:
            if self._watcher_thread is not None and self._watcher_thread.is_alive():
                return
            self._stop_watcher_event.clear()
            self._watcher_thread = threading.Thread(
                target=self._watch_loop,
                name=f"CtrlSignal-{self.safe_key}",
                daemon=True,
            )
            self._watcher_thread.start()

    def stop_listening(self, timeout: float = 2.0) -> None:
        self._stop_watcher_event.set()
        thread = self._watcher_thread
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=timeout)

    def wait_for_signal(self, timeout: float | None = None) -> ControlSignalState | None:
        triggered = self._signal_event.wait(timeout=timeout)
        if not triggered:
            return None
        return self.state

    def reset_signal(self, *, clear_external_signals: bool = True) -> None:
        with self._lock:
            self._state = ControlSignalState()
        self._signal_event.clear()

        if clear_external_signals:
            for action in (ControlAction.STOP, ControlAction.RESTART):
                for scope in ("app", "all"):
                    self._reset_single_channel(action, scope)

    def _reset_single_channel(self, action: ControlAction, scope: str) -> None:
        flag_path = self._flag_file_path(action, scope)
        try:
            if flag_path.exists():
                flag_path.unlink()
        except Exception:
            pass

        if _HAS_WIN32_EVENT and sys.platform == "win32":
            ev_name = self._event_name(action, scope)
            h_ev = None
            try:
                h_ev = win32event.CreateEvent(None, True, False, ev_name)
                win32event.ResetEvent(h_ev)
            except Exception:
                pass
            finally:
                if h_ev is not None:
                    try:
                        win32event.CloseHandle(h_ev)
                    except Exception:
                        pass

    def send_signal(
        self,
        action: ControlAction,
        *,
        scope: str = "app",
        target_app_key: str | None = None,
        nonce: str | None = None,
        sender_key: str | None = None,
        sender_pid: int | None = None,
        sender_role: str | None = None,
    ) -> None:
        if action not in (ControlAction.STOP, ControlAction.RESTART):
            raise ValueError(f"유효하지 않은 제어 액션입니다: {action}")
        if scope not in ("app", "all"):
            raise ValueError(f"유효하지 않은 신호 범위입니다: {scope}")

        effective_raw_key = target_app_key.strip() if target_app_key else self.app_key
        effective_key = self._sanitize_key(effective_raw_key)
        suffix = effective_key if scope == "app" else "ALL"
        flag_path = self._fallback_dir / f"{self.prefix}_{action.value.upper()}_{suffix}.signal"

        resolved_sender_key = (sender_key if sender_key is not None else self.app_key).strip()
        resolved_sender_pid = int(os.getpid() if sender_pid is None else sender_pid)
        resolved_sender_role = (sender_role if sender_role is not None else self.sender_role).strip()

        if self.verifier is not None:
            sig_nonce = nonce or f"{resolved_sender_pid}-{time.monotonic_ns()}"
            signed = self.verifier.sign_payload(
                action=action,
                app_key=effective_raw_key if scope == "app" else "ALL",
                nonce=sig_nonce,
                sender_key=resolved_sender_key,
                sender_pid=resolved_sender_pid,
                sender_role=resolved_sender_role,
            )
            flag_path.write_text(json.dumps(signed, ensure_ascii=False), encoding="utf-8")
        else:
            meta = {
                "ts": time.time(),
                "sender_key": resolved_sender_key,
                "sender_pid": resolved_sender_pid,
                "sender_role": resolved_sender_role,
            }
            flag_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        if _HAS_WIN32_EVENT and sys.platform == "win32":
            raw_name = f"{self.prefix}_{action.value.upper()}_{suffix}"
            ev_name = f"{self.namespace}\\{raw_name}" if self.namespace else raw_name
            h_ev = win32event.CreateEvent(None, True, False, ev_name)
            try:
                win32event.SetEvent(h_ev)
            finally:
                win32event.CloseHandle(h_ev)

    def request_stop(
        self,
        *,
        scope: str = "app",
        target_app_key: str | None = None,
        nonce: str | None = None,
        sender_key: str | None = None,
        sender_pid: int | None = None,
        sender_role: str | None = None,
    ) -> None:
        self.send_signal(
            ControlAction.STOP,
            scope=scope,
            target_app_key=target_app_key,
            nonce=nonce,
            sender_key=sender_key,
            sender_pid=sender_pid,
            sender_role=sender_role,
        )

    def request_restart(
        *,
        scope: str = "app",
        target_app_key: str | None = None,
        nonce: str | None = None,
        sender_key: str | None = None,
        sender_pid: int | None = None,
        sender_role: str | None = None,
    ) -> None:
        self.send_signal(
            ControlAction.RESTART,
            scope=scope,
            target_app_key=target_app_key,
            nonce=nonce,
            sender_key=sender_key,
            sender_pid=sender_pid,
            sender_role=sender_role,
        )

    def _reject_signal(self, channel_label: str, reason: str) -> None:
        if callable(self.on_rejected):
            try:
                self.on_rejected(channel_label, reason)
            except Exception:
                pass

    def _is_self_originated(
        self,
        action: ControlAction,
        sender_key: str,
        sender_pid: int | None,
    ) -> tuple[bool, str]:
        same_pid = sender_pid is not None and sender_pid == os.getpid()
        same_key = bool(sender_key) and sender_key == self.app_key

        if self.ignore_self_signals and (same_pid or same_key):
            return True, f"자기 발신 신호 차단 (sender_key={sender_key}, sender_pid={sender_pid})"

        if action == ControlAction.RESTART and self.ignore_self_restart and (same_pid or same_key):
            return True, f"자기 발신 RESTART 차단 (sender_key={sender_key}, sender_pid={sender_pid})"

        return False, ""

    def _read_and_verify_payload(
        self,
        action: ControlAction,
        scope: str,
        flag_path: Path,
    ) -> tuple[bool, dict[str, Any]]:
        if self.verifier is None:
            data: dict[str, Any] = {}
            try:
                if flag_path.is_file():
                    raw = flag_path.read_text(encoding="utf-8")
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        data = parsed
            except Exception:
                pass
            finally:
                try:
                    if flag_path.exists():
                        flag_path.unlink()
                except Exception:
                    pass
            return True, data

        if not flag_path.is_file():
            self._reject_signal(f"{scope}:{action.value}", "서명 페이로드 파일 없음")
            return False, {}

        try:
            raw_text = flag_path.read_text(encoding="utf-8")
        except Exception as exc:
            self._reject_signal(f"{scope}:{action.value}", f"신호 파일 읽기 실패: {exc}")
            return False, {}
        finally:
            try:
                if flag_path.exists():
                    flag_path.unlink()
            except Exception:
                pass

        try:
            data = json.loads(raw_text)
        except Exception as exc:
            self._reject_signal(f"{scope}:{action.value}", f"JSON 파싱 실패: {exc}")
            return False, {}

        if not isinstance(data, dict):
            self._reject_signal(f"{scope}:{action.value}", "페이로드 형식 오류")
            return False, {}

        if str(data.get("action") or "") != action.value:
            self._reject_signal(f"{scope}:{action.value}", "액션 불일치")
            return False, {}

        ok, reason = self.verifier.verify_payload(data, expected_app_key=self.app_key)
        if not ok:
            self._reject_signal(f"{scope}:{action.value}", reason)
            return False, {}
        return True, data

    def _consume_detected_signal(self, action: ControlAction, source: str, via_file: bool) -> None:
        if _HAS_WIN32_EVENT and sys.platform == "win32":
            ev_name = self._event_name(action, source)
            h_ev = None
            try:
                h_ev = win32event.CreateEvent(None, True, False, ev_name)
                win32event.ResetEvent(h_ev)
            except Exception:
                pass
            finally:
                if h_ev is not None:
                    try:
                        win32event.CloseHandle(h_ev)
                    except Exception:
                        pass

        flag_path = self._flag_file_path(action, source)
        if self.verifier is not None and not via_file:
            if not flag_path.is_file():
                return

        payload: dict[str, Any] = {}
        if via_file or self.verifier is not None:
            ok, payload = self._read_and_verify_payload(action, source, flag_path)
            if not ok:
                return

        sender_key = str(payload.get("sender_key") or "")
        raw_pid = payload.get("sender_pid")
        sender_pid = int(raw_pid) if isinstance(raw_pid, int) or (isinstance(raw_pid, str) and raw_pid.isdigit()) else None
        sender_role = str(payload.get("sender_role") or "")

        blocked, block_reason = self._is_self_originated(action, sender_key, sender_pid)
        if blocked:
            self._reject_signal(f"{source}:{action.value}", block_reason)
            return

        now = time.time()
        with self._lock:
            if self.debounce_sec > 0 and (now - self._last_accepted_at) < self.debounce_sec:
                return
            self._last_accepted_at = now

            if self._state.action == ControlAction.NONE:
                self._state = ControlSignalState(
                    action=action,
                    source=source,
                    triggered_at=now,
                    verified=True,
                    reason="verified" if self.verifier else "unverified",
                    sender_key=sender_key,
                    sender_pid=sender_pid,
                    sender_role=sender_role,
                )
            elif action == ControlAction.RESTART and self._state.action == ControlAction.STOP:
                self._state.action = ControlAction.RESTART
                self._state.triggered_at = now
                self._state.sender_key = sender_key
                self._state.sender_pid = sender_pid
                self._state.sender_role = sender_role

        self._signal_event.set()

        current_state = self.state
        if action == ControlAction.RESTART and callable(self.on_restart):
            try:
                self.on_restart(current_state)
            except Exception:
                pass
        elif callable(self.on_stop):
            try:
                self.on_stop(current_state)
            except Exception:
                pass

    def _watch_loop(self) -> None:
        channels: list[tuple[ControlAction, str, Any, Path]] = []

        for action in (ControlAction.RESTART, ControlAction.STOP):
            for scope in ("app", "all"):
                flag_path = self._flag_file_path(action, scope)
                h_ev = None
                if _HAS_WIN32_EVENT and sys.platform == "win32":
                    try:
                        h_ev = win32event.CreateEvent(None, True, False, self._event_name(action, scope))
                    except Exception:
                        h_ev = None
                channels.append((action, scope, h_ev, flag_path))

        try:
            timeout_ms = int(self.poll_interval_sec * 1000)
            handles = [ch[2] for ch in channels if ch[2] is not None]

            while not self._stop_watcher_event.is_set():
                if _HAS_WIN32_EVENT and sys.platform == "win32" and handles:
                    rc = win32event.WaitForMultipleObjects(handles, False, timeout_ms)
                    if win32con.WAIT_OBJECT_0 <= rc < win32con.WAIT_OBJECT_0 + len(handles):
                        matched_handle = handles[rc - win32con.WAIT_OBJECT_0]
                        for action, scope, h_ev, _ in channels:
                            if h_ev == matched_handle:
                                self._consume_detected_signal(action, scope, via_file=False)
                                break
                else:
                    self._stop_watcher_event.wait(self.poll_interval_sec)

                for action, scope, _, flag_path in channels:
                    if flag_path.exists():
                        self._consume_detected_signal(action, scope, via_file=True)
        finally:
            for _, _, h_ev, _ in channels:
                if h_ev is not None:
                    try:
                        win32event.CloseHandle(h_ev)
                    except Exception:
                        pass

    def spawn_restarted_process(self) -> subprocess.Popen[bytes]:
        if self.restart_cmd:
            cmd = list(self.restart_cmd)
        elif getattr(sys, "frozen", False):
            cmd = [sys.executable, *sys.argv[1:]]
        else:
            cmd = [sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]]

        cwd = self.restart_cwd or os.getcwd()
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        return subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def execute_shutdown_or_restart(
        self,
        *,
        cleanup_fn: Callable[[], None] | None = None,
        exit_code: int = 0,
    ) -> None:
        should_restart = self.is_restart_requested
        self.stop_listening()

        if callable(cleanup_fn):
            try:
                cleanup_fn()
            except Exception:
                pass

        if should_restart:
            self.spawn_restarted_process()

        sys.exit(exit_code)


class AppControlSender:
    """대상 앱 또는 전체 앱(ALL)에 STOP / RESTART 제어 신호를 발송하는 클래스."""

    def __init__(
        self,
        sender_app_key: str = "ControlSender",
        *,
        sender_role: str = "sender",
        sender_pid: int | None = None,
        secret_key: bytes | str | None = None,
        namespace: str = "Local",
        fallback_dir: str | Path | None = None,
        prefix: str = "PrintShopApp_Ctrl",
    ) -> None:
        self.sender_app_key = sender_app_key.strip() or "ControlSender"
        self.sender_role = sender_role.strip() or "sender"
        self.sender_pid = int(os.getpid() if sender_pid is None else sender_pid)
        self._manager = AppControlSignalManager(
            app_key=self.sender_app_key,
            prefix=prefix,
            namespace=namespace,
            fallback_dir=fallback_dir,
            secret_key=secret_key,
            sender_role=self.sender_role,
        )

    def stop_app(self, target_app_key: str, *, nonce: str | None = None) -> None:
        self._manager.send_signal(
            ControlAction.STOP,
            scope="app",
            target_app_key=target_app_key,
            nonce=nonce,
            sender_key=self.sender_app_key,
            sender_pid=self.sender_pid,
            sender_role=self.sender_role,
        )

    def restart_app(self, target_app_key: str, *, nonce: str | None = None) -> None:
        self._manager.send_signal(
            ControlAction.RESTART,
            scope="app",
            target_app_key=target_app_key,
            nonce=nonce,
            sender_key=self.sender_app_key,
            sender_pid=self.sender_pid,
            sender_role=self.sender_role,
        )

    def stop_all(self, *, nonce: str | None = None) -> None:
        self._manager.send_signal(
            ControlAction.STOP,
            scope="all",
            target_app_key="ALL",
            nonce=nonce,
            sender_key=self.sender_app_key,
            sender_pid=self.sender_pid,
            sender_role=self.sender_role,
        )

    def restart_all(self, *, nonce: str | None = None) -> None:
        self._manager.send_signal(
            ControlAction.RESTART,
            scope="all",
            target_app_key="ALL",
            nonce=nonce,
            sender_key=self.sender_app_key,
            sender_pid=self.sender_pid,
            sender_role=self.sender_role,
        )

    def clear_signals(self, target_app_key: str | None = None) -> None:
        if target_app_key:
            temp_mgr = AppControlSignalManager(
                app_key=target_app_key,
                prefix=self._manager.prefix,
                namespace=self._manager.namespace,
                fallback_dir=self._manager._fallback_dir,  # type: ignore[arg-defined]
                secret_key=None,
            )
            temp_mgr.reset_signal(clear_external_signals=True)
            return
        self._manager.reset_signal(clear_external_signals=True)


class AppControlReceiver:
    """대상 앱 기준으로 STOP/RESTART 제어 신호를 감시하고 종료/재시작을 처리하는 클래스."""

    def __init__(
        self,
        app_name: str,
        *,
        cleanup_fn: Callable[[], None] | None = None,
        secret_key: bytes | str | None = None,
        poll_interval_sec: float = 0.2,
        exit_code: int = 0,
        sender_role: str = "app",
        ignore_self_signals: bool = False,
        ignore_self_restart: bool = True,
        on_rejected: Callable[[str, str], None] | None = None,
        auto_start: bool = True,
    ) -> None:
        self.app_name = app_name
        self.cleanup_fn = cleanup_fn
        self.exit_code = exit_code

        _logd(
            f"[CtrlReceiver] 제어 신호 리스너 연결 시작 (app_name={app_name}, "
            f"role={sender_role}, ignore_self={ignore_self_signals}, ignore_self_restart={ignore_self_restart})"
        )
        try:
            self.manager = AppControlSignalManager(
                app_key=app_name,
                secret_key=secret_key,
                poll_interval_sec=poll_interval_sec,
                sender_role=sender_role,
                ignore_self_signals=ignore_self_signals,
                ignore_self_restart=ignore_self_restart,
                on_rejected=on_rejected if on_rejected is not None else _default_on_rejected,
            )
            self.manager.on_stop = self._on_triggered
            self.manager.on_restart = self._on_triggered
            if auto_start:
                self.start()
        except Exception as exc:
            _loge(f"[CtrlReceiver] 제어 신호 리스너 연결 실패 (app_name={app_name}): {exc}")
            raise

    def _on_triggered(self, state: ControlSignalState) -> None:
        action_val = state.action.value if isinstance(state.action, ControlAction) else str(state.action)
        _logd(
            f"[CtrlReceiver] 제어 신호 트리거 수신 (app_name={self.app_name}, "
            f"action={action_val}, sender={state.sender_key}:{state.sender_pid})"
        )
        try:
            self.manager.execute_shutdown_or_restart(
                cleanup_fn=self.cleanup_fn,
                exit_code=self.exit_code,
            )
        except SystemExit:
            raise
        except Exception as exc:
            _loge(f"[CtrlReceiver] 종료/재시작 실행 중 오류 (app_name={self.app_name}): {exc}")
            raise

    def start(self) -> None:
        self.manager.start_listening()
        _logd(f"[CtrlReceiver] 제어 신호 리스너 연결 및 감시 시작 완료 (app_name={self.app_name})")

    def stop(self, timeout: float = 2.0) -> None:
        self.manager.stop_listening(timeout=timeout)


class QtAppControlReceiver(AppControlReceiver):
    """PySide6 메인 이벤트 루프(QApplication.quit)를 통해 종료/재시작을 수행하는 수신기."""

    def __init__(
        self,
        app_name: str,
        qt_app: Any | None = None,
        *,
        cleanup_fn: Callable[[], None] | None = None,
        secret_key: bytes | str | None = None,
        poll_interval_sec: float = 0.2,
        exit_code: int = 0,
        sender_role: str = "app",
        ignore_self_signals: bool = False,
        ignore_self_restart: bool = True,
        on_rejected: Callable[[str, str], None] | None = None,
        auto_start: bool = True,
    ) -> None:
        if not _HAS_PYSIDE6 or QTimer is None or QApplication is None:
            raise RuntimeError("PySide6가 설치되어 있지 않아 QtAppControlReceiver를 사용할 수 없습니다.")

        self.qt_app = qt_app if qt_app is not None else QApplication.instance()
        self.should_restart: bool = False
        self.last_state: ControlSignalState | None = None

        super().__init__(
            app_name,
            cleanup_fn=cleanup_fn,
            secret_key=secret_key,
            poll_interval_sec=poll_interval_sec,
            exit_code=exit_code,
            sender_role=sender_role,
            ignore_self_signals=ignore_self_signals,
            ignore_self_restart=ignore_self_restart,
            on_rejected=on_rejected,
            auto_start=False,
        )
        self.manager.on_stop = self._on_qt_triggered
        self.manager.on_restart = self._on_qt_triggered

        if auto_start:
            self.start()

    def _on_qt_triggered(self, state: ControlSignalState) -> None:
        action_val = state.action.value if isinstance(state.action, ControlAction) else str(state.action)
        self.last_state = state
        self.should_restart = state.action == ControlAction.RESTART
        _logd(
            f"[QtCtrlReceiver] 제어 신호 트리거 수신 (app_name={self.app_name}, "
            f"action={action_val}, restart={self.should_restart}, "
            f"sender={state.sender_key}:{state.sender_pid})"
        )
        self.stop()

        target_app = self.qt_app or QApplication.instance()
        if target_app is not None:
            QTimer.singleShot(0, target_app.quit)
        else:
            self._on_triggered(state)

    def finalize_shutdown_or_restart(
        self,
        *,
        cleanup_fn: Callable[[], None] | None = None,
        before_restart: Callable[[], None] | None = None,
        exit_code: int | None = None,
    ) -> int:
        """Qt 이벤트 루프 종료 후 정리, 재시작 프로세스 실행 및 종료 코드 반환."""
        self.stop()
        effective_cleanup = cleanup_fn if cleanup_fn is not None else self.cleanup_fn
        if callable(effective_cleanup):
            try:
                effective_cleanup()
            except Exception as exc:
                _loge(f"[QtCtrlReceiver] cleanup_fn 실행 중 오류 (app_name={self.app_name}): {exc}")

        if self.should_restart:
            if callable(before_restart):
                try:
                    before_restart()
                except Exception as exc:
                    _loge(f"[QtCtrlReceiver] before_restart 실행 중 오류 (app_name={self.app_name}): {exc}")
            try:
                self.manager.spawn_restarted_process()
            except Exception as exc:
                _loge(f"[QtCtrlReceiver] 재시작 프로세스 실행 실패 (app_name={self.app_name}): {exc}")

        return self.exit_code if exit_code is None else exit_code


def attach_control_signal(
    app_name: str,
    *,
    cleanup_fn: Callable[[], None] | None = None,
    secret_key: bytes | str | None = None,
    poll_interval_sec: float = 0.2,
    exit_code: int = 0,
    sender_role: str = "app",
    ignore_self_signals: bool = False,
    ignore_self_restart: bool = True,
    on_rejected: Callable[[str, str], None] | None = None,
) -> AppControlSignalManager:
    receiver = AppControlReceiver(
        app_name=app_name,
        cleanup_fn=cleanup_fn,
        secret_key=secret_key,
        poll_interval_sec=poll_interval_sec,
        exit_code=exit_code,
        sender_role=sender_role,
        ignore_self_signals=ignore_self_signals,
        ignore_self_restart=ignore_self_restart,
        on_rejected=on_rejected,
        auto_start=True,
    )
    return receiver.manager


def send_stop_signal(
    target_app_key: str,
    *,
    sender_app_key: str = "ControlSender",
    sender_role: str = "sender",
    namespace: str = "Local",
    fallback_dir: str | Path | None = None,
    secret_key: bytes | str | None = None,
) -> None:
    sender = AppControlSender(
        sender_app_key=sender_app_key,
        sender_role=sender_role,
        namespace=namespace,
        fallback_dir=fallback_dir,
        secret_key=secret_key,
    )
    sender.stop_app(target_app_key)


def send_restart_signal(
    target_app_key: str,
    *,
    sender_app_key: str = "ControlSender",
    sender_role: str = "sender",
    namespace: str = "Local",
    fallback_dir: str | Path | None = None,
    secret_key: bytes | str | None = None,
) -> None:
    sender = AppControlSender(
        sender_app_key=sender_app_key,
        sender_role=sender_role,
        namespace=namespace,
        fallback_dir=fallback_dir,
        secret_key=secret_key,
    )
    sender.restart_app(target_app_key)