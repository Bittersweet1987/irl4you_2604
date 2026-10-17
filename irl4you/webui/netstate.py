"""IRL4YOU BOX Oberfläche: Netzwerkkarten für die Kamera, Zustand der Sendewege, SRTLA-Server."""

import json
import os
import re
import secrets
import threading
import time

from .common import HOST_RE, iface_ips, lan_ip, local_macs


LINKS_FILE = "/run/pipbox-send/srtla.json"


def uplink_states(selected):
    """Zustand je Sendeweg aus der Statusdatei von irl4you-srtla (Leitung used/reserve/joining/down, Laufzeit)."""
    try:
        if time.time() - os.stat(LINKS_FILE).st_mtime > 20:
            return {}
        with open(LINKS_FILE) as f:
            links = json.load(f).get("links") or []
    except (OSError, ValueError, AttributeError):
        return {}
    last = {}
    for l in links:
        if isinstance(l, dict) and isinstance(l.get("ip"), str) and l.get("state") in ("used", "reserve"):
            rtt = l.get("rtt_ms")
            last[l["ip"]] = (int(rtt) if isinstance(rtt, (int, float)) else -1, "genutzt" if l["state"] == "used" else "reserve")
    by_ip = {o["ip"]: o["iface"] for o in iface_ips()}
    seen = {by_ip[ip]: v for ip, v in last.items() if ip in by_ip}
    out = {}
    for n in selected:
        v = seen.get(n)
        if v is None:
            out[n] = {"state": "aus", "srtt": None}
        else:
            out[n] = {"state": "an" if v[1] == "genutzt" else "reserve", "srtt": v[0] if v[0] >= 0 else None}
    return out


class NetChoice:

    def __init__(self, path):
        self.path = path
        try:
            with open(path) as f:
                self.iface = json.load(f).get("iface")
        except (OSError, ValueError):
            self.iface = None

    def options(self):
        return iface_ips()

    def ip(self):
        for o in self.options():
            if o["iface"] == self.iface:
                return o.get("cam_ip") or o["ip"]
        return lan_ip()

    def select(self, iface):
        if iface not in [o["iface"] for o in self.options()]:
            raise ValueError("Unbekannte Schnittstelle oder keine IPv4-Adresse")
        self.iface = iface
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"iface": iface}, f)
        os.replace(tmp, self.path)

    def status(self):
        return {"options": self.options(), "selected": self.iface, "ip": self.ip()}


class IfaceMemory:

    def __init__(self, path):
        self.path = path

    def _last(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, cur):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cur, f)
        os.replace(tmp, self.path)

    def reconcile(self, srtla, netchoice, cams, wifi=None, names=None):
        cur = local_macs()
        last = self._last()
        by_mac = {m: n for n, m in cur.items()}
        mapping = {name: by_mac[mac] for name, mac in last.items() if cur.get(name) != mac and by_mac.get(mac) not in (None, name)}
        if mapping:
            self._apply(mapping, srtla, netchoice, cams, wifi, names)
            print("iface_macs:", ", ".join("%s->%s" % kv for kv in sorted(mapping.items())), flush=True)
        if cur != last:
            try:
                self._save(cur)
            except OSError:
                pass
        return mapping

    @staticmethod
    def _apply(m, srtla, netchoice, cams, wifi=None, names=None):
        r = lambda n: m.get(n, n)
        with srtla.lock:
            st = srtla.data.get("settings") or {}
            if isinstance(st.get("uplinks"), list):
                st["uplinks"] = sorted(set(r(u) for u in st["uplinks"]))
            if isinstance(st.get("min_share"), dict):
                st["min_share"] = {r(k): v for k, v in st["min_share"].items()}
            srtla.save()
        if netchoice is not None and netchoice.iface in m:
            netchoice.iface = r(netchoice.iface)
            tmp = netchoice.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"iface": netchoice.iface}, f)
            os.replace(tmp, netchoice.path)
        with cams.lock:
            changed = False
            for c in cams.cams:
                if c.get("iface") in m:
                    c["iface"] = r(c["iface"])
                    changed = True
            if changed:
                cams.save()
        if wifi is not None and not getattr(wifi, "demo", False):
            hs = wifi.hotspots()
            if any(k in m for k in hs):
                out = {r(k): v for k, v in hs.items()}
                tmp = wifi.hs_file + ".tmp"
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(out, f)
                os.replace(tmp, wifi.hs_file)
        if names is not None:
            with names.lock:
                d = names._all()
                out = {}
                for k, v in d.items():
                    pre = k[:3] if k.startswith("if:") else (k[:4] if k.startswith("net:") else "")
                    out[pre + r(k[len(pre):]) if pre else k] = v
                if out != d:
                    tmp = names.path + ".tmp"
                    with open(tmp, "w") as f:
                        json.dump(out, f)
                    os.replace(tmp, names.path)

    def run(self, srtla, netchoice, cams, wifi=None, names=None, every=30):
        while True:
            try:
                self.reconcile(srtla, netchoice, cams, wifi, names)
            except Exception as e:
                print("iface_macs:", type(e).__name__, flush=True)
            time.sleep(every)


