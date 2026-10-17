"""IRL4YOU BOX Oberfläche: Bausteine und Konstanten für den Bildaufbau (Bild-in-Bild, Stile, Verzögerung)."""

import hashlib
import json
import os
import re
import shutil

from .netstate import SrtlaStore


PIP_CORNERS = ("oben links", "oben rechts", "unten links", "unten rechts", "unten Mitte", "frei (verschiebbar)")


FREE = 5


PLUGIN_SO = "/opt/irl4you/gst/libgstpbpip.so"


SEND_STATUS = "/run/pipbox-send/status.json"


VIEW_FILE = "main-view"


VIEW_STATE = "/run/pipbox-send/view-state"


SWAP_SELECT = "main-select"


SWAP_STATE = "/run/pipbox-send/swap-state"


_CENTER = {"mtime": None, "ok": True, "free": True}


def pip_corners():
    try:
        mt = os.stat(PLUGIN_SO).st_mtime
        if _CENTER["mtime"] != mt:
            with open(PLUGIN_SO, "rb") as f:
                data = f.read()
            _CENTER.update(mtime=mt, ok=b"4 unten Mitte" in data, free=b"5 frei" in data)
    except OSError:
        return PIP_CORNERS
    if not _CENTER["ok"]:
        return PIP_CORNERS[:4]
    return PIP_CORNERS if _CENTER["free"] else PIP_CORNERS[:5]


_MULTI = {"mtime": None, "ok": True}


def plugin_multi():
    try:
        mt = os.stat(PLUGIN_SO).st_mtime
        if _MULTI["mtime"] != mt:
            with open(PLUGIN_SO, "rb") as f:
                _MULTI.update(mtime=mt, ok=b"slot3" in f.read())
    except OSError:
        return True
    return _MULTI["ok"]


_SWAP = {"mtime": None, "ok": True}


def plugin_swap():
    try:
        mt = os.stat(PLUGIN_SO).st_mtime
        if _SWAP["mtime"] != mt:
            with open(PLUGIN_SO, "rb") as f:
                data = f.read()
            _SWAP.update(mtime=mt, ok=b"pbpipsel" in data and b"follow-tag" in data)
    except OSError:
        return True
    return _SWAP["ok"]


_FILL = {"mtime": None, "ok": True}


FEED_PORT = 9410


FEED_VIDEO_CAPS = "application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000"


FEED_AUDIO_CAPS = "audio/x-raw,format=S16LE,rate=48000,channels=2,layout=interleaved"


FEED_FILL_VIDEO = "video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1"


CAM_LIVE = "/run/pipbox-send/cam-live"


def plugin_fill():
    try:
        mt = os.stat(PLUGIN_SO).st_mtime
        if _FILL["mtime"] != mt:
            with open(PLUGIN_SO, "rb") as f:
                data = f.read()
            _FILL.update(mtime=mt, ok=b"fill-caps" in data and b"live-file" in data)
    except OSError:
        return True
    return _FILL["ok"]


def feeder_tool():
    return shutil.which("gst-launch-1.0")


_VIEW = {"mtime": None, "ok": True}


VIEW_ENABLED = True


def plugin_view():
    if not VIEW_ENABLED:
        return False
    try:
        mt = os.stat(PLUGIN_SO).st_mtime
        if _VIEW["mtime"] != mt:
            with open(PLUGIN_SO, "rb") as f:
                data = f.read()
            _VIEW.update(mtime=mt, ok=b"view-file" in data and b"view-state-file" in data)
    except OSError:
        return True
    return _VIEW["ok"]


_STYLE = {"mtime": None, "ok": True}


def plugin_style():
    try:
        mt = os.stat(PLUGIN_SO).st_mtime
        if _STYLE["mtime"] != mt:
            with open(PLUGIN_SO, "rb") as f:
                data = f.read()
            _STYLE.update(mtime=mt, ok=b"style1" in data and b"style3" in data)
    except OSError:
        return True
    return _STYLE["ok"]


STYLE_SLOTS = ("1", "2", "3")


CROP_REF_W, CROP_REF_H, CROP_KEEP = 1920, 1080, 32


STYLE_DEFAULT = {"visible": True, "opacity": 100, "crop": {"l": 0, "r": 0, "t": 0, "b": 0}, "radius": 0,
                 "border": {"enabled": False, "width": 6, "color": "#ffffff", "opacity": 100}}


STYLE_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _style_copy(st):
    out = {"visible": st["visible"], "opacity": st["opacity"], "crop": dict(st["crop"]), "radius": st.get("radius", 0), "border": dict(st["border"])}
    if "radius" not in st:
        out["radius"] = int(out["border"].get("radius", 0)) if out["border"].get("enabled") else 0
    out["border"].pop("radius", None)
    return out


