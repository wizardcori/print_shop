"""Operator Settings Management UI Component and Database Configuration."""
from ast import operator
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import sqlite3

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QComboBox, QTableWidget, QTableWidgetItem, 
    QPushButton, QMessageBox, QLineEdit, QCheckBox, QWidget as QWidgetCell, QHBoxLayout as QHBoxLayoutCell
)
from PySide6.QtCore import Qt
from Common.config import DbConfigManager
from Common.paths import CONFIG_DIR
from Common.settings_dialog import register_settings_tab
from Common import globals as app_globals  # 상단에 추가

class OperatorConfig(DbConfigManager):
    section = "Operators"
    table_name = "operators"              # 자식 클래스가 지정한 테이블명
    config_kind = "admin"                 # 자식 클래스가 지정한 기본 kind    
    
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            user_name TEXT NOT NULL,
            user_password TEXT NOT NULL,
            operator TEXT DEFAULT '',
            authority INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            start_date TEXT NOT NULL,
            end_date TEXT
        )
    """
    
    initial_records = [
        {"kind": "admin", "user_name": "admin", "user_password": "admin123", "operator": "system", "authority": 1},
        {"kind": "staff", "user_name": "staff1", "user_password": "staff123", "operator": "system", "authority": 2},
    ]
    
    def __init__(self):
        # 부모 초기화 전에 구버전 테이블이 존재할 경우 강제 삭제하여 스키마 충돌 방지
        self._drop_old_table_if_needed()
        super().__init__()

    def _drop_old_table_if_needed(self):
        try:
            if CONFIG_DIR and os.path.exists(CONFIG_DIR):
                db_path = os.path.join(CONFIG_DIR, "app_config.db")
                if os.path.exists(db_path):
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.table_name,))
                        if cursor.fetchone():
                            cursor.execute(f"PRAGMA table_info({self.table_name})")
                            columns = [row[1] for row in cursor.fetchall()]
                            # user_name 컬럼이나 authority 컬럼이 없는 구버전 테이블인 경우 삭제
                            if columns and ("user_name" not in columns or "authority" not in columns):
                                cursor.execute(f"DROP TABLE {self.table_name}")
                                conn.commit()
        except Exception as e:
            print(f"\033[91m[DB Migration Error] {e}\033[0m")

    def _seed_initial_records(self, cursor, conn):
        if not self.initial_records:
            return

        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        count = cursor.fetchone()[0]

        if count == 0:
            now = datetime.now().isoformat()
            for rec in self.initial_records:
                kind = rec.get("kind", "default")
                user_name = rec.get("user_name", "")
                user_password = rec.get("user_password", "")
                operator = rec.get("operator", "system")
                authority = int(rec.get("authority", 1))
                is_active = rec.get("is_active", 1)
                
                cursor.execute(
                    f"""
                    INSERT INTO {self.table_name} 
                    (kind, user_name, user_password, operator, authority, is_active, start_date, end_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (kind, user_name, user_password, operator, authority, is_active, now)
                )
            conn.commit()

    def get_items(self, kind: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        target_kind = kind or self.config_kind
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = f"""
                SELECT id, kind, user_name, user_password, operator, authority, is_active, start_date, end_date
                FROM {self.table_name}
                WHERE 1=1
            """
            params = []
            
            if target_kind and target_kind != "ALL":
                query += " AND kind = ?"
                params.append(target_kind)
                
            if active_only:
                query += " AND is_active = 1"
                
            query += " ORDER BY kind ASC, id ASC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
        return [{
            "id": r[0],
            "kind": r[1],
            "user_name": r[2],
            "user_password": r[3],
            "operator": r[4] or "",
            "authority": r[5],
            "is_active": r[6],
            "start_date": r[7] or "",
            "end_date": r[8] or ""
        } for r in rows]

    def save_operator(self, user_name: str, user_password: str, operator: str, authority: int, kind: Optional[str] = None):
        target_kind = kind or self.config_kind
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                f"""
                SELECT id, user_password, authority FROM {self.table_name}
                WHERE kind = ? AND user_name = ? AND is_active = 1
                """,
                (target_kind, user_name)
            )
            current = cursor.fetchone()
            
            if current:
                current_id, curr_pass, curr_auth = current
                
                if curr_pass == user_password and int(curr_auth) == int(authority):
                    cursor.execute(
                        f"UPDATE {self.table_name} SET operator = ? WHERE id = ?",
                        (operator, current_id)
                    )
                    conn.commit()
                    return
                
                cursor.execute(
                    f"UPDATE {self.table_name} SET is_active = 0, end_date = ? WHERE id = ?",
                    (now, current_id)
                )
            
            cursor.execute(
                f"""
                INSERT INTO {self.table_name} 
                (kind, user_name, user_password, operator, authority, is_active, start_date, end_date)
                VALUES (?, ?, ?, ?, ?, 1, ?, NULL)
                """,
                (target_kind, user_name, user_password, operator, int(authority), now)
            )
            conn.commit()


class OperatorTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = OperatorConfig()
        
        self.categories = {
            "ALL": "ALL",
            "Admin": "admin",
            "Staff": "staff"
        }
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('<h3>Operator Account Management</h3>'))
        
        cat_layout = QHBoxLayout()
        
        self.active_filter_chk = QCheckBox("Active Only")
        self.active_filter_chk.setChecked(True)
        self.active_filter_chk.stateChanged.connect(self.load_operators_to_table)
        cat_layout.addWidget(self.active_filter_chk)
        
        cat_layout.addWidget(QLabel('Select Role:'))
        
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(list(self.categories.keys()))
        self.cat_combo.currentIndexChanged.connect(self.on_category_changed)
        cat_layout.addWidget(self.cat_combo)
        
        self.kind_indicator_label = QLabel()
        self.kind_indicator_label.setStyleSheet("color: #3498db; font-weight: bold; margin-left: 15px;")
        cat_layout.addWidget(self.kind_indicator_label)
        
        cat_layout.addStretch()
        layout.addLayout(cat_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            'Role (Kind)', 'Active', 'User Name', 'Password', 'Operator', 'Authority', 'Start Date', 'End Date'
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(self.on_table_row_clicked)
        layout.addWidget(self.table)
        
        input_layout = QHBoxLayout()
        
        self.input_kind_combo = QComboBox()
        self.input_kind_combo.setEditable(True)
        real_categories = {k: v for k, v in self.categories.items() if v != "ALL"}
        self.input_kind_combo.addItems(list(real_categories.keys()))
        self.input_kind_combo_dict = real_categories
        
        self.input_active_chk = QCheckBox("Active")
        self.input_active_chk.setChecked(True)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("User Name")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Operator")
        self.operator_input.setText(app_globals.GLOBAL_LOGIN_USER_NAME or "admin")
        self.operator_input.setReadOnly(True)
        
        self.authority_input = QLineEdit()
        self.authority_input.setPlaceholderText("Authority (e.g. 1)")
        self.authority_input.setText("1")
        
        update_btn = QPushButton("Update")
        update_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        update_btn.clicked.connect(self.update_item)
        
        add_btn = QPushButton("Add Operator")
        add_btn.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
        add_btn.clicked.connect(self.add_item)
        
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        delete_btn.clicked.connect(self.delete_item)
        
        input_layout.addWidget(QLabel("Role:"))
        input_layout.addWidget(self.input_kind_combo)
        input_layout.addWidget(self.input_active_chk)
        input_layout.addWidget(QLabel("User:"))
        input_layout.addWidget(self.username_input)
        input_layout.addWidget(QLabel("Pass:"))
        input_layout.addWidget(self.password_input)
        input_layout.addWidget(QLabel("Op:"))
        input_layout.addWidget(self.operator_input)
        input_layout.addWidget(QLabel("Auth:"))
        input_layout.addWidget(self.authority_input)
        input_layout.addWidget(update_btn)
        input_layout.addWidget(add_btn)
        input_layout.addWidget(delete_btn)
        layout.addLayout(input_layout)
        
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
        self.load_operators_to_table()

    def load_operators_to_table(self):
        kind = self.get_current_kind()
        active_only = self.active_filter_chk.isChecked()
        
        self.table.setRowCount(0)
        rows_data = self.config.get_items(kind=kind, active_only=active_only)
            
        row = 0
        for r_data in rows_data:
            r_kind = r_data["kind"]
            user_name = r_data["user_name"]
            user_password = r_data["user_password"]
            operator = r_data["operator"]
            authority = r_data["authority"]
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
            chk.stateChanged.connect(lambda state, k=r_kind, name=user_name: self.on_checkbox_toggled(k, name, state))
            cell_layout.addWidget(chk)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            
            name_item = QTableWidgetItem(user_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            pass_item = QTableWidgetItem(str(user_password))
            op_item = QTableWidgetItem(str(operator or ""))
            auth_item = QTableWidgetItem(str(authority))
            
            start_item = QTableWidgetItem(str(start_date or ""))
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            end_item = QTableWidgetItem(str(end_date or ""))
            end_item.setFlags(end_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.table.setItem(row, 0, kind_item)
            self.table.setCellWidget(row, 1, cell_widget)
            self.table.setItem(row, 2, name_item)
            self.table.setItem(row, 3, pass_item)
            self.table.setItem(row, 4, op_item)
            self.table.setItem(row, 5, auth_item)
            self.table.setItem(row, 6, start_item)
            self.table.setItem(row, 7, end_item)
            row += 1

    def on_checkbox_toggled(self, kind: str, user_name: str, state: int):
        new_active = 1 if state == Qt.CheckState.Checked.value or state == 2 else 0
        with self.config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.config.table_name} SET is_active = ? WHERE kind = ? AND user_name = ?",
                (new_active, kind, user_name)
            )
            conn.commit()

    def on_table_row_clicked(self, row: int, col: int):
        try:
            kind_val = self.table.item(row, 0).text()
            cell_widget = self.table.cellWidget(row, 1)
            chk = cell_widget.findChild(QCheckBox) if cell_widget else None
            is_active = chk.isChecked() if chk else True
            
            username_val = self.table.item(row, 2).text()
            pass_val = self.table.item(row, 3).text()
            operator_val = self.table.item(row, 4).text()
            auth_val = self.table.item(row, 5).text()
            
            found = False
            for display_name, code in self.input_kind_combo_dict.items():
                if code == kind_val:
                    self.input_kind_combo.setCurrentText(display_name)
                    found = True
                    break
            if not found:
                self.input_kind_combo.setCurrentText(kind_val)
            
            self.input_active_chk.setChecked(is_active)
            self.username_input.setText(username_val)
            self.password_input.setText(pass_val)
            if operator_val:
                self.operator_input.setText(operator_val)
            self.authority_input.setText(auth_val)
        except Exception as e:
            pass

    def _resolve_input_kind(self) -> str:
        typed_val = self.input_kind_combo.currentText().strip()
        return self.input_kind_combo_dict.get(typed_val, typed_val)

    def add_item(self):
        kind = self._resolve_input_kind()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        operator = app_globals.GLOBAL_LOGIN_USER_NAME or "admin"
        self.operator_input.setText(operator)        

        auth_str = self.authority_input.text().strip()
        is_active = 1 if self.input_active_chk.isChecked() else 0
        
        if not kind or not username or not password or not auth_str:
            QMessageBox.warning(self, "Warning", "Please enter Role, User Name, Password and Authority.")
            return
            
        try:
            authority = int(auth_str)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Authority must be a valid integer.")
            return
            
        self.config.config_kind = kind
        self.config.save_operator(user_name=username, user_password=password, operator=operator, authority=authority, kind=kind)
        
        with self.config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.config.table_name} SET is_active = ? WHERE kind = ? AND user_name = ? AND is_active = 1",
                (is_active, kind, username)
            )
            conn.commit()
            
        self.username_input.clear()
        self.password_input.clear()
        self.load_operators_to_table()
        QMessageBox.information(self, "Success", f"Operator '{username}' has been added/saved.")

    def update_item(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an operator from the table to update.")
            return
            
        kind = self._resolve_input_kind()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        operator = app_globals.GLOBAL_LOGIN_USER_NAME or "admin"
        self.operator_input.setText(operator)        
        auth_str = self.authority_input.text().strip()
        is_active = 1 if self.input_active_chk.isChecked() else 0
        
        if not kind or not username or not password or not auth_str:
            QMessageBox.warning(self, "Warning", "All fields cannot be empty.")
            return
            
        try:
            authority = int(auth_str)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Authority must be a valid integer.")
            return
            
        old_name_item = self.table.item(selected_row, 2)
        old_name = old_name_item.text() if old_name_item else username
        old_kind_item = self.table.item(selected_row, 0)
        old_kind = old_kind_item.text() if old_kind_item else kind
        
        with self.config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.config.table_name} SET kind = ?, user_name = ?, user_password = ?, operator = ?, authority = ?, is_active = ? WHERE kind = ? AND user_name = ?",
                (kind, username, password, operator, authority, is_active, old_kind, old_name)
            )
            conn.commit()
            
        self.load_operators_to_table()
        QMessageBox.information(self, "Updated", f"Operator '{username}' has been updated successfully.")

    def delete_item(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an operator to delete from the table.")
            return
            
        name_item = self.table.item(selected_row, 2)
        kind_item = self.table.item(selected_row, 0)
        
        if name_item and kind_item:
            username = name_item.text()
            kind = kind_item.text()
            now = datetime.now().isoformat()
            
            with self.config._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE {self.config.table_name} SET is_active = 0, end_date = ? WHERE kind = ? AND user_name = ? AND is_active = 1",
                    (now, kind, username)
                )
                conn.commit()
                
            self.load_operators_to_table()
            QMessageBox.information(self, "Deleted", f"Operator '{username}' has been deactivated.")

    def save_to_config(self):
        try:
            for row in range(self.table.rowCount()):
                kind = self.table.item(row, 0).text()
                username = self.table.item(row, 2).text()
                password = self.table.item(row, 3).text()
                operator = self.table.item(row, 4).text()
                auth_str = self.table.item(row, 5).text()
                
                cell_widget = self.table.cellWidget(row, 1)
                chk = cell_widget.findChild(QCheckBox) if cell_widget else None
                is_active = 1 if (chk and chk.isChecked()) else 0
                
                self.config.save_operator(user_name=username, user_password=password, operator=operator, authority=int(auth_str), kind=kind)
                
                with self.config._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        f"UPDATE {self.config.table_name} SET is_active = ? WHERE kind = ? AND user_name = ? AND is_active = 1",
                        (is_active, kind, username)
                    )
                    conn.commit()
                    
            QMessageBox.information(self, "Success", "All operator changes have been saved successfully!")
            self.load_operators_to_table()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric values for authorities.")

register_settings_tab('operator-settings', 'Operators', OperatorTab, order=35)