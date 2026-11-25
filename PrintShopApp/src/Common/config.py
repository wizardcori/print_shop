"""Unified Configuration Management System (INI & DB with Versioning & Kind Support)"""

import ast
import configparser
import json
import os
import re
import sqlite3
import tempfile
import threading
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Type

from Common.globals import CONFIG_ENCODING
from Common.path_mgr import PathMgr
from .singleton_base import ThreadSafeSingletonBase


# ==========================================
# 1. 지원하는 설정 타입 상수 클래스
# ==========================================
class ConfigType:
    STRING = str
    INTEGER = int
    FLOAT = float
    BOOLEAN = bool
    FILENAME = "filename"
    PATH = "path"
    FULLPATH = "fullpath"
    DATE = date
    TIME = time
    DATETIME = datetime
    LIST = list
    DICT = dict


# ==========================================
# 2. 설정 모델의 메타데이터 정의 셰이프
# ==========================================
class ConfigModelShape:
    file_dir: Optional[str] = None
    file_name: Optional[str] = None
    config_encoding: str = CONFIG_ENCODING
    section: str = "General"
    section_order: int = 1
    auto_save: bool = True
    storage_type: str = "file"
    schema: Dict[str, Dict[str, Any]] = {}

    @property
    def resolved_dir(self) -> str:
        if self.file_dir:
            return str(self.file_dir)
        return getattr(PathMgr, "CONFIG_DIR", "") or tempfile.gettempdir()

    @property
    def resolved_name(self) -> str:
        if self.file_name:
            return str(self.file_name)
        app_name = getattr(PathMgr, "APP_NAME", "") or "app"
        return getattr(PathMgr, "CONFIG_FILE", "") or f"{app_name}.ini"

    @property
    def filepath(self) -> str:
        return os.path.join(self.resolved_dir, self.resolved_name)

    @classmethod
    def _resolve_cls_dir(cls) -> str:
        d = getattr(cls, "file_dir", None)
        if d:
            return str(d)
        return getattr(PathMgr, "CONFIG_DIR", "") or tempfile.gettempdir()

    @classmethod
    def _resolve_cls_name(cls) -> str:
        n = getattr(cls, "file_name", None)
        if n:
            return str(n)
        app_name = getattr(PathMgr, "APP_NAME", "") or "app"
        return getattr(PathMgr, "CONFIG_FILE", "") or f"{app_name}.ini"

    @classmethod
    def _resolve_cls_filepath(cls) -> str:
        return os.path.join(cls._resolve_cls_dir(), cls._resolve_cls_name())


