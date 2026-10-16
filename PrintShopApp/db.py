"""SQLite persistence for portal sessions and usage history."""
import json
import os
import sqlite3
import threading


class AppDatabase:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._lock, self._connect() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_key TEXT PRIMARY KEY,
                    client_ip TEXT NOT NULL,
                    client_token_id TEXT,
                    status TEXT,
                    updated_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT NOT NULL,
                    log_type TEXT,
                    client_ip TEXT,
                    client_token_id TEXT,
                    data_json TEXT NOT NULL
                );
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
                CREATE TABLE IF NOT EXISTS transfer_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_folder TEXT NOT NULL,
                    identity TEXT,
                    filename TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    task_completed INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_transfer_log_folder ON transfer_log(target_folder);
                CREATE INDEX IF NOT EXISTS idx_usage_events_id ON usage_events(id);
                CREATE INDEX IF NOT EXISTS idx_usage_events_client_ip ON usage_events(client_ip);
            ''')
            columns = {
                row['name']
                for row in connection.execute('PRAGMA table_info(usage_events)')
            }
            if 'client_token_id' not in columns:
                connection.execute('ALTER TABLE usage_events ADD COLUMN client_token_id TEXT')
            transfer_columns = {
                row['name'] for row in connection.execute('PRAGMA table_info(transfer_log)')
            }
            if 'task_completed' not in transfer_columns:
                connection.execute('ALTER TABLE transfer_log ADD COLUMN task_completed INTEGER NOT NULL DEFAULT 0')

    def load(self):
        with self._lock, self._connect() as connection:
            sessions = {}
            for row in connection.execute('SELECT client_ip, data_json FROM sessions'):
                try:
                    sessions[row['client_ip']] = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
            history = []
            for row in connection.execute('SELECT data_json FROM usage_events ORDER BY id'):
                try:
                    history.append(json.loads(row['data_json']))
                except (TypeError, json.JSONDecodeError):
                    continue
            return sessions, history

    def save_session(self, session):
        client_ip = str(session.get('client_ip', '-'))
        key = str(session.get('client_token_id') or 'ip:' + client_ip)
        updated_at = str(session.get('last_seen') or session.get('request_time') or '')
        with self._lock, self._connect() as connection:
            connection.execute('''
                INSERT INTO sessions(session_key, client_ip, client_token_id, status, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    client_ip=excluded.client_ip,
                    client_token_id=excluded.client_token_id,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    data_json=excluded.data_json
            ''', (key, client_ip, session.get('client_token_id'),
                  session.get('status'), updated_at, json.dumps(session, ensure_ascii=False)))

    def save_event(self, record):
        with self._lock, self._connect() as connection:
            connection.execute(
                'INSERT INTO usage_events(event_time, log_type, client_ip, client_token_id, data_json) VALUES (?, ?, ?, ?, ?)',
                (str(record.get('request_time') or record.get('approval_time') or ''),
                 record.get('log_type'), record.get('client_ip'), record.get('client_token_id'),
                 json.dumps(record, ensure_ascii=False)),
            )

    def delete_session(self, client_ip):
        with self._lock, self._connect() as connection:
            connection.execute('DELETE FROM sessions WHERE client_ip = ?', (client_ip,))

    def save_file_transfer(self, record):
        with self._lock, self._connect() as connection:
            connection.execute(
                '''INSERT INTO file_transfers
                   (transfer_key, client_ip, client_token_id, started_at, expires_at,
                    file_count, internet_granted, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (str(record.get('transfer_key', '')), record.get('client_ip'),
                 record.get('client_token_id'), str(record.get('started_at', '')),
                 str(record.get('expires_at', '')), int(record.get('file_count', 0)),
                 int(bool(record.get('internet_granted', False))),
                 json.dumps(record, ensure_ascii=False)),
            )

    def save_transfer_log(self, target_folder, identity, record):
        with self._lock, self._connect() as connection:
            connection.execute(
                '''INSERT INTO transfer_log
                   (target_folder, identity, filename, received_at, data_json, task_completed)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (str(target_folder), str(identity or ''), str(record.get('filename', '')),
                 str(record.get('received_time', '')), json.dumps(record, ensure_ascii=False),
                 int(bool(record.get('task_completed', False)))),
            )

    def load_transfer_logs(self):
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                'SELECT target_folder, identity, data_json FROM transfer_log ORDER BY id'
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

    def load_transfer_logs_for_identity(self, identity):
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                'SELECT target_folder, data_json FROM transfer_log WHERE identity = ? ORDER BY id',
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

    def update_transfer_log(self, target_folder, filename, copies=None, color=None):
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                'SELECT id, data_json FROM transfer_log WHERE target_folder = ? AND filename = ?',
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
                    'UPDATE transfer_log SET data_json = ?, task_completed = ? WHERE id = ?',
                    (json.dumps(record, ensure_ascii=False), int(bool(record.get('task_completed', False))), row['id'])
                )

    def update_transfer_completed(self, target_folder, filename, completed):
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                'SELECT id, data_json FROM transfer_log WHERE target_folder = ? AND filename = ?',
                (str(target_folder), str(filename))
            ).fetchall()
            for row in rows:
                try:
                    record = json.loads(row['data_json'])
                except (TypeError, json.JSONDecodeError):
                    record = {}
                record['task_completed'] = bool(completed)
                connection.execute(
                    'UPDATE transfer_log SET data_json = ?, task_completed = ? WHERE id = ?',
                    (json.dumps(record, ensure_ascii=False), int(bool(completed)), row['id'])
                )
