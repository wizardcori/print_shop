"""Internet Rates Price Configuration and UI Tab Component with Table Columns, Active Checkbox, and CRUD Operations."""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QComboBox, QTableWidget, QTableWidgetItem, 
    QPushButton, QMessageBox, QLineEdit, QCheckBox, QHeaderView,
    QWidget as QWidgetCell, QHBoxLayout as QHBoxLayoutCell
)
from PySide6.QtCore import Qt
from Common.config import DbConfigManager
from Common.settings_registry import register_settings_tab
from Common import globals as app_globals  # 상단에 추가
from Common.sortable_table_widget import SortableTableWidget, NaturalSortTableItem
from Common.sort_util import create_natural_sort_key
from Common.geometry_manager import AutoGeometryWidget

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

    def _sort_fares(self, fares: list) -> list:
        """
        [정렬 수행 함수]
        FARE_ORDER 설정값("ASCENDING" 또는 "DESCENDING")을 확인하고,
        create_natural_sort_key 함수를 호출하여 요금 리스트 정렬을 수행합니다.
        """
        fare_order = getattr(app_globals, "FARE_ORDER", "ASCENDING")
        reverse_flag = True if str(fare_order).upper() in ["DESCENDING", "DESC"] else False
        
        # 정렬 키 생성 함수를 key에 전달하여 정렬 수행
        return sorted(fares, key=create_natural_sort_key, reverse=reverse_flag)

    def get_internet_fares_def(self) -> list:
        """initial_records 기반의 기본 인터넷 요금 리스트를 반환합니다."""
        fares = []
        for record in self.initial_records:
            item_name = record.get("item_name")
            price = record.get("price")
            if item_name and price is not None:
                numbers = re.findall(r'\d+', str(item_name))
                minutes = int(numbers[0]) if numbers else 30
                
                fares.append({
                    "minutes": minutes,
                    "price": float(price)
                })
        return self._sort_fares(fares)

    def get_internet_fares(self) -> list:
        """데이터베이스에서 활성화된 모든 인터넷 요금 정보를 조회하며, 실패 시 initial_records 기반 정의값으로 폴백합니다."""
        fares = []
        try:
            items = self.get_items(active_only=True)
            for item in items:
                item_name = item.get("item_name")
                price = item.get("price")
                if item_name and price is not None:
                    numbers = re.findall(r'\d+', str(item_name))
                    minutes = int(numbers[0]) if numbers else 30
                    
                    fares.append({
                        "minutes": minutes,
                        "price": float(price)
                    })
        except Exception:
            pass
        return self._sort_fares(fares) if fares else self.get_internet_fares_def()

    def get_fare_price_def(self, item_name: str) -> float:
        """initial_records 기반으로 특정 item_name의 기본 요금을 조회합니다."""
        for record in self.initial_records:
            if record.get("item_name", "").upper() == str(item_name).upper():
                return float(record.get("price", 0.0))
        return 0.0

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



