from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QPushButton, QWidget, QComboBox, QLineEdit, QGroupBox
)
from PySide6.QtCore import Signal
from Common.date_util import matches_date_filter
from Common.log import logd, loge
from Common.sortable_table_widget import SortableTableWidget
from Common.geometry_manager import SingletonAutoGeometryDialog
from ..db.internet_share_db import internet_share_db
from ..internet_share_filter import InternetShareFilter

from ..internet_share_filter import InternetShareFilter
from Common.current_user_session import get_username
from LinkShare.core.internet_share_services import internet_share_service

class InternetShareApprovalDialog(SingletonAutoGeometryDialog):
    # 시그널 정의: (request_id, client_ip, is_approved, minutes)
    #decision_made_signal = Signal(int, str, bool, int)
    approval_accept_signal = Signal(str, int, str, int)
    approval_reject_signal = Signal(str, int, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("인터넷 사용 요청 승인 관리 (대기 목록)")
        #self.resize(800, 480)
        self.db = internet_share_db
        self.operator = get_username()
        self.filter_manager = InternetShareFilter()
        self.filter_manager.init_tab_states(["RequestApproval"])

        # 모달리스 설정
        self.setModal(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 1. 상단 날짜 필터 (Filter Quick Controls) GroupBox 구성
        filter_group = QGroupBox("Filter Quick Controls")
        filter_layout = QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(10, 5, 10, 5)

        # 콤보박스 (Today, Yesterday, Custom, All 등)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(InternetShareFilter.FILTER_ITEMS)
        self.filter_combo.setCurrentText("Today")

        # 시작 날짜 및 종료 날짜 입력 텍스트박스
        self.start_date_edit = QLineEdit()
        self.start_date_edit.setPlaceholderText("YYYY-MM-DD")
        
        self.end_date_edit = QLineEdit()
        self.end_date_edit.setPlaceholderText("YYYY-MM-DD")

        filter_layout.addWidget(self.filter_combo, 1)
        filter_layout.addWidget(self.start_date_edit, 2)
        filter_layout.addWidget(self.end_date_edit, 2)
        filter_layout.addStretch(1)

        layout.addWidget(filter_group)

        # 필터 이벤트 핸들러 연결
        self.filter_combo.currentIndexChanged.connect(self._on_combo_changed)
        self.start_date_edit.editingFinished.connect(self._on_date_edited)
        self.end_date_edit.editingFinished.connect(self._on_date_edited)

        # 2. 대기 목록 테이블 위젯 구성
        self.table = SortableTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "요청 시간", "IP 주소", "기기 이름", "시간(분)", "요금(PHP)", "관리"
        ])
        
        layout.addWidget(self.table)

        # 초기 필터 날짜 설정 및 데이터 로드
        start_d, end_d = self.filter_manager.calculate_dates_by_filter("Today")
        self.start_date_edit.setText(start_d)
        self.end_date_edit.setText(end_d)
        self.load_pending_requests()

    def _on_combo_changed(self, index):
        combo_text = self.filter_combo.currentText()
        def set_date_cb(start_val, end_val):
            self.start_date_edit.setText(start_val)
            self.end_date_edit.setText(end_val)

        self.filter_manager.handle_filter_combo_changed(
            "RequestApproval", 0, index, combo_text, set_date_callback=set_date_cb
        )
        self.load_pending_requests()

    def _on_date_edited(self):
        start_val = self.start_date_edit.text()
        end_val = self.end_date_edit.text()

        def set_custom_combo_cb(custom_idx):
            self.filter_combo.setCurrentIndex(custom_idx)

        self.filter_manager.handle_date_field_changed(
            "RequestApproval", 0, start_val, end_val, set_custom_combo_callback=set_custom_combo_cb
        )
        self.load_pending_requests()

    def load_pending_requests(self):
        """DB에서 승인 대기 중인 목록을 불러오고 상단 날짜 필터를 적용하여 테이블 렌더링"""
        records = self.db.load(view_type="REQUEST")

        # 날짜 필터링 적용
        start_text = self.start_date_edit.text().strip()
        end_text = self.end_date_edit.text().strip()
        filter_name = self.filter_combo.currentText()

        filtered_records = [
            r for r in records
            if matches_date_filter(r, ['request_time'], start_text, end_text, filter_name)
        ]

        self.table.setRowCount(len(filtered_records))

        for row_idx, record in enumerate(filtered_records):
            client_token_id = record.get("client_token_id")
            req_id = record.get("id")
            request_time = str(record.get("request_time", ""))
            client_ip = str(record.get("client_ip", ""))
            device_name = str(record.get("device_name", "-"))
            duration = record.get("minutes", 60)
            price = record.get("price", 0.0)

            # 텍스트 데이터 세팅
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(req_id)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(request_time))
            self.table.setItem(row_idx, 2, QTableWidgetItem(client_ip))
            self.table.setItem(row_idx, 3, QTableWidgetItem(device_name))
            self.table.setItem(row_idx, 4, QTableWidgetItem(f"{duration}분"))
            self.table.setItem(row_idx, 5, QTableWidgetItem(str(price)))

            # 각 레코드(행)별 승인/거절 버튼 생성
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)

            approve_btn = QPushButton("승인")
            approve_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 3px;")
            approve_btn.clicked.connect(lambda checked=False, client_token_id = client_token_id, rid=req_id, ip=client_ip, dur=duration: self.on_approve(client_token_id, rid, ip, dur))

            reject_btn = QPushButton("거절")
            reject_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold; padding: 3px;")
            reject_btn.clicked.connect(lambda checked=False, client_token_id = client_token_id, rid=req_id, ip=client_ip, dur=duration: self.on_reject(client_token_id, rid, ip, dur))

            btn_layout.addWidget(approve_btn)
            btn_layout.addWidget(reject_btn)
            btn_layout.addStretch()

            self.table.setCellWidget(row_idx, 6, btn_widget)

    def slot_load_request(self, session_data=None):
        """외부 호출 시 최신 대기 목록 갱신 및 창 표시"""
        self.load_pending_requests()

    def on_approve(self, client_token_id, request_id, client_ip, duration):
        """관리자 승인 버튼 클릭 시 승인 시그널 발송"""
        logd(f"[ApprovalDialog] 승인 시그널 발송: ID={request_id}, IP={client_ip}, 기간={duration}분")
        
        # 1. 시그널을 통한 이벤트 전달 (시그널 이름은 프로젝트 환경에 맞게 조정)
        if hasattr(self, "approval_accept_signal"):
            self.approval_accept_signal.emit(client_token_id, request_id, client_ip, duration)
        elif hasattr(self, "decision_made_signal"):
            self.decision_made_signal.emit(request_id, client_ip, True, duration)
            
        #self.accept()

    def on_reject(self, client_token_id: str, request_id: int, client_ip: str, duration: int):
        """관리자 거절 버튼 클릭 시 거절/취소 시그널 발송"""
        logd(f"[ApprovalDialog] 거절 시그널 발송: ID={request_id}, IP={client_ip}")
        
        # 1. 시그널을 통한 이벤트 전달
        if hasattr(self, "approval_reject_signal"):
            self.approval_reject_signal.emit(client_token_id, request_id, client_ip, duration)
        elif hasattr(self, "decision_made_signal"):
            self.decision_made_signal.emit(request_id, client_ip, False, duration)
            
        #self.accept()

def get_approval_dialog(parent=None):
    return InternetShareApprovalDialog.get_instance(parent)
