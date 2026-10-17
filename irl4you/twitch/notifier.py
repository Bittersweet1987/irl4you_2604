"""IRL4YOU BOX Twitch: Benachrichtigungen und Systemwarnungen."""

import json
import math
import os
import re
import threading
import time

from .common import belacoder_running
from .irc import TwitchChat
from .store import TwitchStore


class TwitchNotifier:
    POLL_S = 10
    GAP_S = 3
    FRESH_S = 300
    BACKOFF_S = (30, 60, 120, 120)
    TEST_EVERY_S = 10
    TEST_TEXT = "Test: IRL4YOU BOX"

    def __init__(self, store, djisvc, cams, send, chat=None, demo=False, mono=time.monotonic, wall=time.time, sleep=time.sleep):
        self.store, self.djisvc, self.cams, self.send = store, djisvc, cams, send
        self.chat, self.demo = chat or TwitchChat(), demo
        self.mono, self.wall, self.sleep = mono, wall, sleep
        self.lock = threading.Lock()
        self.net_lock = threading.Lock()
        self.tries = {}
        self.last = None
        self.last_send = None
        self.test_at = None
        self.stop_ev = threading.Event()

    @staticmethod
    def camera_text(name):
        t = " ".join(str(name or "").split())
        t = "".join(ch for ch in t if ch.isprintable()).lstrip("/. ")
        return t[:40].strip()

    @staticmethod
    def render(template, name, percent):
        return re.sub(r"\{(Kamera|Prozent)\}", lambda m: name if m.group(1) == "Kamera" else str(percent), template)

    @staticmethod
    def _percent(e):
        v = e.get("battery") if isinstance(e, dict) else None
        return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100 else None

    def _fresh(self, e):
        age = e.get("battery_age")
        return isinstance(age, (int, float)) and not isinstance(age, bool) and 0 <= age <= self.FRESH_S

    def _live(self):
        return bool(self.send._active() or belacoder_running())

    def _camera_name(self, key):
        cam = next((c for c in list(self.cams.cams) if c.get("key") == key), None)
        return self.camera_text(cam.get("name") if cam else "") or key

    def _deliver(self, cfg, text, wait=False):
        with self.net_lock:
            if wait and self.last_send is not None:
                left = self.GAP_S - (self.mono() - self.last_send)
                if left > 0:
                    self.sleep(left)
            ok, msg = self.chat.send(cfg["login"], cfg["token"], cfg["channel"], text)
            self.last_send = self.mono()
        return ok, msg

    def tick(self):
        cfg = self.store.notify_settings()
        if not (cfg["enabled"] and cfg["login"] and cfg["channel"] and cfg["token"]):
            with self.lock:
                self.tries.clear()
            return
        extras = self.djisvc.camera_extras() or {}
        thr = cfg["threshold"]
        for key in self.store.warned_keys():
            e = extras.get(key)
            pct = self._percent(e)
            if e and (e.get("charging") is True or (pct is not None and pct >= thr + 10)):
                self.store.unwarn(key)
        live, due = None, []
        for key in sorted(extras):
            e = extras[key]
            pct = self._percent(e)
            if pct is None or pct > thr or e.get("charging") is True or not self._fresh(e) or self.store.is_warned(key):
                continue
            if cfg["only_live"]:
                live = self._live() if live is None else live
                if not live:
                    continue
            due.append((key, pct))
        keys = {d[0] for d in due}
        with self.lock:
            self.tries = {k: v for k, v in self.tries.items() if k in keys}
        for key, pct in due:
            now = self.mono()
            t = self.tries.get(key)
            if t is not None and (t["at"] is None or now < t["at"]):
                continue
            if self.last_send is not None and now - self.last_send < self.GAP_S:
                break
            self._warn(cfg, key, pct)

    def _warn(self, cfg, key, pct):
        text = self.render(cfg["message"], self._camera_name(key), pct)
        ok, msg = self._deliver(cfg, text)
        with self.lock:
            if ok:
                self.tries.pop(key, None)
                self.last = {"ok": True, "time": int(self.wall()), "text": text}
            else:
                n = self.tries.get(key, {}).get("n", 0) + 1
                self.tries[key] = {"n": n, "at": self.mono() + self.BACKOFF_S[n - 1] if n <= len(self.BACKOFF_S) else None}
                self.last = {"ok": False, "time": int(self.wall()), "text": msg}
        if ok:
            self.store.mark_warned(key, self.wall())

    def run(self):
        while not self.stop_ev.is_set():
            try:
                self.tick()
            except Exception as e:
                print("twitch:", type(e).__name__)
            self.stop_ev.wait(self.POLL_S)

    def status(self):
        out = self.store.public()
        with self.lock:
            last = dict(self.last) if self.last else None
            waits = [t["at"] for t in self.tries.values() if t["at"] is not None]
            gave_up = any(t["at"] is None for t in self.tries.values())
        st = {"ok": None, "time": None, "text": "", "retry_at": None, "gave_up": gave_up}
        if last:
            st.update(ok=last["ok"], time=last["time"], text=last["text"])
            if not last["ok"] and waits:
                st["retry_at"] = int(self.wall() + max(0.0, min(waits) - self.mono()))
        out["status"] = st
        return out

    def save(self, req):
        self.store.set(req)
        with self.lock:
            self.tries.clear()
        return self.status()

    def test(self):
        cfg = self.store.notify_settings()
        if not (cfg["channel"] and cfg["login"] and cfg["token"]):
            raise ValueError(TwitchStore.ERR_MISSING)
        with self.lock:
            now = self.mono()
            if self.test_at is not None and now - self.test_at < self.TEST_EVERY_S:
                raise PermissionError("Bitte kurz warten")
            self.test_at = now
        ok, msg = (True, "Demo: gesendet.") if self.demo else self._deliver(cfg, self.TEST_TEXT, wait=True)
        with self.lock:
            self.last = {"ok": ok, "time": int(self.wall()), "text": self.TEST_TEXT if ok else msg}
        return {"ok": ok, "message": msg}



