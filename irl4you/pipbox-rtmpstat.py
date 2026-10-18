#!/usr/bin/env python3
"""Statistik des RTMP-Eingangs für IRL4YOU (Port 1936, XML im Format des früheren nginx-rtmp-Moduls).

Der RTMP-Eingang ist SRS (irl4you-srs). SRS meldet seine Streams als JSON über die lokale API (127.0.0.1:1985); IRL4YOU (Oberfläche,
DJI-Dienst, HDMI-Dienst, Sendekette, Protokolle) liest dagegen seit jeher eine XML-Seite auf Port 1936. Dieses kleine Programm
übersetzt: Es holt die Streams von SRS und liefert sie als <rtmp><server><application><live><stream>…, mit

  name, time (ms), bw_in (bit/s), bytes_in, bw_video, bw_audio (bit/s, geschätzt), nclients (Zuschauer),
  <publishing/> solange jemand sendet, meta/video (width, height, frame_rate, codec, profile, level), meta/audio (codec, sample_rate, channels).

Bildrate und Bitrate misst das Programm selbst aus den Zählern von SRS, weil SRS nur Zähler und einen 30-Sekunden-Mittelwert liefert. SRS setzt den Byte-Zähler etwa alle 3 s und den
Bildzähler nur etwa alle 15 s weiter; gemessen wird deshalb je Zähler zwischen seinen Sprüngen (Hintergrundtask liest alle 0,2 s), die Bildrate rastet auf übliche Werte ein. Der Austausch des RTMP-Servers bleibt damit eine Sache dieses Programms.

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
POLL = 0.2                  # so oft liest der Hintergrundtask die SRS-Zähler (Auflösung der Änderungszeitpunkte)
BYTES_WINDOW = 12.0         # Bitrate: Zeitfenster über Zählersprünge der Bytes
BYTES_STALE = 12.0          # so lange darf SRS den Byte-Zähler unverändert lassen, bevor „es kommt nichts mehr an“ gilt
FRAME_JUMPS = 3             # Bildrate: aus so vielen letzten Sprüngen des Bildzählers (also 2 Intervallen) gerechnet
FRAME_MIN_SPAN = 3.0        # kürzere Abstände zwischen Bildzähler-Sprüngen sind zu ungenau
MEMO_KEEP = 3600.0          # letzte Bildrate eines Stream-Namens wird so lange für ein Wiederverbinden gemerkt
STD_RATES = (15, 24, 25, 30, 48, 50, 60, 72, 90, 100, 120)
SNAP = 0.035                # Messwerte bis 3,5 % neben einer üblichen Bildrate gelten als genau diese (29,97 und 30,4 -> 30)
CODEC_NAMES = {"h264": "H264", "avc": "H264", "h265": "H265", "hevc": "H265", "av1": "AV1", "aac": "AAC", "mp3": "MP3", "opus": "Opus"}


def codec(v):
    v = str(v or "").strip()
    return CODEC_NAMES.get(v.lower(), v)


def snap_rate(fps):
    """Messwert auf eine übliche Bildrate einrasten lassen; so zeigt die Anzeige nie mehr, als der Sender wirklich schickt."""
    r = min(STD_RATES, key=lambda x: abs(fps - x))
    return float(r) if abs(fps - r) <= r * SNAP else round(fps)


class Track:
    """Zählerverlauf einer Verbindung. SRS aktualisiert den Byte-Zähler etwa alle 3 s und den Bildzähler nur etwa alle 15 s, jeweils in
    einem Schub dazwischen steht er still. Deshalb wird jeder Zähler für sich und nur zwischen seinen Sprüngen gemessen."""

    def __init__(self, now, cid, frames, nbytes):
        self.cid = cid
        self.frames, self.nbytes = frames, nbytes
        # Beginnt der Bildzähler bei 0, ist die Verbindung gerade neu und der Zeitpunkt jetzt der Messbeginn; sonst fehlt der Anfang
        self.fjumps = [(now, 0)] if frames == 0 else []
        self.bjumps = [(now, nbytes)]
        self.bchanged = now
        self.fps = None

    def feed(self, now, frames, nbytes):
        if frames != self.frames:
            self.frames = frames
            self.fjumps = (self.fjumps + [(now, frames)])[-FRAME_JUMPS:]
            (t0, f0), (t1, f1) = self.fjumps[0], self.fjumps[-1]
            if t1 - t0 >= FRAME_MIN_SPAN and f1 > f0:
                self.fps = snap_rate((f1 - f0) / (t1 - t0))
        if nbytes != self.nbytes:
            self.nbytes, self.bchanged = nbytes, now
            self.bjumps = [j for j in self.bjumps + [(now, nbytes)] if now - j[0] <= BYTES_WINDOW]

    def bps(self, now):
        if now - self.bchanged > BYTES_STALE:
            return 0.0
        (t0, b0), (t1, b1) = self.bjumps[0], self.bjumps[-1]
        return (b1 - b0) * 8 / (t1 - t0) if t1 - t0 > 0 else None


class Meter:
    """Rechnet je Stream Bildrate und Bitrate aus den SRS-Zählern."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.tracks = {}
        self.memo = {}           # sid -> (Bildrate, Bitrate, Zeitpunkt): Anzeige ohne Lücke, bis die neue Verbindung gemessen ist
        self.lock = threading.Lock()

    def feed(self, sid, frames, nbytes, cid=None):
        now = self.clock()
        frames, nbytes = frames or 0, nbytes or 0
        with self.lock:
            tr = self.tracks.get(sid)
            if tr is None or tr.cid != cid or frames < tr.frames or nbytes < tr.nbytes:
                tr = self.tracks[sid] = Track(now, cid, frames, nbytes)      # neue Verbindung: Zähler fangen von vorn an
            else:
                tr.feed(now, frames, nbytes)
            return self._read(sid, tr, now)

    def _read(self, sid, tr, now):
        bps = tr.bps(now)
        if bps == 0.0:
            return 0.0, 0.0                              # seit längerer Zeit kein Byte mehr: es kommt nichts an, auch keine Bildrate
        old = self.memo.get(sid)
        old = old if old and now - old[2] <= MEMO_KEEP else (None, None, now)
        fps = tr.fps if tr.fps is not None else old[0]
        bps = bps if bps is not None else old[1]
        self.memo[sid] = (fps, bps, now)
        return fps, bps

    def forget(self, alive):
        with self.lock:
            for k in [k for k in self.tracks if k not in alive]:
                del self.tracks[k]


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
        fps, bps = meter.feed(sid, s.get("frames"), s.get("recv_bytes"), (s.get("publish") or {}).get("cid"))
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
                    escape(codec(a.get("codec"))), int(a.get("sample_rate") or 0), int(a.get("channel") or a.get("channels") or 0)))
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


