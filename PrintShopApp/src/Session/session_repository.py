"""
Session Database Repository Module.
Handles direct persistence for client identification and tracking using WAL mode.

[파일 역할]
- SQLite 데이터베이스와 직접 통신하여 클라이언트 식별 정보(IP, 토큰, 기기명 등)를 영구 저장(Upsert), 조회, 삭제하는 데이터 레이어입니다.
- 부모 클래스인 BaseDb의 WAL 모드 커넥션과 락(Lock) 기능을 활용하여 동시성 충돌을 안전하게 방지합니다.
- 데이터베이스 로드 및 저장 과정에서 발생하는 예외를 `logd`/`loge`로 추적합니다.
"""
import json
import sqlite3
from typing import Dict, Any
from Common.base_db import BaseDb
from Common.log import logd, loge

from Common.log import set_file_tag ;set_file_tag("SESSION")

class SessionRepository(BaseDb):
    """Client identity and tracking repository backed by SQLite."""
    table_name: str = "sessions"
    key_column: str = "session_key"
    create_table_sql: str = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT PRIMARY KEY,
            client_ip TEXT NOT NULL,
            client_token_id TEXT,
            device_name TEXT,
            updated_at TEXT NOT NULL,
            data_json TEXT NOT NULL
        );
    """

    def _rebuild_table(self, cursor, conn, target_columns_def, target_columns):
        """세션 테이블은 임의 리빌드를 수행하지 않음으로써 Primary Key 중돌을 방지합니다."""
        pass
    
    def load_sessions(self) -> Dict[str, Any]:
        """모든 클라이언트 식별 세션을 로드하여 client_ip를 키로 하는 딕셔너리로 반환합니다."""
        with self._lock, self._connect() as connection:
            sessions = {}
            try:
                for row in connection.execute(f'SELECT client_ip, data_json FROM {self.table_name}'):
                    try:
                        sessions[row['client_ip']] = json.loads(row['data_json'])
                    except (TypeError, json.JSONDecodeError) as e:
                        loge(f" JSON 파싱 실패 (IP: {row.get('client_ip')}): {e}")
                        continue
                logd(f" 총 {len(sessions)}개의 클라이언트 세션 로드 완료")
            except sqlite3.Error as e:
                loge(f" 세션 목록 조회 중 DB 오류 발생: {e}")
            return sessions

    def save_session(self, session: dict):
        """클라이언트 식별 정보를 저장 또는 갱신합니다 (Upsert)."""
        client_ip = str(session.get('client_ip', '-'))
        key = str(session.get('client_token_id') or 'ip:' + client_ip)
        updated_at = str(session.get('last_seen') or session.get('request_time') or '')
        
        try:
            with self._lock, self._connect() as connection:
                connection.execute(f'''
                    INSERT INTO {self.table_name}(session_key, client_ip, client_token_id, device_name, updated_at, data_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_key) DO UPDATE SET
                        client_ip=excluded.client_ip,
                        client_token_id=excluded.client_token_id,
                        device_name=excluded.device_name,
                        updated_at=excluded.updated_at,
                        data_json=excluded.data_json
                ''', (key, client_ip, session.get('client_token_id'),
                      session.get('device_name'), updated_at, json.dumps(session, ensure_ascii=False)))
            logd(f" 세션 저장/갱신 성공: IP={client_ip}, Key={key}")
        except (OSError, sqlite3.Error) as e:
            loge(f" 세션 저장 중 DB 오류 발생 (IP: {client_ip}): {e}")

    def delete_session(self, client_ip: str):
        """특정 클라이언트 IP에 해당하는 세션을 삭제합니다."""
        try:
            with self._lock, self._connect() as connection:
                connection.execute(f'DELETE FROM {self.table_name} WHERE client_ip = ?', (client_ip,))
            logd(f" 세션 삭제 완료: IP={client_ip}")
        except sqlite3.Error as e:
            loge(f" 세션 삭제 중 DB 오류 발생 (IP: {client_ip}): {e}")