# ==========================================
# 3. 설정 관리 핵심 기반 클래스 (싱글톤 및 검증 로직)
# ==========================================
class ConfigManager(ThreadSafeSingletonBase, ConfigModelShape):
    _file_io_lock = threading.RLock()
    _registry: List[Type["ConfigManager"]] = []
    _file_offsets: Dict[str, int] = {}
    _file_encodings: Dict[str, str] = {}
    _offsets_initialized: bool = False
    _instances: Dict[Type, "ConfigManager"] = {}

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
        return cls._instances[cls]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls not in ConfigManager._registry:
            ConfigManager._registry.append(cls)
            ConfigManager._offsets_initialized = False

    @classmethod
    def _ensure_offsets(cls):
        if cls._offsets_initialized:
            return

        unique_filepaths = sorted(
            list({sub_cls._resolve_cls_filepath() for sub_cls in cls._registry})
        )
        cls._file_offsets.clear()
        cls._file_encodings.clear()

        for index, fp in enumerate(unique_filepaths):
            cls._file_offsets[fp] = index * 1000000
            for sub_cls in cls._registry:
                if sub_cls._resolve_cls_filepath() == fp:
                    cls._file_encodings[fp] = getattr(sub_cls, "config_encoding", "utf-8-sig")
                    break

        cls._offsets_initialized = True

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._ensure_offsets()
        self.config = self._create_parser()
        self._load_and_inject()
        self._initialized = True

    @property
    def current_encoding(self) -> str:
        return self._file_encodings.get(self.filepath, self.config_encoding)

    def _create_parser(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser.optionxform = str
        return parser

    def _load_and_inject(self):
        """기본 파일(INI) 로드 및 누락된 스키마 항목 주입 로직"""
        target_dir = self.resolved_dir
        filepath = self.filepath

        if target_dir and not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        if filepath and os.path.exists(filepath):
            self.config.read(filepath, encoding=self.current_encoding)

        injected = False
        if not self.config.has_section(self.section):
            self.config.add_section(self.section)
            injected = True

        for key, meta in self.schema.items():
            if not self.config.has_option(self.section, key):
                default_val = meta.get("default", "")
                if isinstance(default_val, (date, datetime, time)):
                    default_val = default_val.isoformat()
                elif isinstance(default_val, (list, tuple)):
                    default_val = json.dumps(list(default_val), ensure_ascii=False)
                elif isinstance(default_val, dict):
                    default_val = json.dumps(dict(default_val), ensure_ascii=False)
                self.config.set(self.section, key, str(default_val))
                injected = True

        if injected:
            self.save()

    def set(self, key: str, value: Any):
        """설정값 검증 및 설정"""
        if key not in self.schema:
            raise KeyError(f"Allowed configuration key not found: '{key}'")

        meta = self.schema[key]
        expected_type = meta.get("type", ConfigType.STRING)
        min_val = meta.get("min")
        max_val = meta.get("max")
        validator_func = meta.get("validator")

        try:
            if expected_type == ConfigType.BOOLEAN:
                value = (
                    value.lower() in ["true", "1", "yes", "on"]
                    if isinstance(value, str)
                    else bool(value)
                )
                stored_value = str(value)
            elif expected_type == ConfigType.INTEGER:
                value = int(value)
                stored_value = str(value)
            elif expected_type == ConfigType.FLOAT:
                value = float(value)
                stored_value = str(value)
            elif expected_type == ConfigType.LIST:
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        value = [value]
                elif not isinstance(value, (list, tuple)):
                    value = list(value) if hasattr(value, "__iter__") else [value]
                else:
                    value = list(value)
                stored_value = json.dumps(value, ensure_ascii=False)

            elif expected_type == ConfigType.DICT:
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        try:
                            value = ast.literal_eval(value)
                        except Exception:
                            raise TypeError(
                                f"The value('{value}') for key '{key}' does not match the expected type."
                            )
                if not isinstance(value, dict):
                    raise TypeError(
                        f"The value('{value}') for key '{key}' does not match the expected type."
                    )
                value = dict(value)
                stored_value = json.dumps(value, ensure_ascii=False)

            elif expected_type == ConfigType.DATE:
                if isinstance(value, str):
                    value = date.fromisoformat(value)
                stored_value = value.isoformat()
            elif expected_type == ConfigType.TIME:
                if isinstance(value, str):
                    value = time.fromisoformat(value)
                stored_value = value.isoformat()
            elif expected_type == ConfigType.DATETIME:
                if isinstance(value, str):
                    value = datetime.fromisoformat(value)
                stored_value = value.isoformat()
            else:
                value = str(value)
                stored_value = value
        except (ValueError, TypeError):
            raise TypeError(
                f"The value('{value}') for key '{key}' does not match the expected type."
            )

        if min_val is not None or max_val is not None:
            if isinstance(value, (int, float)):
                if min_val is not None and value < min_val:
                    raise ValueError(
                        f"The value for '{key}' must be greater than or equal to {min_val}."
                    )
                if max_val is not None and value > max_val:
                    raise ValueError(
                        f"The value for '{key}' must be less than or equal to {max_val}."
                    )

        if validator_func:
            if isinstance(validator_func, str) and hasattr(self, validator_func):
                func = getattr(self, validator_func)
                if not func(value):
                    raise ValueError(f"[Validation Failed] The value for key '{key}' is invalid.")

        self.config.set(self.section, key, stored_value)

        if self.auto_save:
            self.save()

    def get(self, key: str) -> Any:
        """설정값 조회"""
        if key not in self.schema:
            raise KeyError(f"Non-existent configuration key: {key}")

        meta = self.schema[key]
        expected_type = meta.get("type", ConfigType.STRING)

        try:
            raw_val = self.config.get(self.section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            default_val = meta.get("default", [])
            if isinstance(default_val, (tuple, list)):
                return list(default_val)
            return default_val

        if expected_type == ConfigType.BOOLEAN:
            return raw_val.lower() in ["true", "1", "yes", "on"]
        elif expected_type == ConfigType.INTEGER:
            return int(raw_val)
        elif expected_type == ConfigType.FLOAT:
            return float(raw_val)
        elif expected_type == ConfigType.LIST:
            try:
                parsed = ast.literal_eval(raw_val)
                if isinstance(parsed, (list, tuple)):
                    return list(parsed)
                return [parsed]
            except Exception:
                try:
                    parsed = json.loads(raw_val)
                    if isinstance(parsed, (list, tuple)):
                        return list(parsed)
                    return [parsed]
                except (json.JSONDecodeError, TypeError):
                    default_val = meta.get("default", [])
                    if isinstance(default_val, (tuple, list)):
                        return list(default_val)
                    return [raw_val] if raw_val else []

        elif expected_type == ConfigType.DICT:
            default_val = meta.get("default", {})
            fallback = dict(default_val) if isinstance(default_val, dict) else {}
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, dict):
                    return parsed
                return fallback
            except (json.JSONDecodeError, TypeError):
                try:
                    parsed = ast.literal_eval(raw_val)
                    if isinstance(parsed, dict):
                        return parsed
                    return fallback
                except Exception:
                    return fallback

        elif expected_type == ConfigType.DATE:
            return date.fromisoformat(raw_val)
        elif expected_type == ConfigType.TIME:
            return time.fromisoformat(raw_val)
        elif expected_type == ConfigType.DATETIME:
            return datetime.fromisoformat(raw_val)
        return raw_val

    def _build_section_parser(self) -> configparser.ConfigParser:
        section_parser = configparser.ConfigParser()
        section_parser.optionxform = str  # 대소문자 키 보존이 필요할 때 유용
        if self.config.has_section(self.section):
            section_parser.add_section(self.section)
            for opt, val in self.config.items(self.section):
                section_parser.set(self.section, opt, val)
        return section_parser

    def save(self, key: str = None, value: Any = None):
        """파일 저장 (동일 INI 파일을 공유하는 다른 섹션을 보존하며 내 섹션만 반영)"""
        if key is not None:
            self.set(key, value)
            return

        target_dir = self.resolved_dir
        filepath = self.filepath
        encoding = self.current_encoding

        if not filepath:
            return

        with ConfigManager._file_io_lock:
            if target_dir and not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            merged = self._create_parser()
            if os.path.exists(filepath):
                merged.read(filepath, encoding=encoding)

            # 현재 인스턴스의 섹션을 디스크 병합 파서에 반영
            if merged.has_section(self.section):
                merged.remove_section(self.section)

            if self.config.has_section(self.section):
                merged.add_section(self.section)
                for opt, val in self.config.items(self.section):
                    merged.set(self.section, opt, val)

            with open(filepath, "w", encoding=encoding) as f:
                merged.write(f)

            # 메모리상의 self.config도 최신 디스크 상태와 동기화
            self.config = merged


# ==========================================
# 4. 파일 전용 설정 매니저 (FileConfigManager)
# ==========================================
class FileConfigManager(ConfigManager):
    storage_type = "file"


# ==========================================
# 5. DB 전용 공통 부모 설정 매니저
# ==========================================
class DbConfigManager:
    db_path: Optional[str] = None
    db_filename: str = "app_config.db"
    table_name: str = "printing_prices"
    create_table_sql: Optional[str] = None
    initial_records: List[Dict[str, Any]] = []
    config_kind: str = "print_bw_short"
    key_column: str = "item_name"

    @classmethod
    def resolve_db_path(cls, db_path: Optional[str] = None) -> str:
        if db_path:
            return db_path
        cls_db_path = getattr(cls, "db_path", None)
        if cls_db_path:
            return cls_db_path
        filename = getattr(cls, "db_filename", "app_config.db")
        db_dir = getattr(PathMgr, "DB_DIR", "") or os.path.join(tempfile.gettempdir(), "db")
        return os.path.join(db_dir, filename)

    def __init__(
        self,
        db_path: Optional[str] = None,
        table_name: Optional[str] = None,
        create_table_sql: Optional[str] = None,
        initial_records: Optional[List[Dict[str, Any]]] = None,
        config_kind: Optional[str] = None,
        key_column: Optional[str] = None,
    ):
        cls = self.__class__

        self.db_path = self.resolve_db_path(db_path)
        self.table_name = table_name or getattr(cls, "table_name", "printing_prices")
        self.create_table_sql = create_table_sql or getattr(cls, "create_table_sql", None)
        self.key_column = key_column or getattr(cls, "key_column", "item_name")

        if initial_records is not None:
            self.initial_records = initial_records
        else:
            self.initial_records = getattr(cls, "initial_records", [])

        self.config_kind = config_kind or getattr(cls, "config_kind", "print_bw_short")

        self._ensure_table_exists()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _get_table_columns(self) -> List[str]:
        """현재 테이블의 실제 컬럼 목록을 조회합니다."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({self.table_name})")
            return [row[1] for row in cursor.fetchall()]

    def _ensure_table_exists(self):
        """테이블 생성 및 자동 스키마 마이그레이션 수행 후 초기 데이터(Seed) 적재"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            if self.create_table_sql:
                cursor.execute(self.create_table_sql)
            else:
                cursor.execute(
                    f"""
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
                """
                )
            conn.commit()

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
                "end_date": "TEXT",
            }

        match = re.search(r"\((.*?)\);?\s*$", self.create_table_sql, re.DOTALL)
        if not match:
            return {}

        inner_sql = match.group(1)
        columns_def = {}

        for line in inner_sql.split(","):
            line = line.strip()
            if not line:
                continue
            upper_line = line.upper()
            if any(
                upper_line.startswith(kw)
                for kw in ["PRIMARY KEY", "FOREIGN KEY", "CHECK", "UNIQUE"]
            ):
                continue

            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                col_name = parts[0].strip('"`[]')
                col_type = parts[1].strip()
                if col_name.lower() != "id":
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
                    cursor.execute(
                        f"ALTER TABLE {self.table_name} ADD COLUMN {col_name} {col_def}"
                    )
                    conn.commit()
                    existing_columns.add(col_name)
                except sqlite3.OperationalError as e:
                    print(f"[DB Migration Warning] Add column '{col_name}' failed: {e}")

        target_col_order = list(target_columns_def.keys())
        filtered_current_order = [col for col in current_col_order if col in target_columns_def]

        if filtered_current_order != [col for col in target_col_order if col in existing_columns]:
            self._rebuild_table(cursor, conn, target_columns_def, target_col_order)

    def _rebuild_table(
        self,
        cursor,
        conn,
        target_columns_def: Dict[str, str],
        target_columns: List[str],
    ):
        temp_table = f"{self.table_name}_temp"
        cols_def_sql = ", ".join([f"{col} {col_def}" for col, col_def in target_columns_def.items()])

        try:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
            cursor.execute(
                f"CREATE TABLE {temp_table} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_def_sql})"
            )

            cursor.execute(f"PRAGMA table_info({self.table_name})")
            old_cols = {row[1] for row in cursor.fetchall()}
            common_cols = [col for col in target_columns if col in old_cols]

            if common_cols:
                common_cols_str = ", ".join(common_cols)
                cursor.execute(
                    f"""
                    INSERT INTO {temp_table} ({common_cols_str})
                    SELECT {common_cols_str} FROM {self.table_name}
                """
                )

            cursor.execute(f"DROP TABLE {self.table_name}")
            cursor.execute(f"ALTER TABLE {temp_table} RENAME TO {self.table_name}")
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[DB Migration Error] Table rebuild failed: {e}")

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
                if "start_date" in table_cols and "start_date" not in data:
                    data["start_date"] = now
                if "is_active" in table_cols and "is_active" not in data:
                    data["is_active"] = 1
                if "operator" in table_cols and "operator" not in data:
                    data["operator"] = "system"

                valid_keys = [k for k in data.keys() if k in table_cols and k != "id"]
                values = [data[k] for k in valid_keys]

                cols_str = ", ".join(valid_keys)
                placeholders = ", ".join(["?"] * len(valid_keys))

                cursor.execute(
                    f"INSERT INTO {self.table_name} ({cols_str}) VALUES ({placeholders})",
                    tuple(values),
                )
            conn.commit()

    def get_items(
        self, kind: Optional[str] = None, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """테이블 구조에 구애받지 않고 모든 컬럼을 딕셔너리로 동적 조회합니다."""
        target_kind = kind or self.config_kind
        table_cols = self._get_table_columns()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM {self.table_name} WHERE 1=1"
            params = []

            if "kind" in table_cols and target_kind and target_kind != "ALL":
                query += " AND kind = ?"
                params.append(target_kind)

            if "is_active" in table_cols and active_only:
                query += " AND is_active = 1"

            if "kind" in table_cols:
                query += " ORDER BY kind ASC, id ASC"
            else:
                query += " ORDER BY id ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]

        return [dict(zip(col_names, r)) for r in rows]

    def get_all_records(self, active_only: bool = False) -> List[Dict[str, Any]]:
        return self.get_items(kind="ALL", active_only=active_only)

    def save_record(
        self,
        record_data: Dict[str, Any],
        operator: str = "admin",
        kind: Optional[str] = None,
    ):
        """범용 품목/엔티티 추가 및 수정 (SCD Type 2 지원)"""
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        table_cols = self._get_table_columns()
        k_col = self.key_column

        if k_col not in record_data:
            raise ValueError(f"Record data must contain key column '{k_col}'")

        key_value = record_data[k_col]

        with self._get_connection() as conn:
            cursor = conn.cursor()

            check_query = f"SELECT id FROM {self.table_name} WHERE 1=1"
            check_params = []
            if "kind" in table_cols:
                check_query += " AND kind = ?"
                check_params.append(target_kind)
            check_query += f" AND {k_col} = ?"
            check_params.append(key_value)
            if "is_active" in table_cols:
                check_query += " AND is_active = 1"

            cursor.execute(check_query, check_params)
            current = cursor.fetchone()

            if current:
                current_id = current[0]
                if "is_active" in table_cols and "end_date" in table_cols:
                    cursor.execute(
                        f"UPDATE {self.table_name} SET is_active = 0, end_date = ? WHERE id = ?",
                        (now, current_id),
                    )

            insert_data = dict(record_data)
            if "kind" in table_cols and "kind" not in insert_data:
                insert_data["kind"] = target_kind
            if "operator" in table_cols:
                insert_data["operator"] = operator
            if "is_active" in table_cols:
                insert_data["is_active"] = 1
            if "start_date" in table_cols:
                insert_data["start_date"] = now
            if "end_date" in table_cols:
                insert_data["end_date"] = None

            valid_keys = [k for k in insert_data.keys() if k in table_cols and k != "id"]
            values = [insert_data[k] for k in valid_keys]

            cols_str = ", ".join(valid_keys)
            placeholders = ", ".join(["?"] * len(valid_keys))

            cursor.execute(
                f"INSERT INTO {self.table_name} ({cols_str}) VALUES ({placeholders})",
                tuple(values),
            )
            conn.commit()

    def deactivate_record(
        self, key_value: Any, operator: str = "admin", kind: Optional[str] = None
    ):
        """특정 레코드를 비활성화(Soft Delete)합니다."""
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        table_cols = self._get_table_columns()
        k_col = self.key_column

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = f"UPDATE {self.table_name} SET "
            updates = []
            params = []

            if "is_active" in table_cols:
                updates.append("is_active = 0")
            if "operator" in table_cols:
                updates.append("operator = ?")
                params.append(operator)
            if "end_date" in table_cols:
                updates.append("end_date = ?")
                params.append(now)

            query += ", ".join(updates) + f" WHERE {k_col} = ?"
            params.append(key_value)

            if "kind" in table_cols:
                query += " AND kind = ?"
                params.append(target_kind)
            if "is_active" in table_cols:
                query += " AND is_active = 1"

            cursor.execute(query, params)
            conn.commit()
