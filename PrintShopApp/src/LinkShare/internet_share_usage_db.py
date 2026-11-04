"""Internet share usage events database repository."""
import json
from typing import Dict, Any, List
from Common.base_db import BaseDb


class InternetShareUsageDatabase(BaseDb):
    # BaseDb 설정 오버라이드
    table_name: str = "usage_events"
    key_column: str = "id"
    create_table_sql: str = """
        CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL,
            log_type TEXT,
            client_ip TEXT,
            client_token_id TEXT,
            data_json TEXT NOT NULL
        );
    """

    def _ensure_table_exists(self):
        """테이블 생성 및 인덱스 설정을 수행합니다."""
        super()._ensure_table_exists()
        with self._lock, self._connect() as connection:
            connection.executescript(f'''
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_id ON {self.table_name}(id);
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_client_ip ON {self.table_name}(client_ip);
            ''')

    def load_history(self) -> List[Dict[str, Any]]:
        """저장된 모든 사용 이력 데이터를 로드합니다."""
        with self._lock, self._connect() as connection:
            history = []
            for row in connection.execute(f'SELECT data_json FROM {self.table_name} ORDER BY id'):
                try:
                    history.append(json.loads(row['data_json']))
                except (TypeError, json.JSONDecodeError):
                    continue
            return history

    def save_event(self, record: dict):
        """새로운 사용 이력 이벤트를 저장합니다."""
        event_time = str(record.get('request_time') or record.get('approval_time') or '')
        log_type = record.get('log_type')
        client_ip = record.get('client_ip')
        client_token_id = record.get('client_token_id')
        
        with self._lock, self._connect() as connection:
            connection.execute(
                f'''
                INSERT INTO {self.table_name}(event_time, log_type, client_ip, client_token_id, data_json) 
                VALUES (?, ?, ?, ?, ?)
                ''',
                (event_time, log_type, client_ip, client_token_id, json.dumps(record, ensure_ascii=False)),
            )