class Sampler(threading.Thread):
    """Liest die SRS-Zähler alle POLL Sekunden und hält die fertige Statistik bereit. Wer die Seite abruft, bekommt immer den letzten
    Stand; die Messung hängt so nicht davon ab, wie oft und wann gefragt wird."""

    def __init__(self, srs, app, meter):
        super().__init__(daemon=True)
        self.srs, self.app, self.meter = srs, app, meter
        self.body, self.at = None, 0.0

    def run(self):
        while True:
            t = time.monotonic()
            try:
                with urllib.request.urlopen(self.srs, timeout=2) as r:
                    data = json.loads(r.read(4_000_000))
                streams = data.get("streams") if isinstance(data, dict) else None
                self.body, self.at = build_xml(streams, self.meter, self.app).encode("utf-8"), t
            except (OSError, ValueError):
                pass
            time.sleep(max(0.0, POLL - (time.monotonic() - t)))


class Handler(BaseHTTPRequestHandler):
    sampler = None
    server_version = "irl4you-rtmpstat"

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            return self.send(200, b"ok", "text/plain")
        if path not in ("/", "/stat"):
            return self.send(404, b"not found", "text/plain")
        sp = self.sampler
        if sp.body is None or time.monotonic() - sp.at > 3.0:
            return self.send(503, b"srs nicht erreichbar", "text/plain")
        self.send(200, sp.body, "text/xml")

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
    ap.add_argument("--srs", default="http://127.0.0.1:1985/api/v1/streams/?count=100")
    ap.add_argument("--app", default="publish")
    a = ap.parse_args()
    host, _, port = a.listen.rpartition(":")
    Handler.sampler = Sampler(a.srs, a.app, Meter())
    Handler.sampler.start()
    ThreadingHTTPServer((host or "0.0.0.0", int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
