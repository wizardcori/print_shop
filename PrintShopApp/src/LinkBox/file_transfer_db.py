"""File transfer metadata database repository."""
import json
from typing import Dict, Any
from Common.base_db import BaseDb


class FileTransferDatabase(BaseDb):
    # BaseDb 설정 오버라이드
    table_name: str = "file_transfers"
    key_column: str = "transfer_key"
    create_table_sql: str = """
        CREATE TABLE IF NOT EXISTS file_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_key TEXT NOT NULL,
            client_ip TEXT,
            client_token_id TEXT,
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 0,
            internet_granted INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL
        );
    """

    def save_file_transfer(self, record: dict):
        """파일 전송 세션 정보를 저장합니다."""
        with self._lock, self._connect() as connection:
            connection.execute(
                f'''INSERT INTO {self.table_name}
                   (transfer_key, client_ip, client_token_id, started_at, expires_at,
                    file_count, internet_granted, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (str(record.get('transfer_key', '')), record.get('client_ip'),
                 record.get('client_token_id'), str(record.get('started_at', '')),
                 str(record.get('expires_at', '')), int(record.get('file_count', 0)),
                 int(bool(record.get('internet_granted', False))),
                 json.dumps(record, ensure_ascii=False)),
            )