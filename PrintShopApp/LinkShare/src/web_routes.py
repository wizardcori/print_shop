"""LinkShare browser routes and session state service."""

import datetime
import hashlib
import ipaddress
import json
import re
import secrets
import sqlite3
import subprocess
import socketserver

from flask import Response, make_response, redirect, render_template, request
from Common.globals import CONFIG_ENCODING

from LinkShare.src.client_identity_service import get_client_identity as resolve_client_identity
from LinkShare.src.customer_request_service import customer_request as handle_customer_request


class LinkShareWebService:
    """Own the LinkShare portal routes and browser-session state helpers."""

    def __init__(
        self,
        *,
        client_cookie_name,
        client_identity_map,
        client_metadata_map,
        shared_sessions,
        session_identity_lock,
        usage_history,
        status_condition,
        runtime_settings,
        app_database,
        signals,
        default_status_poll_interval,
        default_internet_fares,
    ):
        self.client_cookie_name = client_cookie_name
        self.client_identity_map = client_identity_map
        self.client_metadata_map = client_metadata_map
        self.shared_sessions = shared_sessions
        self.session_identity_lock = session_identity_lock
        self.usage_history = usage_history
        self.status_condition = status_condition
        self.runtime_settings = runtime_settings
        self.app_database = app_database
        self.signals = signals
        self.default_status_poll_interval = default_status_poll_interval
        self.default_internet_fares = default_internet_fares

    def get_client_identity(self):
        return resolve_client_identity(
            request,
            self.client_cookie_name,
            self.client_identity_map,
            self.shared_sessions,
            self.session_identity_lock,
            self.client_metadata_map,
            secrets,
            datetime,
            hashlib,
        )

    def identity_response(self, payload, token):
        response = make_response(payload)
        response.set_cookie(
            self.client_cookie_name,
            token,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite='Lax',
        )
        return response

    def apply_client_metadata(self, session, token_id):
        """Copy browser-supplied automatic metadata into a session record."""
        metadata = self.client_metadata_map.get(token_id, {})
        for key, value in metadata.items():
            if value:
                session[key] = value
        session.setdefault('first_seen', metadata.get('last_seen', ''))
        session['last_seen'] = metadata.get('last_seen', session.get('last_seen', ''))

    def append_usage_log(self, log_type, session, **overrides):
        """Append an immutable request/approval event to usage history."""
        record = dict(session)
        record.update(overrides)
        record['log_type'] = log_type
        self.usage_history.append(record)
        try:
            self.app_database.save_event(record)
            self.app_database.save_session(session)
        except (OSError, sqlite3.Error):
            pass
        try:
            from Common.logger_service import log_event
            log_event('linkshare', 'USAGE', f"Session event [{log_type}]: IP={record.get('ip')} device={record.get('device_name')} status={record.get('status')} minutes={record.get('remaining_minutes') or record.get('requested_minutes')}")
        except Exception:
            pass

    def get_record_price(self, record):
        """Return the price fixed at approval time, with a legacy fare fallback."""
        value = record.get('approved_price')
        if value is None:
            value = record.get('requested_price')
        try:
            if value is not None and float(value) > 0:
                return float(value)
        except (TypeError, ValueError):
            pass
        match = re.search(r'\(([0-9]+(?:\.[0-9]+)?)\s*PHP\)', str(record.get('fare', '')))
        return float(match.group(1)) if match else 0.0

    def is_client_internet_approved(self, client_ip):
        """Return whether a client currently has an active approved session."""
        session = self.shared_sessions.get(client_ip)
        if not session or session.get('status') != 'Approved':
            return False
        end_timestamp = session.get('end_timestamp', 0)
        if end_timestamp and end_timestamp <= datetime.datetime.now().timestamp():
            session['status'] = 'Expired'
            session['connection_status'] = 'Closed'
            session['remaining_seconds'] = 0
            return False
        return True

    def get_upstream_dns_servers(self):
        fallback_servers = ['1.1.1.1', '8.8.8.8']
        try:
            command = (
                "(Get-DnsClientServerAddress -AddressFamily IPv4).ServerAddresses "
                "| ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                capture_output=True,
                text=True,
                encoding=CONFIG_ENCODING,
                errors='replace',
                timeout=2,
            )
            values = json.loads((result.stdout or '').strip())
            if isinstance(values, str):
                values = [values]
            configured = []
            for value in values if isinstance(values, list) else []:
                try:
                    address = str(ipaddress.ip_address(value))
                except ValueError:
                    continue
                if address != '0.0.0.0' and address not in configured:
                    configured.append(address)
            return configured or fallback_servers
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            return fallback_servers

    def get_client_session(self, client_ip):
        """Return a browser-safe, current snapshot of one client session."""
        session = self.shared_sessions.get(client_ip)
        if not session:
            return {'status': 'None'}

        snapshot = dict(session)
        if snapshot.get('status') == 'Approved':
            remaining = max(
                0,
                int(snapshot.get('end_timestamp', 0) - datetime.datetime.now().timestamp()),
            )
            snapshot['remaining_seconds'] = remaining
            if remaining == 0:
                snapshot['status'] = 'Expired'
                session['status'] = 'Expired'
        snapshot.pop('end_timestamp', None)
        return snapshot

    def notify_status_change(self):
        with self.status_condition:
            self.status_condition.notify_all()

    @staticmethod
    def session_status_signature(session):
        return tuple(session.get(key) for key in (
            'status', 'approval_time', 'end_time', 'remaining_seconds', 'internet_status'
        ))

    def register_routes(self, web_app):
        service = self
        self.web_app = web_app

        @web_app.route('/')
        def portal_root():
            return redirect('/scan')

        @web_app.route('/scan')
        def customer_scan():
            token, _token_id, _client_ip, _device_name = service.get_client_identity()
            response = make_response(render_template(
                'portal.html',
                status_poll_interval=service.runtime_settings.get(
                    'status_poll_interval', service.default_status_poll_interval
                ),
                internet_fares=service.runtime_settings.get(
                    'internet_fares', service.default_internet_fares
                ),
            ))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.set_cookie(
                service.client_cookie_name,
                token,
                max_age=60 * 60 * 24 * 30,
                httponly=True,
                samesite='Lax',
            )
            return response

        @web_app.route('/manifest.webmanifest')
        def app_manifest():
            return Response(json.dumps({
                'name': 'Internet Access Request',
                'short_name': 'Access Request',
                'start_url': '/scan',
                'display': 'standalone',
                'background_color': '#f3f6f8',
                'theme_color': '#1565c0',
                'icons': [{
                    'src': '/app-icon.svg',
                    'sizes': 'any',
                    'type': 'image/svg+xml',
                    'purpose': 'any maskable',
                }],
            }, ensure_ascii=False), mimetype='application/manifest+json')

        @web_app.route('/app-icon.svg')
        @web_app.route('/favicon.ico')
        def app_icon():
            return Response('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
      <rect width="512" height="512" rx="96" fill="#1565c0"/>
      <path d="M128 176h256v160H128z" fill="#fff"/>
      <path d="M176 144c64-64 96-64 160 0M208 112c40-40 56-40 96 0" fill="none" stroke="#fff" stroke-width="24" stroke-linecap="round"/>
      <circle cx="256" cy="256" r="28" fill="#1565c0"/>
    </svg>''', mimetype='image/svg+xml')

        @web_app.route('/request')
        def customer_request():
            return handle_customer_request(
                request,
                service.runtime_settings,
                service.shared_sessions,
                service.get_client_identity,
                service.get_client_session,
                service.append_usage_log,
                service.signals,
                service.apply_client_metadata,
                service.default_internet_fares,
            )

        @web_app.route('/status')
        def get_status():
            wait_for_change = request.args.get('wait') == '1'
            token, token_id, client_ip, device_name = service.get_client_identity()
            session = service.shared_sessions.get(client_ip)
            if session:
                session['last_seen'] = datetime.datetime.now().isoformat(timespec='seconds')
                session['client_token_id'] = token_id
                service.apply_client_metadata(session, token_id)
                if device_name:
                    session['device_name'] = device_name
            if wait_for_change:
                with service.status_condition:
                    before = service.session_status_signature(
                        service.shared_sessions.get(client_ip, {})
                    )
                    service.status_condition.wait_for(
                        lambda: service.session_status_signature(
                            service.shared_sessions.get(client_ip, {})
                        ) != before,
                        timeout=30,
                    )
            return service.identity_response(service.get_client_session(client_ip), token)

        @web_app.route('/internet-status', methods=['GET', 'POST'])
        def report_internet_status():
            token, token_id, client_ip, device_name = service.get_client_identity()
            session = service.shared_sessions.get(client_ip)
            if not session:
                return service.identity_response({'status': 'None'}, token), 404
            session['last_seen'] = datetime.datetime.now().isoformat(timespec='seconds')
            session['client_token_id'] = token_id
            service.apply_client_metadata(session, token_id)
            if device_name:
                session['device_name'] = device_name
            payload = request.get_json(silent=True) or {}
            if request.method == 'GET':
                payload = request.args.to_dict()
                if payload.get('browser_online') is not None:
                    payload['browser_online'] = payload['browser_online'].lower() == 'true'
                if payload.get('internet_check'):
                    try:
                        payload['internet_check'] = json.loads(payload['internet_check'])
                    except (TypeError, json.JSONDecodeError):
                        payload['internet_check'] = {'raw': str(payload['internet_check'])[:200]}
            internet_status = payload.get('internet_status')
            if isinstance(payload.get('internet_check'), dict):
                session['internet_check'] = dict(payload['internet_check'])
            if 'browser_online' in payload:
                session['browser_online'] = bool(payload['browser_online'])
            if payload.get('checked_at'):
                session['internet_checked_at'] = str(payload['checked_at'])[:80]
            if payload.get('test_result'):
                session['internet_test_result'] = str(payload['test_result'])[:20]
            try:
                service.app_database.save_session(session)
            except (OSError, sqlite3.Error):
                pass
            if internet_status in ('Checking', 'Available', 'Check failed', '확인 중', '사용 가능', '확인 실패'):
                if session.get('internet_status') != internet_status:
                    session['internet_status'] = internet_status
                    service.notify_status_change()
            return {'status': session.get('internet_status', 'Checking')}

        return web_app

    def run_server(self):
        """Run the LinkShare Flask server in the host-created worker thread."""
        socketserver.TCPServer.allow_reuse_address = True
        self.web_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
