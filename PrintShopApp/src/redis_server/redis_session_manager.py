import sqlite3
import datetime
import json
import subprocess
import time
import threading
from typing import Dict, Any, List, Callable

import redis  # 외부 라이브러리 redis 명시적 임포트

from Common.log import set_file_tag; set_file_tag("REDIS")
from Common.log import logd, loge

from LinkShare.db.internet_share_db import internet_share_db
from LinkShare.db.db_signal_manager import signal_manager
from LinkShare.core.internet_share_services import internet_share_service


# ==========================================
# 2. Redis Session & Queue Manager
# ==========================================
class RedisSessionManager:
    def __init__(self, host='localhost', port=6379, db=0):
        logd(f"redis server head")
        self.redis_client = redis.Redis(
            host=host, port=port, db=db, decode_responses=True
        )
        logd(f"redis server tail")

    def set_active_session(self, session_key: str, request_id: int, minutes: int):
        """활성 세션(Hash) 설정 및 서비스 레이어 동기화"""
        active_key = f"session:{session_key}:active_session"
        
        now = datetime.datetime.now()
        start_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        expires_dt = now + datetime.timedelta(minutes=minutes)
        expires_at_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        mapping = {
            "request_id": str(request_id),
            "minutes": str(minutes),
            "start_time": start_time_str,
            "expires_at": expires_at_str
        }
        self.redis_client.hset(active_key, mapping=mapping)
        
        # 서비스 레이어를 통한 세션 활성화 및 DB 동기화 처리
        internet_share_service.activate_session(request_id, minutes)
        logd(f"[SessionManager] 활성 세션 즉시 시작: SessionKey={session_key}, ID={request_id}")

    def add_to_queue(self, session_key: str, request_id: int, minutes: int, operator: str = "ADMIN"):
        """
        승인 요청 처리:
        - 서비스 레이어를 통해 대기열 상태(QUEUED)로 DB 반영
        - 현재 활성 세션이 없으면 -> 즉시 set_active_session 호출하여 시작
        - 이미 활성 세션이 돌고 있으면 -> queue(List)에 적재
        """
        internet_share_service.approve_to_queue(request_id)

        active_key = f"session:{session_key}:active_session"
        queue_key = f"session:{session_key}:queue"

        if not self.redis_client.exists(active_key):
            logd(f"[SessionManager] 활성 세션이 없어 바로 시작합니다: SessionKey={session_key}, ID={request_id}")
            self.set_active_session(session_key, request_id, minutes)
        else:
            record_data = {
                "request_id": request_id,
                "minutes": minutes,
                "status": "QUEUED"
            }
            self.redis_client.rpush(queue_key, json.dumps(record_data))
            logd(f"[SessionManager] 활성 세션 존재로 대기열 추가: SessionKey={session_key}, ID={request_id}")

    def del_to_queue(self, session_key: str, request_id: int = None):
        """대기열 항목 삭제 또는 선두 항목 추출(LPOP)"""
        queue_key = f"session:{session_key}:queue"
        
        if request_id is not None:
            items = self.redis_client.lrange(queue_key, 0, -1)
            self.redis_client.delete(queue_key)
            
            removed = False
            for item_str in items:
                try:
                    data = json.loads(item_str)
                    if data.get("request_id") == request_id and not removed:
                        removed = True
                        continue
                    self.redis_client.rpush(queue_key, item_str)
                except json.JSONDecodeError:
                    pass
            logd(f"[SessionManager] 대기열 특정 항목 삭제: SessionKey={session_key}, ID={request_id}")
        else:
            popped = self.redis_client.lpop(queue_key)
            logd(f"[SessionManager] 대기열 선두 항목 제거(LPOP): SessionKey={session_key}")
            return popped

    def get_total_remaining_time(self, session_key: str) -> Dict[str, Any]:
        """특정 session_key의 활성 세션 남은 시간과 대기 중인 모든 승인 레코드의 시간을 합산"""
        active_key = f"session:{session_key}:active_session"
        queue_key = f"session:{session_key}:queue"
        
        total_remaining_seconds = 0
        active_remaining_seconds = 0
        total_queued_minutes = 0
        active_minutes = 0
        active_request_id = None
        
        session_data = self.redis_client.hgetall(active_key)
        if session_data:
            expires_at_str = session_data.get("expires_at", "")
            active_minutes = int(session_data.get("minutes", 0))
            active_request_id = session_data.get("request_id")
            
            if expires_at_str:
                try:
                    expires_dt = datetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
                    now = datetime.datetime.now()
                    remaining = (expires_dt - now).total_seconds()
                    if remaining > 0:
                        active_remaining_seconds = int(remaining)
                        total_remaining_seconds += active_remaining_seconds
                except ValueError:
                    pass

        queue_items = self.redis_client.lrange(queue_key, 0, -1)
        queued_requests = []
        
        for item_str in queue_items:
            try:
                data = json.loads(item_str)
                mins = int(data.get("minutes", 0))
                total_queued_minutes += mins
                queued_requests.append({
                    "request_id": data.get("request_id"),
                    "minutes": mins
                })
            except json.JSONDecodeError:
                pass

        total_remaining_seconds_with_queue = total_remaining_seconds + (total_queued_minutes * 60)

        hours = total_remaining_seconds_with_queue // 3600
        minutes = (total_remaining_seconds_with_queue % 3600) // 60
        secs = total_remaining_seconds_with_queue % 60
        formatted_total = f"{hours:02d}:{minutes:02d}:{secs:02d}"

        return {
            "session_key": session_key,
            "active_session": {
                "request_id": active_request_id,
                "minutes": active_minutes,
                "remaining_seconds": active_remaining_seconds
            },
            "queued_sessions": queued_requests,
            "total_queued_minutes": total_queued_minutes,
            "total_remaining_seconds": total_remaining_seconds_with_queue,
            "total_remaining_formatted": formatted_total
        }

    def log_session_status(self, total_info: dict) -> None:
        """세션 상태를 로그로 출력합니다."""
        session_key = total_info.get("session_key", "")
        active_session = total_info.get("active_session", {})
        remaining_seconds = active_session.get("remaining_seconds", 0)
        
        queued_count = len(total_info.get("queued_sessions", []))
        total_formatted = total_info.get("total_remaining_formatted", "00:00:00")

        rem_hours = int(remaining_seconds) // 3600
        rem_mins = (int(remaining_seconds) % 3600) // 60
        rem_secs = int(remaining_seconds) % 60

        short_session_key = session_key[:10]

        logd(
            f"[SessionManager] {short_session_key} | "
            f"현재 세션 남은 시간: {rem_hours:02d}시 {rem_mins:02d}분 {rem_secs:02d}초 | "
            f"대기 중인 레코드 수: {queued_count}개 | "
            f"전체 남은 시간: {total_formatted}"
        )

    def check_and_trigger_signals(self, session_key: str):
        """주기적 검사: 만료 시 다음 큐 자동 승격 및 1분 전 임박 감지"""
        active_key = f"session:{session_key}:active_session"
        
        session_data = self.redis_client.hgetall(active_key)
        if not session_data:
            return

        expires_at_str = session_data.get("expires_at")
        if not expires_at_str:
            return

        expires_dt = datetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        remaining_seconds = (expires_dt - now).total_seconds()

        total_info = self.get_total_remaining_time(session_key)
        self.log_session_status(total_info)

        # 1. 세션 만료 시점 (0초 이하)
        if remaining_seconds <= 0:
            current_req_id = int(session_data.get("request_id"))
            logd(f"[SessionManager] 세션 만료 발생: SessionKey={session_key}, ID={current_req_id}")

            # 서비스 레이어를 통한 만료 처리
            internet_share_service.expire_session(current_req_id)

            self.redis_client.delete(active_key)
            
            next_item_str = self.del_to_queue(session_key)
            if next_item_str:
                next_data = json.loads(next_item_str)
                self.set_active_session(session_key, next_data["request_id"], next_data["minutes"])
                logd(f"[SessionManager] 대기열 다음 항목 자동 승격 완료: ID={next_data['request_id']}")
            else:
                logd(f"[SessionManager] 대기열이 비어 있어 인터넷 사용이 최종 종료됩니다: SessionKey={session_key}")
                
                if hasattr(signal_manager, "internet_session_ended"):
                    signal_manager.internet_session_ended.emit(session_key)
                else:
                    signal_manager.request_updated.emit()                

        # 2. 만료 1분 전 임박 시점 (0초 초과 60초 이하)
        elif 0 < remaining_seconds <= 60:
            notified_flag = f"session:{session_key}:notified_1min:{session_data.get('request_id')}"
            if not self.redis_client.get(notified_flag):
                logd(f"[SessionManager] 만료 1분 전 임박 감지: SessionKey={session_key}")
                self.redis_client.setex(notified_flag, 70, "1")


