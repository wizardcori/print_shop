"""
================================================================================
모듈명: prio_worker_queue.py
목적  : PySide6 기반 우선순위 백그라운드 작업 큐, 이벤트 시점 기록 및
        윈도우별 안전한 결과 라우팅 엔진
================================================================================

[전체 아키텍처 및 데이터 흐름]
1. TaskManager (Singleton)
   - 앱 전역에서 단일 백그라운드 워커 스레드(PriorityWorkerThread)와
     디스패처(ScopedTaskDispatcher)를 관리합니다.
   - 호출자는 TaskManager().submit(...) 한 번으로
     [파라미터 검증 -> 리스너 등록 -> 시점 레코드 생성 -> 우선순위 큐 적재]를 수행합니다.

2. TaskEventTimestamps (생명주기 시점 기록기)
   - 작업별로 등록(registered), 시작(started), 취소(cancelled), 종료(finished) 시점을
     벽시계 문자열과 단조 시계(monotonic)로 함께 기록합니다.
   - 이후 대기 시간(wait_sec), 실행 시간(run_sec), 전체 소요 시간(total_sec),
     취소 후 종료 지연(cancel_to_finish_sec)을 조회·로그·리포트에 활용할 수 있습니다.

3. PriorityWorkerThread (QThread)
   - Python 표준 PriorityQueue를 사용해 우선순위(HIGH=1 < NORMAL=5 < LOW=10)와
     입력 순서(_counter) 기준으로 작업을 하나씩 꺼내 순차 실행합니다.
   - 실행 중인 작업마다 CancelToken(취소 이벤트 + 외부 프로세스 kill 훅 목록)을 부여합니다.

4. ScopedTaskDispatcher & _MainThreadRelay (QObject)
   - 전역 시그널 브로드캐스트 대신 task_key에 바인딩된 TaskListenerBase에만 이벤트를 전달합니다.
   - 워커 스레드에서 발생한 진행률/완료 이벤트를 Qt Signal(_MainThreadRelay)을 통해
     메인(UI) 스레드로 안전하게 마샬링한 뒤 리스너 메서드를 호출합니다.

5. 윈도우 및 애플리케이션 종료 감지 정책
   - 개별 윈도우 종료 시: TaskManager().on_window_closing(listener) 호출
     * cancel_on_close=True 로 등록된 작업 -> 취소 시점 기록, 즉시 취소 및 외부 프로세스 트리 kill
     * cancel_on_close=False 로 등록된 작업 -> 리스너만 분리하고 백그라운드 계속 실행
   - 안전망: TaskListenerBase(owner_widget=window)의 weakref 생존 검사 + window.destroyed 시그널
   - 앱 전체 종료 시: app.aboutToQuit.connect(TaskManager.on_about_to_quit)
     -> 남은 모든 대기/실행 작업 취소, 외부 프로세스 kill, 워커 스레드 종료

[파일 분리 가이드]
- 본 파일 하단의 `# ==================== [SAMPLE 영역 시작] ====================` 아래 코드를
  별도 파일(예: `sample_queue_demo.py`)로 옮기고, 상단 코어 클래스만 임포트하면
  프로덕션 모듈과 데모 코드를 즉시 분리할 수 있습니다.
================================================================================
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import weakref
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from queue import PriorityQueue
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

# ------------------------------------------------------------------------------
# 로깅 설정: 프로젝트 공통 Common.log (logd, loge) 우선 사용, 미존재 시 표준 logging 폴백
# ------------------------------------------------------------------------------
try:
    from Common.log import logd, loge, set_file_tag  # type: ignore

    set_file_tag("PRIO_QUEUE")
except Exception:
    _fallback_logger = logging.getLogger("PRIO_QUEUE")
    if not _fallback_logger.handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [PRIO_QUEUE] %(message)s", "%H:%M:%S")
        )
        _fallback_logger.addHandler(_handler)
        _fallback_logger.setLevel(logging.DEBUG)

    def logd(msg: str, *args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        _fallback_logger.debug(msg, *args, **kwargs)

    def loge(msg: str, *args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        _fallback_logger.error(msg, *args, **kwargs)


def _now_timestamp_str() -> str:
    """로그 및 리포트 기록용 현재 시각 문자열(밀리초 단위)을 반환합니다."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# ==============================================================================
# 1. 작업별 우선순위 상수 클래스
# ==============================================================================
class TaskPriority:
    """PriorityQueue 정렬 기준 상수 (숫자가 작을수록 먼저 실행됨)."""

    HIGH = 1     # 긴급 작업 (최우선 처리)
    NORMAL = 5   # 일반 작업 (기본값)
    LOW = 10     # 후순위 작업 (여유 시 처리)


