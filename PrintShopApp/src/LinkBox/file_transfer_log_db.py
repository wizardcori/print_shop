"""Transfer log database repository."""
import json
from typing import Dict, Any, List, Tuple
from Common.base_db import BaseDb


class TransferLogDatabase(BaseDb):
    # BaseDb 설정 오버라이드
    table_name: str = "transfer_log"
    key_column: str = "id"
    create_table_sql: str = """
        CREATE TABLE IF NOT EXISTS transfer_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_folder TEXT NOT NULL,
            identity TEXT,
            filename TEXT NOT NULL,
            received_at TEXT NOT NULL,
            data_json TEXT NOT NULL,
            task_completed INTEGER NOT NULL DEFAULT 0
        );
    """

    def _ensure_table_exists(self):
        """테이블 생성 및 인덱스 설정을 수행합니다."""
        super()._ensure_table_exists()
        with self._lock, self._connect() as connection:
            connection.executescript(f'''
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_folder ON {self.table_name}(target_folder);
            ''')

    def save_transfer_log(self, target_folder: str, identity: str, record: dict):
        """개별 전송 로그 및 작업 항목을 저장합니다."""
        with self._lock, self._connect() as connection:
            connection.execute(
                f'''INSERT INTO {self.table_name}
                   (target_folder, identity, filename, received_at, data_json, task_completed)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (str(target_folder), str(identity or ''), str(record.get('filename', '')),
                 str(record.get('received_time', '')), json.dumps(record, ensure_ascii=False),
                 int(bool(record.get('task_completed', False)))),
            )

    def load_transfer_logs(self) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """모든 전송 로그를 로드하여 폴더 및 식별자별로 그룹화하여 반환합니다."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f'SELECT target_folder, identity, data_json FROM {self.table_name} ORDER BY id'
            )
            grouped = {}
            for row in rows:
                try:
                    record = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
                key = (row['target_folder'], row['identity'] or '')
                grouped.setdefault(key, []).append(record)
            return grouped

    def load_transfer_logs_for_identity(self, identity: str) -> Dict[str, List[Dict[str, Any]]]:
        """특정 식별자에 해당하는 전송 로그를 로드하여 폴더별로 그룹화합니다."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f'SELECT target_folder, data_json FROM {self.table_name} WHERE identity = ? ORDER BY id',
                (str(identity),)
            )
            grouped = {}
            for row in rows:
                try:
                    record = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
                grouped.setdefault(row['target_folder'], []).append(record)
            return grouped

    def update_transfer_log(self, target_folder: str, filename: str, copies: int = None, color: str = None):
        """전송 로그의 세부 옵션(복사본 수, 색상 등)을 업데이트합니다."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f'SELECT id, data_json FROM {self.table_name} WHERE target_folder = ? AND filename = ?',
                (str(target_folder), str(filename))
            ).fetchall()
            for row in rows:
                try:
                    record = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
                if copies is not None:
                    record['copies'] = int(copies)
                if color is not None:
                    record['color'] = str(color)
                connection.execute(
                    f'UPDATE {self.table_name} SET data_json = ?, task_completed = ? WHERE id = ?',
                    (json.dumps(record, ensure_ascii=False), int(bool(record.get('task_completed', False))), row['id'])
                )

    def update_transfer_completed(self, target_folder: str, filename: str, completed: bool):
        """전송 로그의 작업 완료 상태를 업데이트합니다."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f'SELECT id, data_json FROM {self.table_name} WHERE target_folder = ? AND filename = ?',
                (str(target_folder), str(filename))
            ).fetchall()
            for row in rows:
                try:
                    record = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    record = {}
                record['task_completed'] = bool(completed)
                connection.execute(
                    f'UPDATE {self.table_name} SET data_json = ?, task_completed = ? WHERE id = ?',
                    (json.dumps(record, ensure_ascii=False), int(bool(completed)), row['id'])
                )