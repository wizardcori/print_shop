"""LinkShare browser routes and session state service (Direct DB Integration Applied)."""

import datetime
import hashlib
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
from waitress import serve

from flask import Flask, Response, make_response, redirect, render_template_string, request
from Common.globals import CONFIG_ENCODING
from Common.log import logd, loge

# 👉 외부 파일에 있는 HtmlLoader 임포트 (경로는 실제 파일 위치에 맞게 수정해주세요)
from Common.html_loader import HtmlLoader

from LinkShare.linkshare_signals import LinkShareServerSignals
from LinkShare.core.client_identity_service import get_client_identity as resolve_client_identity
from LinkShare.core.customer_request_service import handle_customer_request
from LinkShare.db.internet_share_session_db import InternetShareSessionDatabase
from LinkShare.db.internet_share_usage_db import InternetShareUsageDatabase
from LinkShare.setting.internet_rates_settings import InternetRatesConfig
from LinkShare.setting.linkshare_settings import LinkshareConfig

# 설정값 상수 정의
INTERNET_PORTAL_SERVICE_IP = '0.0.0.0'
INTERNET_PORTAL_SERVICE_PORT = 8081

# 외부에서 임포트한 HtmlLoader를 사용하여 모듈 로드 시점에 portal.html 로드
internet_portal_html_content = HtmlLoader(__file__, 'templates/internet_portal.html')


