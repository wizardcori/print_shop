"""Printing Services Price Configuration and UI Tab Component with Extended Table Columns and Active Checkbox."""

from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QComboBox, QTableWidget, QTableWidgetItem, 
    QPushButton, QMessageBox, QLineEdit, QCheckBox, QWidget as QWidgetCell, QHBoxLayout as QHBoxLayoutCell
)
from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from Common.config import DbConfigManager
from Common.settings_dialog import register_settings_tab
from Common import globals as app_globals  # 상단에 추가

class PrintFareConfig(DbConfigManager):
    section = "PrintingPrices"
    table_name = "printing_prices"
    create_table_sql = f"""
                    CREATE TABLE IF NOT EXISTS printing_prices (
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
        # Print B/W - Short
        {"kind": "print_bw_short", "item_name": "TEXT ONLY", "price": 3.00},
        {"kind": "print_bw_short", "item_name": "IMAGE W/ TEXT", "price": 5.00},
        {"kind": "print_bw_short", "item_name": "IMAGE ONLY", "price": 7.00},
        # Print B/W - Long
        {"kind": "print_bw_long", "item_name": "TEXT ONLY", "price": 4.00},
        {"kind": "print_bw_long", "item_name": "IMAGE W/ TEXT", "price": 6.00},
        {"kind": "print_bw_long", "item_name": "IMAGE ONLY", "price": 8.00},
        # Print Colored - Short
        {"kind": "print_colored_short", "item_name": "TEXT ONLY", "price": 5.00},
        {"kind": "print_colored_short", "item_name": "IMAGE W/ TEXT", "price": 7.00},
        {"kind": "print_colored_short", "item_name": "IMAGE ONLY", "price": 20.00},
        # Print Colored - Long
        {"kind": "print_colored_long", "item_name": "TEXT ONLY", "price": 8.00},
        {"kind": "print_colored_long", "item_name": "IMAGE W/ TEXT", "price": 12.00},
        {"kind": "print_colored_long", "item_name": "IMAGE ONLY", "price": 20.00},
        # Xerox/Scan - Short
        {"kind": "xerox_scan_short", "item_name": "ALL TYPES B/W", "price": 3.00},
        {"kind": "xerox_scan_short", "item_name": "ALL TYPES CLRD", "price": 5.00},
        # Xerox/Scan - Long
        {"kind": "xerox_scan_long", "item_name": "ALL TYPES B/W", "price": 5.00},
        {"kind": "xerox_scan_long", "item_name": "ALL TYPES CLRD", "price": 7.00},
        # Photo Paper
        {"kind": "photo_paper", "item_name": "WALLET (1)", "price": 5.00},
        {"kind": "photo_paper", "item_name": "3R SIZE", "price": 7.00},
        {"kind": "photo_paper", "item_name": "4R SIZE", "price": 9.00},
        {"kind": "photo_paper", "item_name": "5R SIZE", "price": 13.00},
        {"kind": "photo_paper", "item_name": "A4 GLOSSY", "price": 25.00},
        {"kind": "photo_paper", "item_name": "A4 BACK2BACK", "price": 50.00},
        # Sticker Paper
        {"kind": "sticker_paper", "item_name": "PRINT ONLY - A4", "price": 25.00},
        {"kind": "sticker_paper", "item_name": "W/ LAYOUT", "price": 35.00},
        # Laminate
        {"kind": "laminate", "item_name": "ID LAMINATE", "price": 20.00},
        {"kind": "laminate", "item_name": "3R LAMINATE", "price": 25.00},
        {"kind": "laminate", "item_name": "4R LAMINATE", "price": 30.00},
        {"kind": "laminate", "item_name": "5R LAMINATE", "price": 35.00},
        {"kind": "laminate", "item_name": "A4 LAMINATE", "price": 35.00},
    ]
    
    def __init__(self):
        super().__init__(
            table_name=self.table_name, 
            initial_records=self.initial_records
        )

    # -------------------------------------------------------------
    # 자식 클래스 전용 데이터 관리 메서드 구현
    # -------------------------------------------------------------
    def save_item(self, item_name: str, price: float, operator: str = "admin", kind: Optional[str] = None):
        """인쇄 요금 품목 추가 및 수정 (SCD Type 2 이력 관리 적용)"""
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
        """인쇄 요금 품목 비활성화 (Soft Delete)"""
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

class PrintFareTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = PrintFareConfig()
        
        self.categories = {
            "ALL": "ALL",
            "Print B/W - Short": "print_bw_short",
            "Print B/W - Long": "print_bw_long",
            "Print Colored - Short": "print_colored_short",
            "Print Colored - Long": "print_colored_long",
            "Xerox/Scan - Short": "xerox_scan_short",
            "Xerox/Scan - Long": "xerox_scan_long",
            "Photo Paper": "photo_paper",
            "Sticker Paper": "sticker_paper",
            "Laminate": "laminate"
        }
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('<h3>Lee\'s Printing Services - Price Management</h3>'))
        
        # 상단 제어 영역
        cat_layout = QHBoxLayout()
        
        self.active_filter_chk = QCheckBox("Active Only")
        self.active_filter_chk.setChecked(True)
        self.active_filter_chk.stateChanged.connect(self.load_prices_to_table)
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
        self.table = QTableWidget()
        self.table.setColumnCount(7)
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
        self.name_input.setPlaceholderText("Item Name")
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
        
        # 하단 제어 버튼 영역
        btn_layout = QHBoxLayout()
        save_btn = QPushButton('Save Changes')
        save_btn.clicked.connect(self.save_to_config)
        
        print_btn = QPushButton('🖨️ Print Price List (PDF / Printer)')
        print_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 6px;")
        print_btn.clicked.connect(self.print_price_list)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(print_btn)
        layout.addLayout(btn_layout)
        
        self.on_category_changed()

    def get_current_kind(self) -> str:
        current_name = self.cat_combo.currentText()
        return self.categories.get(current_name, "ALL")

    def on_category_changed(self):
        kind_code = self.get_current_kind()
        self.kind_indicator_label.setText(f"[DB Kind Code: {kind_code}]")
        self.load_prices_to_table()

    def load_prices_to_table(self):
        """데이터베이스에서 kind별 데이터 및 이력 정보를 불러와 테이블에 렌더링"""
        kind = self.get_current_kind()
        active_only = self.active_filter_chk.isChecked()
        
        self.table.setRowCount(0)
        rows_data = self.config.get_items(kind=kind, active_only=active_only)
            
        row = 0
        for r_data in rows_data:
            r_kind = r_data["kind"]
            item_name = r_data["item_name"]
            price = r_data["price"]
            operator = r_data["operator"]
            is_active = r_data["is_active"]
            start_date = r_data["start_date"]
            end_date = r_data["end_date"]
            
            self.table.insertRow(row)
            
            kind_item = QTableWidgetItem(r_kind)
            kind_item.setFlags(kind_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            cell_widget = QWidgetCell()
            cell_layout = QHBoxLayoutCell(cell_widget)
            chk = QCheckBox()
            chk.setChecked(bool(is_active))
            chk.stateChanged.connect(lambda state, k=r_kind, name=item_name: self.on_checkbox_toggled(k, name, state))
            cell_layout.addWidget(chk)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            
            name_item = QTableWidgetItem(item_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            val_item = QTableWidgetItem(str(price))
            op_item = QTableWidgetItem(str(operator or "admin"))
            
            start_item = QTableWidgetItem(str(start_date or ""))
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            end_item = QTableWidgetItem(str(end_date or ""))
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
        except Exception as e:
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
        self.load_prices_to_table()
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
            
        self.load_prices_to_table()
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
            self.load_prices_to_table()
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
                    
            QMessageBox.information(self, "Success", "All price changes have been saved successfully!")
            self.load_prices_to_table()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric values for prices.")

    def print_price_list(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            # 원본 포스터(20261019_120441.jpg)와 완벽히 동일한 디자인을 구현하기 위한 HTML/CSS
            html_content = """
            <html>
            <head>
                <style>
                    body {
                        font-family: 'Helvetica Neue', Arial, sans-serif;
                        text-align: center;
                        color: #222;
                        margin: 0;
                        padding: 15px;
                        background-color: #ffffff;
                    }
                    .main-title {
                        font-size: 26px;
                        font-weight: 900;
                        letter-spacing: 1px;
                        color: #222;
                        margin: 0 0 5px 0;
                    }
                    .sub-main-title {
                        font-size: 32px;
                        font-weight: 900;
                        letter-spacing: 2px;
                        color: #222;
                        margin: 0 0 10px 0;
                    }
                    .subtitle {
                        font-size: 10px;
                        font-weight: bold;
                        margin-bottom: 25px;
                        color: #444;
                        letter-spacing: 0.5px;
                    }
                    /* 2열 레이아웃 그리드 테이블 */
                    .grid-table {
                        width: 100%;
                        border-collapse: collapse;
                        border: none;
                    }
                    .grid-cell {
                        width: 48%;
                        vertical-align: top;
                        padding: 5px;
                    }
                    /* 둥근 회색 배경 박스 */
                    .section-box {
                        background-color: #e9ecef;
                        border-radius: 12px;
                        padding: 15px 18px;
                        margin-bottom: 15px;
                        text-align: left;
                    }
                    .section-title {
                        font-size: 15px;
                        font-weight: 800;
                        color: #111;
                        text-align: center;
                        margin-top: 0;
                        margin-bottom: 12px;
                        letter-spacing: 0.5px;
                    }
                    /* 가격 아이템 테이블 */
                    .item-table {
                        width: 100%;
                        border-collapse: collapse;
                    }
                    .item-table td {
                        padding: 4px 2px;
                        font-size: 13px;
                    }
                    .item-name {
                        font-weight: 700;
                        color: #222;
                    }
                    .item-price {
                        text-align: right;
                        font-weight: 700;
                        color: #222;
                    }
                </style>
            </head>
            <body>
                <div class="main-title">LEE'S PRINTING SERVICES</div>
                <div class="sub-main-title">PRINTING PRICE</div>
                <div class="subtitle">PHOTOS/FILE FROM GMAIL OR FROM FB PAGES MESSENGER ARE ONLY ACCEPTED</div>
                
                <table class="grid-table">
            """
            
            # 카테고리들을 원본 포스터의 좌우 배치 순서에 맞게 순서화
            # 왼쪽 열 / 오른쪽 열 그룹 매칭
            left_categories = [
                ("Print B/W - Short", "print_bw_short"),
                ("Print B/W - Long", "print_bw_long"),
                ("Print Colored - Short", "print_colored_short"),
                ("Print Colored - Long", "print_colored_long"),
                ("Xerox/Scan - Short", "xerox_scan_short"),
            ]
            right_categories = [
                ("Photo Paper", "photo_paper"),
                ("Sticker Paper", "sticker_paper"),
                ("Laminate", "laminate"),
                ("Xerox/Scan - Long", "xerox_scan_long"),
            ]
            
            max_rows = max(len(left_categories), len(right_categories))
            
            for i in range(max_rows):
                html_content += "<tr>"
                
                # 왼쪽 칸
                html_content += '<td class="grid-cell">'
                if i < len(left_categories):
                    cat_title, kind_code = left_categories[i]
                    html_content += f"""
                    <div class="section-box">
                        <div class="section-title">{cat_title.upper()}</div>
                        <table class="item-table">
                    """
                    rows = self.config.get_items(kind=kind_code, active_only=True)
                    for r in rows:
                        name = r["item_name"]
                        val = r["price"]
                        html_content += f"""
                        <tr>
                            <td class="item-name">{name}</td>
                            <td class="item-price">{float(val):.2f}</td>
                        </tr>
                        """
                    html_content += "</table></div>"
                html_content += "</td>"
                
                # 오른쪽 칸
                html_content += '<td class="grid-cell">'
                if i < len(right_categories):
                    cat_title, kind_code = right_categories[i]
                    html_content += f"""
                    <div class="section-box">
                        <div class="section-title">{cat_title.upper()}</div>
                        <table class="item-table">
                    """
                    rows = self.config.get_items(kind=kind_code, active_only=True)
                    for r in rows:
                        name = r["item_name"]
                        val = r["price"]
                        html_content += f"""
                        <tr>
                            <td class="item-name">{name}</td>
                            <td class="item-price">{float(val):.2f}</td>
                        </tr>
                        """
                    html_content += "</table></div>"
                html_content += "</td>"
                
                html_content += "</tr>"
                
            html_content += """
                </table>
            </body>
            </html>
            """
            
            from PySide6.QtGui import QTextDocument
            doc = QTextDocument()
            doc.setHtml(html_content)
            doc.print_(printer)
            QMessageBox.information(self, "Print Complete", "Price list has been sent to the printer successfully!")

register_settings_tab('linkbox.print-fare-settings', 'Printing Prices', PrintFareTab, order=40)