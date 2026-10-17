"""IRL4YOU BOX Oberfläche: HTTP-Server mit Verbindungsgrenzen."""

import socket
import sys
import threading
from http.server import ThreadingHTTPServer

from .access import source_allowed


class LimitedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    MAX_CONN = 64
    PER_IP = 16
    allow_public = False
    ui_access = None

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._conn_lock = threading.Lock()
        self._conns = {}
        self._senders = {}
        self._total = 0

    LOOPBACK_CONN = 48

    def verify_request(self, request, client_address):
        ip = client_address[0]
        if not self.allow_public and not source_allowed(ip):
            return False
        loop = self.is_loopback(ip)
        ua = self.ui_access
        if ua is not None and ua.block:
            try:
                if ua.refuses(request.getsockname()[0]):
                    return False
            except (OSError, AttributeError):
                pass
        with self._conn_lock:
            if self._total >= self.MAX_CONN or (self._conns.get(ip, 0) >= (self.LOOPBACK_CONN if loop else self.PER_IP)):
                return False
            self._conns[ip] = self._conns.get(ip, 0) + 1
            self._total += 1
        return True

    @staticmethod
    def is_loopback(ip):
        return ip in ("127.0.0.1", "::1")

    def claim_sender(self, ip):
        with self._conn_lock:
            if self._senders.get(ip, 0) >= self.PER_IP:
                return False
            self._senders[ip] = self._senders.get(ip, 0) + 1
            return True

    def release_sender(self, ip):
        with self._conn_lock:
            n = self._senders.get(ip, 1) - 1
            if n > 0:
                self._senders[ip] = n
            else:
                self._senders.pop(ip, None)

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout)) or (isinstance(exc, OSError) and exc.errno in (9, 32, 54, 104)):
            return
        super().handle_error(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            ip = client_address[0]
            with self._conn_lock:
                self._total -= 1
                n = self._conns.get(ip, 1) - 1
                if n > 0:
                    self._conns[ip] = n
                else:
                    self._conns.pop(ip, None)
