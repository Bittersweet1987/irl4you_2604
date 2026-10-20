"""IRL4YOU BOX Oberfläche: Streamerhub-Chat. Die Box holt die Seite (Chat-Overlay) selbst und reicht sie weiter, damit sie im Rahmen der Oberfläche erscheint.

Seiten wie streamerhub.app verbieten das Einbetten (X-Frame-Options, frame-ancestors) und lassen Verbindungen nur von der eigenen Adresse zu. Deshalb läuft hier ein kleiner
Weiterleiter auf einem eigenen Port: Er ruft nur den Rechner auf, dessen Adresse unter dem Zahnrad eingetragen ist, entfernt die Sperren gegen das Einbetten, setzt Herkunft und
Cookies so, wie der Rechner sie erwartet, und gibt die Antwort Stück für Stück zurück (SockJS-Verbindungen bleiben offen). Zugriff hat nur, wer an der Oberfläche angemeldet ist.
WebSocket-Verbindungen (der Chat kommt per STOMP über SockJS) werden nach dem Handschlag unverändert durchgereicht.
"""

import http.client
import os
import select
import socket
import ssl
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler

from .layout import DeckStore


# Das Chat-Overlay von streamerhub.app ruft apiFetch() auf, das auf der Seite selbst nirgends definiert ist (Fehler beim Betreiber: ohne diese Funktion bricht das Skript ab und der
# Chat verbindet sich nie). Wo die Seite sie nicht liefert, ergänzt der Weiterleiter eine einfache Fassung (GET, JSON, Cookies des Weiterleiters).
HTML_SHIM = (b'<script>if(typeof apiFetch==="undefined"){window.apiFetch=function(u,o){return fetch(u,Object.assign({credentials:"same-origin"},o||{}))'
             b'.then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json()})}}</script>')


class HubStore(DeckStore):
    SIZE = {"width": (200, 4000, 500), "height": (200, 4000, 500), "mobile_width": (200, 4000, 500), "mobile_height": (200, 4000, 500)}
    FILE = "streamerhub.json"

    def __init__(self, state_dir):
        super().__init__(state_dir)
        self.path = os.path.join(state_dir, self.FILE)


class HubProxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    timeout = 120
    SCHEME = "https"
    MAX_BODY = 1024 * 1024
    MAX_PAGE = 4 * 1024 * 1024
    MAX_COOKIES = 40
    store = None
    auth = None
    jar = {}
    jar_lock = threading.Lock()
    PASS_REQ = ("accept", "accept-language", "content-type", "user-agent", "x-requested-with", "range", "if-none-match", "if-modified-since")
    DROP_RESP = {"date", "server", "connection", "keep-alive", "transfer-encoding", "upgrade", "x-frame-options", "content-security-policy", "content-security-policy-report-only",
                 "set-cookie", "strict-transport-security", "report-to", "nel", "alt-svc", "proxy-authenticate", "te", "trailer",
                 "access-control-allow-origin", "access-control-allow-credentials", "access-control-expose-headers"}

    def log_message(self, *a):
        pass

    def _token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "pb_session":
                return v
        return ""

    def _fail(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _cookies(self, host):
        with self.jar_lock:
            return "; ".join("%s=%s" % kv for kv in self.jar.get(host, {}).items())

    def _remember(self, host, values):
        with self.jar_lock:
            j = self.jar.setdefault(host, {})
            for v in values:
                name, _, rest = v.partition("=")
                val = rest.partition(";")[0]
                name = name.strip()
                if not name or len(name) > 100 or len(val) > 2000:
                    continue
                if "max-age=0" in v.lower() or val == "":
                    j.pop(name, None)
                elif len(j) < self.MAX_COOKIES or name in j:
                    j[name] = val

    def _upstream(self, host):
        if self.SCHEME == "http":
            return http.client.HTTPConnection(host, timeout=self.timeout)
        return http.client.HTTPSConnection(host, timeout=self.timeout)

    def _tunnel(self, url, host, path):
        """WebSocket: Handschlag mit Herkunft und Cookies des Zielrechners wiederholen, danach Bytes in beide Richtungen reichen."""
        origin = "%s://%s" % (self.SCHEME, host)
        lines = ["GET %s HTTP/1.1" % path, "Host: " + host, "Upgrade: websocket", "Connection: Upgrade", "Origin: " + origin]
        for k in ("Sec-WebSocket-Key", "Sec-WebSocket-Version", "Sec-WebSocket-Protocol", "User-Agent"):
            v = self.headers.get(k)
            if v and "\r" not in v and "\n" not in v:
                lines.append("%s: %s" % (k, v))
        ck = self._cookies(host)
        if ck:
            lines.append("Cookie: " + ck)
        try:
            raw = socket.create_connection((url.hostname, url.port or (80 if self.SCHEME == "http" else 443)), timeout=15)
            up = ssl.create_default_context().wrap_socket(raw, server_hostname=url.hostname) if self.SCHEME == "https" else raw
        except OSError:
            return self._fail(502, "Der Rechner ist nicht erreichbar.")
        try:
            up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1", "replace"))
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 16384:
                chunk = up.recv(4096)
                if not chunk:
                    break
                buf += chunk
            head, sep, rest = buf.partition(b"\r\n\r\n")
            if not sep or b" 101 " not in head.split(b"\r\n")[0] + b" ":
                return self._fail(502, "Der Rechner hat die Verbindung nicht angenommen.")
            self.connection.sendall(head + sep + rest)
            self.connection.settimeout(None)
            up.settimeout(None)
            pair = {self.connection: up, up: self.connection}
            while True:
                ready, _, _ = select.select(list(pair), [], [], 120)
                for src in ready:
                    data = src.recv(65536)
                    if not data:
                        return
                    pair[src].sendall(data)
        except (OSError, ValueError):
            return
        finally:
            try:
                up.close()
            except OSError:
                pass

    def _go(self):
        if not self.auth.valid(self._token()):
            return self._fail(403, "Bitte zuerst an der Oberfläche anmelden.")
        url = urllib.parse.urlsplit(self.store.get().get("url") or "")
        host = url.netloc
        if not url.hostname or not host or "@" in host:
            return self._fail(404, "Keine Adresse eingetragen.")
        path = self.path
        if not path.startswith("/") or path.startswith("//") or any(ord(c) < 33 or ord(c) == 127 for c in path):
            return self._fail(400, "Ungültige Adresse.")
        if (self.headers.get("Upgrade") or "").lower() == "websocket" and self.command == "GET":
            return self._tunnel(url, host, path)
        body = None
        if self.command == "POST":
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > self.MAX_BODY:
                return self._fail(413, "Anfrage zu groß.")
            body = self.rfile.read(n) if n else b""
        out = {k: self.headers[k] for k in self.PASS_REQ if self.headers.get(k)}
        out["Accept-Encoding"] = "identity"
        origin = "%s://%s" % (self.SCHEME, host)
        if self.headers.get("Origin"):
            out["Origin"] = origin
        out["Referer"] = origin + "/"
        ck = self._cookies(host)
        if ck:
            out["Cookie"] = ck
        conn = self._upstream(host)
        try:
            conn.request(self.command, path, body=body, headers=out)
            resp = conn.getresponse()
            self._remember(host, resp.headers.get_all("Set-Cookie") or [])
            page = None
            ctype = (resp.getheader("Content-Type") or "").lower()
            if self.command != "HEAD" and resp.status == 200 and ctype.startswith("text/html") and not resp.getheader("Content-Encoding"):
                page = resp.read(self.MAX_PAGE + 1)
                if len(page) > self.MAX_PAGE:
                    return self._fail(502, "Die Seite ist zu groß.")
                i = page.lower().find(b"<head>")
                page = page[:i + 6] + HTML_SHIM + page[i + 6:] if i >= 0 else HTML_SHIM + page
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                low = k.lower()
                if low in self.DROP_RESP or (page is not None and low in ("content-length", "content-encoding")):
                    continue
                if low == "location":
                    for pre in (origin, "//" + host):
                        if v.startswith(pre):
                            v = v[len(pre):] or "/"
                self.send_header(k, v)
            self.send_header("Cache-Control", "no-store")
            if page is not None:
                self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            if page is not None:
                self.wfile.write(page)
            elif self.command != "HEAD":
                while True:
                    chunk = resp.read1(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (OSError, http.client.HTTPException):
            try:
                self._fail(502, "Der Rechner ist nicht erreichbar.")
            except OSError:
                pass
        finally:
            conn.close()

    do_GET = do_POST = do_HEAD = do_OPTIONS = _go


def make_server(server_class, host, port, auth, store):
    """Der Weiterleiter als eigener Server (gleiche Begrenzungen wie die Oberfläche)."""
    handler = type("HubProxyHandler", (HubProxy,), {"auth": auth, "store": store, "jar": {}})
    return server_class((host, port), handler)
