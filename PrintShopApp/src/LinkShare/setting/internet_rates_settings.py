"""Internet Rates Price Configuration and UI Tab Component with Table Columns and Active Checkbox."""

from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QComboBox, QTableWidget, QTableWidgetItem, 
    QPushButton, QMessageBox, QLineEdit, QCheckBox, QWidget as QWidgetCell, QHBoxLayout as QHBoxLayoutCell
)
from PySide6.QtCore import Qt
from Common.config import DbConfigManager
from Common.settings_registry import register_settings_tab
from Common import globals as app_globals  # 상단에 추가

class InternetRatesConfig(DbConfigManager):
    section = "InternetRates"
    table_name = "internet_rates"  # 인쇄 가격 테이블과 분리된 고유 테이블명 지정

    # 자식 클래스 전용 커스텀 테이블 생성 쿼리 정의
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS internet_rates (
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
    initial_records = [
        {"kind": "standard", "item_name": "30 MINS", "price": 5.00},
        {"kind": "standard", "item_name": "60 MINS", "price": 10.00},
        {"kind": "standard", "item_name": "90 MINS", "price": 15.00},
        {"kind": "standard", "item_name": "120 MINS", "price": 20.00},
    ]
    
    def __init__(self):
        super().__init__(
            table_name=self.table_name, 
            create_table_sql=self.create_table_sql,            
            initial_records=self.initial_records
        )
        self.config_kind = "standard"

    # -------------------------------------------------------------
    # 자식 클래스 전용 데이터 관리 메서드 구현
    # -------------------------------------------------------------
    def save_item(self, item_name: str, price: float, operator: str = "admin", kind: Optional[str] = None):
        """인터넷 요금 품목 추가 및 수정 (SCD Type 2 이력 관리 적용)"""
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                f"""
                SELECT id, price FROM {self.table_name}
                WHERE kind = ? AND item_name = ? AND is_active = 1
                """,
                (target_kind, item_name)
            )
            current = cursor.fetchone()
            
            if current:
                current_id, current_price = current
                
                # 1) 가격 변동이 없는 경우: operator 정보만 최신으로 업데이트
                if float(current_price) == float(price):
                    cursor.execute(
                        f"UPDATE {self.table_name} SET operator = ? WHERE id = ?",
                        (operator, current_id)
                    )
                    conn.commit()
                    return
                
                # 2) 가격이 변경된 경우: 기존 레코드를 비활성화
                cursor.execute(
                    f"UPDATE {self.table_name} SET is_active = 0, end_date = ? WHERE id = ?",
                    (now, current_id)
                )
            
            # 3) 신규 또는 변경된 레코드 삽입
            cursor.execute(
                f"""
                INSERT INTO {self.table_name} 
                (kind, item_name, price, operator, is_active, start_date, end_date)
                VALUES (?, ?, ?, ?, 1, ?, NULL)
                """,
                (target_kind, item_name, float(price), operator, now)
            )
            conn.commit()

    def deactivate_item(self, item_name: str, operator: str = "admin", kind: Optional[str] = None):
        """인터넷 요금 품목 비활성화 (Soft Delete)"""
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE {self.table_name} 
                SET is_active = 0, operator = ?, end_date = ? 
                WHERE kind = ? AND item_name = ? AND is_active = 1
                """,
                (operator, now, target_kind, item_name)
            )
            conn.commit()

    def get_internet_fares_def(self) -> Dict[str, float]:
        """initial_records 기반의 기본 인터넷 요금 딕셔너리를 반환합니다."""
        fares = {}
        for record in self.initial_records:
            item_name = record.get("item_name")
            price = record.get("price")
            if item_name and price is not None:
                fares[item_name] = float(price)
        return fares

    def get_fare_price_def(self, item_name: str) -> float:
        """initial_records 기반으로 특정 item_name의 기본 요금을 조회합니다."""
        for record in self.initial_records:
            if record.get("item_name", "").upper() == str(item_name).upper():
                return float(record.get("price", 0.0))
        return 0.0

    def get_internet_fares(self) -> Dict[str, float]:
        """데이터베이스에서 활성화된 모든 인터넷 요금 정보를 조회하며, 실패 시 initial_records 기반 정의값으로 폴백합니다."""
        fares = {}
        try:
            items = self.get_items(active_only=True)
            for item in items:
                item_name = item.get("item_name")
                price = item.get("price")
                if item_name and price is not None:
                    fares[item_name] = float(price)
        except Exception:
            pass
        return fares if fares else self.get_internet_fares_def()

    def get_fare_price(self, item_name: str) -> float:
        """데이터베이스에서 특정 item_name 요금을 조회하며, 실패 시 initial_records 기반 정의값으로 폴백합니다."""
        try:
            items = self.get_items(active_only=True)
            for item in items:
                if item.get("item_name", "").upper() == str(item_name).upper():
                    return float(item.get("price", 0.0))
        except Exception:
            pass
        return self.get_fare_price_def(item_name)



class InternetRatesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = InternetRatesConfig()
        
        self.categories = {
            "ALL": "ALL",
            "Standard Rates": "standard"
        }
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('<h3>Internet Rate Management</h3>'))
        
        # 상단 제어 영역
        cat_layout = QHBoxLayout()
        
        self.active_filter_chk = QCheckBox("Active Only")
        self.active_filter_chk.setChecked(True)
        self.active_filter_chk.stateChanged.connect(self.load_rates_to_table)
        cat_layout.addWidget(self.active_filter_chk)
        
        cat_layout.addWidget(QLabel('Select Category:'))
        
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(list(self.categories.keys()))
        self.cat_combo.currentIndexChanged.connect(self.on_category_changed)
        cat_layout.addWidget(self.cat_combo)
        
        self.kind_indicator_label = QLabel()
        self.kind_indicator_label.setStyleSheet("color: #3498db; font-weight: bold; margin-left: 15px;")
        cat_layout.addWidget(self.kind_indicator_label)
        
        cat_layout.addStretch()
        layout.addLayout(cat_layout)
        
        # 테이블 컬럼 구성 (0: Kind, 1: Active, 2: Item Name, 3: Price, 4: Operator, 5: Start Date, 6: End Date)
        self.table = QTableWidget