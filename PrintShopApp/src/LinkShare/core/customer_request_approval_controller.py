"""
[모듈 개요]
LinkShare 고객 인터넷 사용 승인 및 거절 워크플로우를 담당하는 관리자 UI 컨트롤러 모듈.

[처리 루틴]
1. signal_manager의 요청 변경 시그널(request_updated) 수신 시 DB에서 대기 목록 로드
2. 관리자 화면 최상단 활성화 및 승인/거절 다이얼로그(InternetShareApprovalDialog) 노출
3. 승인 선택 시:
   - internet_share_db.approve_request()를 호출하여 해당 요청의 상태를 APPROVED / ACTIVE로 업데이트
4. 거절 선택 시:
   - internet_share_db.cancel_request() 또는 상태 업데이트를 통해 거절 처리 반영
"""

import datetime

from PySide6.QtWidgets import QMessageBox
from Common.log import logd, loge
from Session.session_manager import SessionManager
from ..db.internet_share_db import internet_share_db
from ..db.db_signal_manager import signal_manager
from ..ui.internet_share_approval_dialog import get_approval_dialog  # 다이얼로그 모듈 임포트
from LinkShare.core.internet_share_services import internet_share_service

from .logic_signal_manager import logic_signal_manager


class ApprovalController:
    def __init__(
        self,
        parent,
        append_usage_log=None,
        notify_status_change=None,
    ):
        self.parent = parent
        self.sessions = SessionManager.repository
        self.db = internet_share_db
        self.append_usage_log_func = append_usage_log
        self.notify_status_change_func = notify_status_change
        
        # 전용 승인 다이얼로그 인스턴스 생성 및 시그널 연결

        #self.approval_dialog = InternetShareApprovalDialog(self.parent)
        #self.approval_dialog.decision_made_signal.connect(self.handle_dialog_decision)

        
        # DB 변경 시그널 수신 연결 (데이터 갱신 트리거)
        signal_manager.request_updated.connect(self.handle_request_updated)

        # 다이얼로그 인스턴스(internet_share_approval_dialog)의 시그널 연결 수정
        internet_share_approval_dialog = get_approval_dialog()
        internet_share_approval_dialog.approval_accept_signal.connect(self.handle_approval_accept)
        internet_share_approval_dialog.approval_reject_signal.connect(self.handle_approval_reject)
       
        #InternetShareApprovalDialog.approval_accept_signal.connect(client_token_id=client_token_id, request_id=request_id, client_ip=client_ip, minutes=minutes: self.handle_approval_accept)        

        # internet_share_approval_dialog.approval_accept_signal.connect(
        #     lambda c_token=client_token_id, r_id=request_id, c_ip=client_ip, dur=minutes: 
        #     self.handle_approval_accept(c_token, r_id, c_ip, dur)
        # )

        # InternetShareApprovalDialog.approval_reject_signal.connect(client_token_id=client_token_id, request_id=request_id, client_ip=client_ip, minutes=minutes: self.handle_approval_reject)        
        
        logd("[ApprovalController] DB 및 시그널 연동 초기화 완료")

    def handle_request_updated(self):
        """DB 변경 시그널 수신 시 대기 요청 목록 확인 및 다이얼로그 갱신"""
        pending_requests = self.db.load(view_type="REQUEST")
        if pending_requests:
            # 최신 대기 요청이 존재할 경우 알림 및 다이얼로그 갱신 처리
            latest_req = pending_requests[0]
            client_ip = latest_req.get('client_ip')
            request_id = latest_req.get('id')
            minutes = latest_req.get('minutes', 60)
            
            logd(f"[ApprovalController] 승인 대기 요청 감지: IP={client_ip}, ID={request_id}, 시간={minutes}분")
            self.bring_to_front()
            self.update_connection_summary()

            # 소리 알림 설정이 켜져 있는 경우 소리 재생
            # if self.get_sound_enabled():
            #     self.play_approval_sound()

            session_data = {
                'ip': client_ip,
                'request_id': request_id,
                'device_name': latest_req.get('device_name', 'Unknown Device'),
                'requested_minutes': minutes,
                'fare': f"{minutes}분 사용권",
                'token_id': latest_req.get('client_token_id', ''),
                'request_time': latest_req.get('request_time', ''),
            }

            get_approval_dialog().show_unique_dialog(parent=self, session_data=session_data)



    def handle_approval_accept(self, client_token_id: str, request_id: int, client_ip: str, minutes: int):
        # """다이얼로그에서 승인/거절 버튼을 눌렀을 때 호출되는 슬롯 메서드 (decision_made 시그널 연동)"""
        logd(f"[ApprovalController] 관리자 승인 선택됨: IP={client_ip}, ID={request_id}")
        internet_share_service.approve_to_queue(request_id)
        #self.show_auto_close_message(QMessageBox.Information, 'Approved', f'Internet access approved for {client_ip}.')
           
        # if self.notify_status_change_func:
        #     self.notify_status_change_func()
        # self.update_connection_summary()

    def handle_approval_reject(self, client_token_id: str, request_id: int, client_ip: str, minutes: int):
    #     """다이얼로그에서 승인/거절 버튼을 눌렀을 때 호출되는 슬롯 메서드 (decision_made 시그널 연동)"""
        logd(f"[ApprovalController] 관리자 거부 선택됨: IP={client_ip}, ID={request_id}")
        internet_share_service.reject_request(request_id)
        # QMessageBox.warning(self.parent, "Rejected", f"Internet request from {client_ip} was rejected.")
            
        # if self.notify_status_change_func:
        #     self.notify_status_change_func()
        # self.update_connection_summary()


    def bring_to_front(self):
        if hasattr(self.parent, 'bring_to_front'):
            self.parent.bring_to_front()
        elif hasattr(self.parent, 'raise_') and hasattr(self.parent, 'activateWindow'):
            self.parent.raise_()
            self.parent.activateWindow()

    def update_connection_summary(self):
        if hasattr(self.parent, 'update_connection_summary'):
            self.parent.update_connection_summary()

    def get_sound_enabled(self):
        if hasattr(self.parent, 'get_sound_enabled'):
            return self.parent.get_sound_enabled()
        return False

    def play_approval_sound(self):
        if hasattr(self.parent, 'play_approval_sound'):
            self.parent.play_approval_sound()

    def stop_approval_sound(self):
        if hasattr(self.parent, 'stop_approval_sound'):
            self.parent.stop_approval_sound()

    def show_auto_close_message(self, icon, title, text):
        if hasattr(self.parent, 'show_auto_close_message'):
            self.parent.show_auto_close_message(icon, title, text)
        else:
            QMessageBox.information(self.parent, title, text)