from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from build_progress_badge import BuildProgressBadge, format_hms


class BuildProgressTracker(QObject):
    """대상 앱별 초당 소요시간(00:00:00~)과 진행 퍼센트를 관리하고 BuildProgressBadge를 갱신하는 컨트롤러."""

    def __init__(
        self,
        group_lookup: Callable[[str], object | None],
        pace_duration_sec: float = 45.0,
        tick_interval_ms: int = 1000,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._group_lookup = group_lookup
        self._pace_duration_sec = max(1.0, float(pace_duration_sec))

        self._timer = QTimer(self)
        self._timer.setInterval(max(100, int(tick_interval_ms)))
        self._timer.timeout.connect(self._on_tick)

        self._running_key: str | None = None
        self._start_ts: float = 0.0
        self._start_str: str = "-"
        self._percent: int = 0
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
        self._start_ts = 0.0
        self._start_str = "-"
        self._percent = 0
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

        if status == "빌드중":
            if self._running_key != target_key:
                self._running_key = target_key
                self._start_ts = time.perf_counter()
                self._start_str = start_time
                self._percent = 0
                if not self._timer.isActive():
                    self._timer.start()

            elapsed_sec = max(0.0, time.perf_counter() - self._start_ts)
            self._percent = max(self._percent, int(percent))
            self._detail = detail
            badge.set_building(
                percent=self._percent,
                start_time=start_time,
                elapsed_str=format_hms(elapsed_sec),
                end_time="-",
                detail=detail,
            )
        elif status in ("빌드완료", "빌드실패"):
            elapsed_sec = (
                max(0.0, time.perf_counter() - self._start_ts)
                if self._running_key == target_key
                else 0.0
            )
            if self._running_key == target_key:
                self.reset()
            badge.set_completed(
                success=(status == "빌드완료"),
                start_time=start_time,
                elapsed_str=format_hms(elapsed_sec),
                end_time=end_time,
                percent=100 if status == "빌드완료" else int(percent),
            )
        else:
            badge.set_waiting(
                start_time=start_time,
                elapsed_str="00:00:00",
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

        elapsed_sec = max(0.0, time.perf_counter() - self._start_ts)
        paced_pct = min(95, int((elapsed_sec / self._pace_duration_sec) * 95))
        next_pct = max(self._percent, paced_pct)
        self._percent = next_pct
        badge.set_building(
            percent=next_pct,
            start_time=self._start_str,
            elapsed_str=format_hms(elapsed_sec),
            end_time="-",
            detail=self._detail,
        )