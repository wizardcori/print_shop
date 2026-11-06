from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal

class InternetShareApprovalDialog(QDialog):
    # 승인 또는 거절 시 외부(메인 윈도우)로 결과를 전달할 시그널 정의
    decision_made = Signal(str, bool, int) # (client_ip, is_approved, minutes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("인터넷 사용 요청 승인 관리")
        self.resize(380, 220)
        self.current_ip = None
        self.current_minutes = 0

        # 모달리스 설정 (메인 창 뒤로 숨지 않게 하려면 Tool 또는 Normal 유지하되 플래그 조정 가능)
        self.setModal(False)

        layout = QVBoxLayout(self)

        # 정보 표시 레이블들
        self.ip_label = QLabel("<b>IP 주소:</b> 대기 중인 요청 없음")
        self.device_label = QLabel("<b>기기 이름:</b> -")
        self.time_label = QLabel("<b>신청 시간:</b> - 분")
        
        layout.addWidget(self.ip_label)
        layout.addWidget(self.device_label)
        layout.addWidget(self.time_label)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        self.approve_btn = QPushButton("승인 (Approve)")
        self.approve_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px;")
        self.approve_btn.clicked.connect(self.on_approve)
        
        self.reject_btn = QPushButton("거절 (Reject)")
        self.reject_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold; padding: 6px;")
        self.reject_btn.clicked.connect(self.on_reject)

        btn_layout.addWidget(self.approve_btn)
        btn_layout.addWidget(self.reject_btn)
        layout.addLayout(btn_layout)

    def load_request(self, session_data):
        """새로운 요청 데이터를 받아 다이얼로그 내용 갱신 후 표시"""
        self.current_ip = session_data.get('ip')
        self.current_minutes = session_data.get('requested_minutes', 30)
        
        self.ip_label.setText(f"<b>IP 주소:</b> {self.current_ip}")
        self.device_label.setText(f"<b>기기 이름:</b> {session_data.get('device_name', 'Unknown')}")
        self.time_label.setText(f"<b>신청 시간:</b> {self.current_minutes} 분")
        
        self.show()
        self.raise_()
        self.activateWindow()

    def on_approve(self):
        if self.current_ip:
            self.decision_made.emit(self.current_ip, True, self.current_minutes)
        self.hide() # 창을 파괴하지 않고 숨김

    def on_reject(self):
        if self.current_ip:
            self.decision_made.emit(self.current_ip, False, 0)
        self.hide() # 창을 파괴하지 않고 숨김

    def closeEvent(event):
        """X 버튼으로 닫을 때도 창이 완전히 꺼지지 않고 숨겨지도록 처리"""
        event.ignore()
        self.hide()