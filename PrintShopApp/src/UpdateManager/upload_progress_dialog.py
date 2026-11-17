### 3. `upload_progress_dialog.py` (진행 상태 UI 초기화, 상태 변경, 오류 기록 추적)
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit
)
from PySide6.QtCore import Qt, Signal

from Common.log import logd, loge

class UploadProgressDialog(QDialog):
    """전체 및 개별 진행률, 취소 기능이 포함된 모달리스 진행 상태 다이얼로그"""
    
    cancel_all_signal = Signal()
    cancel_item_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("작업 진행 상황 (업로드/다운로드)")
        self.resize(650, 450)
        self.setWindowModality(Qt.WindowModality.NonModal)
        
        self.item_rows = {}  # version -> row index map
        
        layout = QVBoxLayout(self)
        
        # 전체 진행 상태 레이아웃
        total_layout = QVBoxLayout()
        total_layout.addWidget(QLabel("<b>전체 진행률 (Total Progress)</b>"))
        
        total_hb = QHBoxLayout()
        self.total_progress_bar = QProgressBar(self)
        self.total_progress_bar.setRange(0, 100)
        self.total_progress_bar.setValue(0)
        total_hb.addWidget(self.total_progress_bar)
        
        self.btn_cancel_all = QPushButton("전체 취소", self)
        self.btn_cancel_all.setStyleSheet("color: #F44747; font-weight: bold;")
        self.btn_cancel_all.clicked.connect(self._on_cancel_all_clicked)
        total_hb.addWidget(self.btn_cancel_all)
        total_layout.addLayout(total_hb)
        layout.addLayout(total_layout)
        
        # 개별 작업 리스트 테이블
        layout.addWidget(QLabel("<b>개별 작업 진행 상태 (Item Progress)</b>"))
        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["버전 / 파일명", "상태", "진행률", "개별 취소"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        
        # 상세 로그 및 에러 출력 영역
        layout.addWidget(QLabel("<b>상세 로그 및 에러 메시지</b>"))
        self.txt_log = QTextEdit(self)
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(120)
        layout.addWidget(self.txt_log)
        
        # 하단 닫기 버튼
        btn_layout = QHBoxLayout()
        self.btn_close = QPushButton("숨기기 (Hide)", self)
        self.btn_close.clicked.connect(self.hide)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _on_cancel_all_clicked(self):
        logd("진행 다이얼로그: [전체 취소] 버튼 클릭됨")
        self.cancel_all_signal.emit()

    def _on_cancel_item_clicked(self, version_str: str):
        logd(f"진행 다이얼로그: [개별 취소] 버튼 클릭됨 -> v{version_str}")
        self.cancel_item_signal.emit(version_str)

    def closeEvent(self, event):
        event.ignore()
        logd("진행 다이얼로그 닫기 이벤트 -> 숨김(hide) 처리")
        self.hide()

    def init_tasks(self, task_items: list):
        """작업 목록 초기화 (task_items: [{'version': '1.3.1', 'name': '...'}, ...])"""
        logd(f"진행 다이얼로그 작업 테이블 초기화 ({len(task_items)}개 항목)")
        self.table.setRowCount(0)
        self.item_rows.clear()
        self.total_progress_bar.setValue(0)
        self.txt_log.clear()
        
        self.table.setRowCount(len(task_items))
        for idx, item in enumerate(task_items):
            ver = item.get("version", "")
            name = item.get("name", f"v{ver}")
            self.item_rows[ver] = idx
            
            self.table.setItem(idx, 0, QTableWidgetItem(f"v{ver} ({name})"))
            
            status_item = QTableWidgetItem("대기 중")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 1, status_item)
            
            # 개별 프로그레스바
            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setValue(0)
            self.table.setCellWidget(idx, 2, pbar)
            
            # 개별 취소 버튼
            btn_cancel = QPushButton("취소")
            btn_cancel.clicked.connect(lambda checked=False, v=ver: self._on_cancel_item_clicked(v))
            self.table.setCellWidget(idx, 3, btn_cancel)

    def update_total_progress(self, percent: int, msg: str = ""):
        self.total_progress_bar.setValue(percent)
        if msg:
            self.txt_log.append(msg)
            logd(f"[전체 진행률 {percent}%] {msg}")

    def update_item_progress(self, version_str: str, percent: int, status_str: str, msg: str = ""):
        if version_str in self.item_rows:
            row = self.item_rows[version_str]
            status_item = self.table.item(row, 1)
            if status_item:
                status_item.setText(status_str)
            pbar = self.table.cellWidget(row, 2)
            if isinstance(pbar, QProgressBar):
                pbar.setValue(percent)
        if msg:
            self.txt_log.append(msg)
        if percent in (0, 50, 100) or status_str in ("완료", "취소됨"):
            logd(f"[개별 진행 - v{version_str}] {percent}% ({status_str}) {msg}")

    def append_error(self, version_str: str, err_msg: str):
        if version_str in self.item_rows:
            row = self.item_rows[version_str]
            status_item = self.table.item(row, 1)
            if status_item:
                status_item.setText("실패")
        error_line = f"❌ [오류 - v{version_str}] {err_msg}"
        self.txt_log.append(error_line)
        loge(f"진행 다이얼로그 오류 표시 - v{version_str}: {err_msg}")
