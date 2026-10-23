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

    request_records = deduplicate_events(
        [record for record in usage_history if record.get('log_type') == 'request']
    )
    approval_records = deduplicate_events(
        [record for record in usage_history if record.get('log_type') == 'approval']
    )

    table_records = {
        'Connection Status': (usage_history, [
            'connection_status', 'request_time', 'start_time', 'end_time', 'remaining', 'client_ip', 'client_token_id', 'user_info'
        ]),
        'Usage Requests': (request_records, [
            'usage_request', 'request_time', 'client_ip', 'client_token_id', 'user_info'
        ]),
        'Usage Approvals': (
            approval_records,
            ['usage_approval', 'approval_time', 'requested_time', 'client_ip', 'client_token_id', 'user_info']
        ),
    }
    history_records = list(reversed(deduplicate_events(usage_history)))
    if hasattr(window, 'usage_history_filter'):
        filter_name = window.usage_history_filter.currentText()
        today = datetime.date.today()
        start_text = window.usage_history_start.text().strip()
        end_text = window.usage_history_end.text().strip()
        def history_date(record):
            raw = (record.get('completed_time') or record.get('approval_time') or
                   record.get('request_time') or '')
            try:
                return datetime.datetime.strptime(raw[:10], '%Y-%m-%d').date()
            except ValueError:
                return None
        if filter_name in ('오늘', 'Today'):
            history_records = [r for r in history_records if history_date(r) == today]
        elif filter_name in ('이번 달', 'This month'):
            history_records = [r for r in history_records if history_date(r) and
                               history_date(r).year == today.year and history_date(r).month == today.month]
        elif filter_name in ('기간', 'Custom'):
            try:
                start_date = datetime.datetime.strptime(start_text, '%Y-%m-%d').date()
                end_date = datetime.datetime.strptime(end_text, '%Y-%m-%d').date()
                history_records = [r for r in history_records if history_date(r) and
                                   start_date <= history_date(r) <= end_date]
            except ValueError:
                history_records = []
    table_records['Usage History'] = (history_records, [
        'log_type', 'status', 'request_time', 'approval_time', 'completed_time', 'client_ip'
    ])
    approved_history = [r for r in history_records if r.get('log_type') == 'approval' and
                        str(r.get('usage_approval', '')).startswith('Approved')]
    total_minutes = sum(int(r.get('requested_minutes', 0)) for r in approved_history)
    total_amount = sum(get_record_price(r) for r in approved_history)
    if hasattr(window, 'usage_history_total_label'):
        window.usage_history_total_label.setText(
            f'사용시간 누적: {total_minutes}분                         금액 누적: {total_amount:g} PHP'
        )
    table_records['Usage History'] = (approved_history, [
        'request_time', 'approval_time', 'requested_time', 'requested_price', 'client_token_id', 'user_info'
    ])
    connection_tab_name = next(iter(table_records))
    latest_by_client = {}
    requested_seconds_by_client = {}
    for record in usage_history:
        client_ip = record.get('client_ip', '-')
        identity_key = record.get('client_token_id') or f'ip:{client_ip}'
        previous = latest_by_client.get(identity_key)
        if previous is None or str(record.get('last_seen', record.get('request_time', ''))) >= str(
            previous.get('last_seen', previous.get('request_time', ''))
        ):
            latest_by_client[identity_key] = record
        if record.get('log_type') == 'request':
            requested_seconds_by_client[client_ip] = requested_seconds_by_client.get(client_ip, 0) + (
                int(record.get('requested_minutes', 0)) * 60
            )
    for client_ip, session in shared_sessions.items():
        identity_key = session.get('client_token_id') or f'ip:{client_ip}'
        latest_by_client[identity_key] = session
    table_records[connection_tab_name] = (
        list(latest_by_client.values()),
        ['connection_status', 'usage_approval', 'internet_status',
         'request_time', 'start_time', 'end_time', 'total_requested', 'remaining', 'client_ip', 'client_token_id', 'user_info']
    )

    for tab_name, (records, fields) in table_records.items():
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
                '\uc885\ub8cc': 'Closed',
                '\uc0ac\uc6a9 \uac00\ub2a5': 'Available',
                '\ud655\uc778 \uc911': 'Checking',
                '\ud655\uc778 \uc2e4\ud328': 'Check failed',
                '\uc2b9\uc778\ub300\uae30': 'Pending Approval',
                '\ud5c8\uac00': 'Approved',
                '\uac70\ubd80': 'Rejected',
                '\uc54c \uc218 \uc5c6\ub294 \uae30\uae30': 'Unknown Device',
            }
            values = {
                key: legacy_status_labels.get(str(value), value)
                for key, value in values.items()
            }
            for column, field in enumerate(fields):
                table.setItem(row, column, QTableWidgetItem(str(values[field])))

