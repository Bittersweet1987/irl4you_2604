"""IRL4YOU BOX Oberfläche: Wächter für USB-Ereignisse und ausgefallene Kameras."""

import json
import os
import re
import subprocess
import threading
import time

from .camservices import HDMI_KEY
from .common import read


class UsbWatch:
    WINDOW = 24 * 3600.0
    BACK_SHOW = 300.0
    GRACE = 120.0
    EVERY = 20.0
    KEEP = 20
    RE_LINE = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.,]+[+-]\d\d:\d\d) (.*)$")
    RE_PROD = re.compile(r"^usb (\d+-[\d.]+): Product: (.{1,80})$")
    RE_NEW = re.compile(r"^usb (\d+-[\d.]+): new .*USB device number \d+")
    RE_ID = re.compile(r"^usb (\d+-[\d.]+): New USB device found, idVendor=([0-9a-fA-F]{4}), idProduct=([0-9a-fA-F]{4})")
    RE_GONE = re.compile(r"^usb (\d+-[\d.]+): USB disconnect, device number \d+$")
    RE_HUB = re.compile(r"^usb usb(\d+)-port(\d+): (disabled by hub|over-current condition)")
    CATS = (("wlan", re.compile(r"(?i)802\.11|wlan|wireless|wi-?fi|\bnic\b|rtl88|rtl81|ralink|mediatek.*wlan")),
            ("bt", re.compile(r"(?i)bluetooth|\bbt\d|usb-bt")),
            ("net", re.compile(r"(?i)rndis|ethernet|\bcdc\b|router|modem|lte|\b4g\b|\b5g\b|mudi|gl-?inet|tether|android|hotspot|gadget")),
            ("cam", re.compile(r"(?i)camera|uvc|capture|hdmi|video|osmo|action|dji|webcam")))

    def __init__(self, path, runner=None, clock=time.time, demo=False, uptime=None):
        self.path, self.runner, self.clock, self.demo = path, runner or self._dmesg, clock, demo
        self.uptime = uptime or (self._uptime if clock is time.time else (lambda: None))
        self.lock = threading.Lock()
        self.events, self.last = [], 0.0
        self.demo_t, self.demo_closed = clock() - 2100, False
        try:
            with open(path) as f:
                saved = json.load(f)
            if isinstance(saved, list):
                self.events = [e for e in saved if isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and isinstance(e.get("cat"), str)][-self.KEEP:]
        except (OSError, ValueError):
            pass
        boot = self._boot()
        if boot is not None:
            self.events = [e for e in self.events if e["t"] >= boot]

    @staticmethod
    def _uptime():
        try:
            return float(read("/proc/uptime", "").split()[0])
        except (OSError, ValueError, IndexError):
            return None

    def _boot(self):
        up = self.uptime()
        return self.clock() - up if isinstance(up, (int, float)) and up >= 0 else None

    @staticmethod
    def _dmesg():
        try:
            return subprocess.run(["dmesg", "--time-format", "iso"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    @classmethod
    def category(cls, name):
        for cat, rx in cls.CATS:
            if rx.search(name or ""):
                return cat
        return "other"

    def _parse(self, text):
        import datetime
        prod, ids, out, backs = {}, {}, [], []
        boot = self._boot()
        for raw in text.splitlines()[-6000:]:
            m = self.RE_LINE.match(raw)
            if not m:
                continue
            try:
                t = datetime.datetime.fromisoformat(m.group(1).replace(",", ".")).timestamp()
            except ValueError:
                continue
            msg = m.group(2)
            a = self.RE_PROD.match(msg)
            if a:
                prod[a.group(1)] = a.group(2).strip()
                continue
            n = self.RE_NEW.match(msg)
            if n:
                backs.append((t, n.group(1)))
                continue
            i = self.RE_ID.match(msg)
            if i:
                ids[i.group(1)] = "%s:%s" % (i.group(2).lower(), i.group(3).lower())
                continue
            g = self.RE_GONE.match(msg)
            if g:
                if boot is None or t >= boot + self.GRACE:
                    out.append({"t": round(t, 1), "port": g.group(1), "cat": self.category(prod.get(g.group(1), "")), "why": "gone",
                                "name": prod.get(g.group(1), ""), "ids": ids.get(g.group(1), "")})
                continue
            h = self.RE_HUB.match(msg)
            if h:
                port = "%s-%s" % (h.group(1), h.group(2))
                if boot is None or t >= boot + self.GRACE:
                    out.append({"t": round(t, 1), "port": port, "cat": self.category(prod.get(port, "")), "why": "emi" if h.group(3).startswith("disabled") else "over",
                                "name": prod.get(port, ""), "ids": ids.get(port, "")})
        merged = []
        for e in sorted(out, key=lambda x: x["t"]):
            if merged and merged[-1]["port"] == e["port"] and e["t"] - merged[-1]["t"] < 5:
                if e["why"] != "gone":
                    merged[-1]["why"] = e["why"]
                continue
            merged.append(e)
        for e in merged:
            for bt, bport in backs:
                if bport == e["port"] and 0 < bt - e["t"] < 3600:
                    e["back"] = round(bt, 1)
                    break
        return merged

    def scan(self):
        with self.lock:
            now = self.clock()
            if now - self.last < self.EVERY:
                return
            self.last = now
        try:
            found = self._parse(self.runner())
        except Exception:
            return
        with self.lock:
            have = {(round(e["t"]), e.get("port")): e for e in self.events}
            new = [e for e in found if (round(e["t"]), e["port"]) not in have]
            changed = False
            for f in found:
                old = have.get((round(f["t"]), f["port"]))
                if old is not None and f.get("back") and not old.get("back"):
                    old["back"] = f["back"]
                    changed = True
            if not new and not changed:
                return
            self.events = (self.events + new)[-self.KEEP:]
            data = list(self.events)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def alerts(self):
        if self.demo:
            return [] if self.demo_closed else [{"level": "warn", "kind": "usb", "cat": "wlan", "why": "emi", "t": int(self.demo_t), "back": False}]
        self.scan()
        now = self.clock()
        with self.lock:
            fresh = [e for e in self.events if now - e["t"] <= self.WINDOW and not e.get("ack") and not (e.get("back") and now - e["back"] > self.BACK_SHOW)]
        return [{"level": "warn", "kind": "usb", "cat": e["cat"], "why": e.get("why", "gone"), "t": int(e["t"]), "back": bool(e.get("back")),
                 "name": str(e.get("name") or "")[:80], "port": str(e.get("port") or "")[:12], "ids": str(e.get("ids") or "")[:9]}
                for e in sorted(fresh, key=lambda x: -x["t"])[:2]]

    def dismiss(self, t):
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            raise ValueError("Ungültige Anfrage")
        if self.demo:
            self.demo_closed = True
            return True
        found = False
        with self.lock:
            for e in self.events:
                if int(e["t"]) == int(t) and not e.get("ack"):
                    e["ack"] = True
                    found = True
            data = list(self.events)
        if found and not self.demo:
            try:
                tmp = self.path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self.path)
            except OSError:
                pass
        return found


class OutageWatch:
    DOWN = 20.0
    MAX = 6 * 3600.0

    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.seen = {}
        self.since = {}
        self.hdmi_since = None
        self.closed = set()

    def dismiss(self, kind, t):
        if kind not in ("cam", "hdmi") or isinstance(t, bool) or not isinstance(t, (int, float)):
            raise ValueError("Ungültige Anfrage")
        with self.lock:
            self.closed.add((kind, int(t)))
        return True

    def alerts(self, cameras, hdmi=None, parked=()):
        now = self.clock()
        out = []
        with self.lock:
            self.closed = {c for c in self.closed if now - c[1] <= self.MAX}
            keys = set()
            for c in cameras or []:
                key = c.get("key")
                if not isinstance(key, str):
                    continue
                keys.add(key)
                state = c.get("state")
                if key in parked:
                    self.since.pop(key, None)
                    continue
                if state == "live":
                    self.seen[key] = True
                    self.since.pop(key, None)
                elif state == "offline" and self.seen.get(key):
                    self.since.setdefault(key, now)
                    t = self.since[key]
                    if key != HDMI_KEY and now - t >= self.DOWN and now - t <= self.MAX and ("cam", int(t)) not in self.closed:
                        kind = "dji" if str(key).startswith("dji-") else "cam"
                        out.append({"level": "warn", "kind": "cam", "cam": kind, "name": str(c.get("name") or "")[:40], "t": int(t)})
            for k in list(self.seen):
                if k not in keys:
                    self.seen.pop(k, None)
                    self.since.pop(k, None)
            bad = False
            if isinstance(hdmi, dict) and hdmi.get("service") is not False and hdmi.get("available") is not False:
                en = bool((hdmi.get("settings") or {}).get("enabled"))
                sig = hdmi.get("signal") or {}
                bad = hdmi.get("state") == "error" or (en and hdmi.get("signal_known") and sig.get("plugged") is False)
            if bad:
                if self.hdmi_since is None:
                    self.hdmi_since = now
                if self.DOWN <= now - self.hdmi_since <= self.MAX and ("hdmi", int(self.hdmi_since)) not in self.closed:
                    out.append({"level": "warn", "kind": "hdmi", "src": (hdmi.get("settings") or {}).get("source", "hdmi"), "t": int(self.hdmi_since)})
            else:
                self.hdmi_since = None
        return out
