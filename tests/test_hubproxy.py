"""Streamerhub-Chat: Weiterleiter, der die Sperre gegen das Einbetten entfernt, Cookies und Herkunft für den Zielrechner setzt und nur angemeldete Nutzer bedient."""
import http.client
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.seen.append((self.command, self.path, dict(self.headers)))
        if self.path == "/wsecho":
            self.wfile.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: x\r\n\r\n")
            self.wfile.flush()
            while True:
                d = self.connection.recv(100)
                if not d:
                    return
                self.wfile.write(d)
                self.wfile.flush()
        if self.path.startswith("/ws"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            for i in range(3):
                self.wfile.write(b"h\n")
                self.wfile.flush()
            return
        body = b"<html><head></head>overlay</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        self.send_header("Set-Cookie", "XSRF-TOKEN=abc123; Path=/; Secure")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        self.seen.append((self.command, self.path, dict(self.headers)))
        ok = "XSRF-TOKEN=abc123" in (self.headers.get("Cookie") or "") and self.headers.get("Origin", "").startswith("http://127.0.0.1")
        self.send_response(200 if ok else 403)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Auth:
    def valid(self, tok):
        return tok == "gut"


class Store:
    def __init__(self, url):
        self.url = url

    def get(self):
        return {"url": self.url}


class TestWeiterleiter(unittest.TestCase):
    def setUp(self):
        self.hp = irl("webui.hubproxy")
        Upstream.seen = []
        self.up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        self.uport = self.up.server_address[1]
        self.store = Store("https://127.0.0.1:%d/chat-overlay?id=1" % self.uport)
        handler = type("H", (self.hp.HubProxy,), {"auth": Auth(), "store": self.store, "jar": {}, "SCHEME": "http"})
        self.px = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.px.serve_forever, daemon=True).start()
        self.pport = self.px.server_address[1]

    def tearDown(self):
        self.up.shutdown()
        self.px.shutdown()

    def get(self, method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.pport, timeout=10)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, dict((k.lower(), v) for k, v in r.getheaders()), r.read()

    def test_ohne_anmeldung_gesperrt(self):
        st, h, b = self.get("GET", "/chat-overlay?id=1")
        self.assertEqual(st, 403)
        self.assertEqual(Upstream.seen, [])

    def test_sperren_entfernt_und_cookie_im_weiterleiter(self):
        ck = {"Cookie": "pb_session=gut"}
        st, h, b = self.get("GET", "/chat-overlay?id=1", ck)
        self.assertEqual(st, 200)
        self.assertTrue(b"apiFetch" in b and b.endswith(b"</html>"))      # fehlende apiFetch() des Overlays wird ergänzt
        for k in ("x-frame-options", "content-security-policy", "set-cookie"):
            self.assertNotIn(k, h)
        self.assertNotIn("pb_session", Upstream.seen[0][2].get("Cookie", ""))
        st, h, b = self.get("POST", "/ws_new/info", dict(ck, Origin="http://192.168.178.111:8782", **{"Content-Type": "text/plain"}), b"x")
        self.assertEqual((st, b), (200, b"x"))
        self.assertTrue(Upstream.seen[-1][2]["Origin"].startswith("http://127.0.0.1"))      # Herkunft wie beim Zielrechner, Cookie aus der Ablage des Weiterleiters

    def test_websocket_wird_durchgereicht(self):
        s = socket.create_connection(("127.0.0.1", self.pport), timeout=5)
        s.sendall(b"GET /wsecho HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: abc\r\nSec-WebSocket-Version: 13\r\n"
                  b"Origin: http://192.168.1.5\r\nCookie: pb_session=gut\r\n\r\n")
        got = b""
        while b"\r\n\r\n" not in got:
            got += s.recv(1024)
        self.assertIn(b"101", got.split(b"\r\n")[0])
        s.sendall(b"ping")
        self.assertEqual(s.recv(100), b"ping")
        s.close()
        up = [x for x in Upstream.seen if x[1] == "/wsecho"][0][2]
        self.assertEqual((up["Origin"].startswith("http://127.0.0.1"), up["Sec-WebSocket-Key"]), (True, "abc"))
        s = socket.create_connection(("127.0.0.1", self.pport), timeout=5)           # ohne Anmeldung kein Zugang
        s.sendall(b"GET /wsecho HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
        self.assertIn(b"403", s.recv(1024))
        s.close()

    def test_streaming(self):
        st, h, b = self.get("GET", "/ws/stream", {"Cookie": "pb_session=gut"})
        self.assertEqual(b, b"h\nh\nh\n")

    def test_nur_eingetragener_rechner_und_saubere_adresse(self):
        ck = {"Cookie": "pb_session=gut"}
        self.get("GET", "//evil.example/x", ck)           # Python macht daraus einen Pfad; es geht nie an einen anderen Rechner
        self.assertEqual(Upstream.seen[-1][1], "/evil.example/x")
        self.store.url = ""
        self.assertEqual(self.get("GET", "/chat-overlay", ck)[0], 404)

    def test_speicher(self):
        d = tempfile.TemporaryDirectory()
        s = self.hp.HubStore(d.name)
        self.assertEqual(s.get()["url"], "")
        s.put({"url": "https://streamerhub.app/chat-overlay?id=21927f4e", "height": 640})
        got = s.get()
        self.assertEqual((got["url"], got["height"], got["width"]), ("https://streamerhub.app/chat-overlay?id=21927f4e", 640, 500))
        with self.assertRaises(ValueError):
            s.put({"url": "http://streamerhub.app/x"})
        d.cleanup()


if __name__ == "__main__":
    unittest.main()
