"""Mobilfunk-Modems (USB-Sticks, M.2-Module) für die IRL4YOU BOX.

Liest den Zustand über ModemManager (mmcli, nur lesend, als Benutzer pipbox) und gibt Änderungen als Auftrag an den root-Helfer
pipbox-modem.py weiter (Auslösedatei /var/lib/pipbox/modem-request, wie beim WLAN-Helfer). Der Helfer legt je Modem ein
NetworkManager-Profil an (APN, Zugangsdaten, Roaming, feste Netzwahl) und setzt die erlaubten Netztypen (2G/3G/4G/5G).

Die Einstellungen je Modem liegen in /var/lib/pipbox/modems.json, ohne Passwort (das steht nur im NetworkManager-Profil, das
nur root lesen kann). Ein Modem wird über eine Kennung aus der Gerätekennung von ModemManager wiedererkannt (keine IMEI im Klartext).
"""
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time

REQ_NAME = "modem-request"
CONFIG_NAME = "modems.json"
STATUS = "/run/pipbox-modem/status.json"
PROFILE_PREFIX = "irl4you-modem-"
ACTIONS = ("config", "scan", "apply")
APN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
CRED_RE = re.compile(r"^[\x21-\x7e]{0,64}$")
OPERATOR_RE = re.compile(r"^\d{5,6}$")
MODEM_ID_RE = re.compile(r"^[0-9a-f]{12}$")
MODE_NAMES = ("2g", "3g", "4g", "5g")
MODE_LABEL = {"2g": "2G", "3g": "3G", "4g": "4G (LTE)", "5g": "5G"}
TECH_LABEL = {"gsm": "2G", "gprs": "2G", "edge": "2G", "umts": "3G", "hsdpa": "3G", "hsupa": "3G", "hspa": "3G", "hspa-plus": "3G+",
              "lte": "4G", "lte-cat-m": "4G", "lte-nb-iot": "4G", "5gnr": "5G"}
DEFAULT_CONFIG = {"autoconfig": True, "apn": "", "username": "", "roaming": False, "network": "", "network_type": ""}


def modem_id(device_identifier):
    """Feste Kennung je Modem: gekürzter Hash der Gerätekennung von ModemManager (stabil über Neustarts, keine IMEI im Klartext)."""
    if not isinstance(device_identifier, str) or not device_identifier:
        return ""
    return hashlib.sha256(("irl4you-modem:" + device_identifier).encode()).hexdigest()[:12]


def profile_name(mid):
    return PROFILE_PREFIX + mid


def _s(v):
    if isinstance(v, list):
        v = ",".join(str(x) for x in v)
    v = "" if v is None else str(v)
    return "" if v == "--" else v.strip()


def parse_modes(text):
    """'allowed: 3g, 4g; preferred: 4g' -> ('3g|4g', '4g'). Unbekannt -> ('', '')."""
    m = re.match(r"^\s*allowed:\s*([^;]+?)\s*(?:;\s*preferred:\s*(\S+))?\s*$", _s(text))
    if not m:
        return "", ""
    allowed = [x.strip() for x in m.group(1).split(",")]
    if "any" in allowed:
        return "any", ""
    allowed = [x for x in allowed if x in MODE_NAMES]
    pref = m.group(2) if m.group(2) in MODE_NAMES else ""
    return "|".join(sorted(set(allowed), key=MODE_NAMES.index)), pref


def mode_label(key):
    if key == "any":
        return "Automatisch"
    parts = [p for p in (key or "").split("|") if p in MODE_NAMES]
    if not parts:
        return ""
    if len(parts) == 1:
        return "nur " + MODE_LABEL[parts[0]]
    return "/".join(MODE_LABEL[p].split(" ")[0] for p in parts)


def supported_types(mode_list):
    """Liste der erlaubten Netztyp-Kombinationen aus 'supported-modes' (doppelte zusammengefasst, größte zuerst)."""
    out = []
    for t in mode_list or []:
        key, _ = parse_modes(t)
        if key and key not in out:
            out.append(key)
    out.sort(key=lambda k: (-len(k.split("|")), k))
    return out