# ==============================================================================
# 2. 작업 이벤트 시점 기록 및 경과 시간 계산 데이터클래스
# ==============================================================================
@dataclass
class TaskEventTimestamps:
    """
    단일 작업의 상태 전이 시점(등록/시작/취소/종료)을 저장하고
    대기 시간·실행 시간·총 체류 시간·취소 반영 지연을 계산합니다.
    - 경과 시간 계산에는 시스템 시계 변경 영향을 받지 않는 time.monotonic()을 사용합니다.
    - 로그/리포트 가독성을 위해 사람이 읽는 시각 문자열(*_at)도 함께 보관합니다.
    """

    task_key: str
    task_name: str
    priority: int
    cancel_on_close: bool = True

    # 단조 시계(초): 정확한 경과 시간 산출용
    registered_mono: float = field(default_factory=time.monotonic)
    started_mono: float | None = None
    cancelled_mono: float | None = None
    finished_mono: float | None = None

    # 벽시계 문자열: 로그/이력/리포트 표시용
    registered_at: str = field(default_factory=_now_timestamp_str)
    started_at: str | None = None
    cancelled_at: str | None = None
    finished_at: str | None = None

    final_status: str | None = None
    status_detail: str | None = None

    def mark_started(self) -> None:
        """워커가 큐에서 작업을 꺼내 실제 실행을 시작한 시점을 기록합니다."""
        if self.started_mono is None:
            self.started_mono = time.monotonic()
            self.started_at = _now_timestamp_str()

    def mark_cancelled(self) -> None:
        """취소 요청(단일 취소, 윈도우 종료, 전체 취소 등)이 트리거된 시점을 기록합니다."""
        if self.cancelled_mono is None:
            self.cancelled_mono = time.monotonic()
            self.cancelled_at = _now_timestamp_str()

    def mark_finished(self, status: str, detail: str | None = None) -> None:
        """작업이 최종 종료(SUCCESS / CANCELLED / ERROR)된 시점과 상태를 기록합니다."""
        if self.finished_mono is None:
            self.finished_mono = time.monotonic()
            self.finished_at = _now_timestamp_str()
        self.final_status = status
        if detail is not None:
            self.status_detail = detail

    @property
    def wait_sec(self) -> float:
        """등록 시점부터 시작 시점(또는 미시작 시 종료/현재 시점)까지의 대기 시간(초)."""
        end_mono = (
            self.started_mono
            if self.started_mono is not None
            else (self.finished_mono if self.finished_mono is not None else time.monotonic())
        )
        return max(0.0, end_mono - self.registered_mono)

    @property
    def run_sec(self) -> float | None:
        """시작 시점부터 종료 시점(또는 진행 중이면 현재 시점)까지의 순수 실행 시간(초)."""
        if self.started_mono is None:
            return None
        end_mono = self.finished_mono if self.finished_mono is not None else time.monotonic()
        return max(0.0, end_mono - self.started_mono)

    @property
    def total_sec(self) -> float:
        """등록 시점부터 종료 시점(또는 미종료 시 현재 시점)까지의 전체 체류 시간(초)."""
        end_mono = self.finished_mono if self.finished_mono is not None else time.monotonic()
        return max(0.0, end_mono - self.registered_mono)

    @property
    def cancel_to_finish_sec(self) -> float | None:
        """취소 트리거 시점부터 실제 작업 종료 시점까지 걸린 시간(초)."""
        if self.cancelled_mono is None or self.finished_mono is None:
            return None
        return max(0.0, self.finished_mono - self.cancelled_mono)

    def to_dict(self) -> dict[str, Any]:
        """이후 통계/UI/리포트/JSON 직렬화 등에 활용하기 쉬운 딕셔너리로 변환합니다."""
        return {
            "task_key": self.task_key,
            "task_name": self.task_name,
            "priority": self.priority,
            "cancel_on_close": self.cancel_on_close,
            "status": self.final_status or ("RUNNING" if self.started_mono is not None else "QUEUED"),
            "detail": self.status_detail,
            "registered_at": self.registered_at,
            "started_at": self.started_at,
            "cancelled_at": self.cancelled_at,
            "finished_at": self.finished_at,
            "wait_sec": round(self.wait_sec, 3),
            "run_sec": round(self.run_sec, 3) if self.run_sec is not None else None,
            "total_sec": round(self.total_sec, 3),
            "cancel_to_finish_sec": (
                round(self.cancel_to_finish_sec, 3)
                if self.cancel_to_finish_sec is not None
                else None
            ),
        }

    def format_summary(self) -> str:
        """로그 출력용 한 줄 요약 문자열을 생성합니다."""
        run_str = f"{self.run_sec:.2f}s" if self.run_sec is not None else "미시작"
        cancel_lag_str = (
            f", 취소반영={self.cancel_to_finish_sec:.2f}s"
            if self.cancel_to_finish_sec is not None
            else ""
        )
        return (
            f"key={self.task_key}, name={self.task_name}, status={self.final_status or 'ACTIVE'}, "
            f"대기={self.wait_sec:.2f}s, 실행={run_str}, 총체류={self.total_sec:.2f}s{cancel_lag_str}, "
            f"시각[등록={self.registered_at} | 시작={self.started_at or '-'} | "
            f"취소={self.cancelled_at or '-'} | 종료={self.finished_at or '-'}]"
        )


# ==============================================================================
# 3. 취소 토큰 및 외부 프로세스 트리 강제 종료 유틸리티
# ==============================================================================
class CancelToken:
    """
    단일 작업의 취소 상태(threading.Event)와 취소 즉시 실행할 콜백(kill 훅)을 관리합니다.
    - 외부 프로그램(subprocess.Popen)을 실행하는 작업은 on_cancel()에 프로세스 종료 함수를 등록해
      취소 요청 시점에 대기 없이 즉시 프로세스를 종료할 수 있습니다.
    """

    def __init__(self, task_key: str = "", on_triggered: Callable[[], None] | None = None) -> None:
        self.task_key = task_key
        self.event = threading.Event()
        self._lock = threading.Lock()
        self._kill_callbacks: list[Callable[[], None]] = []
        self._on_triggered = on_triggered

    def on_cancel(self, cb: Callable[[], None]) -> None:
        """취소 발생 시 즉시 호출할 콜백(예: kill_process_tree)을 등록합니다."""
        with self._lock:
            if self.event.is_set():
                logd(f"[CancelToken:{self.task_key}] 이미 취소된 상태이므로 kill 콜백 즉시 실행")
                self._safe_call(cb)
            else:
                self._kill_callbacks.append(cb)
                logd(f"[CancelToken:{self.task_key}] 취소 훅 등록 완료 (총 {len(self._kill_callbacks)}개)")

    def clear_callbacks(self) -> None:
        """작업 정상/비정상 종료 후 등록된 kill 콜백 참조를 해제합니다."""
        with self._lock:
            self._kill_callbacks.clear()

    def trigger_cancel(self) -> None:
        """취소 플래그를 설정하고, 취소 시점 기록 콜백 및 등록된 kill 콜백들을 실행합니다."""
        already_set = self.event.is_set()
        self.event.set()
        if not already_set and callable(self._on_triggered):
            self._safe_call(self._on_triggered)

        with self._lock:
            callbacks = list(self._kill_callbacks)
            self._kill_callbacks.clear()

        logd(
            f"[CancelToken:{self.task_key}] 취소 트리거 발동 "
            f"(기존취소여부={already_set}, 실행할 훅={len(callbacks)}개)"
        )
        for cb in callbacks:
            self._safe_call(cb)

    @property
    def is_set(self) -> bool:
        return self.event.is_set()

    @staticmethod
    def _safe_call(cb: Callable[[], None]) -> None:
        try:
            cb()
        except Exception as exc:
            loge(f"[CancelToken] 콜백 실행 중 예외 발생: {exc}")


def kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    """
    실행 중인 외부 프로세스와 그 자식 프로세스 트리를 즉시 종료합니다.
    - Windows: taskkill /F /T /PID <pid> 로 하위 자식 프로세스까지 일괄 종료
    - POSIX  : proc.kill() 호출
    """
    if proc.poll() is not None:
        logd(f"[kill_process_tree] PID={proc.pid} 이미 종료됨 (returncode={proc.returncode})")
        return

    logd(f"[kill_process_tree] 외부 프로세스 강제 종료 시도 (PID={proc.pid})")
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            proc.kill()
        except Exception as exc:
            loge(f"[kill_process_tree] PID={proc.pid} kill 실패: {exc}")


# ==============================================================================
# 4. 리스너 베이스 및 등록 기반 메인 스레드 디스패처
# ==============================================================================
class TaskListenerBase:
    """
    작업을 요청한 윈도우/컨트롤러가 구현하는 이벤트 수신 베이스 클래스.
    - QMainWindow 등과 다중 상속하지 않고 별도 리스너 객체로 상속받아 사용합니다.
    - owner_widget에 대상 윈도우를 전달하면 weakref로 생존 여부를 추적하여
      닫히거나 소멸된 위젯으로 이벤트가 전달되는 것을 차단합니다.
    """

    def __init__(self, owner_widget: QObject | None = None) -> None:
        self._owner_ref: weakref.ref[QObject] | None = (
            weakref.ref(owner_widget) if owner_widget is not None else None
        )

    def is_owner_alive(self) -> bool:
        """연결된 윈도우(owner_widget)가 아직 유효한지 확인합니다."""
        if self._owner_ref is None:
            return True
        obj = self._owner_ref()
        if obj is None:
            return False
        try:
            _ = obj.objectName()
            return True
        except RuntimeError:
            return False

    def on_task_progress(self, task_key: str, task_name: str, percent: int, message: str) -> None:
        """작업 진행률 갱신 시 메인 스레드에서 호출됩니다."""

    def on_task_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
        """작업 종료(SUCCESS / CANCELLED / ERROR) 시 메인 스레드에서 호출됩니다."""


