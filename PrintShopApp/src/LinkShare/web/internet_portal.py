"""
[모듈 개요]
LinkShare 브라우저 라우트 및 세션 상태 관리 웹 서비스 모듈 (Flask / Waitress 기반).
Session 패키지 및 InternetShareService를 활용하여 서비스 레이어와 통합 제어합니다.
"""

import datetime
import ipaddress
import json
import os
import re
import subprocess
import threading
from waitress import serve

from Common.log import set_file_tag ;set_file_tag("WEB")

from flask import Flask, Response, make_response, redirect, render_template_string, request
from Common.globals import CONFIG_ENCODING
from Common.log import logd, loge
from Common.html_loader import HtmlLoader

from LinkShare.linkshare_signals import LinkShareServerSignals
from LinkShare.core.customer_request_use_service import handle_customer_request_use
from LinkShare.core.customer_request_cancel_service import handle_customer_request_cancel

from LinkShare.setting.internet_rates_settings import InternetRatesConfig
from LinkShare.setting.linkshare_settings import LinkshareConfig

# 서비스 레이어 임포트
from LinkShare.core.internet_share_services import internet_share_service

# 새로 구성한 Session 패키지 임포트
from Session import SessionManager

from ..db.internet_share_db import internet_share_db

# 설정값 상수 정의
INTERNET_PORTAL_SERVICE_IP = '0.0.0.0'
INTERNET_PORTAL_SERVICE_PORT = 8081

# 모듈 로드 시점에 portal.html 로드
internet_portal_html_content = HtmlLoader(__file__, 'templates/internet_portal.html')


