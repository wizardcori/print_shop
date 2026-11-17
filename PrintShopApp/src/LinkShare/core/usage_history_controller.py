"""LinkShare usage-history table rendering."""
import datetime
from PySide6.QtWidgets import QTableWidgetItem

def update_usage_history_tables(window, usage_history, shared_sessions, get_record_price):
    if not hasattr(window, 'usage_history_tables'):
        return

    def deduplicate_events(records):
        unique = {}
        for record in records:
            identity = record.get('client_token_id') or f"ip:{record.get('client_ip', '-')}"
            event_key = (
                identity,
                record.get('log_type', ''),
                record.get('request_time', ''),
                record.get('approval_time', ''),
                record.get('completed_time', ''),
                record.get('requested_minutes', ''),
                record.get('usage_approval', ''),
            )
            unique[event_key] = record
        return list(unique.values())

    # 1. 현재 화면(UI)의 필터 위젯에서 직접 최신 값 읽기
    filter_name = "All"
    if hasattr(window, 'internet_share_filter'):
        filter_name = window.internet_share_filter.currentText()
        
    start_text = ""
    if hasattr(window, 'internet_share_start'):
        start_text = window.internet_share_start.text().strip()
        
    end_text = ""
    if hasattr(window, 'internet_share_end'):
        end_text = window.internet_share_end.text().strip()

    # 2. 날짜(YYYY-MM-DD)만 추출하여 안전하게 비교하는 필터 함수
    def matches_date_filter(record, date_field_keys):
        if filter_name in ('All', '전체') or (not start_text and not end_text):
            return True

        raw_date = ''
        for key in date_field_keys:
            val = record.get(key, '')
            if val:
                raw_date = str(val)[:10]
                break

        if not raw_date:
            return False

        try:
            target_date = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
            start_date = datetime.datetime.strptime(start_text, '%Y-%m-%d').date() if start_text else None
            end_date = datetime.datetime.strptime(end_text, '%Y-%m-%d').date() if end_text else None

            if start_date and end_date:
                return start_date <= target_date <= end_date
            elif start_date:
                return target_date >= start_date
            elif end_date:
                return target_date <= end_date
        except ValueError:
            return False

        return True

    # ==========================================
    # 🎯 [탭별 맞춤형 날짜 필터링 적용]
    # ==========================================

    # 1. Connection Status 탭: request_time, start_time 기준
    filtered_conn_history = [r for r in usage_history if matches_date_filter(r, ['request_time', 'start_time'])]

    # 2. Usage Requests 탭: request_time 기준
    req_raw = [r for r in usage_history if r.get('log_type') == 'request']
    filtered_req = [r for r in deduplicate_events(req_raw) if matches_date_filter(r, ['request_time'])]

    # 3. Usage Approvals 탭: approval_time, request_time 기준
    appr_raw = [r for r in usage_history if r.get('log_type') == 'approval']
    filtered_appr = [r for r in deduplicate_events(appr_raw) if matches_date_filter(r, ['approval_time', 'request_time'])]

    # 4. Usage History 탭: approval_time, request_time, completed_time 기준
    hist_raw = list(reversed(deduplicate_events(usage_history)))
    filtered_hist = [r for r in hist_raw if matches_date_filter(r, ['approval_time', 'request_time', 'completed_time'])]

    approved_history = [r for r in filtered_hist if r.get('log_type') == 'approval' and
                        str(r.get('usage_approval', '')).startswith('Approved')]

    # 누적 시간 및 금액 계산
    total_minutes = sum(int(r.get('requested_minutes', 0)) for r in approved_history)
    total_amount = sum(get_record_price(r) for r in approved_history)
    if hasattr(window, 'internet_share_total_label'):
        window.internet_share_total_label.setText(
            f'사용시간 누적: {total_minutes}분                         금액 누적: {total_amount:g} PHP'
        )

    # 클라이언트별 누적 시간 계산
    requested_seconds_by_client = {}
    for record in usage_history:
        client_ip = record.get('client_ip', '-')
        if record.get('log_type') == 'request':
            requested_seconds_by_client[client_ip] = requested_seconds_by_client.get(client_ip, 0) + (
                int(record.get('requested_minutes', 0)) * 60
            )

    # Connection Status 클라이언트 최신화 및 실시간 세션 병합 (날짜 필터를 통과한 항목만 허용)
    latest_by_client = {}
    for record in filtered_conn_history:
        client_ip = record.get('client_ip', '-')
        identity_key = record.get('client_token_id') or f'ip:{client_ip}'
        previous = latest_by_client.get(identity_key)
        if previous is None or str(record.get('last_seen', record.get('request_time', ''))) >= str(
            previous.get('last_seen', previous.get('request_time', ''))
        ):
            latest_by_client[identity_key] = record
            
    for client_ip, session in shared_sessions.items():
        if matches_date_filter(session, ['request_time', 'start_time']):
            identity_key = session.get('client_token_id') or f'ip:{client_ip}'
            latest_by_client[identity_key] = session

    filtered_connection_records = [
        r for r in latest_by_client.values() 
        if matches_date_filter(r, ['request_time', 'start_time'])
    ]

    # 최종 테이블 매핑 구조 생성
    table_records = {
        'Connection Status': (filtered_connection_records, [
            'connection_status', 'usage_approval', 'internet_status',
            'request_time', 'start_time', 'end_time', 'total_requested', 'remaining', 'client_ip', 'client_token_id', 'user_info'
        ]),
        'Usage Requests': (filtered_req, [
            'usage_request', 'request_time', 'client_ip', 'client_token_id', 'user_info'
        ]),
        'Usage Approvals': (filtered_appr, [
            'usage_approval', 'approval_time', 'requested_time', 'client_ip', 'client_token_id', 'user_info'
        ]),
        'Usage History': (approved_history, [
            'request_time', 'approval_time', 'requested_time', 'requested_price', 'client_token_id', 'user_info'
        ])
    }

    # 렌더링 루프
    for tab_name, (records, fields) in table_records.items():
        if tab_name not in window.usage_history_tables:
            continue
        table = window.usage_history_tables[tab_name]
        table.setRowCount(len(records))
        for row, record in enumerate(reversed(records)):
            remaining = record.get('remaining_seconds', 0)
            if record.get('status') == 'Approved' and remaining > 0:
                minutes, seconds = divmod(remaining, 60)
                remaining_text = f'{minutes:02d} min {seconds:02d} sec'
            else:
                remaining_text = '-'
                
            total_requested = requested_seconds_by_client.get(record.get('client_ip', '-'), 0)
            requested_minutes, requested_seconds = divmod(total_requested, 60)
            requested_hours, requested_minutes = divmod(requested_minutes, 60)
            total_requested_text = (
                f'{requested_hours} hr {requested_minutes:02d} min'
                if requested_hours else f'{requested_minutes} min'
            )
            
            values = {
                'log_type': record.get('log_type', '-'),
                'status': record.get('status', '-'),
                'completed_time': record.get('completed_time', '-'),
                'connection_status': record.get('connection_status', '-'),
                'internet_status': record.get('internet_status', 'Checking'),
                'usage_request': record.get('usage_request', record.get('fare', '-')),
                'usage_approval': record.get('usage_approval', '-'),
                'request_time': record.get('request_time', '-'),
                'approval_time': record.get('approval_time', '-'),
                'requested_time': (
                    f"{record.get('requested_minutes', 0)} min"
                    if record.get('requested_minutes') else record.get('usage_request', '-')
                ),
                'requested_price': f"{get_record_price(record):g} PHP",
                'user_info': (
                    f"{record.get('device_name', 'Unknown Device')} / "
                    f"{record.get('device_type', 'Unknown')} / "
                    f"{record.get('browser', 'Unknown')} / {record.get('client_ip', '-')}"
                ),
                'start_time': record.get('start_time', '-'),
                'end_time': record.get('end_time', '-'),
                'total_requested': total_requested_text,
                'remaining': remaining_text,
                'client_ip': record.get('client_ip', '-'),
                'client_token_id': record.get('client_token_id', '-') or '-',
            }
            
            legacy_status_labels = {
                '종료': 'Closed',
                '사용 가능': 'Available',
                '확인 중': 'Checking',
                '확인 실패': 'Check failed',
                '승인대기': 'Pending Approval',
                '허가': 'Approved',
                '거부': 'Rejected',
                '알 수 없는 기기': 'Unknown Device',
            }
            values = {
                key: legacy_status_labels.get(str(value), value)
                for key, value in values.items()
            }
            
            for column, field in enumerate(fields):
                table.setItem(row, column, QTableWidgetItem(str(values[field])))