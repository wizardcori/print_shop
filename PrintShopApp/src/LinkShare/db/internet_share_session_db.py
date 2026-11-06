"""Internet share session database repository."""
import json
from typing import Dict, Any
from Common.base_db import BaseDb


class InternetShareSessionDatabase(BaseDb):
    # BaseDb 설정 오버라이드
    table_name: str = "sessions"
    key_column: str = "session_key"
    create_table_sql: str = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT PRIMARY KEY,
            client_ip TEXT NOT NULL,
            client_token_id TEXT,
            status TEXT,
            updated_at TEXT NOT NULL,
            data_json TEXT NOT NULL
        );
    """

    def load_sessions(self) -> Dict[str, Any]:
        """모든 세션을 로드하여 client_ip를 키로 하는 딕셔너리로 반환합니다."""
        with self._lock, self._connect() as connection:
            sessions = {}
            for row in connection.execute(f'SELECT client_ip, data_json FROM {self.table_name}'):
                try:
                    sessions[row['client_ip']] = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
            return sessions

    def save_session(self, session: dict):
        """세션 정보를 저장 또는 갱신합니다 (Upsert)."""
        client_ip = str(session.get('client_ip', '-'))
        key = str(session.get('client_token_id') or 'ip:' + client_ip)
        updated_at = str(session.get('last_seen') or session.get('request_time') or '')
        
        with self._lock, self._connect() as connection:
            connection.execute(f'''
                INSERT INTO {self.table_name}(session_key, client_ip, client_token_id, status, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    client_ip=excluded.client_ip,
                    client_token_id=excluded.client_token_id,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    data_json=excluded.data_json
            ''', (key, client_ip, session.get('client_token_id'),
                  session.get('status'), updated_at, json.dumps(session, ensure_ascii=False)))

    def delete_session(self, client_ip: str):
        """특정 클라이언트 IP에 해당하는 세션을 삭제합니다."""
        with self._lock, self._connect() as connection:
            connection.execute(f'DELETE FROM {self.table_name} WHERE client_ip = ?', (client_ip,))