"""
[모듈 개요]
LinkShare 고객 인터넷 사용 및 시간 연장 요청 처리 서비스 모듈.
- 실시간 요금표 및 최대 연결 수 검증 후 InternetShareService를 통해 신규 요청 생성
"""

import datetime
from LinkShare.setting.hotspot_settings import HotspotNetworkConfig
from LinkShare.setting.internet_rates_settings import InternetRatesConfig
from Common.log import logd, loge
from ..db.internet_share_db import internet_share_db
from LinkShare.core.internet_share_services import internet_share_service

from Common.log import set_file_tag; set_file_tag("WEB")

def handle_customer_request_use(request, shared_sessions, get_client_identity, get_client_session, append_usage_log = None):        
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    token, token_id, client_ip, device_name = get_client_identity()

    rates_config = InternetRatesConfig()
    current_fares = rates_config.get_internet_fares()
    fare_map = {int(item['minutes']): item for item in current_fares}
    allowed_minutes = set(fare_map)

    try:
        minutes = int(request.args.get('min', 60))
    except (TypeError, ValueError) as e:
        return {'msg': 'Invalid usage time.'}, 400
        
    if minutes not in allowed_minutes:
        return {'msg': 'Select one of the available usage times.'}, 400

    price = fare_map[minutes]['price']
    dur_str = f"{minutes} Min Pass ({price:g} PHP)" if minutes < 60 else f"{minutes//60} Hour Pass ({price:g} PHP)"
    
    # client_token_id 기준 고유 활성 사용자 수 집계
    active_sessions = internet_share_db.load(view_type="CONNECTED")
    unique_active_tokens = {session.get('client_token_id') for session in active_sessions if session.get('client_token_id')}
    active_connection_count = len(unique_active_tokens)
    
    hotspot_config = HotspotNetworkConfig()
    max_conn = hotspot_config.get('max_connections')
    win_limit = hotspot_config.get('windows_hotspot_limit')
    effective_max = min(max_conn, win_limit)

    is_token_active = token_id in unique_active_tokens

    logd(f"[CustomerRequest] is_token_active={is_token_active}, 현재={active_connection_count}, 최대허용={effective_max}")
    if not is_token_active and active_connection_count >= effective_max:
        logd(f"[CustomerRequest] 최대 연결 제한 초과 (Full): is_token_active={is_token_active}, 현재={active_connection_count}, 최대허용={effective_max}")
        return {
            'msg': 'Maximum connection limit reached. Please try again later.',
            'status': 'Full',
            'current': active_connection_count,
            'maximum': effective_max,
        }, 429

    record_item = {
        "user_id": None,
        "user_name": None,
        "device_mac": "",
        "client_ip": client_ip,
        "client_token_id": token_id,  # 토큰 ID로 관리
        "device_name": device_name or "Unknown Device",
        "minutes": minutes,
        "price": price,
        "currency": "PHP",
        "request_time": now_str
    }

    # 서비스 레이어를 통한 신규 요청 생성 일원화
    res, status_code = internet_share_service.create_request(record_item)
    if status_code != 200:
        return res, status_code

    return {
        'status': 'Pending',
        'msg': f"[{dur_str}] Approval request sent. Please pay at the counter.",
        'request_data': record_item
    }
