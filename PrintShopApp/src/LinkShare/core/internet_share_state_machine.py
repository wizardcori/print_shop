from enum import Enum
from typing import Dict, Any, Optional
import datetime

from Common.log import set_file_tag; set_file_tag("STATE")
from Common.log import logd, loge

class RequestStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"

class ApprovalStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class CancelStatus(str, Enum):
    NONE = "NONE"
    NORMAL = "NORMAL"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"

class OverallStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class InternetShareStateMachine:
    ALLOWED_TRANSITIONS = {
        OverallStatus.NONE: [OverallStatus.PENDING],
        OverallStatus.PENDING: [OverallStatus.QUEUED, OverallStatus.ACTIVE, OverallStatus.REJECTED, OverallStatus.CANCELLED],
        OverallStatus.QUEUED: [OverallStatus.ACTIVE, OverallStatus.CANCELLED],
        OverallStatus.ACTIVE: [OverallStatus.EXPIRED, OverallStatus.CANCELLED],
        OverallStatus.EXPIRED: [],
        OverallStatus.REJECTED: [],
        OverallStatus.CANCELLED: []
    }

    def __init__(self, current_overall_status: str = "NONE"):
        try:
            self.overall_status = OverallStatus(current_overall_status)
        except ValueError:
            self.overall_status = OverallStatus.NONE

    def _validate_transition(self, new_overall_status: OverallStatus) -> bool:
        allowed = self.ALLOWED_TRANSITIONS.get(self.overall_status, [])
        if new_overall_status not in allowed:
            loge(f"[StateMachine] 허용되지 않는 상태 전환 시도: {self.overall_status} -> {new_overall_status}")
            return False
        return True

    def transition_to_pending(self, record_item: dict) -> Optional[Dict[str, Any]]:
        """신규 생성 (NONE -> PENDING)"""
        if not self._validate_transition(OverallStatus.PENDING):
            return None
        
        record_item.update({
            "request_status": RequestStatus.PENDING.value,
            "approval_status": ApprovalStatus.PENDING.value,
            "cancel_status": CancelStatus.NORMAL.value,
            "overall_status": OverallStatus.PENDING.value
        })
        return record_item

    def transition_to_queue(self) -> Optional[Dict[str, Any]]:
        """승인 및 대기열 보관 (PENDING -> QUEUED)"""
        if not self._validate_transition(OverallStatus.QUEUED):
            return None
        return {
            "request_status": RequestStatus.COMPLETED.value,
            "approval_status": ApprovalStatus.APPROVED.value,
            "overall_status": OverallStatus.QUEUED.value,
            "start_time": None,
            "expires_at": None
        }

    def transition_to_active(self, minutes: int) -> Optional[Dict[str, Any]]:
        """이용 시작/활성화 (PENDING/QUEUED -> ACTIVE)"""
        if not self._validate_transition(OverallStatus.ACTIVE):
            return None

        now = datetime.datetime.now()
        start_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        expires_at_str = (now + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "request_status": RequestStatus.COMPLETED.value,
            "approval_status": ApprovalStatus.APPROVED.value,
            "overall_status": OverallStatus.ACTIVE.value,
            "start_time": start_time_str,
            "expires_at": expires_at_str
        }

    def transition_to_reject(self) -> Optional[Dict[str, Any]]:
        """승인 거절 (PENDING -> REJECTED)"""
        if not self._validate_transition(OverallStatus.REJECTED):
            return None
        return {
            "request_status": RequestStatus.COMPLETED.value,
            "approval_status": ApprovalStatus.REJECTED.value,
            "overall_status": OverallStatus.REJECTED.value
        }

    def transition_to_cancel(self) -> Optional[Dict[str, Any]]:
        """취소 처리 ( -> CANCELLED)"""
        if not self._validate_transition(OverallStatus.CANCELLED):
            return None
        return {
            "cancel_status": CancelStatus.CANCELLED.value,
            "overall_status": OverallStatus.CANCELLED.value
        }

    def transition_to_expire(self) -> Optional[Dict[str, Any]]:
        """만료 처리 (ACTIVE -> EXPIRED)"""
        if not self._validate_transition(OverallStatus.EXPIRED):
            return None
        return {
            "overall_status": OverallStatus.EXPIRED.value
        }