class SysAlerts:
    METRICS = (("temp", "CPU-Temperatur", "°C", 3, (40, 100), 65), ("cpu", "CPU-Auslastung", "%", 5, (20, 100), 75), ("ram", "RAM-Auslastung", "%", 5, (20, 100), 60))
    DEFAULT_ALERT = "Warnung: {Name} bei {Wert} (Grenze {Grenze})"
    DEFAULT_OK = "{Name} wieder normal ({Wert})"
    DEFAULTS = {"enabled": False, "cooldown": 10, "recover": True, "only_live": True, "msg_alert": DEFAULT_ALERT, "msg_ok": DEFAULT_OK,
                **{k: {"on": True, "limit": dflt} for k, _n, _u, _h, _r, dflt in METRICS}}
    POLL_S = 10
    SUSTAIN = 3
    RETRY_S = 60
    COOLDOWN = (1, 120)

    def __init__(self, path, notifier, sampler, demo=False, mono=time.monotonic, wall=time.time):
        self.path, self.notifier, self.sampler, self.demo = path, notifier, sampler, demo
        self.mono, self.wall = mono, wall
        self.lock = threading.Lock()
        self.data = json.loads(json.dumps(self.DEFAULTS))
        self.state = {k: {"over": 0, "alerting": False, "last": None, "retry": None, "pending_ok": False} for k, *_ in self.METRICS}
        self.last = None
        self.stop_ev = threading.Event()
        try:
            with open(path) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = None
        if isinstance(saved, dict):
            try:
                self.data = self._merge(self.data, saved, strict=False)
            except ValueError:
                pass

    @classmethod
    def _int(cls, v, lo, hi, error):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise ValueError(error)
        return v

    @classmethod
    def _merge(cls, base, req, strict=True):
        new = json.loads(json.dumps(base))

        def take(fn):
            try:
                fn()
            except ValueError:
                if strict:
                    raise
        for key in ("enabled", "recover", "only_live"):
            if key in req:
                if isinstance(req[key], bool):
                    new[key] = req[key]
                elif strict:
                    raise ValueError("ja oder nein")
        if "cooldown" in req:
            def f():
                new["cooldown"] = cls._int(req["cooldown"], cls.COOLDOWN[0], cls.COOLDOWN[1], "Pause: Zahl von %d bis %d Minuten" % cls.COOLDOWN)
            take(f)
        for key, name, unit, _h, (lo, hi), _d in cls.METRICS:
            sub = req.get(key)
            if isinstance(sub, dict):
                if "on" in sub:
                    if isinstance(sub["on"], bool):
                        new[key]["on"] = sub["on"]
                    elif strict:
                        raise ValueError("ja oder nein")
                if "limit" in sub:
                    def g(key=key, sub=sub, name=name, unit=unit, lo=lo, hi=hi):
                        new[key]["limit"] = cls._int(sub["limit"], lo, hi, "%s: Zahl von %d bis %d" % (name, lo, hi))
                    take(g)
            elif sub is not None and strict:
                raise ValueError("Ungültige Anfrage")
        for key in ("msg_alert", "msg_ok"):
            if key in req:
                def h(key=key):
                    new[key] = TwitchStore._message(req[key])
                take(h)
        return new

    def _write(self, data):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def save(self, req):
        if not isinstance(req, dict):
            raise ValueError("Ungültige Anfrage")
        with self.lock:
            new = self._merge(self.data, req, strict=True)
            try:
                self._write(new)
            except OSError:
                raise RuntimeError("Die Einstellungen konnten nicht gespeichert werden")
            self.data = new
            for st in self.state.values():
                st.update(over=0, retry=None)
        return self.status()

    @staticmethod
    def render(template, name, value, limit):
        vals = {"Name": name, "Wert": value, "Grenze": limit}
        return re.sub(r"\{(Name|Wert|Grenze)\}", lambda m: vals[m.group(1)], template)

    @staticmethod
    def fmt(v, unit):
        return "%d %s" % (round(v), unit)

    def values(self):
        try:
            s = self.sampler.sample() or {}
        except Exception:
            return {"temp": None, "cpu": None, "ram": None}

        def num(v):
            return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None
        return {"temp": num(s.get("temp_c")), "cpu": num((s.get("cpu") or {}).get("avg")), "ram": num((s.get("mem") or {}).get("used_pct"))}

    def _creds(self):
        cfg = self.notifier.store.notify_settings()
        return cfg if (cfg.get("login") and cfg.get("channel") and cfg.get("token")) else None

    def _live(self):
        return self.notifier._live()

    def _send(self, cfg, text):
        ok, msg = self.notifier._deliver(cfg, text, wait=True)
        with self.lock:
            self.last = {"ok": ok, "time": int(self.wall()), "text": text if ok else msg}
        return ok

    def tick(self):
        with self.lock:
            data = json.loads(json.dumps(self.data))
        if not data["enabled"]:
            self._reset()
            return
        cfg = self._creds()
        if cfg is None:
            self._reset()
            return
        if data["only_live"] and not self._live():
            self._reset(keep_alert=True)
            return
        vals = self.values()
        now = self.mono()
        pause = data["cooldown"] * 60
        for key, name, unit, hyst, _r, _d in self.METRICS:
            m, v = data[key], vals[key]
            st = self.state[key]
            if not m["on"] or v is None:
                st.update(over=0)
                continue
            limit = m["limit"]
            st["over"] = st["over"] + 1 if v >= limit else 0
            if st["retry"] is not None and now < st["retry"]:
                continue
            if st["over"] >= self.SUSTAIN and (st["last"] is None or now - st["last"] >= pause):
                text = self.render(data["msg_alert"], name, self.fmt(v, unit), self.fmt(limit, unit))
                if self._send(cfg, text):
                    st.update(alerting=True, last=now, retry=None, pending_ok=data["recover"])
                else:
                    st["retry"] = now + self.RETRY_S
            elif st["alerting"] and v < limit - hyst:
                st["alerting"] = False
                if st["pending_ok"] and data["recover"]:
                    text = self.render(data["msg_ok"], name, self.fmt(v, unit), self.fmt(limit, unit))
                    if not self._send(cfg, text):
                        st["alerting"], st["retry"] = True, now + self.RETRY_S
                        continue
                st["pending_ok"] = False

    def _reset(self, keep_alert=False):
        for st in self.state.values():
            st.update(over=0, retry=None)
            if not keep_alert:
                st.update(alerting=False, pending_ok=False)

    def run(self):
        while not self.stop_ev.is_set():
            try:
                self.tick()
            except Exception as e:
                print("sysalerts:", type(e).__name__)
            self.stop_ev.wait(self.POLL_S)

    def status(self):
        with self.lock:
            d = json.loads(json.dumps(self.data))
            last = dict(self.last) if self.last else None
        vals = self.values()
        return dict(d, ready=self._creds() is not None,
                    values={k: (None if vals[k] is None else round(vals[k], 1)) for k in vals},
                    alerting=[k for k, st in self.state.items() if st["alerting"]], last=last)
