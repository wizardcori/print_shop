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
                CREATE INDEX IF NOT EXISTS idx_usage_events_id ON usage_events(id);
                CREATE INDEX IF NOT EXISTS idx_usage_events_client_ip ON usage_events(client_ip);
            ''')
            columns = {
                row['name']
                for row in connection.execute('PRAGMA table_info(usage_events)')
            }
            if 'client_token_id' not in columns:
                connection.execute('ALTER TABLE usage_events ADD COLUMN client_token_id TEXT')

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
