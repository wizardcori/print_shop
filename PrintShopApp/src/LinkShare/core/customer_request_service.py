"""LinkShare customer internet-request workflow."""
import datetime
import threading
from LinkShare.setting.hotspot_settings import HotspotNetworkConfig
from LinkShare.setting.internet_rates_settings import InternetRatesConfig


def handle_customer_request(request, shared_sessions, get_client_identity, get_client_session, append_usage_log, signals, apply_client_metadata):
    # 1. InternetRatesConfig를 직접 이용하여 활성화된 실시간 요금표 동적 조회[cite: 2]
    rates_config = InternetRatesConfig()
    current_fares = rates_config.get_internet_fares()

    fare_map = {int(item['minutes']): item for item in current_fares}

    allowed_minutes = set(fare_map)
    try:
        minutes = int(request.args.get('min', 60))
    except (TypeError, ValueError):
        return {'msg': 'Invalid usage time.'}, 400
    if minutes not in allowed_minutes:
        return {'msg': 'Select one of the available usage times.'}, 400

    token, token_id, client_ip, device_name = get_client_identity()
    fare = fare_map[minutes]['price']
    dur_str = f"{minutes} Min Pass ({fare:g} PHP)" if minutes < 60 else f"{minutes//60} Hour Pass ({fare:g} PHP)"
    
    existing_session = shared_sessions.get(client_ip)
    if existing_session:
        existing_status = get_client_session(client_ip).get('status')
        if existing_status == 'Approved':
            if existing_session.get('extension_pending'):
                return {
                    'status': 'Pending',
                    'msg': 'Your additional usage request is waiting for approval.',
                    'session': get_client_session(client_ip),
                }
            existing_session.update({
                'extension_pending': True,
                'extension_minutes': minutes,
                'extension_fare': dur_str,
                'extension_price': fare,
                'extension_request_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            })
            append_usage_log(
                'request',
                existing_session,
                status='Pending',
                requested_minutes=minutes,
                fare=dur_str,
                usage_request=dur_str,
                usage_approval='-',
                request_time=existing_session['extension_request_time'],
                approval_time='-',
                start_time='-',
                end_time='-',
            )
            threading.Thread(
                target=signals.approval_requested.emit,
                args=(client_ip, minutes, dur_str),
                daemon=True,
            ).start()
            return {
                'status': 'Pending',
                'msg': f"[{dur_str}] Additional usage request sent for approval.",
                'session': get_client_session(client_ip),
            }
        if existing_status == 'Pending':
            return {
                'status': 'Pending',
                'msg': 'Your previous request is waiting for approval.',
                'session': get_client_session(client_ip),
            }

    # 2. 활성 상태('Pending', 'Approved')인 연결의 총합 계산
    active_statuses = {'Pending', 'Approved'}
    active_connection_count = sum(
        1 for session in shared_sessions.values()
        if session.get('status') in active_statuses
    )
    
    # 3. HotspotNetworkConfig를 직접 이용하여 max_connections와 windows_hotspot_limit 조회 후 작은 값 적용[cite: 3]
    hotspot_config = HotspotNetworkConfig()
    max_conn = hotspot_config.get('max_connections')
    win_limit = hotspot_config.get('windows_hotspot_limit')
    effective_max = min(max_conn, win_limit)

    # 4. 실효 제한 값을 초과하면 429 에러 처리
    existing_session = shared_sessions.get(client_ip)
    if existing_session is None and active_connection_count >= effective_max:
        return {
            'msg': 'Maximum connection limit reached (restricted by hotspot configuration/Windows limit). Please try again later.',
            'status': 'Full',
            'current': active_connection_count,
            'maximum': effective_max,
        }, 429

    session_record = {
        'status': 'Pending',
        'requested_minutes': minutes,
        'requested_price': fare,
        'approved_price': None,
        'fare': dur_str,
        'client_ip': client_ip,
        'client_token_id': token_id,
        'device_name': device_name or 'Unknown Device',
        'last_seen': datetime.datetime.now().isoformat(timespec='seconds'),
        'connection_status': '연결됨',
        'usage_request': dur_str,
        'usage_approval': 'Pending Approval',
        'request_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'approval_time': '-',
        'start_time': '-',
        'end_time': '-',
        'internet_status': 'Checking',
        'total_used_seconds': 0,
    }
    apply_client_metadata(session_record, token_id)
    shared_sessions[client_ip] = session_record
    append_usage_log('request', session_record)
    threading.Thread(
        target=signals.approval_requested.emit,
        args=(client_ip, minutes, dur_str),
        daemon=True,
    ).start()
    return {
        'status': 'Pending',
        'msg': f"[{dur_str}] Approval request sent. Please pay at the counter.",
        'session': get_client_session(client_ip),
    }