class LinkShareWebService:
    """SessionManager 및 InternetShareService를 활용하여 라우트 등록 및 브라우저 세션 상태를 관리하는 웹 서비스 클래스."""

    def __init__(
        self,
        *,
        client_identity_map,
        client_metadata_map,
        session_identity_lock=None,
        status_condition=None,
        signals=None,
    ):
        self.internet_share_client_cookie = LinkshareConfig().get('internet_share_client_cookie')
        self.signals = signals or LinkShareServerSignals()
        self.internet_share_status_poll_interval = LinkshareConfig().get('internet_share_status_poll_interval')

        # 통합 세션 관리자 초기화
        self.session_manager = SessionManager(
            cookie_name=self.internet_share_client_cookie,
            client_identity_map=client_identity_map,
            client_metadata_map=client_metadata_map
        )
        
        if session_identity_lock:
            self.session_manager.session_identity_lock = session_identity_lock
            self.session_manager.context.session_identity_lock = session_identity_lock
        if status_condition:
            self.session_manager.status_condition = status_condition

        self.context = self.session_manager.context
        self.repository = self.session_manager.repository

        logd("[LinkShareWebService] SessionManager 코어 기반 세션 서비스 초기화 완료")

    def get_client_identity(self):
        """SessionContext를 통해 현재 요청의 클라이언트 식별자를 가져옵니다."""
        shared_sessions = self.repository.load_sessions()
        return self.context.resolve_identity(request, shared_sessions)

    def identity_response(self, payload, token):
        """식별 쿠키가 포함된 HTTP 응답을 생성합니다."""
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
        """SessionContext로 메타데이터 반영 위임."""
        self.context.apply_metadata(session, token_id)

    def append_usage_log(self, log_type, session, **overrides):
        """사용 로그 및 세션 상태를 DB에 직접 저장합니다."""
        record = dict(session)
        record.update(overrides)
        record['log_type'] = log_type
        
        try:
            self.repository.save_session(session)
            logd(f"[WebService] 사용 로그 및 세션 저장 성공: 타입={log_type}, IP={record.get('client_ip')}")
        except (OSError, sqlite3.Error) as e:
            loge(f"[WebService] 사용 로그 및 세션 저장 중 DB 오류 발생: {e}")

        try:
            from Common.logger_service import log_event
            log_event('linkshare', 'USAGE', f"Session event [{log_type}]: IP={record.get('ip')} device={record.get('device_name')} status={record.get('status')} minutes={record.get('remaining_minutes') or record.get('requested_minutes')}")
        except Exception as e:
            loge(f"[WebService] 외부 로거 이벤트 기록 오류: {e}")

    def is_client_internet_approved(self, client_ip):
        """클라이언트의 인터넷 승인 세션 유효성을 검증합니다."""
        sessions = self.repository.load_sessions()
        session = sessions.get(client_ip)
        if not session or session.get('status') != 'Approved':
            return False
        end_timestamp = session.get('end_timestamp', 0)
        if end_timestamp and end_timestamp <= datetime.datetime.now().timestamp():
            logd(f"[WebService] 세션 시간 만료 감지: IP={client_ip}")
            session['status'] = 'Expired'
            session['connection_status'] = 'Closed'
            session['remaining_seconds'] = 0
            self.repository.save_session(session)
            return False
        return True

    def get_client_session(self, client_ip):
        """Return a browser-safe, current snapshot of client session(s) from internet_share_db, calculating start/end times by id."""
        db = internet_share_db
        all_records = db.load(view_type="ALL")
        
        active_recs = []
        current_time = datetime.datetime.now()
        current_timestamp = current_time.timestamp()

        for req in all_records:
            if req.get("client_ip") == client_ip:
                status = req.get("overall_status") or req.get("status")
                cancel_status = req.get("cancel_status", "NORMAL")
                if cancel_status == 'CANCELLED' or status in ('CANCELLED', 'REJECTED', 'EXPIRED'):
                    continue
                if status in ('ACTIVE', 'APPROVED', 'QUEUED'):
                    expires_at = req.get("expires_at")
                    if expires_at:
                        try:
                            exp_ts = datetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").timestamp()
                            if exp_ts > current_timestamp:
                                active_recs.append(req)
                        except ValueError:
                            pass
                    else:
                        active_recs.append(req)

        if not active_recs:
            return {'status': 'None'}

        active_recs.sort(key=lambda x: x.get("id", 0))

        first_rec = active_recs[0]
        last_rec = active_recs[-1]

        start_time = first_rec.get("start_time")
        expires_at = last_rec.get("expires_at")

        remaining = 0
        if expires_at:
            try:
                exp_ts = datetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").timestamp()
                remaining = max(0, int(exp_ts - current_timestamp))
            except ValueError:
                pass

        snapshot = {
            'status': 'Approved',
            'start_time': start_time,
            'expires_at': expires_at,
            'remaining_seconds': remaining
        }
        return snapshot

    def notify_status_change(self):
        """SessionManager로 상태 변경 알림 위임."""
        self.session_manager.notify_status_change()

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
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as e:
            loge(f"[WebService] 업스트림 DNS 서버 조회 오류 (기본값 대체): {e}")
            return fallback_servers

    def register_routes(self, web_app):
        ws = self
        self.web_app = web_app

        @web_app.route('/')
        def portal_root():
            return redirect('/scan')

        @web_app.route('/scan')
        def customer_scan():
            token, _token_id, _client_ip, _device_name = ws.get_client_identity()
            current_fares = InternetRatesConfig().get_internet_fares()

            response = make_response(render_template_string(
                internet_portal_html_content,
                status_poll_interval=ws.internet_share_status_poll_interval,
                internet_fares=current_fares
            ))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.set_cookie(
                ws.internet_share_client_cookie,
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
            current_sessions = ws.repository.load_sessions()
            return handle_customer_request_use(
                request,
                current_sessions,
                ws.get_client_identity,
                ws.get_client_session,
                ws.append_usage_log,
            )

        @web_app.route('/status')
        def get_status():
            token, token_id, client_ip, device_name = ws.get_client_identity()
            
            db = internet_share_db
            all_requests = db.load(view_type="ALL")
            
            current_timestamp = datetime.datetime.now().timestamp()
            user_requests = []
            
            for req in all_requests:
                if req.get("client_ip") == client_ip:
                    status = req.get("status") or req.get("overall_status")
                    cancel_status = req.get("cancel_status", "NORMAL")
                    
                    if cancel_status == 'CANCELLED' or status == 'CANCELLED':
                        continue
                        
                    if status in ('Approved', 'ACTIVE', 'QUEUED'):
                        end_timestamp = req.get("end_timestamp")
                        if not end_timestamp and req.get("expires_at"):
                            try:
                                end_timestamp = datetime.datetime.strptime(
                                    req.get("expires_at"), "%Y-%m-%d %H:%M:%S"
                                ).timestamp()
                            except ValueError:
                                pass
                        
                        if end_timestamp and end_timestamp <= current_timestamp:
                            continue
                        
                        user_requests.append(req)

            session_data = ws.get_client_session(client_ip)
            session_data['history'] = user_requests
            
            return ws.identity_response(session_data, token)

        @web_app.route('/cancel-request', methods=['POST'])
        def cancel_request_route():
            # Controller는 요청을 받고 Service 레이어로 위임
            return handle_customer_request_cancel(
                request,
                ws.get_client_identity
            )

        @web_app.route('/internet-status', methods=['GET', 'POST'])
        def report_internet_status():
            token, token_id, client_ip, device_name = ws.get_client_identity()
            
            sessions = ws.repository.load_sessions()
            session = sessions.get(client_ip)
            if not session:
                return ws.identity_response({'status': 'None'}, token), 404
            
            session['last_seen'] = datetime.datetime.now().isoformat(timespec='seconds')
            session['client_token_id'] = token_id
            ws.apply_client_metadata(session, token_id)
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
                    except (TypeError, json.JSONDecodeError) as e:
                        loge(f"[WebService] internet_check JSON 파싱 오류: {e}")
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
                ws.repository.save_session(session)
            except Exception as e:
                loge(f"[WebService] internet-status 세션 저장 DB 오류: {e}")
                
            if internet_status in ('Checking', 'Available', 'Check failed', '확인 중', '사용 가능', '확인 실패'):
                if session.get('internet_status') != internet_status:
                    logd(f"[WebService] 인터넷 상태 변경 감지: IP={client_ip}, 상태={internet_status}")
                    session['internet_status'] = internet_status
                    ws.repository.save_session(session)
                    ws.notify_status_change()
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
                session_identity_lock=kwargs.get('session_identity_lock'),
                status_condition=kwargs.get('status_condition'),
                signals=kwargs.get('signals')
            )
        else:
            self.service_instance = service_instance

        self.web_app = Flask(__name__)
        self.service_instance.register_routes(self.web_app)
        self.service_instance.web_app = self.web_app

    def start(self):
        if self._is_running:
            logd("[WebServerManager] 서버가 이미 실행 중입니다.")
            return

        def run():
            try:
                self._is_running = True
                logd(f"[WebServerManager] 서버 스레드 시작 성공 (host={self.host}, port={self.port})")
                self.service_instance.run_server(host=self.host, port=self.port)
            except Exception as e:
                loge(f"[WebServerManager] 서버 실행 중 치명적인 오류 발생: {e}")
            finally:
                self._is_running = False
                logd("[WebServerManager] 서버 스레드 종료됨")

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

    def stop(self):
        if not self._is_running:
            logd("[WebServerManager] 중지할 실행 중인 서버가 없습니다.")
            return
        logd("[WebServerManager] 서버 중지 요청 처리")
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
    logd(f"[Server] link_share_init_server 호출됨 (host={host}, port={port})")
    _server_manager_instance = WebServerManager(service_instance, host, port, **kwargs)
    logd(f"[Server] WebServerManager 인스턴스 초기화 완료")

def link_share_start(service_instance=None, host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT, **kwargs):
    global _server_manager_instance
    
    if _server_manager_instance is None:
        logd("[Server] _server_manager_instance가 None입니다. 자동 초기화(link_share_init_server) 실행")
        link_share_init_server(service_instance, host, port, **kwargs)
    else:
        logd("[Server] 기존 _server_manager_instance 재사용")
    
    if _server_manager_instance:
        logd("[Server] 웹 서버 시작 명령 전달")
        _server_manager_instance.start()

def link_share_stop():
    global _server_manager_instance
    if _server_manager_instance:
        logd("[Server] 웹 서버 중지 요청 접수")
        _server_manager_instance.stop()
    else:
        logd("[Server] 서버 관리자 인스턴스가 존재하지 않아 중지할 수 없음")

def link_share_status():
    global _server_manager_instance
    if _server_manager_instance:
        return _server_manager_instance.status()
    logd("[Server] 서버 관리자 인스턴스가 없어 기본 상태(is_running: False) 반환")
    return {"is_running": False}
