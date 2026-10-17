#!/usr/bin/env python3
"""Statistik des RTMP-Eingangs für IRL4YOU (Port 1936, XML im Format des früheren nginx-rtmp-Moduls).

Der RTMP-Eingang ist SRS (irl4you-srs). SRS meldet seine Streams als JSON über die lokale API (127.0.0.1:1985); IRL4YOU (Oberfläche,
DJI-Dienst, HDMI-Dienst, Sendekette, Protokolle) liest dagegen seit jeher eine XML-Seite auf Port 1936. Dieses kleine Programm
übersetzt: Es holt die Streams von SRS und liefert sie als <rtmp><server><application><live><stream>…, mit

  name, time (ms), bw_in (bit/s), bytes_in, bw_video, bw_audio (bit/s, geschätzt), nclients (Zuschauer),
  <publishing/> solange jemand sendet, meta/video (width, height, frame_rate, codec, profile, level), meta/audio (codec, sample_rate, channels).

Bildrate und Bitrate misst das Programm selbst aus den Zählern von SRS (Unterschied über etwa 2 bis 5 Sekunden), weil SRS nur Zähler und einen
30-Sekunden-Mittelwert liefert. Der Austausch des RTMP-Servers bleibt damit eine Sache dieses Programms.

  pipbox-rtmpstat.py [--listen ADR:PORT] [--srs URL] [--app publish]
"""
import argparse
import json
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

AUDIO_BPS = 128000          # Schätzung für den Tonanteil, solange SRS nur die Summe meldet
WINDOW_MIN, WINDOW_MAX = 2.0, 6.0
CODEC_NAMES = {"h264": "H264", "avc": "H264", "h265": "H265", "hevc": "H265", "av1": "AV1", "aac": "AAC", "mp3": "MP3", "opus": "Opus"}


def codec(v):
    v = str(v or "").strip()
    return CODEC_NAMES.get(v.lower(), v)


class Meter:
    """Merkt sich je Stream die letzten Zählerstände und rechnet daraus Bildrate und Bitrate aus."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.hist = {}
        self.lock = threading.Lock()

    def feed(self, sid, frames, nbytes):
        now = self.clock()
        with self.lock:
            h = [x for x in self.hist.get(sid, []) if now - x[0] <= WINDOW_MAX and x[1] <= (frames or 0) and x[2] <= (nbytes or 0)]
            if not h or now - h[-1][0] >= 0.4:
                h.append((now, frames or 0, nbytes or 0))
            self.hist[sid] = h
            old = next((x for x in h if now - x[0] >= WINDOW_MIN), None)
            if old is None or now - old[0] <= 0:
                return None, None
            dt = now - old[0]
            return (h[-1][1] - old[1]) / dt, (h[-1][2] - old[2]) * 8 / dt

    def forget(self, alive):
        with self.lock:
            for k in [k for k in self.hist if k not in alive]:
                del self.hist[k]


def build_xml(streams, meter, app="publish"):
    """SRS-Streams (JSON-Liste von /api/v1/streams) -> XML im Format von nginx-rtmp. Nur Streams der Applikation `app`."""
    items = []
    alive = set()
    for s in streams or []:
        if not isinstance(s, dict) or s.get("app") != app or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", str(s.get("name", ""))):
            continue
        sid = "%s/%s" % (s.get("app"), s.get("name"))
        alive.add(sid)
        pub = bool((s.get("publish") or {}).get("active"))
        fps, bps = meter.feed(sid, s.get("frames"), s.get("recv_bytes"))
        v, a = s.get("video") or {}, s.get("audio") or {}
        x = ["<stream>", "<name>%s</name>" % escape(str(s["name"])), "<time>%d</time>" % int(s.get("live_ms") or 0),
             "<bw_in>%d</bw_in>" % int(bps or 0), "<bytes_in>%d</bytes_in>" % int(s.get("recv_bytes") or 0)]
        bw_audio = AUDIO_BPS if a and bps else 0
        x.append("<bw_video>%d</bw_video>" % max(0, int(bps or 0) - bw_audio))
        x.append("<bw_audio>%d</bw_audio>" % bw_audio)
        if v or a:
            x.append("<meta>")
            if v:
                x.append("<video><width>%d</width><height>%d</height>%s<codec>%s</codec><profile>%s</profile><level>%s</level></video>" % (
                    int(v.get("width") or 0), int(v.get("height") or 0),
                    "<frame_rate>%d</frame_rate>" % round(fps) if fps and fps > 0 else "",
                    escape(codec(v.get("codec"))), escape(str(v.get("profile") or "")), escape(str(v.get("level") or ""))))
            if a:
                x.append("<audio><codec>%s</codec><sample_rate>%s</sample_rate><channels>%s</channels></audio>" % (
                    escape(codec(a.get("codec"))), int(a.get("sample_rate") or 0), int(a.get("channels") or 0)))
            x.append("</meta>")
        x.append("<nclients>%d</nclients>" % max(0, int(s.get("clients") or 0) - (1 if pub else 0)))
        if pub:
            x.append("<publishing/>")
        x.append("<active/>")
        x.append("</stream>")
        items.append("".join(x))
    meter.forget(alive)
    return ('<?xml version="1.0" encoding="utf-8" ?><rtmp><server><application><name>%s</name><live>%s<nclients>0</nclients></live></application></server></rtmp>\n'
            % (escape(app), "".join(items)))


class Handler(BaseHTTPRequestHandler):
    srs = "http://127.0.0.1:1985/api/v1/streams/?count=100"
    app = "publish"
    meter = None
    server_version = "irl4you-rtmpstat"

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            return self.send(200, b"ok", "text/plain")
        if path not in ("/", "/stat"):
            return self.send(404, b"not found", "text/plain")
        try:
            with urllib.request.urlopen(self.srs, timeout=2) as r:
                data = json.loads(r.read(4_000_000))
            streams = data.get("streams") if isinstance(data, dict) else None
        except (OSError, ValueError):
            return self.send(503, b"srs nicht erreichbar", "text/plain")
        body = build_xml(streams, self.meter, self.app).encode("utf-8")
        self.send(200, body, "text/xml")

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="0.0.0.0:1936")
    ap.add_argument("--srs", default=Handler.srs)
    ap.add_argument("--app", default="publish")
    a = ap.parse_args()
    host, _, port = a.listen.rpartition(":")
    Handler.srs, Handler.app, Handler.meter = a.srs, a.app, Meter()
    ThreadingHTTPServer((host or "0.0.0.0", int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
