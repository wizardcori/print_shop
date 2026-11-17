### 2. `customer_request_cancel_service.py` (취소 요청 서비스)
#고객이 보낸 취소 요청 ID를 파싱하여, 직접 상태 머신이나 DB를 호출하는 대신 
# **`internet_share_service.cancel_request`**를 호출하여 상태 전이, 세션 재계산 및 시그널 발행이 한 번에 안전하게 처리되도록 구성합니다
# """
# [모듈 개요]
# LinkShare 고객 인터넷 사용 및 시간 연장 요청 취소 처리 서비스 모듈.
# - InternetShareService를 활용하여 취소 처리 및 세션 재계산/시그널 연동 제어
# """

import datetime
from Common.log import logd, loge
from LinkShare.core.internet_share_services import internet_share_service

from Common.log import set_file_tag; set_file_tag("WEB")

def handle_customer_request_cancel(request, get_client_identity):
    """
    클라이언트가 보낸 사용 요청 취소 처리를 담당하는 서비스 함수.
    1. 클라이언트 식별 정보 조회
    2. InternetShareService를 통한 CANCELLED 처리 및 세션 재계산 위임
    """
    token, token_id, client_ip, device_name = get_client_identity()
    req_id = request.args.get('id')

    if not req_id or not req_id.isdigit():
        loge(f"[CustomerCancel] 잘못된 요청 ID 형식: {req_id}")
        return {'status': 'Error', 'msg': 'Invalid request ID.'}, 400

    request_id = int(req_id)

    # 서비스 레이어를 통한 취소 처리 실행
    try:
        res, status_code = internet_share_service.cancel_request(request_id, operator="USER")
        if status_code != 200:
            return res, status_code
            
        logd(f"[CustomerCancel] 사용 요청 취소 완료: IP={client_ip}, ReqID={request_id}")
    except Exception as e:
        loge(f"[CustomerCancel] 취소 처리 중 오류 발생: {e}")
        return {'status': 'Error', 'msg': 'Failed to cancel request.'}, 500

    return {
        'status': 'OK',
        'msg': '사용 요청이 취소되었습니다.'
    }
