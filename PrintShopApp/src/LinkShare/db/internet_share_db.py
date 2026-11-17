import sqlite3
import datetime
from typing import Dict, Any, List
from Common.base_db import BaseDb
from Common.log import logd, loge
from .db_signal_manager import signal_manager
from Common.current_user_session import get_username

from Common.log import set_file_tag; set_file_tag("DB")


class InternetShareDB(BaseDb):
    table_name: str = "internet_share"
    key_column: str = "id"

    def __init__(self):
        super().__init__()
        self.operator = get_username()

    create_table_sql: str = """
        CREATE TABLE IF NOT EXISTS internet_share (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_name TEXT,
            device_mac TEXT,
            client_ip TEXT NOT NULL,
            client_token_id TEXT NOT NULL,
            device_name TEXT,
            minutes INTEGER NOT NULL DEFAULT 60,
            price REAL NOT NULL DEFAULT 0.0,
            currency TEXT DEFAULT 'PHP',
            request_status TEXT DEFAULT 'PENDING',
            approval_status TEXT DEFAULT 'PENDING',
            cancel_status TEXT DEFAULT 'NORMAL',
            overall_status TEXT DEFAULT 'PENDING',            
            approval_operator TEXT,
            cancel_operator TEXT,
            request_time TEXT NOT NULL,
            approved_at TEXT,
            cancelled_at TEXT,
            start_time TEXT,
            expires_at TEXT
        );
    """

    initial_records: List[Dict[str, Any]] = [
        {"user_id": "user_01", "user_name": "김철수", "device_mac": "AA:BB:CC:DD:EE:01", "client_ip": "192.168.1.101", "client_token_id": "tok_001", "device_name": "Galaxy-S23", "minutes": 60, "price": 10.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "APPROVED", "cancel_status": "NORMAL", "overall_status": "ACTIVE", "approval_operator": "ADMIN", "request_time": "2026-06-03 10:00:00", "approved_at": "2026-06-03 10:05:00", "start_time": "2026-06-03 10:05:00", "expires_at": "2026-06-03 11:05:00"},
        {"user_id": "user_02", "user_name": "이영희", "device_mac": "AA:BB:CC:DD:EE:02", "client_ip": "192.168.1.102", "client_token_id": "tok_002", "device_name": "iPhone-15", "minutes": 120, "price": 20.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "APPROVED", "cancel_status": "NORMAL", "overall_status": "ACTIVE", "approval_operator": "ADMIN", "request_time": "2026-06-03 10:30:00", "approved_at": "2026-06-03 10:32:00", "start_time": "2026-06-03 10:32:00", "expires_at": "2026-06-03 12:32:00"},
        {"user_id": "user_03", "user_name": "박민수", "device_mac": "AA:BB:CC:DD:EE:03", "client_ip": "192.168.1.103", "client_token_id": "tok_003", "device_name": "MacBook-Pro", "minutes": 30, "price": 5.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "APPROVED", "cancel_status": "NORMAL", "overall_status": "ACTIVE", "approval_operator": "MANAGER", "request_time": "2026-06-03 11:00:00", "approved_at": "2026-06-03 11:01:00", "start_time": "2026-06-03 11:01:00", "expires_at": "2026-06-03 11:31:00"},
        {"user_id": "user_04", "user_name": "정지은", "device_mac": "AA:BB:CC:DD:EE:04", "client_ip": "192.168.1.104", "client_token_id": "tok_004", "device_name": "iPad-Air", "minutes": 60, "price": 10.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "APPROVED", "cancel_status": "NORMAL", "overall_status": "ACTIVE", "approval_operator": "ADMIN", "request_time": "2026-06-03 11:15:00", "approved_at": "2026-06-03 11:16:00", "start_time": "2026-06-03 11:16:00", "expires_at": "2026-06-03 12:16:00"},
        {"user_id": "user_05", "user_name": "홍길동", "device_mac": "AA:BB:CC:DD:EE:05", "client_ip": "192.168.1.105", "client_token_id": "tok_005", "device_name": "Galaxy-Tab", "minutes": 10, "price": 2.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "APPROVED", "cancel_status": "NORMAL", "overall_status": "ACTIVE", "approval_operator": "ADMIN", "request_time": "2026-06-03 11:40:00", "approved_at": "2026-06-03 11:42:00", "start_time": "2026-06-03 11:42:00", "expires_at": "2026-06-03 11:52:00"},
        {"user_id": "user_06", "user_name": "강호동", "device_mac": "AA:BB:CC:DD:EE:06", "client_ip": "192.168.1.106", "client_token_id": "tok_006", "device_name": "iPhone-14", "minutes": 60, "price": 10.0, "currency": "PHP", "request_status": "PENDING", "approval_status": "PENDING", "cancel_status": "NORMAL", "overall_status": "PENDING", "request_time": "2026-06-03 11:50:00"},
        {"user_id": "user_07", "user_name": "유재석", "device_mac": "AA:BB:CC:DD:EE:07", "client_ip": "192.168.1.107", "client_token_id": "tok_007", "device_name": "Galaxy-S22", "minutes": 30, "price": 5.0, "currency": "PHP", "request_status": "PENDING", "approval_status": "PENDING", "cancel_status": "NORMAL", "overall_status": "PENDING", "request_time": "2026-06-03 11:53:00"},
        {"user_id": "user_08", "user_name": "신동엽", "device_mac": "AA:BB:CC:DD:EE:08", "client_ip": "192.168.1.108", "client_token_id": "tok_008", "device_name": "LG-Velvet", "minutes": 120, "price": 20.0, "currency": "PHP", "request_status": "PENDING", "approval_status": "PENDING", "cancel_status": "NORMAL", "overall_status": "PENDING", "request_time": "2026-06-03 11:55:00"},
        {"user_id": "user_09", "user_name": "서장훈", "device_mac": "AA:BB:CC:DD:EE:09", "client_ip": "192.168.1.109", "client_token_id": "tok_009", "device_name": "iPhone-13", "minutes": 5, "price": 1.0, "currency": "PHP", "request_status": "PENDING", "approval_status": "PENDING", "cancel_status": "NORMAL", "overall_status": "PENDING", "request_time": "2026-06-03 11:58:00"},
        {"user_id": "user_10", "user_name": "김종국", "device_mac": "AA:BB:CC:DD:EE:10", "client_ip": "192.168.1.110", "client_token_id": "tok_010", "device_name": "Galaxy-Note20", "minutes": 90, "price": 15.0, "currency": "PHP", "request_status": "PENDING", "approval_status": "PENDING", "cancel_status": "NORMAL", "overall_status": "PENDING", "request_time": "2026-06-03 11:59:00"},
        {"user_id": "user_11", "user_name": "하하", "device_mac": "AA:BB:CC:DD:EE:11", "client_ip": "192.168.1.111", "client_token_id": "tok_011", "device_name": "iPhone-SE", "minutes": 60, "price": 10.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "REJECTED", "cancel_status": "NORMAL", "overall_status": "REJECTED", "approval_operator": "ADMIN", "request_time": "2026-06-02 13:40:00", "approved_at": "2026-06-02 13:45:00"},
        {"user_id": "user_12", "user_name": "양세찬", "device_mac": "AA:BB:CC:DD:EE:12", "client_ip": "192.168.1.112", "client_token_id": "tok_012", "device_name": "Galaxy-A52", "minutes": 30, "price": 5.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "REJECTED", "cancel_status": "NORMAL", "overall_status": "REJECTED", "approval_operator": "MANAGER", "request_time": "2026-06-02 14:00:00", "approved_at": "2026-06-02 14:05:00"},
        {"user_id": "user_13", "user_name": "전소민", "device_mac": "AA:BB:CC:DD:EE:13", "client_ip": "192.168.1.113", "client_token_id": "tok_013", "device_name": "iPhone-12", "minutes": 60, "price": 10.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "REJECTED", "cancel_status": "NORMAL", "overall_status": "REJECTED", "approval_operator": "ADMIN", "request_time": "2026-06-02 14:30:00", "approved_at": "2026-06-02 14:35:00"},
        {"user_id": "user_14", "user_name": "송지효", "device_mac": "AA:BB:CC:DD:EE:14", "client_ip": "192.168.1.114", "client_token_id": "tok_014", "device_name": "Galaxy-Z-Flip", "minutes": 60, "price": 10.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "PENDING", "cancel_status": "CANCELLED", "overall_status": "CANCELLED", "cancel_operator": "USER", "request_time": "2026-06-01 09:00:00", "cancelled_at": "2026-06-01 09:10:00"},
        {"user_id": "user_15", "user_name": "지석진", "device_mac": "AA:BB:CC:DD:EE:15", "client_ip": "192.168.1.115", "client_token_id": "tok_015", "device_name": "iPhone-11", "minutes": 120, "price": 20.0, "currency": "PHP", "request_status": "COMPLETED", "approval_status": "PENDING", "cancel_status": "CANCELLED", "overall_status": "CANCELLED", "cancel_operator": "ADMIN", "request_time": "2026-06-01 10:00:00", "cancelled_at": "2026-06-01 10:15:00"}
    ]

    def _ensure_table_exists(self):
        super()._ensure_table_exists()
        with self._lock, self._connect() as connection:
            connection.executescript(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_id ON {self.table_name}(id);"
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_token_id ON {self.table_name}(client_token_id);"
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_overall_status ON {self.table_name}(overall_status);"
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_approval_status ON {self.table_name}(approval_status);"
            )

    def load(self, view_type: str = "ALL") -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            connection.row_factory = sqlite3.Row
            requests = []
            try:
                if view_type == "REQUEST":
                    query = f"SELECT * FROM {self.table_name} WHERE request_status = 'PENDING' AND overall_status = 'PENDING' ORDER BY id DESC"
                elif view_type == "APPROVAL":
                    query = f"SELECT * FROM {self.table_name} WHERE approval_status IN ('APPROVED', 'REJECTED') ORDER BY id DESC"
                elif view_type == "CONNECTED":
                    query = f"""
                        SELECT * FROM {self.table_name} 
                        WHERE overall_status = 'ACTIVE' 
                          AND (expires_at IS NULL OR datetime(expires_at) > datetime('now', 'localtime')) 
                        ORDER BY id DESC
                    """
                else:
                    query = f"SELECT * FROM {self.table_name} ORDER BY id DESC"

                for row in connection.execute(query):
                    requests.append(dict(row))
                logd(f"[InternetShareDB] View({view_type}) 데이터 {len(requests)}건 로드 완료")
            except sqlite3.Error as e:
                loge(f"[InternetShareDB] 데이터 조회 중 DB 오류 발생 ({view_type}): {e}")
            return requests

    def save(self, record: dict):

        token_id = record.get("client_token_id")
        if not token_id:
            loge(f"[InternetShareDB] 경고: client_token_id가 누락되었습니다. (IP: {record.get('client_ip')})")
            return

        request_time = str(record.get("request_time") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        sql = f"""
            INSERT INTO {self.table_name} (
                user_id, user_name, device_mac, client_ip, client_token_id, device_name,
                minutes, price, currency,
                request_status, approval_status, cancel_status, overall_status,
                approval_operator, cancel_operator,
                request_time, approved_at, cancelled_at, start_time, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            record.get("user_id"),
            record.get("user_name"),
            record.get("device_mac"),
            record.get("client_ip", ""),
            record.get("client_token_id"),
            record.get("device_name"),
            record.get("minutes", 60),
            record.get("price", 0.0),
            record.get("currency", "PHP"),
            record.get("request_status", "PENDING"),
            record.get("approval_status", "PENDING"),
            record.get("cancel_status", "NORMAL"),
            record.get("overall_status", "PENDING"),
            record.get("approval_operator"),
            record.get("cancel_operator"),
            request_time,
            record.get("approved_at"),
            record.get("cancelled_at"),
            record.get("start_time"),
            record.get("expires_at"),
        )

        try:
            with self._lock, self._connect() as connection:
                connection.execute(sql, params)
            logd(f"[InternetShareDB] 신규 사용 요청 저장 성공: IP={record.get('client_ip')}")
            signal_manager.request_updated.emit()
        except (OSError, sqlite3.Error) as e:
            loge(f"[InternetShareDB] 저장 중 DB 오류 발생: {e}")

    def update(self, request_id: int, record: dict):
        sql = f"""
            UPDATE {self.table_name} 
            SET user_id = ?, user_name = ?, device_mac = ?, client_ip = ?, client_token_id = ?, device_name = ?,
                minutes = ?, price = ?, currency = ?,
                request_status = ?, approval_status = ?, cancel_status = ?, overall_status = ?,
                approval_operator = ?, cancel_operator = ?,
                request_time = ?, approved_at = ?, cancelled_at = ?, start_time = ?, expires_at = ?
            WHERE id = ?
        """
        params = (
            record.get("user_id"),
            record.get("user_name"),
            record.get("device_mac"),
            record.get("client_ip", ""),
            record.get("client_token_id"),
            record.get("device_name"),
            record.get("minutes", 60),
            record.get("price", 0.0),
            record.get("currency", "PHP"),
            record.get("request_status", "PENDING"),
            record.get("approval_status", "PENDING"),
            record.get("cancel_status", "NORMAL"),
            record.get("overall_status", "PENDING"),
            record.get("approval_operator"),
            record.get("cancel_operator"),
            str(record.get("request_time") or ""),
            record.get("approved_at"),
            record.get("cancelled_at"),
            record.get("start_time"),
            record.get("expires_at"),
            request_id
        )
        try:
            with self._lock, self._connect() as connection:
                connection.execute(sql, params)
            logd(f"[InternetShareDB] 사용 요청 수정 완료: ID={request_id}")
            signal_manager.request_updated.emit()
        except sqlite3.Error as e:
            loge(f"[InternetShareDB] 수정 중 DB 오류 발생: {e}")

    def delete(self, request_id: int):
        try:
            with self._lock, self._connect() as connection:
                connection.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (request_id,))
            logd(f"[InternetShareDB] 레코드 삭제 완료: ID={request_id}")
            signal_manager.request_updated.emit()
        except sqlite3.Error as e:
            loge(f"[InternetShareDB] 삭제 중 DB 오류 발생: {e}")

    def get_by_id(self, record_id: int) -> dict:
        with self._lock, self._connect() as connection:
            connection.row_factory = sqlite3.Row
            try:
                cursor = connection.execute(f"SELECT * FROM {self.table_name} WHERE id = ?", (record_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
            except sqlite3.Error as e:
                loge(f"[InternetShareDB] ID 조회 중 DB 오류 발생 (ID: {record_id}): {e}")
            return {}
        
    def load_pending_requests(self) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            connection.row_factory = sqlite3.Row
            requests = []
            try:
                query = f"""
                    SELECT * FROM {self.table_name} 
                    WHERE request_status = 'PENDING' AND overall_status = 'PENDING' 
                    ORDER BY id ASC
                """
                for row in connection.execute(query):
                    requests.append(dict(row))
                logd(f"[InternetShareDB] 대기 중인 사용 요청 총 {len(requests)}건 로드")
            except sqlite3.Error as e:
                loge(f"[InternetShareDB] 대기 요청 조회 중 DB 오류: {e}")
            return requests        

    def recalculate_sessions_for_client(self, client_token_id: str = None, client_ip: str = None):
        """
        동일한 클라이언트의 활성/승인된 레코드들을 id 기준 오름차순으로 정렬하여
        시작시간(start_time)과 종료시간(expires_at)을 순차적으로 재계산합니다.
        """
        with self._lock, self._connect() as connection:
            connection.row_factory = sqlite3.Row
            try:
                query = f"""
                    SELECT * FROM {self.table_name} 
                    WHERE (client_token_id = ? OR client_ip = ?)
                      AND cancel_status != 'CANCELLED'
                      AND overall_status NOT IN ('CANCELLED', 'REJECTED', 'EXPIRED')
                    ORDER BY id ASC
                """
                cursor = connection.execute(query, (client_token_id or "", client_ip or ""))
                rows = [dict(row) for row in cursor.fetchall()]
                
                if not rows:
                    return

                current_time = datetime.datetime.now()
                start_dt = current_time
                
                if rows[0].get("start_time"):
                    try:
                        parsed_start = datetime.datetime.strptime(rows[0]["start_time"], "%Y-%m-%d %H:%M:%S")
                        if parsed_start > current_time:
                            start_dt = parsed_start
                    except ValueError:
                        pass

                for idx, row in enumerate(rows):
                    minutes = int(row.get("minutes", 60))
                    end_dt = start_dt + datetime.timedelta(minutes=minutes)
                    
                    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                    expires_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                    
                    new_overall = "ACTIVE" if row.get("overall_status") in ("ACTIVE", "QUEUED") else row.get("overall_status")
                    if new_overall == "QUEUED" and idx == 0:
                        new_overall = "ACTIVE"

                    update_sql = f"""
                        UPDATE {self.table_name}
                        SET start_time = ?, expires_at = ?, overall_status = ?
                        WHERE id = ?
                    """
                    connection.execute(update_sql, (start_str, expires_str, new_overall, row["id"]))
                    start_dt = end_dt

                connection.commit()
                logd(f"[InternetShareDB] 클라이언트(token={client_token_id}, ip={client_ip}) 세션 시간 재계산 완료 ({len(rows)}건)")
            except sqlite3.Error as e:
                loge(f"[InternetShareDB] 세션 시간 재계산 중 오류 발생: {e}")


internet_share_db = InternetShareDB()
