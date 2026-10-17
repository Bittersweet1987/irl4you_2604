"""IRL4YOU BOX Oberfläche: Kameraliste, Gerätenamen, Bildraten-Messung."""

import json
import os
import random
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import dji

from .camservices import HDMI_KEY
from .common import KEY_RE, ROLES, iface_ips, lan_ip


class CameraStore:

    def __init__(self, path, app, stat_url, demo):
        self.path, self.app, self.stat_url, self.demo = path, app, stat_url, demo
        self.lock = threading.Lock()
        self.cams = []
        self.ipfn = lan_ip
        self.ifaces = iface_ips
        self.forgotten = set()
        try:
            with open(path) as f:
                self.cams = json.load(f)
        except (OSError, ValueError):
            pass
        try:
            with open(path + ".removed") as f:
                self.forgotten = {k for k in json.load(f) if isinstance(k, str)}
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.cams, f, indent=1)
        os.replace(tmp, self.path)

    def _save_forgotten(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".removed.tmp"
        with open(tmp, "w") as f:
            json.dump(sorted(self.forgotten)[-200:], f)
        os.replace(tmp, self.path + ".removed")

    def forget(self, key):
        if key and key not in self.forgotten:
            self.forgotten.add(key)
            self._save_forgotten()

    def add(self, name, key, role):
        name = (name or "").strip()[:40]
        if not name:
            raise ValueError("Name fehlt")
        if role not in ROLES:
            raise ValueError("Rolle ungültig")
        key = (key or "").strip().lower() or "cam-" + secrets.token_hex(3)
        if not KEY_RE.match(key):
            raise ValueError("Schlüssel: nur a-z, 0-9, - und _, höchstens 32 Zeichen")
        with self.lock:
            if any(c["key"] == key for c in self.cams):
                raise ValueError("Schlüssel existiert schon")
            if key in self.forgotten:
                self.forgotten.discard(key)
                self._save_forgotten()
            if role in ("main", "pip") and any(c["role"] == role for c in self.cams):
                raise ValueError("Diese Rolle ist schon vergeben")
            cam = {"id": secrets.token_hex(4), "name": name, "key": key, "role": role}
            self.cams.append(cam)
            self.save()
        return cam

    def remove(self, cam_id):
        with self.lock:
            n = len(self.cams)
            self.cams = [c for c in self.cams if c["id"] != cam_id]
            if len(self.cams) != n:
                self.save()
            return len(self.cams) != n

    def auto_add(self):
        live = self.live_streams() or {}
        added = []
        with self.lock:
            known = {c["key"] for c in self.cams}
            for key in sorted(live):
                if key in known or key in self.forgotten or not KEY_RE.match(key) or key.startswith("test-"):
                    continue
                roles = {c["role"] for c in self.cams}
                role = "main" if "main" not in roles else "pip" if "pip" not in roles else "extra"
                cam = {"id": secrets.token_hex(4), "name": f"Kamera {key}", "key": key,
                       "role": role, "auto": True}
                self.cams.append(cam)
                added.append(cam)
            if added:
                self.save()
        return added

    def host_for_iface(self, name):
        for o in self.ifaces():
            if o["iface"] == name:
                return o.get("cam_ip") or o["ip"]
        return None

    def update(self, cam_id, name=None, role=None, iface=None):
        with self.lock:
            cam = next((c for c in self.cams if c["id"] == cam_id), None)
            if not cam:
                raise KeyError(cam_id)
            if iface is not None:
                if not isinstance(iface, str):
                    raise ValueError("Verbindung ungültig")
                if iface and self.host_for_iface(iface) is None:
                    raise ValueError("Unbekannte Verbindung oder keine IPv4-Adresse")
                if iface:
                    cam["iface"] = iface
                else:
                    cam.pop("iface", None)
            if name is not None:
                name = name.strip()[:40]
                if not name:
                    raise ValueError("Name fehlt")
                if any(c["id"] != cam_id and c["name"].casefold() == name.casefold() for c in self.cams):
                    raise ValueError("Diesen Namen hat schon eine andere Kamera")
                cam["name"] = name
            if role is not None:
                if role not in ROLES:
                    raise ValueError("Rolle ungültig")
                if role in ("main", "pip") and any(
                        c["role"] == role and c["id"] != cam_id for c in self.cams):
                    raise ValueError("Diese Rolle ist schon vergeben")
                cam["role"] = role
            self.save()
            return cam

    def swap(self, cam_id, other_id):
        with self.lock:
            i = next((n for n, c in enumerate(self.cams) if c["id"] == cam_id), None)
            j = next((n for n, c in enumerate(self.cams) if c["id"] == other_id), None)
            if i is None or j is None:
                raise KeyError(cam_id if i is None else other_id)
            if i != j:
                self.cams[i], self.cams[j] = self.cams[j], self.cams[i]
                self.save()
            return self.cams[j]

    def move(self, cam_id, before_id=None):
        with self.lock:
            cam = next((c for c in self.cams if c["id"] == cam_id), None)
            if cam is None:
                raise KeyError(cam_id)
            if before_id is not None and before_id != cam_id and not any(c["id"] == before_id for c in self.cams):
                raise KeyError(before_id)
            if before_id == cam_id:
                return cam
            rest = [c for c in self.cams if c is not cam]
            at = next((n for n, c in enumerate(rest) if c["id"] == before_id), len(rest))
            rest.insert(at, cam)
            if [c["id"] for c in rest] != [c["id"] for c in self.cams]:
                self.cams[:] = rest
                self.save()
            return cam

    def live_streams(self):
        if self.demo:
            return {c["key"]: {"fps": 30.0, "mbit": round(6 + random.random() * 2, 1)}
                    for i, c in enumerate(self.cams) if i % 3 != 2}
        if not self.stat_url:
            return None
        hit = getattr(self, "_live", None)
        if hit is not None and time.monotonic() - hit[0] < 1.5:
            return hit[1]
        res = self._live_read()
        self._live = (time.monotonic(), res)
        return res

    def _live_read(self):
        try:
            with urllib.request.urlopen(self.stat_url, timeout=2) as r:
                root = ET.fromstring(r.read())
        except (OSError, ET.ParseError):
            return None
        res = {}
        for app in root.iter("application"):
            if app.findtext("name") != self.app:
                continue
            for st in app.iter("stream"):
                if st.find("publishing") is None:
                    continue
                bw = (int(st.findtext("bw_video") or 0) + int(st.findtext("bw_audio") or 0))
                fps = st.findtext("meta/video/frame_rate")
                key = (st.findtext("name") or "").strip()
                w, h = st.findtext("meta/video/width"), st.findtext("meta/video/height")
                res[key] = {"fps": float(fps) if fps else None, "mbit": round(bw / 1e6, 1),
                            "w": int(w) if w and w.isdigit() else 0, "h": int(h) if h and h.isdigit() else 0}
        return res

    def listing(self, host, addr_for=None):
        main = self.ipfn()
        live = self.live_streams()
        out = []
        for c in self.cams:
            st = None if live is None else live.get(c["key"])
            via, src, host = None, "main", main
            over = addr_for(c["key"]) if addr_for else None
            if c["key"] == HDMI_KEY:
                src = "hdmi"
            elif over and over[0]:
                host, via, src = over[0], over[1], "dji"
            elif c.get("iface") and self.host_for_iface(c["iface"]):
                host, via, src = self.host_for_iface(c["iface"]), c["iface"], "own"
            out.append({**c, "via": via, "via_src": src,
                        "url": "" if src == "hdmi" else f"rtmp://{host}:1935/{self.app}/{c['key']}",
                        "state": "unknown" if live is None else
                                 ("live" if st else "offline"),
                        "fps": st and st["fps"], "mbit": st and st["mbit"],
                        "w": (st or {}).get("w", 0), "h": (st or {}).get("h", 0)})
        return out


class DeviceNames:
    KEY_RE = re.compile(r"^(usb:[0-9a-f]{4}:[0-9a-f]{4}|if:[a-z0-9]{2,15}|net:[a-z0-9]{2,15}|bt:([0-9A-F]{2}:){5}[0-9A-F]{2})$")

    def __init__(self, state_dir):
        self.path = os.path.join(state_dir, "device-names.json")
        self.lock = threading.Lock()

    def _all(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            return {k: v for k, v in d.items() if isinstance(k, str) and self.KEY_RE.match(k) and isinstance(v, str)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def key(usb_id="", iface="", address=""):
        if usb_id:
            return "usb:" + usb_id
        if iface:
            return "if:" + iface
        return "bt:" + address.upper() if address else ""

    def label(self, key, default):
        return self._all().get(key) or default

    def conn_names(self):
        return {k[4:]: v for k, v in self._all().items() if k.startswith("net:") and v}

    def set(self, key, name):
        if not isinstance(key, str) or not self.KEY_RE.match(key):
            raise ValueError("Gerät unbekannt")
        if not isinstance(name, str):
            raise ValueError("Name ungültig")
        name = " ".join(name.split())
        if len(name) > 40 or any(not ch.isprintable() for ch in name):
            raise ValueError("Name: höchstens 40 Zeichen, keine Sonderzeichen")
        with self.lock:
            d = self._all()
            if name:
                d[key] = name
            else:
                d.pop(key, None)
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
            with os.fdopen(fd, "w") as f:
                json.dump(d, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)


class FpsProbe:
    TTL_S, FAIL_TTL_S, WINDOW_S = 120.0, 20.0, 6.0
    COMMON = (24, 25, 30, 50, 60)
    RE_AVG = re.compile(r"rendered: (\d+), dropped: \d+, current: ([\d.]+), average: ([\d.]+)")

    def __init__(self, base="rtmp://127.0.0.1:1935/publish", registry="", demo=False, runner=None):
        self.base, self.registry, self.demo = base, registry, demo
        self.runner = runner or self._gst
        self.lock = threading.Lock()
        self.cache = {}
        self.busy = False

    @classmethod
    def snap(cls, fps):
        for c in cls.COMMON:
            if abs(fps - c) <= 0.04 * c:
                return float(c)
        return round(fps, 1)

    @classmethod
    def parse(cls, out):
        found = [(int(f), float(c)) for f, c, a in cls.RE_AVG.findall(out or "")]
        if len(found) < 2 or found[-1][0] < 45:
            return None
        cur = [c for f, c in found[1:] if c > 0]
        return cls.snap(sum(cur) / len(cur)) if cur else None

    def _gst(self, key):
        cmd = ["gst-launch-1.0", "-v", "rtmpsrc", "location=%s/%s" % (self.base, key), "!", "flvdemux", "name=d", "d.video", "!", "queue", "!", "h264parse", "!",
               "fpsdisplaysink", "text-overlay=false", "video-sink=fakesink", "fps-update-interval=1000", "signal-fps-measurements=true"]
        env = dict(os.environ)
        if self.registry:
            env["GST_REGISTRY"] = self.registry
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        try:
            out, _ = p.communicate(timeout=self.WINDOW_S + 1.0)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        return out

    def _run(self, key):
        fps = None
        try:
            fps = self.parse(self.runner(key))
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            print("Bildrate-Messung von %s: %r" % (key, e), flush=True)
            fps = None
        finally:
            with self.lock:
                now = time.monotonic()
                old = self.cache.get(key)
                if fps is None and old and old[1] is not None and now - old[0] < 3 * self.TTL_S:
                    fps = old[1]
                self.cache[key] = (now, fps)
                self.busy = False

    def get(self, key):
        if self.demo or not isinstance(key, str) or not KEY_RE.match(key):
            return None
        now = time.monotonic()
        with self.lock:
            hit = self.cache.get(key)
            ttl = self.TTL_S if hit and hit[1] is not None else self.FAIL_TTL_S
            if (hit is None or now - hit[0] >= ttl) and not self.busy:
                self.busy = True
                threading.Thread(target=self._run, args=(key,), daemon=True).start()
            return hit[1] if hit else None

    def keep(self, live_keys):
        with self.lock:
            for k in [k for k in self.cache if k not in live_keys]:
                del self.cache[k]


def label_bluetooth(st, names):
    for a in st.get("adapters") or []:
        a["key"] = DeviceNames.key(a.get("usb_id", ""), "", a.get("address", ""))
        default = dji.device_label(a.get("name", ""), a.get("vendor", ""), a.get("usb_id", "")) or ("Eingebauter Bluetooth-Adapter" if not a.get("usb_id") else "Bluetooth-Stick")
        a["label"] = names.label(a["key"], default) if names and a["key"] else default
        a["custom"] = a["label"] != default
    for x in st.get("adapter_problems") or []:
        x["key"] = DeviceNames.key(x.get("id", ""))
        default = dji.device_label(x.get("name", ""), "", x.get("id", ""))
        x["label"] = names.label(x["key"], default) if names and x["key"] else default
    return st
