from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Slot  # <-- Slot은 QtCore에서 가져와야 합니다.
from Common.geometry_manager import AutoGeometrySplitterTableWidget
from Common.date_util import matches_date_filter, set_date_safely
from Common.sortable_table_widget import ColumnManageableTableWidget, NaturalSortTableItem

from ..db.internet_share_db import internet_share_db
from ..db.db_signal_manager import signal_manager


class InternetHistoryTab(AutoGeometrySplitterTableWidget):
    title = "History"
    table_header_info_def = {
        # --- 전체 이력 탭 핵심 노출 컬럼 ---
        "id":            {"name": "ID",         "default": True,  "width": 60},
        "request_time":  {"name": "요청시각",   "default": True,  "width": 140},
        "user_name":     {"name": "사용자명",   "default": True,  "width": 100},
        "overall_status":{"name": "전체상태",   "default": True,  "width": 100},
        "client_ip":     {"name": "IP주소",     "default": True,  "width": 120},
        "device_name":   {"name": "기기이름",   "default": True,  "width": 110},
        "approval_status":{"name": "승인상태",  "default": True,  "width": 90},
        "cancel_status": {"name": "취소상태",   "default": True,  "width": 90},

        # --- 우클릭 메뉴에서 켜서 볼 수 있는 추가 컬럼 ---
        "approved_at":   {"name": "승인시각",   "default": False, "width": 140},
        "cancelled_at":  {"name": "취소시각",   "default": False, "width": 140},
        "cancel_operator":{"name": "취소처리자","default": False, "width": 100},
        "approval_operator":{"name": "승인처리자", "default": False, "width": 100},
        "minutes":       {"name": "사용시간",   "default": False, "width": 90},
        "price":         {"name": "요금",       "default": False, "width": 80},
        "user_id":       {"name": "사용자ID",   "default": False, "width": 100},
        "device_mac":    {"name": "MAC주소",    "default": False, "width": 140},
        "client_token_id":{"name": "토큰ID",    "default": False, "width": 120},
        "currency":      {"name": "화폐단위",   "default": False, "width": 80},
        "request_status":     {"name": "요청상태",     "default": False, "width": 90},
        "start_time":         {"name": "사용시작시각", "default": False, "width": 140},
        "expires_at":         {"name": "만료시각",     "default": False, "width": 140},
    }


    def __init__(self, window=None, share_filter=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.share_filter = share_filter
        self.db = internet_share_db

        self.table = None        
        self.start_text = ""
        self.end_text = ""

        self.field_keys = list(self.table_header_info_def.keys())

        self.init_ui()
        self.refresh_with_filter()
        
        # DB 업데이트 시그널 발생 시에도 현재 설정된 필터 유지하며 갱신
        signal_manager.request_updated.connect(self.refresh_with_filter)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if self.table is None:
            self.table = ColumnManageableTableWidget(self)
            self.table.setObjectName("history_list_table")
            
            headers = [info["name"] for info in self.table_header_info_def.values()]
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)

            self.table.set_header_info_definition(self.table_header_info_def)
            self.set_table_default_from_info(
                table_name="history_list_table",
                header_info_def=self.table_header_info_def
            )
        else:
            headers = [info["name"] for info in self.table_header_info_def.values()]
            self.table.setHorizontalHeaderLabels(headers)
            
        layout.addWidget(self.table)

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass
        self.load()

    def load(self):
        records = self.db.load(view_type="HISTORY")
        self.populate_table(records)

    def populate_table(self, records):
        if not isinstance(records, list):
            records = list(records.values()) if hasattr(records, 'values') else []
            
        self.table.setRowCount(len(records))
        for row_idx, record in enumerate(records):
            for col_idx, field_key in enumerate(self.field_keys):
                val = record.get(field_key, "")
                item = NaturalSortTableItem(str(val))
                self.table.setItem(row_idx, col_idx, item)

    def save(self, record_data: dict):
        self.db.save(record_data)

    def update(self, record_id: int, record_data: dict):
        self.db.update(record_id, record_data)

    def delete(self, record_id: int):
        self.db.delete(record_id)

    @Slot(str, str, str)
    @Slot(str, str, str)
    def load_filtered(self, start_text, end_text, filter_name):

        set_date_safely(start_text, self, 'start_text')
        set_date_safely(end_text, self, 'end_text')
        
        records = self.db.load(view_type="HISTORY")
        if not isinstance(records, list):
            records = list(records.values()) if hasattr(records, 'values') else []
        
        filtered_records = [
            r for r in records
            if matches_date_filter(r, ['request_time'], self.start_text, self.end_text, filter_name)
        ]
        self.populate_table(filtered_records)

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass
        self.refresh_with_filter()

    def refresh_with_filter(self):
        """share_filter가 연결되어 있으면 저장된 필터 조건으로 로드, 없으면 전체 로드"""
        if self.share_filter:
            self.share_filter.apply_filter_to_tab(self)
        else:
            self.load()        