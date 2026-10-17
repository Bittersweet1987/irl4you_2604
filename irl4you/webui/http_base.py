"""IRL4YOU BOX Oberfläche: HTTP-Handler: Grundlagen (Anfrage lesen, Antwort senden, Anmeldung prüfen)."""

import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

try:
    import pipbox_preview
except ImportError:
    pipbox_preview = None

from .access import client_origin
from .common import WEB_DIR, read
from .webfiles import expand_includes


class HttpBase(BaseHTTPRequestHandler):
    ERR_NO_ACCOUNT = "Zum Schreiben und Moderieren bitte in diesem Browser bei Twitch anmelden (Zuschauer oder Moderator)"

    ERR_NOT_MOD = "Moderieren dürfen nur der Streamer und Moderatoren dieses Kanals"

    timeout = 15

    BODY_SECONDS = 15.0

    REQUEST_SECONDS = 15.0

    _timer = None

    _claimed = None

    def setup(self):
        super().setup()
        self._timer = threading.Timer(self.REQUEST_SECONDS, self._cut)
        self._timer.daemon = True
        self._timer.start()

    def _cut(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass

    def request_read(self):
        t = self._timer
        if t is not None:
            t.cancel()

    def finish(self):
        self.request_read()
        if self._claimed is not None:
            try:
                self.server.release_sender(self._claimed)
            except AttributeError:
                pass
            self._claimed = None
        super().finish()

    def parse_request(self):
        ok = super().parse_request()
        if ok and self.client_address[0] in ("127.0.0.1", "::1") and hasattr(self.server, "claim_sender"):
            real = self.ip()
            if real not in ("127.0.0.1", "::1"):
                if not self.server.claim_sender(real):
                    self.send_error(429, "Zu viele Verbindungen")
                    return False
                self._claimed = real
        return ok

    def log_message(self, *a):
        pass

    def host(self):
        return (self.headers.get("Host") or "box").split(":")[0]

    def ip(self):
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1"):
            last = (self.headers.get("X-Forwarded-For", "") or "").split(",")[-1].strip()
            try:
                ipaddress.ip_address(last)
                return last
            except ValueError:
                pass
        return peer

    def origin(self):
        return client_origin(self.client_address[0], bool(self.headers.get("X-Forwarded-For")))

    def local_ip(self):
        try:
            return self.connection.getsockname()[0]
        except (OSError, AttributeError):
            return None

    def token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "pb_session":
                return v
        return ""

    def authed(self):
        return self.auth.valid(self.token())

    def read_json(self, limit=4096):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            raise ValueError("ungültige Länge")
        if n > limit:
            raise ValueError("Die Anfrage ist zu groß")
        data = self.read_body(n)
        self.request_read()
        out = json.loads(data or b"{}")
        if not isinstance(out, dict):
            raise ValueError("Ungültige Anfrage")
        return out

    def read_body(self, n):
        end = time.monotonic() + self.BODY_SECONDS
        buf = b""
        while len(buf) < n:
            left = end - time.monotonic()
            if left <= 0:
                raise ValueError("Die Anfrage kam zu langsam")
            conn = getattr(self, "connection", None)
            if conn is None:
                return self.rfile.read(n)
            conn.settimeout(left)
            try:
                chunk = self.rfile.read1(n - len(buf))
            except OSError:
                raise ValueError("Die Anfrage kam zu langsam")
            if not chunk:
                raise ValueError("Die Anfrage ist unvollständig")
            buf += chunk
        return buf

    def preview_stream(self):
        pv = self.preview
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        if not pv:
            return self.reply(503, {"error": "missing"})
        org = self.origin()
        pa = self.previewaccess
        if not pa.allowed(org):
            return self.reply(403, {"error": "extern"})
        if not self.send._active():
            return self.reply(503, {"error": "off"})
        if not pa.acquire(org):
            return self.reply(429, {"error": "busy"})
        try:
            return self._preview_stream(pv, q, org)
        finally:
            pa.release(org)

    def _preview_stream(self, pv, q, org):
        try:
            fmt = (q.get("fmt") or ["mp4"])[0]
            fmt = fmt if fmt in pipbox_preview.FORMATS else "mp4"
            fps, width, long = (q.get("fps") or [30])[0], (q.get("w") or [640])[0], (q.get("long") or [""])[0] == "1"
            if org == "extern":
                try:
                    fps = min(int(fps), self.previewaccess.EXT_FPS)
                    width = min(int(width), self.previewaccess.EXT_WIDTH)
                except (TypeError, ValueError):
                    fps, width = self.previewaccess.EXT_FPS, self.previewaccess.EXT_WIDTH
                long = False
            up, head = pv.open(fps, width, long, fmt)
        except OSError:
            return self.reply(503, {"error": "missing"})
        if up is None:
            why = head.get("error", "capture")
            return self.reply(429 if why == "busy" else 503, {"error": why})
        started = False
        self.close_connection = True
        lip = self.local_ip() or ""
        try:
            up.settimeout(20)
            while True:
                data = up.recv(65536)
                if not data:
                    break
                if not started:
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4" if fmt == "mp4" else "multipart/x-mixed-replace;boundary=" + pipbox_preview.BOUNDARY)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("X-Frame-Options", "DENY")
                    self.end_headers()
                    started = True
                self.wfile.write(data)
                self.wfile.flush()
                pipbox_preview.TRAFFIC.add(lip, len(data))
        except OSError:
            pass
        finally:
            try:
                up.close()
            except OSError:
                pass
        if not started:
            self.reply(503, {"error": "kein-bild"})

    def send_bytes(self, code, body, ctype, cookie=None, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def reply(self, code, obj, cookie=None):
        self.send_bytes(code, json.dumps(obj).encode(), "application/json", cookie)

    def cookie(self, tok, max_age):
        flags = "HttpOnly; SameSite=Strict; Path=/"
        if self.headers.get("X-Forwarded-Proto") == "https":
            flags += "; Secure"
        return f"pb_session={tok}; Max-Age={max_age}; {flags}"

    I18N_RE = re.compile(r"^/i18n/([a-z]{2,3}|languages)\.json$")

    def i18n_file(self, path):
        if path == "/i18n.js":
            name, ctype = "i18n.js", "application/javascript; charset=utf-8"
        else:
            m = self.I18N_RE.match(path)
            if not m:
                return False
            name, ctype = "i18n/%s.json" % m.group(1), "application/json; charset=utf-8"
        body = read(os.path.join(WEB_DIR, name), None)
        if body is None:
            self.reply(404, {"error": "not found"})
        else:
            self.send_bytes(200, body.encode("utf-8"), ctype)
        return True

    def page(self, name):
        body = expand_includes(read(os.path.join(WEB_DIR, name), ""))
        self.send_bytes(200, body.encode(), "text/html; charset=utf-8")