class SrtlaStore:
    DEFAULT_SETTINGS = {"min_kbps": 300, "max_kbps": 12000, "latency_ms": 4000, "uplinks": ["eth0", "eth1"],
                        "spread": "best"}

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.data = {"servers": [], "selected": None, "settings": dict(self.DEFAULT_SETTINGS)}
        try:
            with open(path) as f:
                loaded = json.load(f)
            self.data.update({k: loaded[k] for k in ("servers", "selected") if k in loaded})
            self.data["settings"].update(loaded.get("settings", {}))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
        with os.fdopen(fd, "w") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    @staticmethod
    def check(req):
        name = str(req.get("name", "")).strip()
        host = str(req.get("host", "")).strip().lower()
        sid = str(req.get("streamid", "")).strip()
        try:
            port = int(req.get("port"))
        except (TypeError, ValueError):
            raise ValueError("Port: Zahl von 1 bis 65535")
        if not 1 <= len(name) <= 40:
            raise ValueError("Name: 1 bis 40 Zeichen")
        if not HOST_RE.match(host):
            raise ValueError("Adresse: nur Buchstaben, Ziffern, Punkt und Bindestrich (ohne rtmp:// oder Leerzeichen)")
        if not 1 <= port <= 65535:
            raise ValueError("Port: Zahl von 1 bis 65535")
        if len(sid) > 512 or any(ord(c) < 32 or ord(c) > 126 for c in sid):
            raise ValueError("Stream-ID: höchstens 512 sichtbare Zeichen")
        return {"name": name, "host": host, "port": port, "streamid": sid}

    def public(self):
        with self.lock:
            return {"servers": [{"id": s["id"], "name": s["name"], "host": s["host"], "port": s["port"],
                                 "has_streamid": bool(s.get("streamid"))} for s in self.data["servers"]],
                    "selected": self.data["selected"], "settings": dict(self.data["settings"])}

    def add(self, req):
        item = self.check(req)
        with self.lock:
            item["id"] = secrets.token_hex(4)
            self.data["servers"].append(item)
            if not self.data["selected"]:
                self.data["selected"] = item["id"]
            self.save()
        return item["id"]

    def update(self, sid, req):
        with self.lock:
            cur = next((s for s in self.data["servers"] if s["id"] == sid), None)
            if not cur:
                raise KeyError(sid)
            merged = {"name": cur["name"], "host": cur["host"], "port": cur["port"],
                      "streamid": cur.get("streamid", "")}
            merged.update({k: v for k, v in req.items() if k in merged and not (k == "streamid" and v in (None, ""))})
            if req.get("clear_streamid"):
                merged["streamid"] = ""
            cur.update(self.check(merged))
            self.save()

    def remove(self, sid):
        with self.lock:
            n = len(self.data["servers"])
            self.data["servers"] = [s for s in self.data["servers"] if s["id"] != sid]
            if len(self.data["servers"]) == n:
                raise KeyError(sid)
            if self.data["selected"] == sid:
                self.data["selected"] = self.data["servers"][0]["id"] if self.data["servers"] else None
            self.save()

    def select(self, sid):
        with self.lock:
            if not any(s["id"] == sid for s in self.data["servers"]):
                raise ValueError("Server nicht gefunden")
            self.data["selected"] = sid
            self.save()

    def set_settings(self, req, valid_ifaces):
        with self.lock:
            cur = dict(self.data["settings"])
        try:
            mn = int(req.get("min_kbps", cur.get("min_kbps")))
            mx = int(req.get("max_kbps", cur.get("max_kbps")))
            lat = int(req.get("latency_ms", cur.get("latency_ms")))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Bitrate und Latenz müssen Zahlen sein")
        if not 100 <= mn < mx <= 20000:
            raise ValueError("Bitrate: Minimum ab 100, kleiner als Maximum, Maximum höchstens 20000 kbit/s")
        if not 100 <= lat <= 10000:
            raise ValueError("Latenz: 100 bis 10000 ms")
        ups = [u for u in req.get("uplinks", []) if isinstance(u, str)]
        if any(not re.fullmatch(r"[A-Za-z0-9._-]{1,15}", u) for u in ups):
            raise ValueError("Ungültiger Name eines Netzwerks")
        with self.lock:
            before = set(self.data["settings"].get("uplinks", []))
        if any(u not in valid_ifaces and u not in before for u in ups) or not any(u in valid_ifaces for u in ups):
            raise ValueError("Mindestens ein vorhandenes Netzwerk als Sendeweg wählen")
        spread = req.get("spread", cur.get("spread", "best"))
        if spread not in ("best", "all"):
            raise ValueError("Verteilung: beste Leitung bevorzugen oder alle gleichzeitig")
        with self.lock:
            self.data["settings"] = {"min_kbps": mn, "max_kbps": mx, "latency_ms": lat, "uplinks": sorted(set(ups)),
                                     "spread": spread}
            self.save()