class InternetRatesTab(AutoGeometryWidget):
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

        # 2. 테이블 생성 시 SortableTableWidget 사용
        self.table = SortableTableWidget()
        self.table.setColumnCount(7)
        # 테이블 컬럼 구성 (0: Kind, 1: Active, 2: Item Name, 3: Price, 4: Operator, 5: Start Date, 6: End Date)
        self.table.setHorizontalHeaderLabels([
            'Kind', 'Active', 'Item Name', 'Price', 'Operator', 'Start Date', 'End Date'
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(self.on_table_row_clicked)
        layout.addWidget(self.table)
        
        # 추가/수정/삭제 입력 영역
        input_layout = QHBoxLayout()
        
        self.input_kind_combo = QComboBox()
        self.input_kind_combo.setEditable(True)
        real_categories = {k: v for k, v in self.categories.items() if v != "ALL"}
        self.input_kind_combo.addItems(list(real_categories.keys()))
        self.input_kind_combo_dict = real_categories
        
        self.input_active_chk = QCheckBox("Active")
        self.input_active_chk.setChecked(True)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Item Name (e.g. 150 MINS)")
        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("Price")
        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Operator")
        self.operator_input.setText(app_globals.GLOBAL_LOGIN_USER_NAME or "admin")
        self.operator_input.setReadOnly(True)  # 읽기 전용 설정

        update_btn = QPushButton("Update")
        update_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        update_btn.clicked.connect(self.update_item)
        
        add_btn = QPushButton("Add Item")
        add_btn.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
        add_btn.clicked.connect(self.add_item)
        
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        delete_btn.clicked.connect(self.delete_item)
        
        input_layout.addWidget(QLabel("Kind:"))
        input_layout.addWidget(self.input_kind_combo)
        input_layout.addWidget(self.input_active_chk)
        input_layout.addWidget(QLabel("Name:"))
        input_layout.addWidget(self.name_input)
        input_layout.addWidget(QLabel("Price:"))
        input_layout.addWidget(self.price_input)
        input_layout.addWidget(QLabel("Op:"))
        input_layout.addWidget(self.operator_input)
        input_layout.addWidget(update_btn)
        input_layout.addWidget(add_btn)
        input_layout.addWidget(delete_btn)
        layout.addLayout(input_layout)
        
        # 하단 제어 버튼 영역 (일괄 저장)
        btn_layout = QHBoxLayout()
        save_btn = QPushButton('Save Changes')
        save_btn.clicked.connect(self.save_to_config)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        
        self.on_category_changed()

    def get_current_kind(self) -> str:
        current_name = self.cat_combo.currentText()
        return self.categories.get(current_name, "ALL")

    def on_category_changed(self):
        kind_code = self.get_current_kind()
        self.kind_indicator_label.setText(f"[DB Kind Code: {kind_code}]")
        self.load_rates_to_table()

    def load_rates_to_table(self):
        """데이터베이스에서 kind별 데이터 및 이력 정보를 불러와 테이블에 렌더링"""
        kind = self.get_current_kind()
        active_only = self.active_filter_chk.isChecked()
        
        self.table.setRowCount(0)
        
        try:
            if kind == "ALL":
                rows_data = self.config.get_items(active_only=active_only)
            else:
                rows_data = self.config.get_items(kind=kind, active_only=active_only)
        except Exception:
            rows_data = []
            
        row = 0
        for r_data in rows_data:
            r_kind = r_data.get("kind", "")
            item_name = r_data.get("item_name", "")
            price = r_data.get("price", 0.0)
            operator = r_data.get("operator", "admin")
            is_active = r_data.get("is_active", 1)
            start_date = r_data.get("start_date", "")
            end_date = r_data.get("end_date", "")
            
            self.table.insertRow(row)
            
            kind_item = NaturalSortTableItem(r_kind)
            kind_item.setFlags(kind_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            cell_widget = QWidgetCell()
            cell_layout = QHBoxLayoutCell(cell_widget)
            chk = QCheckBox()
            chk.setChecked(bool(is_active))
            chk.stateChanged.connect(lambda state, k=r_kind, name=item_name: self.on_checkbox_toggled(k, name, state))
            cell_layout.addWidget(chk)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            
            name_item = NaturalSortTableItem(item_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            val_item = NaturalSortTableItem(str(price))
            op_item = NaturalSortTableItem(str(operator or "admin"))
            
            start_item = NaturalSortTableItem(str(start_date or ""))
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            end_item = NaturalSortTableItem(str(end_date or ""))
            end_item.setFlags(end_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.table.setItem(row, 0, kind_item)
            self.table.setCellWidget(row, 1, cell_widget)
            self.table.setItem(row, 2, name_item)
            self.table.setItem(row, 3, val_item)
            self.table.setItem(row, 4, op_item)
            self.table.setItem(row, 5, start_item)
            self.table.setItem(row, 6, end_item)
            row += 1

    def on_checkbox_toggled(self, kind: str, item_name: str, state: int):
        new_active = 1 if state == Qt.CheckState.Checked.value or state == 2 else 0
        with self.config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.config.table_name} SET is_active = ? WHERE kind = ? AND item_name = ?",
                (new_active, kind, item_name)
            )
            conn.commit()

    def on_table_row_clicked(self, row: int, col: int):
        try:
            kind_val = self.table.item(row, 0).text()
            cell_widget = self.table.cellWidget(row, 1)
            chk = cell_widget.findChild(QCheckBox) if cell_widget else None
            is_active = chk.isChecked() if chk else True
            
            name_val = self.table.item(row, 2).text()
            price_val = self.table.item(row, 3).text()
            operator_val = self.table.item(row, 4).text()
            
            found = False
            for display_name, code in self.input_kind_combo_dict.items():
                if code == kind_val:
                    self.input_kind_combo.setCurrentText(display_name)
                    found = True
                    break
            if not found:
                self.input_kind_combo.setCurrentText(kind_val)
            
            self.input_active_chk.setChecked(is_active)
            self.name_input.setText(name_val)
            self.price_input.setText(price_val)
            if operator_val:
                self.operator_input.setText(operator_val)
        except Exception:
            pass

    def _resolve_input_kind(self) -> str:
        typed_val = self.input_kind_combo.currentText().strip()
        return self.input_kind_combo_dict.get(typed_val, typed_val)

    def add_item(self):
        kind = self._resolve_input_kind()
        name = self.name_input.text().strip().upper()
        price_str = self.price_input.text().strip()
        operator = app_globals.GLOBAL_LOGIN_USER_NAME or "admin"
        is_active = 1 if self.input_active_chk.isChecked() else 0
        
        if not kind or not name or not price_str:
            QMessageBox.warning(self, "Warning", "Please enter Kind, Item Name and Price.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Price must be a valid number.")
            return
            
        self.config.config_kind = kind
        self.config.save_item(item_name=name, price=price, operator=operator, kind=kind)
        
        with self.config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.config.table_name} SET is_active = ? WHERE kind = ? AND item_name = ? AND is_active = 1",
                (is_active, kind, name)
            )
            conn.commit()
            
        self.name_input.clear()
        self.price_input.clear()
        self.load_rates_to_table()
        QMessageBox.information(self, "Success", f"Item '{name}' has been added/saved.")

    def update_item(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an item from the table to update.")
            return
            
        kind = self._resolve_input_kind()
        name = self.name_input.text().strip().upper()
        price_str = self.price_input.text().strip()
        operator = app_globals.GLOBAL_LOGIN_USER_NAME or "admin"        
        is_active = 1 if self.input_active_chk.isChecked() else 0
        
        if not kind or not name or not price_str:
            QMessageBox.warning(self, "Warning", "Kind, Item Name and Price cannot be empty.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Price must be a valid number.")
            return
            
        old_name_item = self.table.item(selected_row, 2)
        old_name = old_name_item.text() if old_name_item else name
        old_kind_item = self.table.item(selected_row, 0)
        old_kind = old_kind_item.text() if old_kind_item else kind
        
        with self.config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.config.table_name} SET kind = ?, item_name = ?, price = ?, operator = ?, is_active = ? WHERE kind = ? AND item_name = ?",
                (kind, name, price, operator, is_active, old_kind, old_name)
            )
            conn.commit()
            
        self.load_rates_to_table()
        QMessageBox.information(self, "Updated", f"Item '{name}' has been updated successfully.")

    def delete_item(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an item to delete from the table.")
            return
            
        name_item = self.table.item(selected_row, 2)
        kind_item = self.table.item(selected_row, 0)
        operator = app_globals.GLOBAL_LOGIN_USER_NAME or "admin"
        
        if name_item and kind_item:
            name = name_item.text()
            kind = kind_item.text()
            
            self.config.deactivate_item(item_name=name, operator=operator, kind=kind)
            self.load_rates_to_table()
            QMessageBox.information(self, "Deleted", f"Item '{name}' has been deactivated.")

    def save_to_config(self):
        try:
            for row in range(self.table.rowCount()):
                kind = self.table.item(row, 0).text()
                name = self.table.item(row, 2).text()
                val_str = self.table.item(row, 3).text()
                operator = self.table.item(row, 4).text()
                
                cell_widget = self.table.cellWidget(row, 1)
                chk = cell_widget.findChild(QCheckBox) if cell_widget else None
                is_active = 1 if (chk and chk.isChecked()) else 0
                
                self.config.save_item(item_name=name, price=float(val_str), operator=operator, kind=kind)
                
                with self.config._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        f"UPDATE {self.config.table_name} SET is_active = ? WHERE kind = ? AND item_name = ? AND is_active = 1",
                        (is_active, kind, name)
                    )
                    conn.commit()
                    
            QMessageBox.information(self, "Success", "All internet rate changes have been saved successfully!")
            self.load_rates_to_table()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric values for prices.")

register_settings_tab('InternetRateSettings', 'InternetRates', InternetRatesTab, 10)