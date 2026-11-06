"""LinkShare captive-portal transport service.

The integrated shell supplies the session approval predicate and portal URL;
this module owns the gateway-bound DNS and HTTP behavior.
"""

import http.server
import ipaddress
import json
import socket
import socketserver
import subprocess
import threading
import time


class CaptivePortalRedirectHandler(http.server.BaseHTTPRequestHandler):
    portal_url = ''
    is_approved = staticmethod(lambda _client_ip: False)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return

    def do_GET(self):
        if self.is_approved(self.client_address[0]):
            host = (self.headers.get('Host') or '').lower().split(':', 1)[0]
            probe_hosts = {
                'www.msftconnecttest.com', 'www.msftncsi.com',
                'connectivitycheck.gstatic.com', 'clients3.google.com',
                'connectivitycheck.android.com', 'captive.apple.com',
            }
            if host in probe_hosts:
                body = b'Microsoft Connect Test'
                self.send_response(200 if host.startswith('www.msft') else 204)
                if body and host.startswith('www.msft'):
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                else:
                    self.send_header('Content-Length', '0')
                self.end_headers()
                if body and host.startswith('www.msft'):
                    self.wfile.write(body)
                return
        self.send_response(302)
        self.send_header('Location', self.portal_url)
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_HEAD = do_GET

    def log_message(self, _format, *_args):
        return


class CaptivePortalDNSHandler(socketserver.BaseRequestHandler):
    is_approved = staticmethod(lambda _client_ip: False)
    get_upstream_dns_servers = staticmethod(lambda: ['1.1.1.1', '8.8.8.8'])

    def handle(self):
        query, udp_socket = self.request
        client_address = self.client_address
        if len(query) < 12:
            return
        try:
            if self.is_approved(client_address[0]):
                for upstream in self.get_upstream_dns_servers():
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as resolver:
                            resolver.settimeout(1.5)
                            resolver.sendto(query, (upstream, 53))
                            response, _ = resolver.recvfrom(4096)
                        udp_socket.sendto(response, client_address)
                        return
                    except (OSError, socket.timeout):
                        continue

            offset = 12
            while offset < len(query) and query[offset] != 0:
                offset += 1 + query[offset]
            question_end = offset + 5
            if question_end > len(query):
                return
            question = query[12:question_end]
            query_type = int.from_bytes(query[offset + 1:offset + 3], 'big')
            answers = b''
            answer_count = 0
            if query_type == 1:
                answers = (b'\xc0\x0c' + b'\x00\x01\x00\x01' + (30).to_bytes(4, 'big') +
                           b'\x00\x04' + socket.inet_aton(self.server.gateway))
                answer_count = 1
            response = (query[:2] + b'\x81\x80' + b'\x00\x01' + answer_count.to_bytes(2, 'big') +
                        b'\x00\x00\x00\x00' + question + answers)
            udp_socket.sendto(response, client_address)
        except (IndexError, OSError, ValueError):
            return


class CaptivePortalDNSServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True

    def __init__(self, server_address, gateway, is_approved, get_upstream_dns_servers):
        handler = type('ConfiguredDNSHandler', (CaptivePortalDNSHandler,), {
            'is_approved': staticmethod(is_approved),
            'get_upstream_dns_servers': staticmethod(get_upstream_dns_servers),
        })
        self.gateway = gateway
        super().__init__(server_address, handler)


class CaptivePortalService:
    def __init__(self, gateway, portal_url, is_approved, get_upstream_dns_servers,
                 status_sink=None, retry_delay=3, max_retries=10):
        self.gateway = gateway
        self.portal_url = portal_url
        self.is_approved = is_approved
        self.get_upstream_dns_servers = get_upstream_dns_servers
        self.servers = []
        self.status_sink = status_sink
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.retry_count = 0
        self._retry_timer = None

    def _publish_status(self, messages):
        if self.status_sink is not None:
            self.status_sink('Captive Portal: ' + ' | '.join(messages))

    def start(self):
        messages = []
        handler = type('ConfiguredHTTPHandler', (CaptivePortalRedirectHandler,), {
            'portal_url': self.portal_url,
            'is_approved': staticmethod(self.is_approved),
        })
        try:
            server = http.server.ThreadingHTTPServer((self.gateway, 80), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.servers.append(server)
            messages.append('HTTP redirect ON (port 80)')
        except OSError as exc:
            messages.append(f'HTTP redirect unavailable: {exc}')
        try:
            server = CaptivePortalDNSServer(
                (self.gateway, 53), self.gateway,
                self.is_approved, self.get_upstream_dns_servers,
            )
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.servers.append(server)
            messages.append('DNS redirect ON (port 53)')
        except OSError as exc:
            messages.append(f'DNS redirect unavailable: {exc}')
        self._publish_status(messages)
        if not self.servers and self.retry_count < self.max_retries:
            self.retry_count += 1
            self._retry_timer = threading.Timer(self.retry_delay, self.start)
            self._retry_timer.daemon = True
            self._retry_timer.start()
        return messages

    def stop(self):
        if self._retry_timer is not None:
            self._retry_timer.cancel()
            self._retry_timer = None
        for server in self.servers:
            try:
                server.shutdown()
                server.server_close()
            except OSError:
                pass
        self.servers.clear()