class _MainThreadRelay(QObject):
    """워커 스레드에서 발생한 이벤트를 Qt 메인 스레드로 안전하게 전달하는 내부 릴레이."""

    progress_sig = Signal(object, str, str, int, str)      # (listener, task_key, task_name, percent, message)
    finished_sig = Signal(object, str, str, str, object)  # (listener, task_key, task_name, status, data)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.progress_sig.connect(self._deliver_progress)
        self.finished_sig.connect(self._deliver_finished)

    @Slot(object, str, str, int, str)
    def _deliver_progress(
        self,
        listener: TaskListenerBase,
        task_key: str,
        task_name: str,
        percent: int,
        message: str,
    ) -> None:
        if not listener.is_owner_alive():
            logd(f"[Relay] owner 소멸 감지로 진행률 전달 생략 (task_key={task_key})")
            return
        listener.on_task_progress(task_key, task_name, percent, message)

    @Slot(object, str, str, str, object)
    def _deliver_finished(
        self,
        listener: TaskListenerBase,
        task_key: str,
        task_name: str,
        status: str,
        data: Any,
    ) -> None:
        if not listener.is_owner_alive():
            logd(f"[Relay] owner 소멸 감지로 완료 통지 생략 (task_key={task_key}, status={status})")
            return
        listener.on_task_finished(task_key, task_name, status, data)


