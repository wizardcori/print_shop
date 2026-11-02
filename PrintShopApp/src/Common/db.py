"""SQLite persistence for portal sessions and usage history."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager


class AppDatabase:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        """Yield a SQLite connection and always close it on Windows."""
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

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
                CREATE TABLE IF NOT EXISTS print_pricing (
                    color_type TEXT NOT NULL,
                    paper_size TEXT NOT NULL,
                    unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
                    PRIMARY KEY (color_type, paper_size)
                );
                CREATE TABLE IF NOT EXISTS print_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    client_info TEXT,
                    operator_info TEXT,
                    printer_name TEXT,
                    color_type TEXT NOT NULL,
                    paper_size TEXT NOT NULL,
                    requested_pages INTEGER NOT NULL DEFAULT 0,
                    actual_pages INTEGER NOT NULL DEFAULT 0,
                    unit_price INTEGER NOT NULL DEFAULT 0,
                    total_price INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    spooler_job_id INTEGER,
                    counter_before INTEGER,
                    counter_after INTEGER,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    client_info TEXT,
                    current_state TEXT NOT NULL,
                    total_price INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS order_files (
                    file_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY(order_id) REFERENCES orders(order_id)
                );
                CREATE TABLE IF NOT EXISTS order_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    changed_by TEXT,
                    reason TEXT,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    file_id TEXT,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS print_pricing (
                    color_type TEXT NOT NULL,
                    paper_size TEXT NOT NULL,
                    unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
                    PRIMARY KEY (color_type, paper_size)
                );
                CREATE TABLE IF NOT EXISTS print_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    client_info TEXT,
                    operator_info TEXT,
                    printer_name TEXT,
                    color_type TEXT NOT NULL,
                    paper_size TEXT NOT NULL,
                    requested_pages INTEGER NOT NULL DEFAULT 0,
                    actual_pages INTEGER NOT NULL DEFAULT 0,
                    unit_price INTEGER NOT NULL DEFAULT 0,
                    total_price INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    spooler_job_id INTEGER,
                    counter_before INTEGER,
                    counter_after INTEGER,
                    error_message TEXT
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
            connection.executemany(
                'INSERT OR IGNORE INTO print_pricing(color_type, paper_size, unit_price) VALUES (?, ?, ?)',
                [('MONO', 'A4', 50), ('COLOR', 'A4', 250)],
            )

    def get_print_price(self, color_type, paper_size):
        with self._lock, self._connect() as connection:
            row = connection.execute(
                'SELECT unit_price FROM print_pricing WHERE color_type = ? AND paper_size = ?',
                (str(color_type).upper(), str(paper_size).upper()),
            ).fetchone()
            return None if row is None else int(row['unit_price'])

    def save_print_log(self, record):
        fields = ('timestamp', 'client_info', 'operator_info', 'printer_name',
                  'color_type', 'paper_size', 'requested_pages', 'actual_pages',
                  'unit_price', 'total_price', 'status', 'spooler_job_id',
                  'counter_before', 'counter_after', 'error_message')
        values = [record.get(field) for field in fields]
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO print_logs ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                values,
            )
            return cursor.lastrowid

    def load_print_logs(self, limit=100):
        with self._lock, self._connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM print_logs ORDER BY id DESC LIMIT ?', (int(limit),)
            )]

    def create_order(self, order_id, client_info='', state='UPLOADED', total_price=0, created_at=''):
        with self._lock, self._connect() as connection:
            connection.execute('INSERT INTO orders(order_id, created_at, client_info, current_state, total_price) VALUES (?, ?, ?, ?, ?)',
                               (str(order_id), str(created_at), str(client_info), str(state), int(total_price)))

    def add_order_file(self, file_id, order_id, filename, options, validation=None):
        with self._lock, self._connect() as connection:
            connection.execute('INSERT INTO order_files(file_id, order_id, filename, options_json, validation_json) VALUES (?, ?, ?, ?, ?)',
                               (str(file_id), str(order_id), str(filename), json.dumps(options, ensure_ascii=False), json.dumps(validation or [], ensure_ascii=False)))

    def transition_order(self, order_id, to_state, changed_by='', reason='', timestamp=''):
        from .order_workflow import OrderState, TRANSITIONS
        with self._lock, self._connect() as connection:
            row = connection.execute('SELECT current_state FROM orders WHERE order_id = ?', (str(order_id),)).fetchone()
            if row is None:
                raise KeyError(order_id)
            current = OrderState(row['current_state'])
            target = OrderState(to_state)
            if target not in TRANSITIONS[current]:
                raise ValueError(f'Invalid order transition: {current.value} -> {target.value}')
            connection.execute('UPDATE orders SET current_state = ? WHERE order_id = ?', (target.value, str(order_id)))
            connection.execute('INSERT INTO order_state_history(order_id, from_state, to_state, changed_by, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
                               (str(order_id), current.value, target.value, str(changed_by), str(reason), str(timestamp)))
            return target.value

    def add_notification(self, order_id, code, message, severity='WARNING', file_id=None, created_at=''):
        with self._lock, self._connect() as connection:
            cursor = connection.execute('INSERT INTO notification_logs(order_id, file_id, code, message, severity, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                                        (str(order_id), file_id, str(code), str(message), str(severity), str(created_at)))
            return cursor.lastrowid

    def get_order_state(self, order_id):
        with self._lock, self._connect() as connection:
            row = connection.execute('SELECT current_state FROM orders WHERE order_id = ?',
                                     (str(order_id),)).fetchone()
            return None if row is None else row['current_state']

    def find_order_ids_for_filename(self, filename):
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                'SELECT order_id FROM order_files WHERE lower(filename) = lower(?) ORDER BY rowid',
                (str(filename),)).fetchall()
            return [row['order_id'] for row in rows]

    def load_orders(self):
        """Return persisted orders for the administrator dashboard."""
        with self._lock, self._connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT order_id, client_info, current_state, total_price FROM orders ORDER BY created_at DESC')]

    def load_order_notifications(self, order_id):
        """Return validation notifications associated with one order."""
        with self._lock, self._connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT code, message, severity, status FROM notification_logs '
                'WHERE order_id = ? ORDER BY id', (str(order_id),))]
            connection.executemany(
                'INSERT OR IGNORE INTO print_pricing(color_type, paper_size, unit_price) VALUES (?, ?, ?)',
                [('MONO', 'A4', 50), ('COLOR', 'A4', 250)],
            )

    def get_print_price(self, color_type, paper_size):
        with self._lock, self._connect() as connection:
            row = connection.execute(
                'SELECT unit_price FROM print_pricing WHERE color_type = ? AND paper_size = ?',
                (str(color_type).upper(), str(paper_size).upper()),
            ).fetchone()
            return None if row is None else int(row['unit_price'])

    def save_print_log(self, record):
        fields = ('timestamp', 'client_info', 'operator_info', 'printer_name',
                  'color_type', 'paper_size', 'requested_pages', 'actual_pages',
                  'unit_price', 'total_price', 'status', 'spooler_job_id',
                  'counter_before', 'counter_after', 'error_message')
        values = [record.get(field) for field in fields]
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO print_logs ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                values,
            )
            return cursor.lastrowid

    def load_print_logs(self, limit=100):
        with self._lock, self._connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM print_logs ORDER BY id DESC LIMIT ?', (int(limit),)
            )]

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
