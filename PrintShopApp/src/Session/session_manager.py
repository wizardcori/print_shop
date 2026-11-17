"""
Session Controller & Thread Coordinator.
Manages locks, condition signals, and thread synchronization for client identification.

[파일 역할]
- 멀티스레드 및 웹 라우트 환경에서 세션 데이터 접근 충돌을 막기 위한 스레드 락(Lock)과 조건 변수(Condition)를 총괄합니다.
- Repository와 Context를 조합하여 클라이언트 식별 및 상태 알림 제어 코어 역할을 수행합니다.
- 상태 변경 전파(notify_all) 이벤트를 상세히 로깅합니다.
"""
import threading
from Common.log import logd
from .session_repository import SessionRepository
from .session_context import SessionContext

from Common.log import set_file_tag ;set_file_tag("SESSION")

class SessionManager:
    """Central Client Identification Controller."""

    repository = SessionRepository()

    def __init__(self, cookie_name: str, client_identity_map: dict, client_metadata_map: dict):
        self.session_identity_lock = threading.Lock()
        self.status_condition = threading.Condition()
        
        self.context = SessionContext(
            cookie_name=cookie_name,
            client_identity_map=client_identity_map,
            client_metadata_map=client_metadata_map,
            identity_lock=self.session_identity_lock,
        )
        logd("[SessionManager] 클라이언트 식별 세션 관리자 코어 초기화 완료")

    def notify_status_change(self):
        """클라이언트 상태 변경 이벤트를 대기 중인 스레드들에 전파합니다."""
        logd("[SessionManager] 클라이언트 상태 변경 알림 전파 (notify_all) 실행")
        with self.status_condition:
            self.status_condition.notify_all()

    @staticmethod
    def session_status_signature(session: dict):
        return tuple(session.get(key) for key in (
            'status', 'approval_time', 'end_time', 'remaining_seconds', 'internet_status'
        ))