def clean_style(src, old=None, strict=False):
    st = _style_copy(old if isinstance(old, dict) and "crop" in old and "border" in old else STYLE_DEFAULT)
    if src is None:
        src = {}
    if not isinstance(src, dict):
        if strict:
            raise ValueError("Aussehen des kleinen Bildes: ungültige Angabe")
        src = {}

    def num(v, lo, hi, cur, what):
        if isinstance(v, bool) or not isinstance(v, (int, float)) and not (isinstance(v, str) and v.strip().lstrip("-").isdigit()):
            if strict:
                raise ValueError(f"{what} muss eine Zahl sein")
            return cur
        n = int(float(v))
        if strict and not lo <= n <= hi:
            raise ValueError(f"{what}: {lo} bis {hi}")
        return max(lo, min(hi, n))
    if "visible" in src:
        if isinstance(src["visible"], bool):
            st["visible"] = src["visible"]
        elif strict:
            raise ValueError("Kleines Bild zeigen: ja oder nein")
    if "opacity" in src:
        st["opacity"] = num(src["opacity"], 0, 100, st["opacity"], "Deckkraft")
    crop = src.get("crop")
    if isinstance(crop, dict):
        for k, lbl in (("l", "links"), ("r", "rechts"), ("t", "oben"), ("b", "unten")):
            if k in crop:
                st["crop"][k] = num(crop[k], 0, 1900, st["crop"][k], f"Beschnitt {lbl}") // 2 * 2
    elif crop is not None and strict:
        raise ValueError("Beschnitt: ungültige Angabe")
    c = st["crop"]
    for a, b, total in (("l", "r", CROP_REF_W), ("t", "b", CROP_REF_H)):
        room = total - CROP_KEEP
        if c[a] + c[b] > room:
            if strict:
                raise ValueError(f"Beschnitt: {'links plus rechts' if a == 'l' else 'oben plus unten'} höchstens {room} Pixel "
                                 f"(es bleiben mindestens {CROP_KEEP} Pixel stehen)")
            k = room / float(c[a] + c[b])
            c[a], c[b] = int(c[a] * k) // 2 * 2, int(c[b] * k) // 2 * 2
    if "radius" in src:
        st["radius"] = num(src["radius"], 0, 60, st["radius"], "Eckenrundung")
    border = src.get("border")
    if isinstance(border, dict):
        b = st["border"]
        if "enabled" in border:
            if isinstance(border["enabled"], bool):
                b["enabled"] = border["enabled"]
            elif strict:
                raise ValueError("Rahmen: ein oder aus")
        if "width" in border:
            b["width"] = num(border["width"], 1, 40, b["width"], "Rahmendicke")
        if "color" in border:
            if isinstance(border["color"], str) and STYLE_COLOR_RE.match(border["color"]):
                b["color"] = border["color"].lower()
            elif strict:
                raise ValueError("Rahmenfarbe: Farbe wie #ffffff")
        if "opacity" in border:
            b["opacity"] = num(border["opacity"], 10, 100, b["opacity"], "Rahmendeckkraft")
        if "radius" in border:
            legacy = num(border["radius"], 0, 60, st["radius"], "Eckenrundung")
            if "radius" not in src and b["enabled"]:
                st["radius"] = legacy
    elif border is not None and strict:
        raise ValueError("Rahmen: ungültige Angabe")
    return st


def clean_styles(src, old=None, strict=False):
    if src is not None and not isinstance(src, dict):
        if strict:
            raise ValueError("Aussehen der kleinen Bilder: ungültige Angabe")
        src = None
    old = old if isinstance(old, dict) else {}
    return {k: clean_style((src or {}).get(k), old.get(k), strict) for k in STYLE_SLOTS}


def style_text(st):
    parts = []
    op = st["opacity"] if st["visible"] else 0
    if op != 100:
        parts.append(f"op={int(op)}")
    for key, name in (("l", "cl"), ("r", "cr"), ("t", "ct"), ("b", "cb")):
        if st["crop"][key]:
            parts.append(f"{name}={int(st['crop'][key])}")
    b = st["border"]
    if b["enabled"]:
        parts.append(f"bw={int(b['width'])}")
        parts.append(f"bc={b['color'][1:]}")
        if b["opacity"] != 100:
            parts.append(f"bo={int(b['opacity'])}")
    if st["radius"]:
        parts.append(f"br={int(st['radius'])}")
    return ",".join(parts)


SIZE_MIN, SIZE_MAX = 1, 100


HW_MIN_W, HW_MIN_H = 128, 72


def pip_size(pct):
    w = max(16, int(round(1920 * pct / 100.0 / 16.0)) * 16)
    h = int(round(w * 9 / 16.0 / 2.0)) * 2
    return w, h


def small_decode(w, h):
    if w >= HW_MIN_W:
        return f"mppvideodec width={w} height={h} !\nvideo/x-raw,format=NV12 !\n"
    return (f"mppvideodec width={HW_MIN_W} height={HW_MIN_H} !\nvideoscale !\nvideo/x-raw,format=NV12,width={w},height={h} !\n")


DEFAULT_MAIN_DELAY_MS = 450


DEFAULT_PIP_DELAY_MS = 0


DELAY_KEYS = ("main_delay_ms", "pip_delay_ms", "pip2_delay_ms", "pip3_delay_ms")


FRAME_MS = 33


PENDING_LABELS = (("server", "SRTLA-Server"), ("bitrate", "Bitrate"), ("latency", "Latenz"), ("spread", "Verteilung"))


def srtla_signature(data):
    cur = next((x for x in data.get("servers", []) if x.get("id") == data.get("selected")), None) or {}
    st = {**SrtlaStore.DEFAULT_SETTINGS, **data.get("settings", {})}

    def h(*a):
        return hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()[:12]
    try:
        mn, mx, lat = int(st["min_kbps"]), int(st["max_kbps"]), int(st["latency_ms"])
    except (TypeError, ValueError):
        mn = mx = lat = 0
    return {"server": h(cur.get("id"), cur.get("host"), cur.get("port"), cur.get("streamid")),
            "bitrate": h(mn, mx), "latency": h(lat), "spread": h("all" if st.get("spread") == "all" else "best")}