def parse_scan(lines):
    """Ergebnis von 'mmcli --3gpp-scan' (JSON-Liste von Zeilen 'operator-code: 26201, operator-name: …, access-technologies: lte, availability: available')."""
    out, seen = [], set()
    for line in lines or []:
        d = {}
        for part in re.split(r",\s*(?=[a-z-]+:)", _s(line)):
            k, _, v = part.partition(":")
            d[k.strip()] = v.strip()
        code = d.get("operator-code", "")
        if not OPERATOR_RE.match(code):
            continue
        tech = [t.strip() for t in d.get("access-technologies", "").split(",") if t.strip()]
        avail = d.get("availability", "")
        key = (code, tuple(tech))
        if key in seen:
            continue
        seen.add(key)
        out.append({"code": code, "name": d.get("operator-name", "") or code, "tech": sorted({TECH_LABEL.get(t, t) for t in tech}),
                    "available": avail in ("available", "current"), "current": avail == "current", "forbidden": avail == "forbidden"})
    out.sort(key=lambda n: (not n["current"], n["forbidden"], n["name"].lower()))
    return out


def signal_percent(generic):
    q = generic.get("signal-quality")
    if isinstance(q, dict):
        q = q.get("value")
    try:
        v = int(_s(q))
    except ValueError:
        return None
    return v if 0 <= v <= 100 else None


def net_iface(generic):
    """Netzwerk-Schnittstelle des Modems ('wwan0 (net)' in den Ports)."""
    for p in generic.get("ports") or []:
        m = re.match(r"^([A-Za-z0-9_.-]{1,15})\s*\(net\)$", _s(p))
        if m:
            return m.group(1)
    return ""


def modem_state(generic):
    """Zustand für die Oberfläche: kein-sim, gesperrt, aus, suche, eingebucht, verbinde, verbunden, fehler."""
    st = _s(generic.get("state")).lower()
    why = _s(generic.get("state-failed-reason")).lower()
    if why == "sim-missing" or st == "failed" and "sim" in why:
        return "kein-sim"
    if st == "locked":
        return "gesperrt"
    if st == "failed":
        return "fehler"
    if st in ("disabled", "disabling", "enabling", "initializing", "unknown"):
        return "aus"
    if st == "searching":
        return "suche"
    if st in ("registered", "enabled"):
        return "eingebucht" if st == "registered" else "suche"
    if st == "connecting":
        return "verbinde"
    if st == "connected":
        return "verbunden"
    if st == "disconnecting":
        return "eingebucht"
    return "aus"


def modem_info(modem_json, sim_json=None):
    """Aus 'mmcli -J -m N' (und optional 'mmcli -J -i N') die Angaben für die Oberfläche (ohne IMEI/ICCID/IMSI)."""
    m = (modem_json or {}).get("modem") or {}
    g = m.get("generic") or {}
    g3 = m.get("3gpp") or {}
    sim = ((sim_json or {}).get("sim") or {}).get("properties") or {}
    dev = _s(g.get("device-identifier"))
    allowed, pref = parse_modes(g.get("current-modes"))
    reg = _s(g3.get("registration-state")).lower()
    techs = [t.strip() for t in _s(g.get("access-technologies")).split(",") if t.strip()]
    state = modem_state(g)
    return {
        "id": modem_id(dev),
        "path": _s(m.get("dbus-path")),
        "name": " ".join(x for x in (_s(g.get("manufacturer")), _s(g.get("model"))) if x)[:80] or "Modem",
        "iface": net_iface(g),
        "state": state,
        "no_sim": state == "kein-sim",
        "signal": signal_percent(g),
        "tech": sorted({TECH_LABEL.get(t, t) for t in techs}),
        "operator": _s(g3.get("operator-name")),
        "operator_code": _s(g3.get("operator-code")),
        "sim_operator": _s(sim.get("operator-name")),
        "sim_operator_code": _s(sim.get("operator-code")),
        "roaming": reg == "roaming",
        "registration": reg,
        "network_type": allowed,
        "network_type_preferred": pref,
        "network_types": supported_types(g.get("supported-modes")),
    }


