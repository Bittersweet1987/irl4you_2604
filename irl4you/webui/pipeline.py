"""IRL4YOU BOX Oberfläche: Bildaufbau: gespeicherte Auswahl (Hauptbild, kleine Bilder, Ton)."""

import json
import os
import threading

import pipbox_live

from .common import KEY_RE
from .pipeline_build import PipelineBuild
from .pipeline_plugins import (DEFAULT_MAIN_DELAY_MS, DEFAULT_PIP_DELAY_MS, DELAY_KEYS, FREE, SEND_STATUS, SIZE_MAX, SIZE_MIN,
    STYLE_SLOTS, clean_styles, pip_corners, plugin_style)


class PipelineStore(PipelineBuild):
    DEFAULT = {"type": "single", "main": "", "pip": "", "corner": 3, "size_pct": 25, "size_pct2": 25, "size_pct3": 25, "audio": "main",
               "pip2": "", "corner2": 2, "pip3": "", "corner3": 0, "x": 500, "y": 500, "x2": 500, "y2": 500, "x3": 500, "y3": 500, "main_delay_ms": DEFAULT_MAIN_DELAY_MS,
               "pip_delay_ms": DEFAULT_PIP_DELAY_MS, "pip2_delay_ms": DEFAULT_PIP_DELAY_MS,
               "pip3_delay_ms": DEFAULT_PIP_DELAY_MS, "auto_failover": True, "swap_cams": 0, "always_ready": False, "facecam": ""}
    # Bildaufbau ist immer Bild-in-Bild; ohne kleines Bild (eine Kamera) bleibt der Typ "single". Mit kleinem Bild gilt immer "Alle Kameras immer bereit"
    # und der Tausch des Hauptbilds über alle Kameras (keine Einstellung mehr in der Oberfläche).

    SLOTS = ("main", "pip", "pip2", "pip3")

    Q = "queue max-size-time=10000000000 max-size-buffers=1000 max-size-bytes=41943040"

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.cfg = dict(self.DEFAULT)
        try:
            with open(path) as f:
                self.cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        self.cfg["styles"] = clean_styles(self.cfg.get("styles"))

    def save(self):
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
        with os.fdopen(fd, "w") as f:
            json.dump(self.cfg, f, indent=1)
        os.replace(tmp, self.path)
        self.write_delay_file()

    def write_delay_file(self):
        if self.path == os.devnull:
            return
        d = os.path.join(os.path.dirname(os.path.abspath(self.path)), "main-delay-ms")
        try:
            base = None
            try:
                with open(SEND_STATUS) as f:
                    base = (json.load(f).get("swap") or {}).get("cams")
            except (OSError, ValueError, AttributeError):
                pass
            vals = self.delay_values(self.cfg, base if isinstance(base, list) else None)
            with open(d + ".tmp", "w") as f:
                f.write(" ".join(map(str, vals)) + "\n")
            os.chmod(d + ".tmp", 0o644)
            os.replace(d + ".tmp", d)
        except OSError:
            pass

    SLOT_DELAY = {"pip": "pip_delay_ms", "pip2": "pip2_delay_ms", "pip3": "pip3_delay_ms"}

    @classmethod
    def facecam_slot(cls, c):
        k = c.get("facecam")
        if not k or c.get("type") != "pip":
            return None
        return next((s for s in cls.SLOTS if c.get(s) == k), None)

    @classmethod
    def _facecam_keeps_the_sound(cls, c):
        if not c.get("facecam"):
            return
        slot = cls.facecam_slot(c)
        if slot is None:
            c["facecam"] = ""
        elif slot != "main" and c.get(slot) in (c.get("inactive") or []):
            c["audio"] = "main"
        else:
            c["audio"] = slot

    def set_facecam(self, slot):
        if slot not in ("", "pip", "pip2", "pip3"):
            raise ValueError("Facecam: eines der kleinen Bilder oder keine")
        with self.lock:
            c = self.cfg
            if c.get("type") != "pip":
                raise ValueError("Das gibt es nur bei der Art Bild-in-Bild")
            if slot:
                key = c.get(slot)
                if not key:
                    raise ValueError("Dieses kleine Bild ist nicht belegt")
                if key in (c.get("inactive") or []):
                    raise ValueError("Diese Kamera ist deaktiviert und kann nicht die Facecam sein")
                c["facecam"] = key
            else:
                c["facecam"] = ""
            self.save()
            return slot or "main"

    def _carry_facecam(self, new):
        old = self.cfg.get("facecam")
        if not old or new.get("type") != "pip":
            return ""
        slot = self.facecam_slot(self.cfg)
        here = {new.get(s) for s in self.SLOTS} - {""}
        if slot in ("pip", "pip2", "pip3"):
            return new.get(slot) or (old if old in here else "")
        return old if slot == "main" and old in here else ""

    def swap_main_pip(self, with_key=None):
        with self.lock:
            c = self.cfg
            if c.get("type") != "pip" or not c.get("pip") or not c.get("main"):
                raise ValueError("Zum Tauschen braucht es ein Hauptbild und ein kleines Bild")
            slot = "pip"
            if with_key:
                slot = next((k for k in self.SLOT_DELAY if c.get(k) == with_key), None)
                if slot is None:
                    raise ValueError("Diese Kamera ist gerade nicht als kleines Bild im Bild")
            dk = self.SLOT_DELAY[slot]
            c["main"], c[slot] = c[slot], c["main"]
            c["main_delay_ms"], c[dk] = c.get(dk, 0), c.get("main_delay_ms", 0)
            if c.get("inactive"):
                rest = [k for k in c["inactive"] if k != c["main"]]
                if rest:
                    c["inactive"] = rest
                else:
                    c.pop("inactive")
            self._facecam_keeps_the_sound(c)
            styles = clean_styles(c.get("styles"))
            idx = STYLE_SLOTS[list(self.SLOT_DELAY).index(slot)]
            shown = not styles[idx]["visible"]
            if shown:
                styles[idx]["visible"] = True
                c["styles"] = styles
            self.save()
            return shown

    DELAY_OF = {"main": "main_delay_ms", "pip": "pip_delay_ms", "pip2": "pip2_delay_ms", "pip3": "pip3_delay_ms"}

    def assign_slot(self, slot, key, camera_keys):
        """Eine Kamera auf einen Platz des Bildaufbaus legen (Hauptbild oder kleines Bild). Liegt sie schon auf einem anderen Platz, tauschen beide.
        Gibt (Art, Bild erschienen) zurück: Art ist "same", "swap" (beide Kameras bleiben im Bild) oder "replace" (die neue Kamera war noch nicht im Bild)."""
        with self.lock:
            c = self.cfg
            if c.get("type") != "pip" or slot not in self.SLOTS or not c.get(slot):
                raise ValueError("Dieser Platz ist im Bildaufbau nicht belegt")
            if key not in camera_keys:
                raise ValueError("Kamera unbekannt")
            old = c[slot]
            if key == old:
                return "same", False
            other = next((s for s in self.SLOTS if s != slot and c.get(s) == key), None)
            if other:
                c[slot], c[other] = key, old
                c[self.DELAY_OF[slot]], c[self.DELAY_OF[other]] = c.get(self.DELAY_OF[other], 0), c.get(self.DELAY_OF[slot], 0)
                kind, touched = "swap", [slot, other]
            else:
                c[slot] = key
                c[self.DELAY_OF[slot]] = DEFAULT_MAIN_DELAY_MS if slot == "main" else DEFAULT_PIP_DELAY_MS
                kind, touched = "replace", [slot]
            rest = [k for k in (c.get("inactive") or []) if k != key and k != c["main"]]
            if rest:
                c["inactive"] = rest
            else:
                c.pop("inactive", None)
            self._facecam_keeps_the_sound(c)
            styles = clean_styles(c.get("styles"))
            shown = False
            for s in touched:
                if s != "main":
                    idx = STYLE_SLOTS[list(self.SLOT_DELAY).index(s)]
                    if not styles[idx]["visible"]:
                        styles[idx]["visible"] = True
                        shown = True
            if shown:
                c["styles"] = styles
            self.save()
            return kind, shown

    def set(self, req, camera_keys):
        if req.get("type", "pip") not in ("single", "pip"):
            raise ValueError("Art des Bildaufbaus unbekannt")
        main = str(req.get("main", ""))
        if main not in camera_keys:
            raise ValueError("Hauptkamera: bitte eine vorhandene Kamera wählen")
        t = "pip" if str(req.get("pip", "") or "") else "single"     # eine Kamera: kein kleines Bild nötig
        cfg = {"type": t, "main": main, "pip": "", "corner": 3, "size_pct": 25, "size_pct2": 25, "size_pct3": 25, "audio": "main",
               "pip2": "", "corner2": 2, "pip3": "", "corner3": 0, "x": 500, "y": 500, "x2": 500, "y2": 500, "x3": 500, "y3": 500, "main_delay_ms": DEFAULT_MAIN_DELAY_MS,
               "pip_delay_ms": DEFAULT_PIP_DELAY_MS, "pip2_delay_ms": DEFAULT_PIP_DELAY_MS,
               "pip3_delay_ms": DEFAULT_PIP_DELAY_MS, "auto_failover": req.get("auto_failover", True) is not False, "swap_cams": 0,
               "always_ready": t == "pip"}
        cfg["styles"] = clean_styles(req.get("styles"), self.cfg.get("styles"), strict=True)
        if t == "pip":
            cfg["swap_cams"] = 4
            pipk = str(req.get("pip", ""))
            if pipk not in camera_keys or pipk == main:
                raise ValueError("Kleines Bild: eine andere vorhandene Kamera wählen")
            try:
                corner, pct = int(req.get("corner", 3)), int(req.get("size_pct", 25))
                pct2, pct3 = int(req.get("size_pct2", pct)), int(req.get("size_pct3", pct))
            except (TypeError, ValueError):
                raise ValueError("Ecke und Größe müssen Zahlen sein")
            if corner not in range(len(pip_corners())) or not all(SIZE_MIN <= v <= SIZE_MAX for v in (pct, pct2, pct3)):
                raise ValueError("Position aus der Liste wählen, Skalierung jedes kleinen Bildes %d bis %d Prozent" % (SIZE_MIN, SIZE_MAX))
            audio = req.get("audio", "main")
            if audio not in ("main", "pip", "pip2", "pip3"):
                raise ValueError("Ton: Hauptbild oder eines der kleinen Bilder")
            cfg.update(pip=pipk, corner=corner, size_pct=pct, size_pct2=pct2, size_pct3=pct3, audio=audio)
            for key in ("x", "y", "x2", "y2", "x3", "y3"):
                try:
                    val = int(req.get(key, 500))
                except (TypeError, ValueError):
                    raise ValueError("Position muss eine Zahl sein")
                cfg[key] = max(0, min(1000, val))
            for key, dflt in (("main_delay_ms", DEFAULT_MAIN_DELAY_MS), ("pip_delay_ms", DEFAULT_PIP_DELAY_MS),
                              ("pip2_delay_ms", DEFAULT_PIP_DELAY_MS), ("pip3_delay_ms", DEFAULT_PIP_DELAY_MS)):
                try:
                    delay = int(req.get(key, dflt)) if req.get(key) != "" else 0
                except (TypeError, ValueError):
                    raise ValueError("Verzögerung muss eine Zahl sein (Millisekunden)")
                if not 0 <= delay <= 3000:
                    raise ValueError("Verzögerung: 0 bis 3000 ms")
                cfg[key] = delay
            pip2 = str(req.get("pip2", "") or "")
            if pip2:
                try:
                    corner2 = int(req.get("corner2", 2))
                except (TypeError, ValueError):
                    raise ValueError("Ecke muss eine Zahl sein")
                if pip2 not in camera_keys or pip2 in (main, pipk):
                    raise ValueError("Zweites kleines Bild: eine weitere vorhandene Kamera wählen")
                if corner2 not in range(len(pip_corners())) or (corner2 == corner and corner != FREE):
                    raise ValueError("Zweites kleines Bild: eine andere Position als das erste wählen")
                cfg.update(pip2=pip2, corner2=corner2)
            else:
                cfg["pip2_delay_ms"] = 0
            pip3 = str(req.get("pip3", "") or "")
            if pip3 and pip2:
                try:
                    corner3 = int(req.get("corner3", 0))
                except (TypeError, ValueError):
                    raise ValueError("Ecke muss eine Zahl sein")
                if pip3 not in camera_keys or pip3 in (main, pipk, pip2):
                    raise ValueError("Drittes kleines Bild: eine weitere vorhandene Kamera wählen")
                if corner3 not in range(len(pip_corners())) or (corner3 != FREE and corner3 in (corner, cfg["corner2"])):
                    raise ValueError("Drittes kleines Bild: eine andere Position als die ersten beiden wählen")
                cfg.update(pip3=pip3, corner3=corner3)
            else:
                cfg["pip3_delay_ms"] = 0
            if cfg["audio"] == "pip2" and not cfg["pip2"] or cfg["audio"] == "pip3" and not cfg["pip3"]:
                raise ValueError("Ton: dieses kleine Bild ist nicht gewählt")
        pips = {cfg.get(k) for k in ("pip", "pip2", "pip3")} - {""}
        old = req.get("inactive") if "inactive" in req else self.cfg.get("inactive", [])
        inactive = list(dict.fromkeys(k for k in (old if isinstance(old, list) else []) if isinstance(k, str) and k in pips))[:3]
        if t == "pip" and inactive:
            cfg["inactive"] = inactive
        fc = self._carry_facecam(cfg)
        if fc:
            cfg["facecam"] = fc
        with self.lock:
            self.cfg = cfg
            self.save()

    def set_active(self, key, active):
        if not isinstance(active, bool) or not isinstance(key, str) or not KEY_RE.match(key):
            raise ValueError("Kamera oder Zustand ungültig")
        with self.lock:
            c = self.cfg
            if c.get("type") != "pip":
                raise ValueError("Das gibt es nur bei der Art Bild-in-Bild")
            if key == c.get("main"):
                raise ValueError("Das Hauptbild lässt sich nicht deaktivieren")
            if key not in (c.get("pip"), c.get("pip2"), c.get("pip3")):
                raise ValueError("Diese Kamera ist nicht im Bild")
            cur = [k for k in (c.get("inactive") or []) if k != key]
            if not active:
                cur.append(key)
            if cur:
                c["inactive"] = cur
            else:
                c.pop("inactive", None)
            self.save()

    def set_view(self, visible=None, audio=None):
        with self.lock:
            c = self.cfg
            if c.get("type") != "pip":
                raise ValueError("Das gibt es nur bei der Art Bild-in-Bild")
            if visible is not None:
                if not isinstance(visible, dict) or any(k not in STYLE_SLOTS or not isinstance(v, bool) for k, v in visible.items()):
                    raise ValueError("Bild einblenden: Stelle 1 bis 3, ja oder nein")
                for k, v in visible.items():
                    if k == "2" and not c.get("pip2") or k == "3" and not c.get("pip3") or k == "1" and not c.get("pip"):
                        raise ValueError("Dieses kleine Bild gibt es nicht")
            if audio is not None:
                if not isinstance(audio, str) or audio not in self.AUDIO_POS:
                    raise ValueError("Ton: Hauptbild oder eines der kleinen Bilder")
                if audio == "pip" and not c.get("pip") or audio == "pip2" and not c.get("pip2") or audio == "pip3" and not c.get("pip3"):
                    raise ValueError("Ton: dieses kleine Bild gibt es nicht")
                if audio != "main" and c.get(audio) in (c.get("inactive") or []):
                    raise ValueError("Ton: eine deaktivierte Kamera kann nicht die Tonquelle sein")
            styles = clean_styles(c.get("styles"))
            for k, v in (visible or {}).items():
                styles[k]["visible"] = v
            c["styles"] = styles
            if audio is not None:
                c["audio"] = audio
            self.save()
            return self.view_values(c)

    def status(self, cams):
        keys = [c["key"] for c in cams]
        return {"config": dict(self.cfg, styles=clean_styles(self.cfg.get("styles"))), "plugin_style": plugin_style(), "cameras": [{"key": c["key"], "name": c["name"], "state": c.get("state", "unknown"), "w": c.get("w", 0), "h": c.get("h", 0)} for c in cams],
                "corners": list(pip_corners()), "preview": self.build() if self.cfg.get("main") in keys else "",
                "needs_plugin": self.cfg.get("type") == "pip", "plugin_present": os.path.exists("/opt/irl4you/gst/libgstpbpip.so")}


def view_only_change(a, b):
    def norm(c):
        c = dict(c)
        c.pop("facecam", None)
        c["audio"] = "main"
        c["styles"] = clean_styles(c.get("styles"))
        for k in STYLE_SLOTS:
            c["styles"][k] = dict(c["styles"][k], visible=True)
        return c
    return a.get("type") == "pip" and norm(a) == norm(b)


def always_compatible(a, b):
    def norm(c):
        c = dict(c)
        for k in ("main", "pip", "pip2", "pip3"):
            c[k] = bool(c.get(k))
        for k in DELAY_KEYS:
            c.pop(k, None)
        for k in ("audio", "inactive", "auto_failover", "swap_cams", "facecam"):
            c.pop(k, None)
        c["styles"] = clean_styles(c.get("styles"))
        for k in STYLE_SLOTS:
            c["styles"][k] = dict(c["styles"][k], visible=True)
        return c
    if pipbox_live.supported() and a.get("type") == "pip" and b.get("type") == "pip" and a.get("always_ready") is True and b.get("always_ready") is True:
        return True
    return a.get("type") == "pip" and b.get("type") == "pip" and a.get("always_ready") is True and b.get("always_ready") is True and norm(a) == norm(b)
