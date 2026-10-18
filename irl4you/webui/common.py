"""IRL4YOU BOX Oberfläche: Gemeinsame Konstanten und Hilfsfunktionen der Oberfläche."""

import json
import os
import re
import socket
import subprocess
import time


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # Ordner mit server.py (Version, web/, state/)
WEB_DIR = os.path.join(APP_DIR, "web")


NET_PREFIXES = ("eth", "en", "wlan", "wl", "usb", "wwan", "ppp", "rndis")


NET_SKIP = ("docker", "veth", "br-", "virbr", "tailscale", "tun", "tap", "lo")


ARP_STATUS = "/run/pipbox-arp/status.json"


ARP_STATUS_MAX_AGE = 60


NET_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$")


def net_conflict(path=None):
    try:
        with open(path or ARP_STATUS, "rb") as f:
            d = json.loads(f.read(4096).decode("utf-8", "replace"))
        if not isinstance(d, dict) or not isinstance(d.get("time"), int) or abs(time.time() - d["time"]) > ARP_STATUS_MAX_AGE:
            return None
        names, nets = d.get("conflict"), d.get("nets")
        if not isinstance(names, list):
            return None
        cards = [n for n in names if isinstance(n, str) and IFACE_NAME_RE.match(n)][:8]
        if len(cards) < 2:
            return None
        nets = [n for n in nets if isinstance(n, str) and NET_RE.match(n)][:4] if isinstance(nets, list) else []
        return {"cards": cards, "nets": nets}
    except (OSError, ValueError):
        return None


LIMITS = {"temp_warn": 70.0, "temp_crit": 80.0, "cpu_warn": 85.0, "core_warn": 90.0, "mem_warn": 85.0}


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def lan_ip():
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("203.0.113.1", 9))
        ip = sk.getsockname()[0]
        sk.close()
        return ip
    except OSError:
        return "127.0.0.1"


NET_LABELS = {}


def net_label(name):
    if name.startswith(("wl",)):
        return f"WLAN ({name})"
    try:
        if "/usb" in os.path.realpath(f"/sys/class/net/{name}/device"):
            return f"USB-Router ({name})"
    except OSError:
        pass
    return f"Ethernet ({name})"


FIXED_ALIAS = {"eth1": "192.168.80.50"}


def fixed_ip(name):
    want = FIXED_ALIAS.get(name)
    if not want:
        return None
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", name],
                             capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return want if f" {want}/" in out else None


_TTL = {}


def ttl_cached(key, ttl, fn):
    now = time.monotonic()
    hit = _TTL.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _TTL[key] = (now, val)
    return val


def ttl_cached_drop(key):
    _TTL.pop(key, None)


def iface_ips():
    return [dict(x) for x in ttl_cached("iface_ips", 3.0, _iface_ips_raw)]


def _iface_ips_raw():
    try:
        import fcntl
        import struct
        names = sorted(os.listdir("/sys/class/net"))
    except (ImportError, OSError):
        return []
    out = []
    for name in names:
        if name == "lo" or name.startswith(("docker", "veth", "br-", "virbr", "p2p", "tailscale", "tun", "tap", "wg", "zt")):
            continue
        try:
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ip = socket.inet_ntoa(fcntl.ioctl(sk.fileno(), 0x8915,
                                              struct.pack("256s", name[:15].encode()))[20:24])
            sk.close()
        except OSError:
            continue
        out.append({"iface": name, "ip": ip, "cam_ip": fixed_ip(name) or ip, "label": NET_LABELS.get(name) or net_label(name),
                    "wifi": os.path.isdir(f"/sys/class/net/{name}/wireless")})
    return out


HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


ROLES = ("main", "pip", "extra")


def belacoder_running():
    try:
        for d in os.listdir("/proc"):
            if d.isdigit() and (read(f"/proc/{d}/comm", "") or "").strip() in ("belacoder", "irl4you-encoder"):
                return True
    except OSError:
        pass
    return False



IFACE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,15}$")


def local_macs():
    out = {}
    try:
        for n in sorted(os.listdir("/sys/class/net")):
            if n == "lo" or not IFACE_NAME_RE.match(n):
                continue
            m = (read("/sys/class/net/%s/address" % n, "") or "").strip().lower()
            if re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", m) and m != "00:00:00:00:00:00":
                out[n] = m
    except OSError:
        pass
    return out
