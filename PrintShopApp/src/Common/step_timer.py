"""
빌드 단계별 시작/종료 시간 측정 및 퍼센테이지 산출 모듈 (step_timer.py)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Iterable


class BuildStepTimer:
    """하위 클래스에서 단계를 등록해 사용할 수 있는 단계별 시간 측정/진행률 계산기."""

    # 부모 클래스에서는 고정 단계 목록을 강제하지 않음
    STEP_DEFINITIONS: list[tuple[str, float]] | list[str] = []

    def __init__(
        self,
        steps: Iterable[str | tuple[str, float]] | None = None,
        auto_register_class_steps: bool = True,
    ):
        self.step_order: list[str] = []
        self.step_weights: dict[str, float] = {}
        self.reset()

        if auto_register_class_steps and self.STEP_DEFINITIONS:
            self.register_steps(self.STEP_DEFINITIONS)

        if steps is not None:
            self.register_steps(steps)

    def reset(self) -> None:
        """단계 타이밍 및 전체 빌드 시작/종료 기록을 초기화합니다."""
        self.step_timings: dict[str, dict[str, Any]] = {}
        self.build_start_ts: float | None = None
        self.build_end_ts: float | None = None
        self.build_start_str: str = "-"
        self.build_end_str: str = "-"
        self.current_step: str | None = None

    def register_step(
        self,
        step_key: str,
        weight: float | None = None,
        index: int | None = None,
    ) -> str:
        """단일 단계를 등록합니다. 이미 있으면 가중치/위치만 갱신할 수 있습니다."""
        key = str(step_key).strip()
        if not key:
            raise ValueError("step_key는 비어 있을 수 없습니다.")

        if key not in self.step_order:
            if index is None or index < 0 or index >= len(self.step_order):
                self.step_order.append(key)
            else:
                self.step_order.insert(index, key)
        elif index is not None:
            self.step_order.remove(key)
            clamped_idx = max(0, min(len(self.step_order), index))
            self.step_order.insert(clamped_idx, key)

        if weight is not None:
            self.step_weights[key] = max(0.001, float(weight))
        elif key not in self.step_weights:
            self.step_weights[key] = 0.0  # 0.0이면 미지정 가중치로 취급해 자동 분배

        return key

    def register_steps(self, steps: Iterable[str | tuple[str, float]]) -> list[str]:
        """여러 단계를 순서대로 일괄 등록합니다. (예: ['a', ('b', 0.4), 'c'])"""
        registered: list[str] = []
        for item in steps:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                k = self.register_step(str(item[0]), weight=float(item[1]))
            else:
                k = self.register_step(str(item), weight=None)
            registered.append(k)
        return registered

    def start_step(
        self,
        step_key: str,
        weight: float | None = None,
        now_ts: float | None = None,
        now_str: str | None = None,
    ) -> dict[str, Any]:
        """특정 단계의 시작 시각을 기록합니다. 미등록 단계면 자동으로 등록합니다."""
        key = self.register_step(step_key, weight=weight)
        ts = time.perf_counter() if now_ts is None else float(now_ts)
        s_str = now_str or datetime.now().strftime("%H:%M:%S")

        if self.build_start_ts is None:
            self.build_start_ts = ts
            self.build_start_str = s_str

        self.current_step = key
        record: dict[str, Any] = {
            "start_ts": ts,
            "end_ts": None,
            "start_str": s_str,
            "end_str": "-",
            "elapsed": 0.0,
        }
        self.step_timings[key] = record
        return dict(record)

    def end_step(
        self,
        step_key: str,
        now_ts: float | None = None,
        now_str: str | None = None,
    ) -> dict[str, Any]:
        """특정 단계의 종료 시각과 경과 시간을 기록합니다."""
        key = self.register_step(step_key)
        ts = time.perf_counter() if now_ts is None else float(now_ts)
        e_str = now_str or datetime.now().strftime("%H:%M:%S")

        self.build_end_ts = ts
        self.build_end_str = e_str

        record = self.step_timings.get(key)
        if record is None:
            record = {
                "start_ts": ts,
                "end_ts": ts,
                "start_str": e_str,
                "end_str": e_str,
                "elapsed": 0.0,
            }
            self.step_timings[key] = record
        else:
            start_ts = float(record.get("start_ts") or ts)
            record["end_ts"] = ts
            record["end_str"] = e_str
            record["elapsed"] = max(0.0, ts - start_ts)

        return dict(record)

    def get_step_timing(self, step_key: str) -> dict[str, Any]:
        rec = self.step_timings.get(step_key)
        return dict(rec) if isinstance(rec, dict) else {}

    def snapshot_timings(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self.step_timings.items()}

    def import_timings(self, timings: dict[str, dict[str, Any]]) -> None:
        if not isinstance(timings, dict):
            return
        for k, v in timings.items():
            if isinstance(v, dict):
                self.register_step(k)
                self.step_timings[k] = dict(v)

    def _get_base_normalized_weights(self) -> dict[str, float]:
        """등록된 단계들의 초기 가중치를 합이 1.0이 되도록 정규화합니다."""
        if not self.step_order:
            return {}

        explicit_sum = sum(
            max(0.0, float(self.step_weights.get(k) or 0.0))
            for k in self.step_order
        )
        unspecified_keys = [
            k for k in self.step_order
            if max(0.0, float(self.step_weights.get(k) or 0.0)) == 0.0
        ]

        raw: dict[str, float] = {}
        if explicit_sum <= 0.0:
            equal_w = 1.0 / len(self.step_order)
            for k in self.step_order:
                raw[k] = equal_w
            return raw

        if unspecified_keys:
            rem = max(0.0, 1.0 - min(0.95, explicit_sum))
            scale = (1.0 - rem) / explicit_sum if explicit_sum > 0.95 else 1.0
            each_unspec = rem / len(unspecified_keys)
            for k in self.step_order:
                w = max(0.0, float(self.step_weights.get(k) or 0.0))
                raw[k] = (w * scale) if w > 0.0 else each_unspec
        else:
            for k in self.step_order:
                raw[k] = max(0.0, float(self.step_weights.get(k) or 0.0)) / explicit_sum

        return raw

    def get_effective_weights(self) -> dict[str, float]:
        """종료된 단계의 실측 소요 시간을 반영한 동적 가중치를 반환합니다."""
        weights = self._get_base_normalized_weights()
        if not weights:
            return {}

        measured_elapsed = {
            k: float(v.get("elapsed") or 0.0)
            for k, v in self.step_timings.items()
            if k in weights and v.get("end_ts") is not None and float(v.get("elapsed") or 0.0) > 0.0
        }
        total_measured = sum(measured_elapsed.values())
        if total_measured <= 0.0:
            return weights

        finished_keys = set(measured_elapsed.keys())
        remaining_keys = [k for k in self.step_order if k not in finished_keys]
        remaining_base_sum = sum(weights.get(k, 0.0) for k in remaining_keys)

        if not remaining_keys:
            finished_budget = 1.0
        else:
            finished_budget = min(
                0.85,
                total_measured / max(total_measured + (remaining_base_sum * 10.0), 1e-6),
            )

        for k in finished_keys:
            weights[k] = (measured_elapsed[k] / total_measured) * finished_budget

        if remaining_keys and remaining_base_sum > 0.0:
            rem_budget = max(0.0, 1.0 - finished_budget)
            for k in remaining_keys:
                weights[k] = (weights.get(k, 0.0) / remaining_base_sum) * rem_budget

        return weights

    def calc_percent(self, current_step: str, phase_ratio: float = 0.5, is_final: bool = False) -> int:
        """등록된 단계 순서와 측정된 시작/종료 시간을 기반으로 퍼센테이지(1~100)를 계산합니다."""
        if is_final:
            return 100

        key = self.register_step(current_step)
        weights = self.get_effective_weights()
        clamped_ratio = max(0.0, min(1.0, float(phase_ratio)))

        rec = self.step_timings.get(key)
        if rec and rec.get("end_ts") is None and rec.get("start_ts") is not None:
            live_elapsed = max(0.0, time.perf_counter() - float(rec["start_ts"]))
            completed_durs = [
                float(v.get("elapsed") or 0.0)
                for v in self.step_timings.values()
                if v.get("end_ts") is not None and float(v.get("elapsed") or 0.0) > 0.0
            ]
            if completed_durs:
                avg_dur = max(1.0, sum(completed_durs) / len(completed_durs))
                clamped_ratio = max(clamped_ratio, min(0.9, live_elapsed / avg_dur))

        accumulated = 0.0
        for step_k in self.step_order:
            w = weights.get(step_k, 0.0)
            if step_k == key:
                accumulated += w * clamped_ratio
                break
            if self.step_timings.get(step_k, {}).get("end_ts") is not None:
                accumulated += w

        return max(1, min(99, int(round(accumulated * 100))))

    def build_progress_payload(
        self,
        step_key: str,
        phase: str,
        detail: str = "",
        phase_ratio: float = 0.5,
        is_final: bool = False,
        force_percent: int | None = None,
    ) -> dict[str, Any]:
        key = self.register_step(step_key)
        rec = self.step_timings.get(key, {})
        pct = (
            max(0, min(100, int(force_percent)))
            if force_percent is not None
            else self.calc_percent(key, phase_ratio=phase_ratio, is_final=is_final)
        )
        return {
            "step": key,
            "phase": phase,
            "detail": detail or key,
            "percent": pct,
            "start_time": self.build_start_str,
            "end_time": self.build_end_str if is_final else "-",
            "step_start_time": str(rec.get("start_str") or "-"),
            "step_end_time": str(rec.get("end_str") or "-"),
            "elapsed": float(rec.get("elapsed") or 0.0),
            "step_order": list(self.step_order),
            "step_timings": self.snapshot_timings(),
        }