def clean_config(d, current=None):
    """Prüft eine Änderung der Einstellungen eines Modems (alles optional außer dem, was geändert werden soll)."""
    if not isinstance(d, dict):
        raise ValueError("Ungültige Anfrage")
    out = dict(DEFAULT_CONFIG)
    out.update({k: v for k, v in (current or {}).items() if k in DEFAULT_CONFIG})
    if "autoconfig" in d:
        if not isinstance(d["autoconfig"], bool):
            raise ValueError("Automatische Einrichtung: ja oder nein")
        out["autoconfig"] = d["autoconfig"]
    if "apn" in d:
        apn = d["apn"]
        if not isinstance(apn, str) or apn and not APN_RE.match(apn):
            raise ValueError("APN: Buchstaben, Ziffern, Punkt, Minus, Unterstrich, höchstens 100 Zeichen")
        out["apn"] = apn
    if "username" in d:
        u = d["username"]
        if not isinstance(u, str) or not CRED_RE.match(u):
            raise ValueError("Benutzername: höchstens 64 Zeichen ohne Leerzeichen")
        out["username"] = u
    if "password" in d:
        p = d["password"]
        if p is not None and (not isinstance(p, str) or not CRED_RE.match(p)):
            raise ValueError("Passwort: höchstens 64 Zeichen ohne Leerzeichen")
    if "roaming" in d:
        if not isinstance(d["roaming"], bool):
            raise ValueError("Roaming: ja oder nein")
        out["roaming"] = d["roaming"]
    if "network" in d:
        n = d["network"]
        if not isinstance(n, str) or n and not OPERATOR_RE.match(n):
            raise ValueError("Netz: automatisch oder eine Netzkennung (5 bis 6 Ziffern)")
        out["network"] = n
    if "network_type" in d:
        t = d["network_type"]
        if t not in ("", "any") and (not isinstance(t, str) or not all(p in MODE_NAMES for p in t.split("|")) or len(set(t.split("|"))) != len(t.split("|"))):
            raise ValueError("Netztyp ungültig")
        out["network_type"] = "" if t == "any" else t
    if not out["autoconfig"] and not out["apn"]:
        raise ValueError("Ohne automatische Einrichtung bitte einen APN angeben")
    return out


def nm_settings(cfg, device_identifier, password=None):
    """Argumente für 'nmcli connection add/modify' (Profil vom Typ gsm). password=None lässt ein gespeichertes Passwort unverändert."""
    args = ["connection.autoconnect", "yes", "connection.autoconnect-retries", "0",
            "gsm.device-id", device_identifier,
            "gsm.auto-config", "yes" if cfg["autoconfig"] else "no",
            "gsm.apn", "" if cfg["autoconfig"] else cfg["apn"],
            "gsm.username", "" if cfg["autoconfig"] else cfg["username"],
            "gsm.home-only", "no" if cfg["roaming"] else "yes",
            "gsm.network-id", cfg["network"],
            "ipv4.method", "auto", "ipv4.route-metric", "700", "ipv6.method", "auto"]
    if password is not None:
        args += ["gsm.password", "" if cfg["autoconfig"] else password, "gsm.password-flags", "0"]
    return args


def mm_modes_args(network_type, supported):
    """mmcli-Argumente für die erlaubten Netztypen; bevorzugt wird der schnellste. '' = nicht ändern."""
    if not network_type or network_type not in (supported or []):
        return []
    parts = network_type.split("|")
    args = ["--set-allowed-modes=" + network_type]
    if len(parts) > 1:
        args.append("--set-preferred-mode=" + parts[-1])
    return args


def read_json(path, default):
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return default
    return d if isinstance(d, type(default)) else default


