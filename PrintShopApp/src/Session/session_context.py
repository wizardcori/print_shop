"""
Session Context & Client Identity Resolver Module.
Handles client token identification and metadata processing.

[파일 역할]
- HTTP 요청이 들어왔을 때 쿠키, IP, 요청 헤더 등을 분석하여 클라이언트의 고유 신원(Identity)을 판별합니다.
- 브라우저 환경에서 전달된 메타데이터(기기 정보, 마지막 접속 시각 등)를 클라이언트 세션에 병합하고 관리합니다.
- 신원 식별 및 메타데이터 적용 과정을 디버그 로그로 상세히 남깁니다.
"""
import datetime
import hashlib
import secrets
from typing import Tuple
from Common.log import logd, loge
from LinkShare.core.client_identity_service import get_client_identity as resolve_client_identity

from Common.log import set_file_tag ;set_file_tag("SESSION")

class SessionContext:
    """Client Identity resolver and metadata manager."""

    def __init__(self, cookie_name: str, client_identity_map: dict, client_metadata_map: dict, identity_lock):
        self.cookie_name = cookie_name
        self.client_identity_map = client_identity_map
        self.client_metadata_map = client_metadata_map
        self.session_identity_lock = identity_lock

    def resolve_identity(self, request_obj, shared_sessions: dict) -> Tuple[str, str, str, str]:
        """현재 HTTP 요청으로부터 (token, token_id, client_ip, device_name) 식별 구조를 도출합니다."""
        logd("[SessionContext] 클라이언트 식별 신원(Identity) 분석 시작")
        try:
            token, token_id, client_ip, device_name = resolve_client_identity(
                request_obj,
                self.cookie_name,
                self.client_identity_map,
                shared_sessions,
                self.session_identity_lock,
                self.client_metadata_map,
                secrets,
                datetime,
                hashlib,
            )
            logd(f"[SessionContext] 식별 완료: IP={client_ip}, TokenID={token_id}, Device={device_name}")
            return token, token_id, client_ip, device_name
        except Exception as e:
            loge(f"[SessionContext] 클라이언트 식별 중 예외 발생: {e}")
            raise

    def apply_metadata(self, session: dict, token_id: str):
        """브라우저 자동 측정 메타데이터를 클라이언트 세션에 반영합니다."""
        metadata = self.client_metadata_map.get(token_id, {})
        if metadata:
            logd(f"[SessionContext] 메타데이터 적용 중: TokenID={token_id}")
        for key, value in metadata.items():
            if value:
                session[key] = value
        session.setdefault('first_seen', metadata.get('last_seen', ''))
        session['last_seen'] = metadata.get('last_seen', session.get('last_seen', ''))