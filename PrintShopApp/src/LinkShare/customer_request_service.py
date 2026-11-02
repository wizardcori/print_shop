"""LinkShare customer internet-request workflow."""
import datetime
import threading
def customer_request(request, runtime_settings, shared_sessions, get_client_identity, get_client_session, append_usage_log, signals, apply_client_metadata, default_internet_fares):
    fare_map = {int(item['minutes']): item for item in runtime_settings.get('internet_fares', default_internet_fares)}
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

    active_statuses = {'Pending', 'Approved'}
    active_count = sum(
        1 for session in shared_sessions.values()
        if session.get('status') in active_statuses
    )
    existing_session = shared_sessions.get(client_ip)
    if existing_session is None and active_count >= runtime_settings['max_connections']:
        return {
            'msg': 'Maximum connection limit reached. Please try again later.',
            'status': 'Full',
            'current': active_count,
            'maximum': runtime_settings['max_connections'],
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