class ScopedTaskDispatcher:
    """
    task_key 단위로 등록된 리스너에만 이벤트를 라우팅하는 디스패처.
    - 전역 브로드캐스트 및 owner_id 문자열 비교 없이 등록된 리스너 인스턴스만 호출합니다.
    - 리스너별 등록 작업 목록(_listener_tasks)과 창 종료 시 취소 정책(_cancel_on_close)을 함께 관리합니다.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        self._lock = threading.Lock()
        self._listeners: dict[str, TaskListenerBase] = {}
        self._cancel_on_close: dict[str, bool] = {}
        self._listener_tasks: dict[int, set[str]] = {}
        self._listener_refs: dict[int, TaskListenerBase] = {}
        self._relay = _MainThreadRelay(parent)

    def register(
        self,
        task_key: str,
        listener: TaskListenerBase,
        cancel_on_close: bool = True,
    ) -> None:
        with self._lock:
            lid = id(listener)
            self._listeners[task_key] = listener
            self._cancel_on_close[task_key] = bool(cancel_on_close)
            self._listener_refs[lid] = listener
            self._listener_tasks.setdefault(lid, set()).add(task_key)
        logd(
            f"[Dispatcher] 리스너 등록 완료 (task_key={task_key}, "
            f"listener={type(listener).__name__}, cancel_on_close={cancel_on_close})"
        )

    def _remove_task_locked(self, task_key: str) -> TaskListenerBase | None:
        listener = self._listeners.pop(task_key, None)
        self._cancel_on_close.pop(task_key, None)
        if listener is not None:
            lid = id(listener)
            keys = self._listener_tasks.get(lid)
            if keys:
                keys.discard(task_key)
                if not keys:
                    self._listener_tasks.pop(lid, None)
                    self._listener_refs.pop(lid, None)
        return listener

    def pop_listener(self, task_key: str) -> TaskListenerBase | None:
        with self._lock:
            return self._remove_task_locked(task_key)

    def detach_listener_tasks(self, listener: TaskListenerBase) -> tuple[list[str], list[str]]:
        """
        특정 리스너(윈도우) 종료 시 호출됩니다.
        반환값:
        - to_cancel: cancel_on_close=True 로 등록되어 즉시 취소해야 할 task_key 목록
        - to_keep  : cancel_on_close=False 로 등록되어 리스너만 떼고 백그라운드 유지할 task_key 목록
        """
        to_cancel: list[str] = []
        to_keep: list[str] = []

        with self._lock:
            lid = id(listener)
            keys = list(self._listener_tasks.pop(lid, set()))
            self._listener_refs.pop(lid, None)
            for k in keys:
                should_cancel = self._cancel_on_close.pop(k, True)
                self._listeners.pop(k, None)
                if should_cancel:
                    to_cancel.append(k)
                else:
                    to_keep.append(k)

        if keys:
            logd(
                f"[Dispatcher] 리스너 분리 완료 (listener={type(listener).__name__}, "
                f"취소대상={to_cancel}, 백그라운드유지={to_keep})"
            )
        return to_cancel, to_keep

    def purge_dead_listeners(self) -> list[str]:
        """소멸된(owner가 죽은) 리스너를 정리하고 취소해야 할 task_key 목록을 반환합니다."""
        dead_cancel_keys: list[str] = []
        with self._lock:
            dead_lids = [
                lid for lid, lst in self._listener_refs.items() if not lst.is_owner_alive()
            ]
            for lid in dead_lids:
                keys = list(self._listener_tasks.pop(lid, set()))
                self._listener_refs.pop(lid, None)
                for k in keys:
                    should_cancel = self._cancel_on_close.pop(k, True)
                    self._listeners.pop(k, None)
                    if should_cancel:
                        dead_cancel_keys.append(k)

        if dead_cancel_keys:
            logd(f"[Dispatcher] 소멸된 윈도우 감지 -> 자동 취소 대상 키: {dead_cancel_keys}")
        return dead_cancel_keys

    def dispatch_progress(self, task_key: str, task_name: str, percent: int, message: str) -> None:
        with self._lock:
            listener = self._listeners.get(task_key)
        if listener is not None and listener.is_owner_alive():
            self._relay.progress_sig.emit(listener, task_key, task_name, percent, message)

    def dispatch_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
        listener = self.pop_listener(task_key)
        if listener is not None and listener.is_owner_alive():
            self._relay.finished_sig.emit(listener, task_key, task_name, status, data)


# ==============================================================================
# 5. 파라미터 검증 헬퍼
# ==============================================================================
def _validate_task_params(
    listener: TaskListenerBase,
    priority: int,
    task_key: str,
    task_name: str,
    func: Callable[..., Any],
    existing_keys: set[str] | None = None,
) -> None:
    """큐 적재(add_task) 전에 입력 인자의 타입, 유효성, 중복 키 여부를 검증합니다."""
    if not isinstance(listener, TaskListenerBase):
        loge(f"[Validation] 잘못된 listener 타입: {type(listener)}")
        raise TypeError("listener는 TaskListenerBase 인스턴스여야 합니다.")

    if not listener.is_owner_alive():
        loge("[Validation] 이미 종료된 윈도우(owner)의 리스너로 작업 등록 시도")
        raise RuntimeError("연결된 윈도우(owner)가 이미 종료되었거나 유효하지 않습니다.")

    if isinstance(priority, bool) or not isinstance(priority, int):
        loge(f"[Validation] 잘못된 priority 값: {priority!r}")
        raise TypeError("priority는 정수(int)여야 합니다.")

    if not isinstance(task_key, str) or not task_key.strip():
        loge(f"[Validation] 잘못된 task_key: {task_key!r}")
        raise ValueError("task_key는 비어 있지 않은 문자열이어야 합니다.")

    if not isinstance(task_name, str) or not task_name.strip():
        loge(f"[Validation] 잘못된 task_name: {task_name!r}")
        raise ValueError("task_name은 비어 있지 않은 문자열이어야 합니다.")

    if not callable(func):
        loge(f"[Validation] 호출 불가능한 func 전달됨: {func!r}")
        raise TypeError("func는 호출 가능한(callable) 함수여야 합니다.")

    if existing_keys and task_key in existing_keys:
        loge(f"[Validation] 중복된 task_key 등록 시도: {task_key}")
        raise ValueError(f"이미 사용 중이거나 대기 중인 task_key입니다: {task_key}")


# ==============================================================================
# 6. 우선순위, 취소 및 이벤트 시점 기록이 포함된 백그라운드 워커 스레드
# ==============================================================================
class PriorityWorkerThread(QThread):
    """
    우선순위 큐에서 작업을 꺼내 순차 실행하고 작업별 이벤트 시점을 관리하는 워커 스레드.
    - queue_updated       : 현재 대기열 표시 문자열 리스트 송출
    - current_task_changed: 현재 실행 중인 작업 이름 송출
    """

    queue_updated = Signal(list)
    current_task_changed = Signal(str)

    def __init__(self, dispatcher: ScopedTaskDispatcher, history_limit: int = 200) -> None:
        super().__init__()
        self.dispatcher = dispatcher
        self.task_queue: PriorityQueue[tuple[int, int, tuple[Any, ...]]] = PriorityQueue()
        self._counter = 0

        self._state_lock = threading.Lock()
        self._is_running = True
        self.current_task_key: str | None = None
        self.cancel_tokens: dict[str, CancelToken] = {}
        self.active_tasks_info: list[tuple[int, int, str, str]] = []

        # 작업별 시점 기록 저장소 (활성/대기 작업 + 최근 완료 이력)
        self._timings: dict[str, TaskEventTimestamps] = {}
        self._timing_history: deque[TaskEventTimestamps] = deque(maxlen=max(10, history_limit))

    def _format_queue_snapshot_locked(self) -> list[str]:
        """_state_lock 보유 상태에서 현재 대기열 스냅샷 문자열 목록을 만듭니다."""
        return [
            f"#{idx + 1}[{self.get_priority_name(t[0])}:{t[2]}]{t[3]}"
            for idx, t in enumerate(self.active_tasks_info)
        ]

    def _log_queue_event(self, event_name: str, detail: str = "") -> None:
        """큐 이벤트가 발생할 때마다 현재 대기열·실행 상태 스냅샷을 로그로 출력합니다."""
        with self._state_lock:
            q_len = len(self.active_tasks_info)
            current_key = self.current_task_key or "없음"
            snapshot = self._format_queue_snapshot_locked()
        suffix = f" | {detail}" if detail else ""
        logd(
            f"[QueueEvent:{event_name}] current={current_key}, queued={q_len}, "
            f"queue={snapshot}{suffix}"
        )

    def _mark_cancelled_locked(self, task_key: str) -> None:
        """_state_lock 보유 상태에서 특정 작업의 취소 시점을 기록합니다."""
        timing = self._timings.get(task_key)
        if timing is not None:
            timing.mark_cancelled()
            logd(
                f"[Timing] 작업 취소 시점 기록 (task_key={task_key}, cancelled_at={timing.cancelled_at}, "
                f"등록후경과={timing.total_sec:.2f}s)"
            )

    def _finalize_timing_locked(self, task_key: str, status: str, detail: str) -> TaskEventTimestamps | None:
        """_state_lock 보유 상태에서 종료 시점을 기록하고 최근 이력에 이동/저장합니다."""
        timing = self._timings.pop(task_key, None)
        if timing is not None:
            timing.mark_finished(status, detail=detail)
            self._timing_history.append(timing)
            logd(f"[Timing] 작업 종료 요약 -> {timing.format_summary()}")
        return timing

    def get_timing(self, task_key: str) -> TaskEventTimestamps | None:
        """활성/대기 작업 또는 최근 종료 이력에서 task_key의 시점 기록을 조회합니다."""
        with self._state_lock:
            if task_key in self._timings:
                return self._timings[task_key]
            for item in reversed(self._timing_history):
                if item.task_key == task_key:
                    return item
        return None

    def get_recent_timings(self, limit: int = 50) -> list[dict[str, Any]]:
        """최근 종료된 작업들의 시점/소요시간 요약 목록을 딕셔너리 리스트로 반환합니다."""
        with self._state_lock:
            items = list(self._timing_history)[-max(1, limit):]
        return [item.to_dict() for item in reversed(items)]

    def add_task(
        self,
        priority: int,
        task_key: str,
        task_name: str,
        func: Callable[..., Any],
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        cancel_on_close: bool = True,
    ) -> None:
        safe_args = tuple(args) if args is not None else ()
        safe_kwargs = dict(kwargs) if kwargs is not None else {}

        # 등록 시점 레코드 생성 (registered_at / registered_mono 자동 기록)
        timing = TaskEventTimestamps(
            task_key=task_key,
            task_name=task_name,
            priority=priority,
            cancel_on_close=cancel_on_close,
        )
        token = CancelToken(
            task_key=task_key,
            on_triggered=lambda k=task_key: self._record_cancel_timestamp(k),
        )

        with self._state_lock:
            self._timings[task_key] = timing
            self.cancel_tokens[task_key] = token
            self._counter += 1
            seq = self._counter
            item = (priority, seq, (task_key, task_name, func, safe_args, safe_kwargs))
            self.task_queue.put(item)
            self.active_tasks_info.append((priority, seq, task_key, task_name))
            self.active_tasks_info.sort(key=lambda x: (x[0], x[1]))
            queue_len = len(self.active_tasks_info)

        logd(
            f"[Worker] 작업 등록 및 큐 적재 (task_key={task_key}, name={task_name}, "
            f"priority={self.get_priority_name(priority)}, registered_at={timing.registered_at}, "
            f"대기열수={queue_len})"
        )
        self._log_queue_event(
            "ENQUEUE",
            f"added={task_key}({task_name}), prio={self.get_priority_name(priority)}",
        )
        self.emit_queue_status()

    def _record_cancel_timestamp(self, task_key: str) -> None:
        with self._state_lock:
            self._mark_cancelled_locked(task_key)

    def cancel_task(self, task_key: str) -> None:
        """단일 task_key 작업을 취소합니다(실행 중이면 kill 훅 발동, 대기 중이면 큐에서 제거)."""
        with self._state_lock:
            token = self.cancel_tokens.get(task_key)
            was_queued = any(t[2] == task_key for t in self.active_tasks_info)
            self.active_tasks_info = [t for t in self.active_tasks_info if t[2] != task_key]
            is_current = self.current_task_key == task_key
            if token is None:
                self._mark_cancelled_locked(task_key)

        logd(
            f"[Worker] 단일 작업 취소 요청 (task_key={task_key}, "
            f"실행중={is_current}, 대기중={was_queued})"
        )
        self._log_queue_event(
            "CANCEL_ONE",
            f"target={task_key}, running={is_current}, was_queued={was_queued}",
        )
        if token is not None:
            token.trigger_cancel()

        self.emit_queue_status()

        if was_queued and not is_current:
            reason = "대기 중 작업이 취소되었습니다."
            with self._state_lock:
                self._finalize_timing_locked(task_key, "CANCELLED", reason)
            self._log_queue_event("DEQUEUE_CANCELLED", f"removed={task_key}, reason={reason}")
            self.dispatcher.dispatch_finished(task_key, task_key, "CANCELLED", reason)

    def cancel_keys(self, target_keys: list[str], reason: str = "작업이 취소되었습니다.") -> None:
        """지정된 여러 task_key(예: 특정 윈도우 소속 작업들)를 일괄 취소/제거합니다."""
        if not target_keys:
            return

        target_set = set(target_keys)
        tokens_to_trigger: list[CancelToken] = []
        queued_cancelled_keys: list[str] = []

        with self._state_lock:
            for k in target_set:
                token = self.cancel_tokens.get(k)
                if token is not None:
                    tokens_to_trigger.append(token)
                else:
                    self._mark_cancelled_locked(k)

            for _, _, task_key, _ in self.active_tasks_info:
                if task_key in target_set and task_key != self.current_task_key:
                    queued_cancelled_keys.append(task_key)

            self.active_tasks_info = [t for t in self.active_tasks_info if t[2] not in target_set]

        logd(
            f"[Worker] 다중 키 취소 실행 (대상={list(target_set)}, "
            f"대기열제거={queued_cancelled_keys}, reason={reason})"
        )
        self._log_queue_event(
            "CANCEL_KEYS",
            f"targets={list(target_set)}, removed_queued={queued_cancelled_keys}, reason={reason}",
        )
        for token in tokens_to_trigger:
            token.trigger_cancel()

        self.emit_queue_status()

        for key in queued_cancelled_keys:
            with self._state_lock:
                self._finalize_timing_locked(key, "CANCELLED", reason)
            self.dispatcher.dispatch_finished(key, key, "CANCELLED", reason)

    def cancel_all(self, reason: str = "프로그램 종료로 작업이 취소되었습니다.") -> None:
        """현재 실행 중인 작업과 큐에 남아 있는 모든 작업을 전부 취소합니다."""
        with self._state_lock:
            queued_keys = [t[2] for t in self.active_tasks_info]
            all_keys = set(queued_keys)
            if self.current_task_key:
                all_keys.add(self.current_task_key)
            all_keys.update(self.cancel_tokens.keys())

            tokens_to_trigger: list[CancelToken] = []
            for k in all_keys:
                if k in self.cancel_tokens:
                    tokens_to_trigger.append(self.cancel_tokens[k])
                else:
                    self._mark_cancelled_locked(k)

            self.active_tasks_info.clear()

            drained = 0
            while not self.task_queue.empty():
                try:
                    self.task_queue.get_nowait()
                    self.task_queue.task_done()
                    drained += 1
                except Exception:
                    break

        logd(
            f"[Worker] 전체 작업 취소 실행 (총키수={len(all_keys)}, "
            f"큐비움={drained}, reason={reason})"
        )
        self._log_queue_event(
            "CANCEL_ALL",
            f"total_keys={len(all_keys)}, drained={drained}, reason={reason}",
        )
        for token in tokens_to_trigger:
            token.trigger_cancel()

        self.emit_queue_status()

        for key in queued_keys:
            with self._state_lock:
                self._finalize_timing_locked(key, "CANCELLED", reason)
            self.dispatcher.dispatch_finished(key, key, "CANCELLED", reason)

    def emit_queue_status(self) -> None:
        with self._state_lock:
            task_names = [f"[{self.get_priority_name(t[0])}] {t[3]}" for t in self.active_tasks_info]
            current_key = self.current_task_key or "없음"
            snapshot = self._format_queue_snapshot_locked()
        logd(
            f"[QueueEvent:STATUS_EMIT] current={current_key}, queued={len(task_names)}, "
            f"queue={snapshot}"
        )
        self.queue_updated.emit(task_names)

    def get_priority_name(self, p: int) -> str:
        if p == TaskPriority.HIGH:
            return "긴급"
        if p == TaskPriority.LOW:
            return "후순위"
        return "일반"

    def run(self) -> None:
        logd("[Worker] 백그라운드 워커 스레드 루프 시작")
        self._log_queue_event("WORKER_START", "loop started")
        while True:
            with self._state_lock:
                if not self._is_running:
                    break

            try:
                _, _, task_data = self.task_queue.get(timeout=0.3)
                task_key, task_name, func, args, kwargs = task_data
            except Exception:
                continue

            self._log_queue_event("DEQUEUE", f"popped={task_key}({task_name})")

            # 큐에서 꺼낼 때마다 소멸된 윈도우의 cancel_on_close=True 작업 정리
            dead_keys = self.dispatcher.purge_dead_listeners()
            if dead_keys:
                self.cancel_keys(dead_keys, reason="연결된 윈도우가 종료되어 취소되었습니다.")

            with self._state_lock:
                if not self._is_running:
                    self._finalize_timing_locked(task_key, "CANCELLED", "워커 종료로 미실행 취소")
                    self.task_queue.task_done()
                    self._log_queue_event("SKIP_SHUTDOWN", f"task={task_key}({task_name})")
                    break

                token = self.cancel_tokens.get(task_key)
                if token is not None and token.is_set:
                    logd(f"[Worker] 이미 취소된 작업 스킵 (task_key={task_key}, name={task_name})")
                    self._finalize_timing_locked(task_key, "CANCELLED", "큐 대기 중 취소됨")
                    self.task_queue.task_done()
                    self._log_queue_event("SKIP_CANCELLED", f"task={task_key}({task_name})")
                    continue

                prev_task = self.current_task_key or "없음"
                self.current_task_key = task_key
                self.active_tasks_info = [t for t in self.active_tasks_info if t[2] != task_key]

                # 실행 시작 시점 및 큐 대기 시간 기록
                timing = self._timings.get(task_key)
                if timing is not None:
                    timing.mark_started()
                    wait_sec = timing.wait_sec
                    started_at = timing.started_at
                else:
                    wait_sec = 0.0
                    started_at = _now_timestamp_str()

            logd(
                f"[Worker] 작업 실행 시작 (task_key={task_key}, name={task_name}, "
                f"started_at={started_at}, 큐대기={wait_sec:.2f}s)"
            )
            self._log_queue_event(
                "CURRENT_TASK_CHANGED",
                f"{prev_task} -> {task_key}({task_name}), wait={wait_sec:.2f}s",
            )
            self.current_task_changed.emit(task_name)
            self.emit_queue_status()

            cancel_event = token.event if token is not None else threading.Event()

            def progress_callback(percent: int, message: str) -> None:
                if cancel_event.is_set():
                    raise InterruptedError("작업이 취소되었습니다.")
                logd(f"[Worker:{task_name}] 진행률 {percent}% - {message}")
                self.dispatcher.dispatch_progress(task_key, task_name, percent, message)

            call_kwargs = dict(kwargs)
            call_kwargs["progress_cb"] = progress_callback
            call_kwargs["cancel_event"] = cancel_event
            call_kwargs["cancel_token"] = token

            final_status = "ERROR"
            result_or_msg: Any = ""

            try:
                result = func(*args, **call_kwargs)
                if cancel_event.is_set():
                    raise InterruptedError("작업이 취소되었습니다.")
                final_status = "SUCCESS"
                result_or_msg = result
                logd(f"[Worker] 작업 정상 완료 (task_key={task_key}, name={task_name})")
            except InterruptedError as ie:
                final_status = "CANCELLED"
                result_or_msg = str(ie)
                logd(f"[Worker] 작업 취소 종료 (task_key={task_key}, name={task_name}, 사유={ie})")
            except Exception as exc:
                final_status = "ERROR"
                result_or_msg = str(exc)
                loge(f"[Worker] 작업 실행 중 예외 발생 (task_key={task_key}, name={task_name}): {exc}")
            finally:
                if token is not None:
                    token.clear_callbacks()
                with self._state_lock:
                    self.cancel_tokens.pop(task_key, None)
                    self.current_task_key = None
                    self._finalize_timing_locked(task_key, final_status, str(result_or_msg))

                self._log_queue_event(
                    "TASK_FINISHED",
                    f"finished={task_key}({task_name}), status={final_status}, current -> 없음",
                )
                self.dispatcher.dispatch_finished(task_key, task_name, final_status, result_or_msg)
                self.current_task_changed.emit("없음")
                self.emit_queue_status()
                self.task_queue.task_done()

        logd("[Worker] 백그라운드 워커 스레드 루프 종료")
        self._log_queue_event("WORKER_STOP", "loop exited")

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """모든 작업을 취소하고 워커 스레드 종료를 대기합니다."""
        logd(f"[Worker] 워커 종료 요청 (timeout_ms={timeout_ms})")
        self._log_queue_event("SHUTDOWN_REQUEST", f"timeout_ms={timeout_ms}")
        with self._state_lock:
            self._is_running = False
        self.cancel_all("프로그램 종료로 작업이 취소되었습니다.")
        if self.isRunning():
            self.quit()
            finished = self.wait(timeout_ms)
            logd(f"[Worker] 워커 스레드 wait 완료 (정상종료={finished})")


# ==============================================================================
# 7. 전역 큐 매니저 (Singleton)
# ==============================================================================
class TaskManager:
    """
    애플리케이션 전역에서 사용하는 작업 큐 매니저.
    - submit(...)            : 파라미터 검증 + 리스너 등록 + 시점 기록 + 큐 적재를 한 번에 수행
    - cancel(task_key)       : 특정 작업 취소
    - on_window_closing(...) : 특정 윈도우 종료 시 해당 윈도우 작업 취소 또는 리스너 분리
    - get_timing / get_recent_timings : 작업별 등록/시작/취소/종료 시점 및 소요시간 조회
    - on_about_to_quit()     : QApplication.aboutToQuit 에 연결하는 앱 종료 핸들러
    """

    _instance: TaskManager | None = None
    _shutting_down: bool = False

    def __new__(cls) -> TaskManager:
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
            cls._instance.dispatcher = ScopedTaskDispatcher()
            cls._instance.worker = PriorityWorkerThread(dispatcher=cls._instance.dispatcher)
            cls._instance.worker.start()
            logd("[TaskManager] 싱글톤 인스턴스 생성 및 워커 스레드 시작 완료")
        return cls._instance

    def submit(
        self,
        listener: TaskListenerBase,
        priority: int,
        task_key: str,
        task_name: str,
        func: Callable[..., Any],
        *args: Any,
        cancel_on_close: bool = True,
        **kwargs: Any,
    ) -> str:
        """
        작업을 검증하고 리스너와 함께 우선순위 큐에 등록합니다.

        Parameters
        ----------
        listener        : 진행률/완료 이벤트를 받을 TaskListenerBase 구현체
        priority        : TaskPriority.HIGH / NORMAL / LOW
        task_key        : 고유 작업 키 (중복 불가)
        task_name       : UI 및 로그에 표시할 작업 이름
        func            : 백그라운드에서 실행할 콜러블
        cancel_on_close : True면 연결된 윈도우 종료 시 작업 취소/kill,
                          False면 윈도우 종료 시 리스너만 분리하고 작업은 계속 수행
        """
        if TaskManager._shutting_down:
            loge(f"[TaskManager] 앱 종료 진행 중이므로 작업 등록 거부 (task_key={task_key})")
            raise RuntimeError("애플리케이션이 종료 중이므로 새 작업을 등록할 수 없습니다.")

        with self.worker._state_lock:
            existing_keys = {t[2] for t in self.worker.active_tasks_info}
            if self.worker.current_task_key:
                existing_keys.add(self.worker.current_task_key)

        _validate_task_params(
            listener=listener,
            priority=priority,
            task_key=task_key,
            task_name=task_name,
            func=func,
            existing_keys=existing_keys,
        )

        self.dispatcher.register(task_key, listener, cancel_on_close=cancel_on_close)
        self.worker.add_task(
            priority,
            task_key,
            task_name,
            func,
            args,
            kwargs,
            cancel_on_close=cancel_on_close,
        )
        return task_key

    def cancel(self, task_key: str) -> None:
        """단일 작업 취소."""
        self.worker.cancel_task(task_key)

    def get_timing(self, task_key: str) -> TaskEventTimestamps | None:
        """특정 작업의 시점 기록(등록/시작/취소/종료 및 경과시간)을 조회합니다."""
        return self.worker.get_timing(task_key)

    def get_recent_timings(self, limit: int = 50) -> list[dict[str, Any]]:
        """최근 완료/취소된 작업들의 시점 요약 목록을 조회합니다."""
        return self.worker.get_recent_timings(limit=limit)

    def on_window_closing(
        self,
        listener: TaskListenerBase,
        reason: str = "윈도우 종료로 작업이 취소되었습니다.",
    ) -> None:
        """
        개별 윈도우가 닫힐 때 호출합니다.
        - cancel_on_close=True 작업 -> 취소 시점 기록, 즉시 취소(실행 중이면 kill 훅 호출) 및 큐 제거
        - cancel_on_close=False 작업 -> 리스너만 해제하고 백그라운드 실행 유지
        """
        logd(f"[TaskManager] 윈도우 종료 처리 시작 (listener={type(listener).__name__})")
        to_cancel, to_keep = self.dispatcher.detach_listener_tasks(listener)
        if to_keep:
            logd(f"[TaskManager] 백그라운드 유지 작업(리스너 분리됨): {to_keep}")
        if to_cancel:
            self.worker.cancel_keys(to_cancel, reason=reason)

    def cancel_all(self, reason: str = "프로그램 종료로 작업이 취소되었습니다.") -> None:
        """큐에 있는 모든 대기/실행 작업을 취소합니다."""
        self.worker.cancel_all(reason=reason)

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """모든 작업을 취소하고 백그라운드 워커를 종료합니다."""
        self.worker.shutdown(timeout_ms=timeout_ms)

    def get_worker(self) -> PriorityWorkerThread:
        return self.worker

    @classmethod
    def on_about_to_quit(cls) -> None:
        """QApplication.aboutToQuit 시그널에 연결하는 애플리케이션 전체 종료 핸들러."""
        if cls._shutting_down:
            return
        cls._shutting_down = True
        logd("[TaskManager] 앱 종료(aboutToQuit) 감지 -> 전체 큐 취소 및 워커 정리 시작")
        manager = cls()
        manager.cancel_all("애플리케이션 종료로 모든 작업이 취소되었습니다.")
        manager.shutdown(timeout_ms=3000)


# ==============================================================================
# [SAMPLE 영역 시작]
# - 아래 코드는 사용 예제를 위한 데모 모듈입니다.
# - 별도 파일(예: sample_queue_demo.py)로 분리할 때 이 구분선 아래만 잘라내어
#   `from prio_worker_queue import CancelToken, TaskListenerBase, TaskManager, TaskPriority, kill_process_tree`
#   만 추가하면 그대로 동작합니다.
# ==============================================================================
if __name__ == "__main__":
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    # --------------------------------------------------------------------------
    # [사용법 1] 백그라운드에서 실행할 작업 함수 정의
    # - 워커가 호출 시 자동으로 아래 키워드 인자를 주입해 줍니다:
    #   * progress_cb(percent: int, message: str) : 진행률 보고 (취소 시 InterruptedError 발생)
    #   * cancel_event: threading.Event           : 취소 여부 폴링용 이벤트
    #   * cancel_token: CancelToken               : 외부 프로세스 kill 훅(on_cancel) 등록용
    # --------------------------------------------------------------------------
    def sample_worker_job(
        steps: int = 6,
        use_external_process: bool = False,
        progress_cb: Callable[[int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
        cancel_token: CancelToken | None = None,
    ) -> str:
        logd(f"[SampleJob] 작업 시작 (steps={steps}, external={use_external_process})")

        # 케이스 A: 외부 프로그램(subprocess.Popen)을 띄우고 취소 시 즉시 kill 하는 패턴
        if use_external_process:
            if cancel_token and cancel_token.is_set:
                raise InterruptedError("외부 프로세스 실행 전 취소되었습니다.")

            cmd = (
                ["ping", "-n", str(steps + 1), "127.0.0.1"]
                if os.name == "nt"
                else ["sleep", str(steps)]
            )
            logd(f"[SampleJob] 외부 프로세스 실행: {cmd}")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # 핵심: 취소 버튼 클릭 또는 윈도우/앱 종료 시 프로세스 트리를 즉시 kill 하도록 훅 등록
            if cancel_token is not None:
                cancel_token.on_cancel(lambda: kill_process_tree(proc))

            try:
                for step in range(1, steps + 1):
                    if cancel_token and cancel_token.is_set:
                        raise InterruptedError("외부 프로세스 실행 중 취소되었습니다.")
                    if proc.poll() is not None:
                        logd(f"[SampleJob] 외부 프로세스 조기 종료 감지 (rc={proc.returncode})")
                        break
                    time.sleep(0.5)
                    if progress_cb:
                        progress_cb(int((step / steps) * 100), f"외부 프로세스 감시 {step}/{steps}")

                if cancel_token and cancel_token.is_set:
                    raise InterruptedError("외부 프로세스가 강제 종료되었습니다.")
                if proc.poll() is None:
                    proc.wait(timeout=1.0)
                return f"외부 프로세스 작업 완료 (PID={proc.pid})"
            finally:
                if cancel_token is not None:
                    cancel_token.clear_callbacks()
                if proc.poll() is None:
                    kill_process_tree(proc)

        # 케이스 B: 순수 Python 루프 작업에서 cancel_event / progress_cb 로 취소 감지
        for step in range(1, steps + 1):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("내부 작업 도중 취소되었습니다.")
            time.sleep(0.5)
            if progress_cb:
                progress_cb(int((step / steps) * 100), f"내부 단계 처리 {step}/{steps}")

        return f"내부 작업 완료 ({steps}단계)"

    # --------------------------------------------------------------------------
    # [사용법 2] 윈도우 전용 리스너 구현 (TaskListenerBase 상속)
    # - QMainWindow와 다중 상속하지 않고 별도 리스너 클래스를 만들어 연결합니다.
    # - super().__init__(owner_widget=window) 를 호출하면 윈도우 생존 여부를 자동 추적합니다.
    # --------------------------------------------------------------------------
    class SampleWindowTaskListener(TaskListenerBase):
        def __init__(self, window: "SampleQueueDemoWindow") -> None:
            super().__init__(owner_widget=window)
            self._window = window

        def on_task_progress(self, task_key: str, task_name: str, percent: int, message: str) -> None:
            self._window.on_demo_progress(task_key, task_name, percent, message)

        def on_task_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
            self._window.on_demo_finished(task_key, task_name, status, data)

    # --------------------------------------------------------------------------
    # [사용법 3] 데모 메인/서브 윈도우
    # - 작업 제출: TaskManager().submit(..., cancel_on_close=True/False)
    # - 시점 조회: TaskManager().get_timing(task_key) / get_recent_timings()
    # - 창 닫힘  : closeEvent 및 destroyed 에서 TaskManager().on_window_closing(...)
    # --------------------------------------------------------------------------
    class SampleQueueDemoWindow(QMainWindow):
        def __init__(self, title: str = "TaskQueue SAMPLE Window", parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(title)
            self.resize(740, 480)

            self._seq = 0
            self._last_task_key: str | None = None
            self._child_windows: list[SampleQueueDemoWindow] = []

            # 1) 리스너 생성 (owner_widget=self 로 생존 추적 연결)
            self._listener = SampleWindowTaskListener(self)

            # 2) 안전망: C++ 객체 소멸(destroyed) 시에도 위젯 접근 없이 큐 정리 수행
            self.destroyed.connect(lambda *_: TaskManager().on_window_closing(self._listener))

            self._init_ui()
            self._connect_global_queue_view()

        def _init_ui(self) -> None:
            central = QWidget(self)
            root = QVBoxLayout(central)

            self.lbl_current = QLabel("현재 실행 중: 없음")
            self.lbl_status = QLabel("상태: 대기 중")
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

            root.addWidget(self.lbl_current)
            root.addWidget(self.lbl_status)
            root.addWidget(self.progress_bar)

            # 옵션 행
            opt_row = QHBoxLayout()
            opt_row.addWidget(QLabel("우선순위:"))
            self.combo_priority = QComboBox()
            self.combo_priority.addItem("긴급 (HIGH)", TaskPriority.HIGH)
            self.combo_priority.addItem("일반 (NORMAL)", TaskPriority.NORMAL)
            self.combo_priority.addItem("후순위 (LOW)", TaskPriority.LOW)
            self.combo_priority.setCurrentIndex(1)
            opt_row.addWidget(self.combo_priority)

            self.chk_external = QCheckBox("외부 프로세스(kill 테스트)")
            self.chk_cancel_on_close = QCheckBox("창 닫을 때 작업 취소 (cancel_on_close)")
            self.chk_cancel_on_close.setChecked(True)
            opt_row.addWidget(self.chk_external)
            opt_row.addWidget(self.chk_cancel_on_close)
            root.addLayout(opt_row)

            # 버튼 행
            btn_row = QHBoxLayout()
            self.btn_submit = QPushButton("작업 등록 (submit)")
            self.btn_submit.clicked.connect(self.on_click_submit)

            self.btn_cancel = QPushButton("최근 등록 작업 취소")
            self.btn_cancel.clicked.connect(self.on_click_cancel_last)

            self.btn_timing_log = QPushButton("시점 이력 출력")
            self.btn_timing_log.clicked.connect(self.on_click_print_timings)

            self.btn_sub_win = QPushButton("서브 윈도우 열기")
            self.btn_sub_win.clicked.connect(self.on_click_open_sub_window)

            btn_row.addWidget(self.btn_submit)
            btn_row.addWidget(self.btn_cancel)
            btn_row.addWidget(self.btn_timing_log)
            btn_row.addWidget(self.btn_sub_win)
            root.addLayout(btn_row)

            # 로그 & 대기열 목록
            body_row = QHBoxLayout()
            self.log_view = QTextEdit()
            self.log_view.setReadOnly(True)

            queue_col = QVBoxLayout()
            queue_col.addWidget(QLabel("전체 대기열 (Queue)"))
            self.queue_list = QListWidget()
            queue_col.addWidget(self.queue_list)

            body_row.addWidget(self.log_view, stretch=2)
            body_row.addLayout(queue_col, stretch=1)
            root.addLayout(body_row, stretch=1)

            self.setCentralWidget(central)

        def _connect_global_queue_view(self) -> None:
            worker = TaskManager().get_worker()
            worker.current_task_changed.connect(self._on_current_task_changed)
            worker.queue_updated.connect(self._on_queue_updated)

        def on_click_submit(self) -> None:
            self._seq += 1
            priority = int(self.combo_priority.currentData())
            use_ext = bool(self.chk_external.isChecked())
            cancel_on_close = bool(self.chk_cancel_on_close.isChecked())

            task_key = f"DEMO_{id(self)}_{self._seq}_{int(time.time() * 1000)}"
            task_name = f"{'ExtJob' if use_ext else 'Job'}#{self._seq}"

            try:
                # 한 번의 submit 호출로 파라미터 검증 + 리스너 등록 + 시점 기록 + 큐 적재 완료
                TaskManager().submit(
                    self._listener,
                    priority,
                    task_key,
                    task_name,
                    sample_worker_job,
                    steps=6,
                    use_external_process=use_ext,
                    cancel_on_close=cancel_on_close,
                )
                self._last_task_key = task_key
                timing = TaskManager().get_timing(task_key)
                reg_at = timing.registered_at if timing else "-"
                self.log_view.append(
                    f"[등록] {task_name} (prio={priority}, cancel_on_close={cancel_on_close}, 등록={reg_at})"
                )
            except Exception as exc:
                loge(f"[SampleUI] 작업 등록 실패: {exc}")
                QMessageBox.warning(self, "작업 등록 오류", str(exc))

        def on_click_cancel_last(self) -> None:
            if not self._last_task_key:
                self.log_view.append("[안내] 취소할 최근 작업이 없습니다.")
                return
            TaskManager().cancel(self._last_task_key)
            self.log_view.append(f"[취소 요청] {self._last_task_key}")

        def on_click_print_timings(self) -> None:
            """종료된 작업들의 등록/시작/취소/종료 시점 및 소요시간 요약 출력."""
            recent = TaskManager().get_recent_timings(limit=10)
            if not recent:
                self.log_view.append("[시점이력] 아직 종료된 작업 이력이 없습니다.")
                return
            self.log_view.append("--- [최근 작업 시점 이력] ---")
            for row in recent:
                self.log_view.append(
                    f"{row['task_name']} [{row['status']}] "
                    f"등록={row['registered_at']} | 시작={row['started_at'] or '-'} | "
                    f"취소={row['cancelled_at'] or '-'} | 종료={row['finished_at'] or '-'} | "
                    f"대기={row['wait_sec']}s, 실행={row['run_sec']}s, 총={row['total_sec']}s"
                )

        def on_click_open_sub_window(self) -> None:
            sub_idx = len(self._child_windows) + 1
            sub = SampleQueueDemoWindow(title=f"SAMPLE SubWindow #{sub_idx}")
            sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self._child_windows.append(sub)
            sub.show()

        def _on_current_task_changed(self, task_name: str) -> None:
            self.lbl_current.setText(f"현재 실행 중: {task_name}")

        def _on_queue_updated(self, task_names: list[str]) -> None:
            self.queue_list.clear()
            self.queue_list.addItems(task_names)

        def on_demo_progress(self, task_key: str, task_name: str, percent: int, message: str) -> None:
            self.progress_bar.setValue(max(0, min(100, int(percent))))
            self.lbl_status.setText(f"[{task_name}] {message} ({percent}%)")

        def on_demo_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
            if task_key == self._last_task_key:
                self._last_task_key = None

            # 완료 시점에 누적된 시점 기록(대기/실행/총 체류 시간) 조회
            timing = TaskManager().get_timing(task_key)
            timing_note = ""
            if timing is not None:
                run_txt = f"{timing.run_sec:.2f}s" if timing.run_sec is not None else "-"
                timing_note = f" (대기={timing.wait_sec:.2f}s, 실행={run_txt}, 총={timing.total_sec:.2f}s)"

            self.progress_bar.setValue(100 if status == "SUCCESS" else 0)
            self.lbl_status.setText(f"[{task_name}] {status}{timing_note}")
            self.log_view.append(f"[완료:{status}] {task_name}{timing_note} -> {data}")

        def closeEvent(self, event: Any) -> None:
            # 3) 윈도우 닫힐 때 정책(cancel_on_close)에 따라 취소/kill 또는 리스너만 분리
            logd(f"[SampleUI] closeEvent 호출 -> {self.windowTitle()}")
            TaskManager().on_window_closing(
                self._listener,
                reason=f"{self.windowTitle()} 종료로 작업이 취소되었습니다.",
            )
            super().closeEvent(event)

    # --------------------------------------------------------------------------
    # [사용법 4] 애플리케이션 시작 및 전체 종료(aboutToQuit) 연결
    # --------------------------------------------------------------------------
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(TaskManager.on_about_to_quit)

    main_demo = SampleQueueDemoWindow(title="TaskQueue Main SAMPLE Window")
    main_demo.show()
    sys.exit(app.exec())
# ```

# ### 추가된 `[QueueEvent]` 로그 항목
# * **`WORKER_START` / `WORKER_STOP` / `SHUTDOWN_REQUEST`**: 워커 루프 시작, 종료 요청, 루프 종료 시점
# * **`ENQUEUE` / `DEQUEUE` / `DEQUEUE_CANCELLED`**: 작업 적재, 큐에서 꺼냄, 대기 중 취소로 큐에서 제거될 때
# * **`CURRENT_TASK_CHANGED` / `TASK_FINISHED`**: 현재 실행 작업 전환 및 완료(`SUCCESS`/`CANCELLED`/`ERROR`)로 `없음`으로 돌아갈 때
# * **`CANCEL_ONE` / `CANCEL_KEYS` / `CANCEL_ALL` / `SKIP_CANCELLED` / `SKIP_SHUTDOWN`**: 단일/다중/전체 취소 및 스킵 발생 시
# * **`STATUS_EMIT`**: `queue_updated` 시그널을 내보내며 대기열 스냅샷을 출력할 때