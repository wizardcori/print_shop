# """File transfer database repository."""
# import json
# from Common.base_db import BaseDb


# class TransferDatabase(BaseDb):
#     def _initialize(self):
#         super()._initialize()
#         with self._lock, self._connect() as connection:
#             connection.executescript('''
#                 CREATE TABLE IF NOT EXISTS file_transfers (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     transfer_key TEXT NOT NULL,
#                     client_ip TEXT,
#                     client_token_id TEXT,
#                     started_at TEXT NOT NULL,
#                     expires_at TEXT NOT NULL,
#                     file_count INTEGER NOT NULL DEFAULT 0,
#                     internet_granted INTEGER NOT NULL DEFAULT 0,
#                     data_json TEXT NOT NULL
#                 );
#                 CREATE TABLE IF NOT EXISTS transfer_log (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     target_folder TEXT NOT NULL,
#                     identity TEXT,
#                     filename TEXT NOT NULL,
#                     received_at TEXT NOT NULL,
#                     data_json TEXT NOT NULL,
#                     task_completed INTEGER NOT NULL DEFAULT 0
#                 );
#                 CREATE INDEX IF NOT EXISTS idx_transfer_log_folder ON transfer_log(target_folder);
#             ''')
#             transfer_columns = {
#                 row['name'] for row in connection.execute('PRAGMA table_info(transfer_log)')
#             }
#             if 'task_completed' not in transfer_columns:
#                 connection.execute('ALTER TABLE transfer_log ADD COLUMN task_completed INTEGER NOT NULL DEFAULT 0')

#     def save_file_transfer(self, record):
#         with self._lock, self._connect() as connection:
#             connection.execute(
#                 '''INSERT INTO file_transfers
#                    (transfer_key, client_ip, client_token_id, started_at, expires_at,
#                     file_count, internet_granted, data_json)
#                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
#                 (str(record.get('transfer_key', '')), record.get('client_ip'),
#                  record.get('client_token_id'), str(record.get('started_at', '')),
#                  str(record.get('expires_at', '')), int(record.get('file_count', 0)),
#                  int(bool(record.get('internet_granted', False))),
#                  json.dumps(record, ensure_ascii=False)),
#             )

#     def save_transfer_log(self, target_folder, identity, record):
#         with self._lock, self._connect() as connection:
#             connection.execute(
#                 '''INSERT INTO transfer_log
#                    (target_folder, identity, filename, received_at, data_json, task_completed)
#                    VALUES (?, ?, ?, ?, ?, ?)''',
#                 (str(target_folder), str(identity or ''), str(record.get('filename', '')),
#                  str(record.get('received_time', '')), json.dumps(record, ensure_ascii=False),
#                  int(bool(record.get('task_completed', False)))),
#             )

#     def load_transfer_logs(self):
#         with self._lock, self._connect() as connection:
#             rows = connection.execute(
#                 'SELECT target_folder, identity, data_json FROM transfer_log ORDER BY id'
#             )
#             grouped = {}
#             for row in rows:
#                 try:
#                     record = json.loads(row['data_json'])
#                 except (TypeError, json.JSONDecodeError):
#                     continue
#                 key = (row['target_folder'], row['identity'] or '')
#                 grouped.setdefault(key, []).append(record)
#             return grouped

#     def load_transfer_logs_for_identity(self, identity):
#         with self._lock, self._connect() as connection:
#             rows = connection.execute(
#                 'SELECT target_folder, data_json FROM transfer_log WHERE identity = ? ORDER BY id',
#                 (str(identity),)
#             )
#             grouped = {}
#             for row in rows:
#                 try:
#                     record = json.loads(row['data_json'])
#                 except (TypeError, json.JSONDecodeError):
#                     continue
#                 grouped.setdefault(row['target_folder'], []).append(record)
#             return grouped

#     def update_transfer_log(self, target_folder, filename, copies=None, color=None):
#         with self._lock, self._connect() as connection:
#             rows = connection.execute(
#                 'SELECT id, data_json FROM transfer_log WHERE target_folder = ? AND filename = ?',
#                 (str(target_folder), str(filename))
#             ).fetchall()
#             for row in rows:
#                 try:
#                     record = json.loads(row['data_json'])
#                 except (TypeError, json.JSONDecodeError):
#                     continue
#                 if copies is not None:
#                     record['copies'] = int(copies)
#                 if color is not None:
#                     record['color'] = str(color)
#                 connection.execute(
#                     'UPDATE transfer_log SET data_json = ?, task_completed = ? WHERE id = ?',
#                     (json.dumps(record, ensure_ascii=False), int(bool(record.get('task_completed', False))), row['id'])
#                 )

#     def update_transfer_completed(self, target_folder, filename, completed):
#         with self._lock, self._connect() as connection:
#             rows = connection.execute(
#                 'SELECT id, data_json FROM transfer_log WHERE target_folder = ? AND filename = ?',
#                 (str(target_folder), str(filename))
#             ).fetchall()
#             for row in rows:
#                 try:
#                     record = json.loads(row['data_json'])
#                 except (TypeError, json.JSONDecodeError):
#                     record = {}
#                 record['task_completed'] = bool(completed)
#                 connection.execute(
#                     'UPDATE transfer_log SET data_json = ?, task_completed = ? WHERE id = ?',
#                     (json.dumps(record, ensure_ascii=False), int(bool(completed)), row['id'])
#                 )