# ==========================================
# 3. Redis 구동 및 백그라운드 감시 데몬
# ==========================================
def ensure_redis_running():
    client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    try:
        client.ping()
        logd("[Redis] Redis 서버가 이미 실행 중입니다.")
        return True
    except redis.ConnectionError:
        logd("[Redis] Redis 서버 구동을 시도합니다...")
        try:
            subprocess.Popen(["wsl", "sudo", "service", "redis-server", "start"], 
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(2)
            client.ping()
            logd("[Redis] Redis 서버 구동 성공!")
            return True
        except Exception as e:
            loge(f"[Redis] 자동 구동 실패: {e}")
            return False

class RedisSessionDaemon:
    def __init__(self, manager: RedisSessionManager):
        self.manager = manager
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logd("[Daemon] Redis 세션 감시 스레드가 시작되었습니다.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        logd("[Daemon] Redis 세션 감시 스레드가 중지되었습니다.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                keys = self.manager.redis_client.keys("session:*:active_session")
                for key in keys:
                    parts = key.split(":")
                    if len(parts) >= 2:
                        session_key = parts[1]
                        self.manager.check_and_trigger_signals(session_key)
            except Exception as e:
                loge(f"[Daemon] 감시 루프 오류: {e}")
            time.sleep(3)


# 전역 인스턴스
redis_session_manager = RedisSessionManager()
session_daemon = RedisSessionDaemon(redis_session_manager)
session_daemon.start()