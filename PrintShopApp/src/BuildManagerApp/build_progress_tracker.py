from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from BuildManagerApp.build_progress_badge import BuildProgressBadge, format_hms

DEFAULT_PACE_DURATION_SEC: float = 45.0
MIN_PACE_DURATION_SEC: float = 1.0
DEFAULT_TICK_INTERVAL_MS: int = 1000
MIN_TICK_INTERVAL_MS: int = 100

PACED_PERCENT_CAP: int = 95
COMPLETED_PERCENT_VALUE: int = 100
INITIAL_PERCENT_VALUE: int = 0
ZERO_SECONDS_VALUE: float = 0.0

DEFAULT_TIME_PLACEHOLDER: str = "-"
DEFAULT_ELAPSED_STR: str = "00:00:00"

STATUS_BUILDING: str = "빌드중"
STATUS_COMPLETED: str = "빌드완료"
STATUS_FAILED: str = "빌드실패"
TERMINAL_STATUSES: tuple[str, ...] = (STATUS_COMPLETED, STATUS_FAILED)


class BuildProgressTracker(QObject):
    """대상 앱별 초당 소요시간(00:00:00~)과 진행 퍼센트를 관리하고 BuildProgressBadge를 갱신하는 컨트롤러."""

    def __init__(
        self,
        group_lookup: Callable[[str], object | None],
        pace_duration_sec: float = DEFAULT_PACE_DURATION_SEC,
        tick_interval_ms: int = DEFAULT_TICK_INTERVAL_MS,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._group_lookup = group_lookup
        self._pace_duration_sec = max(MIN_PACE_DURATION_SEC, float(pace_duration_sec))

        self._timer = QTimer(self)
        self._timer.setInterval(max(MIN_TICK_INTERVAL_MS, int(tick_interval_ms)))
        self._timer.timeout.connect(self._on_tick)

        self._running_key: str | None = None
        self._start_ts: float = ZERO_SECONDS_VALUE
        self._start_str: str = DEFAULT_TIME_PLACEHOLDER
        self._percent: int = INITIAL_PERCENT_VALUE
        self._detail: str = ""

    def _resolve_badge(self, target_key: str) -> BuildProgressBadge | None:
        grp = self._group_lookup(target_key)
        if grp is None:
            return None
        badge = getattr(grp, "progress_badge", None)
        return badge if isinstance(badge, BuildProgressBadge) else None

    def reset(self):
        self._timer.stop()
        self._running_key = None
        self._start_ts = ZERO_SECONDS_VALUE
        self._start_str = DEFAULT_TIME_PLACEHOLDER
        self._percent = INITIAL_PERCENT_VALUE
        self._detail = ""

    def handle_progress(
        self,
        target_key: str,
        status: str,
        percent: int,
        start_time: str,
        end_time: str,
        detail: str,
    ):
        badge = self._resolve_badge(target_key)
        if badge is None:
            return

        if status == STATUS_BUILDING:
            if self._running_key != target_key:
                self._running_key = target_key
                self._start_ts = time.perf_counter()
                self._start_str = start_time
                self._percent = INITIAL_PERCENT_VALUE
                if not self._timer.isActive():
                    self._timer.start()

            elapsed_sec = max(ZERO_SECONDS_VALUE, time.perf_counter() - self._start_ts)
            self._percent = max(self._percent, int(percent))
            self._detail = detail
            badge.set_building(
                percent=self._percent,
                start_time=start_time,
                elapsed_str=format_hms(elapsed_sec),
                end_time=DEFAULT_TIME_PLACEHOLDER,
                detail=detail,
            )
        elif status in TERMINAL_STATUSES:
            elapsed_sec = (
                max(ZERO_SECONDS_VALUE, time.perf_counter() - self._start_ts)
                if self._running_key == target_key
                else ZERO_SECONDS_VALUE
            )
            if self._running_key == target_key:
                self.reset()
            badge.set_completed(
                success=(status == STATUS_COMPLETED),
                start_time=start_time,
                elapsed_str=format_hms(elapsed_sec),
                end_time=end_time,
                percent=COMPLETED_PERCENT_VALUE if status == STATUS_COMPLETED else int(percent),
            )
        else:
            badge.set_waiting(
                start_time=start_time,
                elapsed_str=DEFAULT_ELAPSED_STR,
                end_time=end_time,
                percent=int(percent),
            )

    def _on_tick(self):
        key = self._running_key
        if not key:
            self._timer.stop()
            return
        badge = self._resolve_badge(key)
        if badge is None:
            self.reset()
            return

        elapsed_sec = max(ZERO_SECONDS_VALUE, time.perf_counter() - self._start_ts)
        paced_pct = min(
            PACED_PERCENT_CAP,
            int((elapsed_sec / self._pace_duration_sec) * PACED_PERCENT_CAP),
        )
        next_pct = max(self._percent, paced_pct)
        self._percent = next_pct
        badge.set_building(
            percent=next_pct,
            start_time=self._start_str,
            elapsed_str=format_hms(elapsed_sec),
            end_time=DEFAULT_TIME_PLACEHOLDER,
            detail=self._detail,
        )