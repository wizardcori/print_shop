"""Base database class for configuration and general entity management with SQLite persistence."""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Any, List, Optional

import Common.paths as paths
from Common.log import logd, loge  # logd, loge 임포트 확인


class BaseDb:
    # 부모 클래스 기본 설정 변수 선언
    db_path: str = os.path.join(paths.DB_DIR, "app.db")
    table_name: str = "table1"
    create_table_sql: Optional[str] = None
    initial_records: List[Dict[str, Any]] = []
    child_class_name: str = "Child"
    config_kind: str = "print_bw_short"
    key_column: str = "item_name"  # 자식 클래스에서 식별자 컬럼 지정 가능 (예: operators는 "user_name")

    def __init__(self, db_path: Optional[str] = None, 
                 table_name: Optional[str] = None, 
                 create_table_sql: Optional[str] = None,
                 initial_records: Optional[List[Dict[str, Any]]] = None,
                 config_kind: Optional[str] = None,
                 key_column: Optional[str] = None):
        
        cls = self.__class__
        
        # 자식 클래스에 정의된 항목이 없으면 부모 클래스의 기본값 사용
        self.db_path = db_path or getattr(cls, "db_path", os.path.join(paths.DB_DIR, "app_config.db"))
        self.table_name = table_name or getattr(cls, "table_name", "printing_prices")
        self.create_table_sql = create_table_sql or getattr(cls, "create_table_sql", None)
        self.key_column = key_column or getattr(cls, "key_column", "item_name")
        
        if initial_records is not None:
            self.initial_records = initial_records
        else:
            self.initial_records = getattr(cls, "initial_records", [])
            
        self.config_kind = config_kind or getattr(cls, "config_kind", "print_bw_short")

        # 1. 자식 클래스명 변수로 저장
        self.child_class_name = cls.__name__

        # 2. 초기화(__init__) 시점에 단 한 번 로그 출력
        logd(f"[DB 초기화] 자식 클래스: {self.child_class_name} | 테이블명: {self.table_name} | 경로: {self.db_path}")
        
        # 멀티스레드 동시성 제어를 위한 락 생성
        self._lock = threading.RLock()
        
        # 테이블 존재 확인 및 마이그레이션/시드 데이터 적재 수행
        self._ensure_table_exists()

    @contextmanager
    def _connect(self):
        """Yield a SQLite connection with row factory and always close it safely."""

        try:
            connection = sqlite3.connect(self.db_path, timeout=10)
        except Exception as e:
            loge(f"[DB] SQLite 데이터베이스 연결 실패 [{self.child_class_name} / {self.table_name}] (path={self.db_path}): {e}")
            raise

        try:
            # 잠금 발생 시 대기 시간 설정 먼저 적용
            connection.execute("PRAGMA busy_timeout=5000;")
            
            # WAL 모드 변경은 이미 적용되어 있거나 외부 툴 점유 시 예외 발생 가능
            try:
                connection.execute("PRAGMA journal_mode=WAL;")
            except sqlite3.OperationalError as e:
                # 외부 툴(DB Browser 등) 점유로 인한 정상적인 우회 상황은 디버그(logd)로 기록
                logd(f"[DB] WAL 모드 변경 건너뜀 [{self.child_class_name}.{self.table_name}]: {e}")

            connection.row_factory = sqlite3.Row

            yield connection
            connection.commit()
        except BaseException as e:
            connection.rollback()
            # 비정상 종료 또는 쿼리 실행 중 예외 발생 시 에러(loge)로 기록
            loge(f"[DB] 트랜잭션 오류 발생으로 롤백 수행 [{self.child_class_name}.{self.table_name}]: {e}")
            raise
        finally:
            connection.close()

    def _get_table_columns(self) -> List[str]:
        """현재 테이블의 실제 컬럼 목록을 조회합니다."""
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({self.table_name})")
            return [row[1] for row in cursor.fetchall()]

    def get_table_columns_with_index(self) -> List[Dict[str, Any]]:
        """
        테이블의 컬럼명과 인덱스를 매핑하여 
        [{'column_name': 'id', 'index': 0}, {'column_name': 'request_time', 'index': 1}, ...] 
        형태의 리스트로 반환합니다.
        """
        columns = self._get_table_columns()
        return [{"column_name": col, "index": idx} for idx, col in enumerate(columns)]        

    def get_table_columns_with_details(self) -> List[Dict[str, Any]]:
        """
        테이블의 컬럼 인덱스, 이름, 데이터 타입을 함께 조회하여 반환합니다.
        반환 예시: 
        [
            {'index': 0, 'column_name': 'id', 'data_type': 'INTEGER'},
            {'index': 1, 'column_name': 'request_time', 'data_type': 'TEXT'},
            ...
        ]
        """
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({self.table_name})")
            # PRAGMA table_info 결과 row 구조: (cid, name, type, notnull, dflt_value, pk)
            return [
                {
                    "index": row[0],
                    "column_name": row[1],
                    "data_type": row[2].upper()
                } 
                for row in cursor.fetchall()
            ]    

    def _ensure_table_exists(self):
        """테이블 생성 및 자동 스키마 마이그레이션 수행 후 초기 데이터(Seed) 적재"""
        if paths.DB_DIR and not os.path.exists(paths.DB_DIR):
            os.makedirs(paths.DB_DIR, exist_ok=True)

        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            
            if self.create_table_sql:
                cursor.execute(self.create_table_sql)
            else:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        item_name TEXT NOT NULL,
                        price REAL NOT NULL,
                        operator TEXT DEFAULT 'admin',
                        is_active INTEGER DEFAULT 1,
                        start_date TEXT NOT NULL,
                        end_date TEXT
                    )
                """)

            self._migrate_table_columns(cursor, conn)
            self._seed_initial_records(cursor, conn)

    def _parse_columns_from_sql(self) -> Dict[str, str]:
        """자식 클래스의 create_table_sql에서 컬럼명과 정의를 파싱합니다."""
        if not self.create_table_sql:
            return {
                "kind": "TEXT NOT NULL DEFAULT 'default'",
                "item_name": "TEXT NOT NULL DEFAULT ''",
                "price": "REAL NOT NULL DEFAULT 0.0",
                "operator": "TEXT DEFAULT 'admin'",
                "is_active": "INTEGER DEFAULT 1",
                "start_date": "TEXT DEFAULT ''",
                "end_date": "TEXT"
            }
        
        match = re.search(r'\((.*?)\);?\s*$', self.create_table_sql, re.DOTALL)
        if not match:
            return {}
        
        inner_sql = match.group(1)
        columns_def = {}
        
        for line in inner_sql.split(','):
            line = line.strip()
            if not line:
                continue
            upper_line = line.upper()
            if any(upper_line.startswith(kw) for kw in ['PRIMARY KEY', 'FOREIGN KEY', 'CHECK', 'UNIQUE']):
                continue
                
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                col_name = parts[0].strip('"`[]')
                col_type = parts[1].strip()
                if col_name.lower() != 'id':
                    columns_def[col_name] = col_type
                    
        return columns_def

    def _migrate_table_columns(self, cursor, conn):
        """자식 클래스의 create_table_sql을 참조하여 컬럼 변경, 추가, 순서 정렬 수행"""
        cursor.execute(f"PRAGMA table_info({self.table_name})")
        columns_info = cursor.fetchall()
        existing_columns = {row[1] for row in columns_info}
        current_col_order = [row[1] for row in columns_info if row[1] != "id"]

        target_columns_def = self._parse_columns_from_sql()
        if not target_columns_def:
            return

        for col_name, col_def in target_columns_def.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE {self.table_name} ADD COLUMN {col_name} {col_def}")
                    existing_columns.add(col_name)
                except sqlite3.OperationalError as e:
                    logd(f"[DB Migration Warning] Add column '{col_name}' failed: {e}")

        target_col_order = list(target_columns_def.keys())
        filtered_current_order = [col for col in current_col_order if col in target_columns_def]
        
        if filtered_current_order != [col for col in target_col_order if col in existing_columns]:
            self._rebuild_table(cursor, conn, target_columns_def, target_col_order)

    def _rebuild_table(self, cursor, conn, target_columns_def: Dict[str, str], target_columns: List[str]):
        temp_table = f"{self.table_name}_temp"
        cols_def_sql = ", ".join([f"{col} {col_def}" for col, col_def in target_columns_def.items()])
        
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
            cursor.execute(f"CREATE TABLE {temp_table} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_def_sql})")
            
            cursor.execute(f"PRAGMA table_info({self.table_name})")
            old_cols = {row[1] for row in cursor.fetchall()}
            common_cols = [col for col in target_columns if col in old_cols]
            
            if common_cols:
                common_cols_str = ", ".join(common_cols)
                cursor.execute(f"""
                    INSERT INTO {temp_table} ({common_cols_str})
                    SELECT {common_cols_str} FROM {self.table_name}
                """)
            
            cursor.execute(f"DROP TABLE {self.table_name}")
            cursor.execute(f"ALTER TABLE {temp_table} RENAME TO {self.table_name}")
        except Exception as e:
            logd(f"[DB Migration Error] Table rebuild failed: {e}")
            raise

    def _seed_initial_records(self, cursor, conn):
        """자식 스키마 컬럼에 맞춘 동적 시드 데이터 주입"""
        if not self.initial_records:
            return

        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        count = cursor.fetchone()[0]

        if count == 0:
            now = datetime.now().isoformat()
            table_cols = self._get_table_columns()
            
            for rec in self.initial_records:
                data = dict(rec)
                if 'start_date' in table_cols and 'start_date' not in data:
                    data['start_date'] = now
                if 'is_active' in table_cols and 'is_active' not in data:
                    data['is_active'] = 1
                if 'operator' in table_cols and 'operator' not in data:
                    data['operator'] = 'system'
                
                valid_keys = [k for k in data.keys() if k in table_cols and k != 'id']
                values = [data[k] for k in valid_keys]
                
                cols_str = ", ".join(valid_keys)
                placeholders = ", ".join(["?"] * len(valid_keys))
                
                cursor.execute(
                    f"INSERT INTO {self.table_name} ({cols_str}) VALUES ({placeholders})",
                    tuple(values)
                )

    # -------------------------------------------------------------
    # READ (동적 컬럼 매핑 조회)
    # -------------------------------------------------------------
    def get_items(self, kind: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """테이블 구조에 구애받지 않고 모든 컬럼을 딕셔너리로 동적 조회합니다."""
        target_kind = kind or self.config_kind
        table_cols = self._get_table_columns()
        
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM {self.table_name} WHERE 1=1"
            params = []
            
            if 'kind' in table_cols and target_kind and target_kind != "ALL":
                query += " AND kind = ?"
                params.append(target_kind)
                
            if 'is_active' in table_cols and active_only:
                query += " AND is_active = 1"
                
            if 'kind' in table_cols:
                query += " ORDER BY kind ASC, id ASC"
            else:
                query += " ORDER BY id ASC"
                
            cursor.execute(query, params)
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]
            
        return [dict(zip(col_names, r)) for r in rows]

    def get_all_records(self, active_only: bool = False) -> List[Dict[str, Any]]:
        return self.get_items(kind="ALL", active_only=active_only)

    # -------------------------------------------------------------
    # CREATE & UPDATE (범용 레코드 저장 및 SCD Type 2 이력 관리)
    # -------------------------------------------------------------
    def save_record(self, record_data: Dict[str, Any], operator: str = "admin", kind: Optional[str] = None):
        """범용 품목/엔티티 추가 및 수정 (SCD Type 2 지원)"""
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        table_cols = self._get_table_columns()
        k_col = self.key_column
        
        if k_col not in record_data:
            raise ValueError(f"Record data must contain key column '{k_col}'")
            
        key_value = record_data[k_col]
        
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            
            check_query = f"SELECT id FROM {self.table_name} WHERE 1=1"
            check_params = []
            if 'kind' in table_cols:
                check_query += " AND kind = ?"
                check_params.append(target_kind)
            check_query += f" AND {k_col} = ?"
            check_params.append(key_value)
            if 'is_active' in table_cols:
                check_query += " AND is_active = 1"
                
            cursor.execute(check_query, check_params)
            current = cursor.fetchone()
            
            if current:
                current_id = current[0]
                if 'is_active' in table_cols and 'end_date' in table_cols:
                    cursor.execute(
                        f"UPDATE {self.table_name} SET is_active = 0, end_date = ? WHERE id = ?",
                        (now, current_id)
                    )
            
            insert_data = dict(record_data)
            if 'kind' in table_cols and 'kind' not in insert_data:
                insert_data['kind'] = target_kind
            if 'operator' in table_cols:
                insert_data['operator'] = operator
            if 'is_active' in table_cols:
                insert_data['is_active'] = 1
            if 'start_date' in table_cols:
                insert_data['start_date'] = now
            if 'end_date' in table_cols:
                insert_data['end_date'] = None
                
            valid_keys = [k for k in insert_data.keys() if k in table_cols and k != 'id']
            values = [insert_data[k] for k in valid_keys]
            
            cols_str = ", ".join(valid_keys)
            placeholders = ", ".join(["?"] * len(valid_keys))
            
            cursor.execute(
                f"INSERT INTO {self.table_name} ({cols_str}) VALUES ({placeholders})",
                tuple(values)
            )

    # -------------------------------------------------------------
    # DELETE / DEACTIVATE (소프트 딜리트)
    # -------------------------------------------------------------
    def deactivate_record(self, key_value: Any, operator: str = "admin", kind: Optional[str] = None):
        """특정 레코드를 비활성화(Soft Delete)합니다."""
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        table_cols = self._get_table_columns()
        k_col = self.key_column
        
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            query = f"UPDATE {self.table_name} SET "
            updates = []
            params = []
            
            if 'is_active' in table_cols:
                updates.append("is_active = 0")
            if 'operator' in table_cols:
                updates.append("operator = ?")
                params.append(operator)
            if 'end_date' in table_cols:
                updates.append("end_date = ?")
                params.append(now)
                
            query += ", ".join(updates) + f" WHERE {k_col} = ?"
            params.append(key_value)
            
            if 'kind' in table_cols:
                query += " AND kind = ?"
                params.append(target_kind)
            if 'is_active' in table_cols:
                query += " AND is_active = 1"
                
            cursor.execute(query, params)