class LinkShareWebService:
    """Own the LinkShare portal routes and browser-session state helpers using direct DB repositories."""

    def __init__(
        self,
        *,
        client_identity_map,
        client_metadata_map,
        session_identity_lock,
        status_condition,
        signals,
    ):
        self.internet_share_client_cookie = LinkshareConfig().get('internet_share_client_cookie')
        self.client_identity_map = client_identity_map
        self.client_metadata_map = client_metadata_map
        self.session_identity_lock = session_identity_lock
        self.status_condition = status_condition
        self.signals = signals
        self.internet_share_status_poll_interval = LinkshareConfig().get('internet_share_status_poll_interval')

        # 데이터베이스 리포지토리 직접 초기화
        self.session_db = InternetShareSessionDatabase()
        self.usage_db = InternetShareUsageDatabase()

    def get_client_identity(self):
        shared_sessions = self.session_db.load_sessions()
        return resolve_client_identity(
            request,
            self.internet_share_client_cookie,
            self.client_identity_map,
            shared_sessions,
            self.session_identity_lock,
            self.client_metadata_map,
            secrets,
            datetime,
            hashlib,
        )

    def identity_response(self, payload, token):
        response = make_response(payload)
        response.set_cookie(
            self.internet_share_client_cookie,
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
        """Append an immutable request/approval event directly to usage and session DBs."""
        record = dict(session)
        record.update(overrides)
        record['log_type'] = log_type
        
        try:
            self.usage_db.save_event(record)
            self.session_db.save_session(session)
        except (OSError, sqlite3.Error):
            pass

        try:
            from Common.logger_service import log_event
            log_event('linkshare', 'USAGE', f"Session event [{log_type}]: IP={record.get('ip')} device={record.get('device_name')} status={record.get('status')} minutes={record.get('remaining_minutes') or record.get('requested_minutes')}")
        except Exception:
            pass

    def is_client_internet_approved(self, client_ip):
        """Return whether a client currently has an active approved session from DB."""
        sessions = self.session_db.load_sessions()
        session = sessions.get(client_ip)
        if not session or session.get('status') != 'Approved':
            return False
        end_timestamp = session.get('end_timestamp', 0)
        if end_timestamp and end_timestamp <= datetime.datetime.now().timestamp():
            session['status'] = 'Expired'
            session['connection_status'] = 'Closed'
            session['remaining_seconds'] = 0
            self.session_db.save_session(session)
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
        """Return a browser-safe, current snapshot of one client session from DB."""
        sessions = self.session_db.load_sessions()
        session = sessions.get(client_ip)
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
                self.session_db.save_session(session)
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
            current_fares = InternetRatesConfig().get_internet_fares()

            response = make_response(render_template_string(
                internet_portal_html_content,
                status_poll_interval=service.internet_share_status_poll_interval,
                internet_fares=current_fares
            ))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.set_cookie(
                service.internet_share_client_cookie,
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
            current_sessions = service.session_db.load_sessions()
            return handle_customer_request(
                request,
                current_sessions,
                service.get_client_identity,
                service.get_client_session,
                service.append_usage_log,
                service.signals,
                service.apply_client_metadata
            )

        @web_app.route('/status')
        def get_status():
            wait_for_change = request.args.get('wait') == '1'
            token, token_id, client_ip, device_name = service.get_client_identity()
            
            sessions = service.session_db.load_sessions()
            session = sessions.get(client_ip)
            if session:
                session['last_seen'] = datetime.datetime.now().isoformat(timespec='seconds')
                session['client_token_id'] = token_id
                service.apply_client_metadata(session, token_id)
                if device_name:
                    session['device_name'] = device_name
                service.session_db.save_session(session)

            if wait_for_change:
                with service.status_condition:
                    before = service.session_status_signature(
                        service.session_db.load_sessions().get(client_ip, {})
                    )
                    service.status_condition.wait_for(
                        lambda: service.session_status_signature(
                            service.session_db.load_sessions().get(client_ip, {})
                        ) != before,
                        timeout=30,
                    )
            return service.identity_response(service.get_client_session(client_ip), token)

        @web_app.route('/internet-status', methods=['GET', 'POST'])
        def report_internet_status():
            token, token_id, client_ip, device_name = service.get_client_identity()
            
            sessions = service.session_db.load_sessions()
            session = sessions.get(client_ip)
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
                service.session_db.save_session(session)
            except (OSError, sqlite3.Error):
                pass
                
            if internet_status in ('Checking', 'Available', 'Check failed', '확인 중', '사용 가능', '확인 실패'):
                if session.get('internet_status') != internet_status:
                    session['internet_status'] = internet_status
                    service.session_db.save_session(session)
                    service.notify_status_change()
            return {'status': session.get('internet_status', 'Checking')}

        return web_app

    def run_server(self, host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT):
        logd(f"[Server] Waitress 서버 시작 중... (http://{host}:{port})")
        serve(self.web_app, host=host, port=port, threads=8)


class WebServerManager:
    def __init__(self, service_instance=None, host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT, **kwargs):
        self.host = host
        self.port = port
        self.server_thread = None
        self._is_running = False

        if service_instance is None:
            self.service_instance = LinkShareWebService(
                client_identity_map=kwargs.get('client_identity_map', {}),
                client_metadata_map=kwargs.get('client_metadata_map', {}),
                session_identity_lock=kwargs.get('session_identity_lock', threading.Lock()),
                status_condition=kwargs.get('status_condition', threading.Condition()),
                signals=kwargs.get('signals', LinkShareServerSignals())
            )
        else:
            self.service_instance = service_instance

        self.web_app = Flask(__name__)
        self.service_instance.register_routes(self.web_app)
        self.service_instance.web_app = self.web_app

    def start(self):
        if self._is_running:
            return

        def run():
            try:
                self._is_running = True
                self.service_instance.run_server(host=self.host, port=self.port)
            except Exception as e:
                logd(f"[Server] 서버 실행 중 오류 발생: {e}")
            finally:
                self._is_running = False

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

    def stop(self):
        if not self._is_running:
            return
        self._is_running = False

    def status(self):
        return {
            "is_running": self._is_running,
            "host": self.host,
            "port": self.port,
            "url": f"http://{self.host if self.host != '0.0.0.0' else '127.0.0.1'}:{self.port}"
        }


_server_manager_instance = None

def link_share_init_server(service_instance=None, host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT, **kwargs):
    global _server_manager_instance
    logd(f"[Server] [Debug] link_share_init_server 호출됨 (host={host}, port={port})")
    _server_manager_instance = WebServerManager(service_instance, host, port, **kwargs)
    logd(f"[Server] WebServerManager 인스턴스가 새로 생성 및 초기화되었습니다.")

def link_share_start(service_instance=None, host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT, **kwargs):
    global _server_manager_instance
    
    if _server_manager_instance is None:
        logd("[Server] [Debug] _server_manager_instance가 None입니다. 자동으로 초기화(link_share_init_server)를 진행합니다.")
        link_share_init_server(service_instance, host, port, **kwargs)
    else:
        logd("[Server] [Debug] 기존에 생성된 _server_manager_instance를 재사용합니다.")
    
    if _server_manager_instance:
        logd("[Server] 웹 서버 시작 명령을 전달합니다.")
        _server_manager_instance.start()

def link_share_stop():
    global _server_manager_instance
    if _server_manager_instance:
        logd("[Server] 웹 서버 중지 요청이 접수되었습니다.")
        _server_manager_instance.stop()
    else:
        logd("[Server] [Debug] 서버 관리자 인스턴스가 존재하지 않습니다 (None). 중지할 서버가 없습니다.")

def link_share_status():
    global _server_manager_instance
    if _server_manager_instance:
        logd("[Server] [Debug] 서버 관리자 인스턴스가 존재합니다. 상태를 조회합니다.")
        return _server_manager_instance.status()
    
    logd("[Server] [Debug] 서버 관리자 인스턴스가 존재하지 않습니다 (None). 기본 상태(is_running: False)를 반환합니다.")
    return {"is_running": False}