def write_json(path, data, mode=0o600):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def _mmcli_json(*args, timeout=6):
    try:
        r = subprocess.run(["mmcli", "-J", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def list_modems(run=_mmcli_json):
    """Alle Modems mit Angaben (Liste von (info, device_identifier, supported))."""
    lst = run("-L") or {}
    out = []
    for path in lst.get("modem-list") or []:
        m = re.search(r"/Modem/(\d{1,4})$", _s(path))
        if not m:
            continue
        mj = run("-m", m.group(1))
        if not mj:
            continue
        g = (mj.get("modem") or {}).get("generic") or {}
        sj = None
        sp = re.search(r"/SIM/(\d{1,4})$", _s(g.get("sim")))
        if sp:
            sj = run("-i", sp.group(1))
        info = modem_info(mj, sj)
        info["index"] = int(m.group(1))
        if info["id"]:
            out.append((info, _s(g.get("device-identifier"))))
    return out


class Modems:
    """Teil der Oberfläche (server.py): Zustand lesen, Aufträge an den Helfer geben."""

    def __init__(self, state_dir, demo=False, run=None):
        self.req = os.path.join(state_dir, REQ_NAME)
        self.cfg_path = os.path.join(state_dir, CONFIG_NAME)
        self.demo = demo
        self.run = run or _mmcli_json
        self.lock = threading.Lock()
        self._cache = (0.0, [])
        self.fake_cfg = {}
        self.fake_scan = {}

    def configs(self):
        if self.demo:
            return dict(self.fake_cfg)
        d = read_json(self.cfg_path, {})
        return {k: v for k, v in d.items() if MODEM_ID_RE.match(k) and isinstance(v, dict)}

    def _modems(self):
        if self.demo:
            return [({"id": "a1b2c3d4e5f6", "path": "/org/freedesktop/ModemManager1/Modem/0", "name": "Quectel EM12-G", "iface": "wwan0",
                      "state": "verbunden", "no_sim": False, "signal": 72, "tech": ["4G"], "operator": "Telekom.de", "operator_code": "26201",
                      "sim_operator": "Telekom", "sim_operator_code": "26201", "roaming": False, "registration": "home", "network_type": "3g|4g",
                      "network_type_preferred": "4g", "network_types": ["2g|3g|4g", "3g|4g", "4g", "3g"], "index": 0}, "demo")]
        now = time.monotonic()
        if now - self._cache[0] < 3.0:
            return self._cache[1]
        val = list_modems(self.run)
        self._cache = (now, val)
        return val

    def helper_status(self):
        if self.demo:
            return {"state": "idle", "message": "", "scan": self.fake_scan}
        return read_json(STATUS, {})

    def status(self):
        cfgs = self.configs()
        h = self.helper_status()
        scans = h.get("scan") if isinstance(h.get("scan"), dict) else {}
        out = []
        for info, _dev in self._modems():
            c = dict(DEFAULT_CONFIG)
            c.update({k: v for k, v in cfgs.get(info["id"], {}).items() if k in DEFAULT_CONFIG})
            c["password_set"] = bool(cfgs.get(info["id"], {}).get("password_set"))
            item = {k: v for k, v in info.items() if k not in ("path", "index")}
            item["config"] = c
            item["network_types"] = [{"key": k, "label": mode_label(k)} for k in info["network_types"]]
            item["network_type_label"] = mode_label(info["network_type"])
            sc = scans.get(info["id"]) if isinstance(scans.get(info["id"]), dict) else {}
            item["available_networks"] = sc.get("nets") if isinstance(sc.get("nets"), list) else []
            item["scan_time"] = sc.get("time", 0) if isinstance(sc.get("time"), int) else 0
            out.append(item)
        return {"helper_installed": self.demo or os.path.exists("/etc/systemd/system/pipbox-modem.path"),
                "modems": out, "state": h.get("state", "idle"), "message": h.get("message", ""), "action": h.get("action", ""),
                "time": h.get("time", 0)}

    def request(self, d):
        if not self.lock.acquire(blocking=False):
            raise ValueError("Es läuft schon eine Aktion")
        try:
            return self._request(d)
        finally:
            self.lock.release()

    def _request(self, d):
        if not isinstance(d, dict) or d.get("action") not in ("config", "scan"):
            raise ValueError("Unbekannte Aktion")
        st = self.status()
        if not st["helper_installed"]:
            raise ValueError("Der Mobilfunk-Helfer ist nicht installiert (Installation erneut ausführen)")
        if st["state"] == "working" and time.time() - (st.get("time") or 0) < 330:
            raise ValueError("Es läuft schon eine Aktion")
        mid = d.get("id")
        modem = next((m for m in st["modems"] if m["id"] == mid), None)
        if not modem:
            raise ValueError("Dieses Modem gibt es nicht (mehr)")
        req = {"action": d["action"], "id": mid, "mark": secrets.token_hex(8)}
        if d["action"] == "config":
            changes = {k: d[k] for k in ("autoconfig", "apn", "username", "password", "roaming", "network", "network_type") if k in d}
            cfg = clean_config(changes, modem["config"])
            if cfg["network_type"] and cfg["network_type"] not in [t["key"] for t in modem["network_types"]]:
                raise ValueError("Diesen Netztyp kann das Modem nicht")
            req["config"] = cfg
            if "password" in changes and changes["password"] is not None:
                req["password"] = changes["password"]
        elif modem["no_sim"]:
            raise ValueError("Ohne SIM-Karte kann das Modem keine Netze suchen")
        if self.demo:
            if d["action"] == "config":
                self.fake_cfg[mid] = dict(req["config"], password_set=bool(req.get("password")) or self.fake_cfg.get(mid, {}).get("password_set", False))
            else:
                self.fake_scan[mid] = {"time": int(time.time()), "nets": [
                    {"code": "26201", "name": "Telekom.de", "tech": ["2G", "4G"], "available": True, "current": True, "forbidden": False},
                    {"code": "26202", "name": "Vodafone.de", "tech": ["4G"], "available": True, "current": False, "forbidden": False},
                    {"code": "26203", "name": "o2 - de", "tech": ["4G"], "available": True, "current": False, "forbidden": True}]}
            return {"ok": True}
        tmp = self.req + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(req, f)
        os.replace(tmp, self.req)
        self._cache = (0.0, [])
        return {"ok": True, "mark": req["mark"]}
