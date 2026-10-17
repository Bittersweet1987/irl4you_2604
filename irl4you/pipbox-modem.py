#!/usr/bin/env python3
"""IRL4YOU BOX Mobilfunk-Helfer (root, nur feste Aktionen).

Aufrufe:
  pipbox-modem.py          Auftrag aus /var/lib/pipbox/modem-request ausführen (pipbox-modem.path)
  pipbox-modem.py apply    alle Modems einrichten: neues Modem bekommt ein Profil mit automatischer Einrichtung,
                           gespeicherte Netztypen werden wieder gesetzt (pipbox-modem.timer, beim Booten und jede Minute)

Aktionen im Auftrag:
  config  Einstellungen eines Modems speichern und anwenden (NetworkManager-Profil irl4you-modem-<id>, Netztypen über mmcli)
  scan    verfügbare Netze suchen (dauert bis zu einige Minuten), Ergebnis in /run/pipbox-modem/status.json
"""
import json
import os
import pwd
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipbox_modem as pm  # noqa: E402

STATE = "/var/lib/pipbox"
REQ = os.path.join(STATE, pm.REQ_NAME)
CFG = os.path.join(STATE, pm.CONFIG_NAME)
RUN = os.path.dirname(pm.STATUS)
SCAN_TIMEOUT = 300


def nm(*args, timeout=30):
    return subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)


def mmcli(*args, timeout=30):
    return subprocess.run(["mmcli", *args], capture_output=True, text=True, timeout=timeout)


def write_status(**kw):
    os.makedirs(RUN, exist_ok=True)
    s = pm.read_json(pm.STATUS, {})
    s.update(kw)
    s["time"] = int(time.time())
    tmp = pm.STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, pm.STATUS)


def save_configs(cfgs):
    pm.write_json(CFG, cfgs, 0o600)
    try:
        pw = pwd.getpwnam("pipbox")
        os.chown(CFG, pw.pw_uid, pw.pw_gid)
    except (KeyError, OSError):
        pass


def read_req(path, limit=8192):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("keine normale Datei")
        return os.read(fd, limit).decode("utf-8", "replace")
    finally:
        os.close(fd)


def find(mid):
    for info, dev in pm.list_modems():
        if info["id"] == mid:
            return info, dev
    raise ValueError("Das Modem ist nicht mehr da")


def profile_exists(name):
    r = nm("-t", "-f", "NAME", "connection", "show")
    return name in [l.replace("\\:", ":") for l in r.stdout.splitlines()]


def write_profile(info, dev, cfg, password=None):
    name = pm.profile_name(info["id"])
    settings = pm.nm_settings(cfg, dev, password)
    if profile_exists(name):
        r = nm("connection", "modify", "id", name, *settings)
    else:
        if password is None:
            settings += ["gsm.password-flags", "0"]
        r = nm("connection", "add", "type", "gsm", "ifname", "*", "con-name", name, *settings)
    if r.returncode != 0:
        raise RuntimeError("NetworkManager: " + (r.stderr.strip().splitlines() or ["Fehler"])[-1][:200])


def set_modes(info, cfg):
    args = pm.mm_modes_args(cfg.get("network_type"), info["network_types"])
    if not args or info["network_type"] == cfg["network_type"]:
        return False
    r = mmcli("-m", str(info["index"]), *args)
    if r.returncode != 0:
        raise RuntimeError("Netztyp konnte nicht gesetzt werden: " + (r.stderr.strip().splitlines() or ["Fehler"])[-1][:200])
    return True


def reconnect(info):
    name = pm.profile_name(info["id"])
    if info["no_sim"]:
        return
    nm("connection", "down", "id", name, timeout=30)
    nm("connection", "up", "id", name, timeout=90)


def do_config(req):
    mid = req.get("id")
    info, dev = find(mid)
    cfgs = pm.read_json(CFG, {})
    cfg = pm.clean_config(req.get("config") or {}, cfgs.get(mid))
    password = req.get("password") if isinstance(req.get("password"), str) else None
    if password is not None:
        pm.clean_config({"password": password}, cfg)
    write_profile(info, dev, cfg, password)
    set_modes(info, cfg)
    entry = dict(cfg)
    entry["password_set"] = bool(password) if password is not None else bool((cfgs.get(mid) or {}).get("password_set"))
    if cfg["autoconfig"]:
        entry["password_set"] = False
    cfgs[mid] = entry
    save_configs(cfgs)
    reconnect(info)
    return "Gespeichert, das Modem verbindet sich neu"


def do_scan(req):
    info, _dev = find(req.get("id"))
    if info["no_sim"]:
        raise ValueError("Ohne SIM-Karte kann das Modem keine Netze suchen")
    r = mmcli("-J", "-m", str(info["index"]), "--3gpp-scan", "--timeout=%d" % SCAN_TIMEOUT, timeout=SCAN_TIMEOUT + 30)
    if r.returncode != 0:
        raise RuntimeError("Suche fehlgeschlagen: " + (r.stderr.strip().splitlines() or ["Fehler"])[-1][:200])
    try:
        nets = pm.parse_scan(((json.loads(r.stdout).get("modem") or {}).get("3gpp") or {}).get("scan-networks"))
    except ValueError:
        nets = []
    s = pm.read_json(pm.STATUS, {})
    scans = s.get("scan") if isinstance(s.get("scan"), dict) else {}
    scans[info["id"]] = {"time": int(time.time()), "nets": nets}
    write_status(scan=scans)
    return "%d Netze gefunden" % len(nets) if nets else "Keine Netze gefunden"


def do_apply():
    """Neue Modems automatisch einrichten, gespeicherte Netztypen wieder setzen (nach Neustart oder Neueinstecken)."""
    cfgs = pm.read_json(CFG, {})
    changed = False
    for info, dev in pm.list_modems():
        mid = info["id"]
        if mid not in cfgs:
            if profile_exists(pm.profile_name(mid)):
                cfgs[mid] = dict(pm.DEFAULT_CONFIG, password_set=False)
            else:
                cfg = dict(pm.DEFAULT_CONFIG)
                try:
                    write_profile(info, dev, cfg)
                except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                    print("pipbox-modem: %s: %s" % (info["name"], e))
                    continue
                cfgs[mid] = dict(cfg, password_set=False)
                print("pipbox-modem: %s neu eingerichtet (automatischer APN)" % info["name"])
            changed = True
            continue
        try:
            if set_modes(info, cfgs[mid]):
                print("pipbox-modem: %s Netztyp %s wieder gesetzt" % (info["name"], cfgs[mid]["network_type"]))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            print("pipbox-modem: %s: %s" % (info["name"], e))
    if changed:
        save_configs(cfgs)
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        return do_apply()
    try:
        req = json.loads(read_req(REQ))
    except (OSError, ValueError):
        req = None
    try:
        os.remove(REQ)
    except OSError:
        pass
    if not isinstance(req, dict) or req.get("action") not in ("config", "scan"):
        write_status(state="error", message="Ungültige Anfrage", action="")
        return 1
    action = req["action"]
    write_status(state="working", message="Suche läuft …" if action == "scan" else "Wird eingerichtet …", action=action, id=str(req.get("id", ""))[:12])
    try:
        msg = do_scan(req) if action == "scan" else do_config(req)
        write_status(state="done", message=msg)
    except (ValueError, RuntimeError) as e:
        write_status(state="error", message=str(e))
    except (OSError, subprocess.TimeoutExpired) as e:
        write_status(state="error", message="Fehler: " + type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
