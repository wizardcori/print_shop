### 2. `internet_share_services.py` 수정본
# 상태 머신(`InternetShareStateMachine`)과 연동하여 승인, 거절, 취소, 만료 등의 모든 액션을 명확하게 처리하고, 
# 관리자/운영자(`approval_operator`, `cancel_operator`) 및 처리 시각(`approved_at`, `cancelled_at`)이 절대 누락되지 않도록 견고하게 보완한 서비스 클래스입니다
import datetime
from typing import Dict, Any, Tuple, Optional

from Common.log import set_file_tag; set_file_tag("SERVICE")
from Common.log import logd, loge
from Common.current_user_session import get_username

from ..db.internet_share_db import internet_share_db
from ..db.db_signal_manager import signal_manager
from .internet_share_state_machine import InternetShareStateMachine


class InternetShareService:
    """
    인터넷 공유 요청 및 세션 관리를 제어하는 비즈니스 서비스 클래스.
    - 상태 머신(InternetShareStateMachine)을 통한 상태 전이 규칙 검증
    - 데이터베이스(InternetShareDB) 영속화 및 클라이언트 세션 재계산 오케스트레이션
    """

    def __init__(self, db=None, signals=None):
        self.db = db or internet_share_db
        self.signals = signals or signal_manager

    def _get_current_operator(self) -> str:
        """현재 실행 중인 관리자/운영자 계정명을 반환합니다."""
        return get_username() or "ADMIN"

    def create_request(self, record_item: dict) -> Tuple[Dict[str, Any], int]:
        """
        1. 신규 사용 요청 생성 서비스 (NONE -> PENDING)
        """
        machine = InternetShareStateMachine("NONE")
        data = machine.transition_to_pending(record_item)
        if not data:
            loge("[InternetShareService] 신규 요청 생성 상태 전이 실패")
            return {"status": "Error", "msg": "Invalid transition to pending."}, 400

        self.db.save(data)
        self.signals.request_updated.emit()
        logd(f"[InternetShareService] 신규 사용 요청 생성 완료: IP={data.get('client_ip')}")
        return {"status": "Pending", "msg": "Request created successfully.", "request_data": data}, 200

    def approve_to_queue(self, request_id: int) -> Tuple[Dict[str, Any], int]:
        """
        2. 사용 요청 승인 및 대기열 보관 서비스 (PENDING -> QUEUED)
        """
        record = self.db.get_by_id(request_id)
        if not record:
            loge(f"[InternetShareService] 레코드를 찾을 수 없음: ID={request_id}")
            return {"status": "Error", "msg": "Record not found."}, 404

        machine = InternetShareStateMachine(record.get("overall_status", "NONE"))
        data = machine.transition_to_queue()
        if not data:
            loge(f"[InternetShareService] 대기열 보관 전이 실패: ID={request_id}")
            return {"status": "Error", "msg": "Invalid state transition to queue."}, 400

        operator = self._get_current_operator()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        data["approval_operator"] = operator
        data["approved_at"] = now_str

        self.db.update(request_id, data)
        self.db.recalculate_sessions_for_client(
            client_token_id=record.get("client_token_id"), 
            client_ip=record.get("client_ip")
        )
        self.signals.request_updated.emit()
        logd(f"[InternetShareService] 대기열 보관 승인 완료: ID={request_id}, Operator={operator}")
        return {"status": "OK", "msg": "Request queued successfully."}, 200

    def reject_request(self, request_id: int) -> Tuple[Dict[str, Any], int]:
        """
        4. 사용 요청 승인 거절 서비스 (PENDING -> REJECTED)
        """
        record = self.db.get_by_id(request_id)
        if not record:
            loge(f"[InternetShareService] 레코드를 찾을 수 없음: ID={request_id}")
            return {"status": "Error", "msg": "Record not found."}, 404

        machine = InternetShareStateMachine(record.get("overall_status", "NONE"))
        data = machine.transition_to_reject()
        if not data:
            loge(f"[InternetShareService] 거절 전이 실패: ID={request_id}")
            return {"status": "Error", "msg": "Invalid state transition to reject."}, 400

        operator = self._get_current_operator()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data["approval_operator"] = operator
        data["approved_at"] = now_str

        self.db.update(request_id, data)
        self.signals.request_updated.emit()
        logd(f"[InternetShareService] 사용 요청 거절 완료: ID={request_id}, Operator={operator}")
        return {"status": "OK", "msg": "Request rejected."}, 200

    def cancel_request(self, request_id: int, operator: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
        """
        5. 사용 요청 취소 서비스 (PENDING/QUEUED/ACTIVE -> CANCELLED)
        """
        record = self.db.get_by_id(request_id)
        if not record:
            loge(f"[InternetShareService] 레코드를 찾을 수 없음: ID={request_id}")
            return {"status": "Error", "msg": "Record not found."}, 404

        machine = InternetShareStateMachine(record.get("overall_status", "NONE"))
        data = machine.transition_to_cancel()
        if not data:
            loge(f"[InternetShareService] 취소 전이 실패: ID={request_id}")
            return {"status": "Error", "msg": "Invalid state transition to cancel."}, 400

        cancel_operator = operator or self._get_current_operator()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data["cancel_operator"] = cancel_operator
        data["cancelled_at"] = now_str

        self.db.update(request_id, data)
        self.db.recalculate_sessions_for_client(
            client_token_id=record.get("client_token_id"), 
            client_ip=record.get("client_ip")
        )
        self.signals.request_updated.emit()
        logd(f"[InternetShareService] 사용 요청 취소 완료: ID={request_id}, Operator={cancel_operator}")
        return {"status": "OK", "msg": "Request cancelled successfully."}, 200

    def activate_session(self, request_id: int, minutes: int) -> Tuple[Dict[str, Any], int]:
        """
        3. 세션 사용 시작 및 활성화 서비스 (PENDING/QUEUED -> ACTIVE)
        """
        record = self.db.get_by_id(request_id)
        if not record:
            loge(f"[InternetShareService] 레코드를 찾을 수 없음: ID={request_id}")
            return {"status": "Error", "msg": "Record not found."}, 404

        machine = InternetShareStateMachine(record.get("overall_status", "NONE"))
        data = machine.transition_to_active(minutes=minutes)
        if not data:
            loge(f"[InternetShareService] 활성화 전이 실패: ID={request_id}")
            return {"status": "Error", "msg": "Invalid state transition to active."}, 400

        operator = self._get_current_operator()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data["approval_operator"] = operator
        data["approved_at"] = now_str

        self.db.update(request_id, data)

        # Redis 세션 큐 연동
        try:
            from redis_server.redis_session_manager import redis_session_manager
            redis_session_manager.add_to_queue(
                client_token_id=record.get("client_token_id"),
                request_id=request_id,
                minutes=minutes,
                operator=operator
            )
        except Exception as e:
            loge(f"[InternetShareService] Redis 큐 연동 중 오류 (무시됨): {e}")

        self.db.recalculate_sessions_for_client(
            client_token_id=record.get("client_token_id"), 
            client_ip=record.get("client_ip")
        )
        self.signals.request_updated.emit()
        logd(f"[InternetShareService] 세션 활성화 완료: ID={request_id}, Operator={operator}, Duration={minutes}분")
        return {"status": "OK", "msg": "Session activated successfully."}, 200

    def expire_session(self, request_id: int) -> Tuple[Dict[str, Any], int]:
        """
        6. 활성 세션 만료 서비스 (ACTIVE -> EXPIRED)
        """
        record = self.db.get_by_id(request_id)
        if not record:
            loge(f"[InternetShareService] 레코드를 찾을 수 없음: ID={request_id}")
            return {"status": "Error", "msg": "Record not found."}, 404

        machine = InternetShareStateMachine(record.get("overall_status", "NONE"))
        data = machine.transition_to_expire()
        if not data:
            loge(f"[InternetShareService] 만료 전이 실패: ID={request_id}")
            return {"status": "Error", "msg": "Invalid state transition to expire."}, 400

        self.db.update(request_id, data)
        self.signals.request_updated.emit()
        logd(f"[InternetShareService] 세션 만료 처리 완료: ID={request_id}")
        return {"status": "OK", "msg": "Session expired."}, 200


# 전역 싱글톤 인스턴스 제공
internet_share_service = InternetShareService()
