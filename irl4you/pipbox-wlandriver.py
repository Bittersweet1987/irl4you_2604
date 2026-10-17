#!/usr/bin/env python3
"""IRL4YOU BOX: schaltet WLAN-Sticks mit AIC8800-Chip in den WLAN-Modus und prüft, dass eine WLAN-Schnittstelle entsteht.

Die Treiber kommen als Pakete (irl4you-wifi-rtw88 für Realtek-Sticks, irl4you-wifi-aic8800 für AIC-Sticks) fertig für den Kernel der Box;
hier wird nichts mehr gebaut oder geladen. Realtek-Sticks laufen ohne Zutun. AIC-Sticks melden sich zuerst als USB-Laufwerk
(a69c:5721 ... 572f, Pandora-Klon 1111:1111) und müssen einmal umgeschaltet werden. Der Zustand steht in /run/pipbox-wlandriver/status.json.
"""
import fcntl
import json
import os
import subprocess
import sys
import time

RUN = "/run/pipbox-wlandriver"
STATUS = f"{RUN}/status.json"
LOCK = "/run/pipbox-wlandriver.lock"
SYSFS_USB = "/sys/bus/usb/devices"
SYSFS_NET = "/sys/class/net"
PKG = "irl4you-wifi-aic8800"
MODULES = ("aic_load_fw", "aic8800_fdrv")
NAME = "AIC8800-WLAN-Stick"
# USB-Laufwerk-Modus (Umschaltung per SCSI-Auswurf) und Pandora-Klon (eigene Umschaltdatei aus dem Paket)
MSC_IDS = tuple(f"a69c:57{x}" for x in ("21", "22", "23", "24", "25", "26", "27", "2a", "2c", "2f"))
PANDORA_ID = "1111:1111"
# Arbeitsmodus: Lader (8d80) und fertiger Stick (8d81)
WORKING_IDS = ("a69c:8d81", "368b:8d81")
LOADER_IDS = ("a69c:8d80",)
KNOWN = {i: NAME for i in MSC_IDS + LOADER_IDS + WORKING_IDS + (PANDORA_ID,)}


def log(msg):
    print(msg, flush=True)


def status(**kw):
    os.makedirs(RUN, exist_ok=True)
    try:
        with open(STATUS) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.update(kw)
    s["time"] = int(time.time())
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATUS)


def run(args, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)


def usb_ids_present(root=SYSFS_USB):
    out = set()
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for n in names:
        if ":" in n:
            continue
        try:
            with open(f"{root}/{n}/idVendor") as f:
                v = f.read().strip().lower()
            with open(f"{root}/{n}/idProduct") as f:
                p = f.read().strip().lower()
        except OSError:
            continue
        out.add(f"{v}:{p}")
    return out


def wanted(present=None):
    present = usb_ids_present() if present is None else present
    return sorted(i for i in KNOWN if i in present)


def modules_ok(run_cmd=run):
    return all(run_cmd(["modinfo", "-n", m]).returncode == 0 for m in MODULES)


def netdev_for_usb(idents, net_root=SYSFS_NET, resolve=os.path.realpath):
    """Name der WLAN-Schnittstelle, die zu einem der USB-Geräte gehört (sonst "")."""
    try:
        names = sorted(os.listdir(net_root))
    except OSError:
        return ""
    for n in names:
        p = resolve(os.path.join(net_root, n, "device"))
        while p and p != os.path.dirname(p):
            try:
                with open(os.path.join(p, "idVendor")) as f:
                    v = f.read().strip().lower()
                with open(os.path.join(p, "idProduct")) as f:
                    pr = f.read().strip().lower()
            except OSError:
                p = os.path.dirname(p)
                continue
            if f"{v}:{pr}" in idents:
                return n
            break
    return ""


def wait_for_wlan(timeout=60, find=netdev_for_usb, sleep=time.sleep, now=time.time):
    end = now() + timeout
    while True:
        name = find(WORKING_IDS)
        if name or now() >= end:
            return name
        sleep(2)


def switch_cmd(ident):
    if ident == PANDORA_ID:
        return ["usb_modeswitch", "-c", "/etc/usb_modeswitch.d/1111:1111"]
    return ["usb_modeswitch", "-KW", "-v", ident.split(":")[0], "-p", ident.split(":")[1]]


def switch_mode(ident, present=usb_ids_present, run_cmd=run, sleep=time.sleep, now=time.time, timeout=20):
    r = run_cmd(switch_cmd(ident), timeout=30)
    end = now() + timeout
    while ident in present():
        if now() >= end:
            last = [x.strip() for x in (r.stdout + r.stderr).splitlines() if x.strip()]
            return (last[-1] if last else "keine Antwort")[:80]
        sleep(1)
    return ""


def do_auto():
    need = wanted()
    if not need:
        return 0
    if all(i in WORKING_IDS for i in need) and netdev_for_usb(WORKING_IDS):
        status(state="ok", ids=need, message=f"Treiber für {NAME} ist eingerichtet.")
        return 0
    if not modules_ok():
        status(state="unsupported", ids=need, message=f"Für den Kernel {os.uname().release} fehlt das Treiberpaket {PKG}. Der {NAME} läuft so nicht.")
        return 0
    try:
        for ident in need:
            if ident in MSC_IDS or ident == PANDORA_ID:
                status(state="working", ids=need, message=f"Der {NAME} wird in den WLAN-Modus geschaltet …")
                err = switch_mode(ident)
                if err:
                    raise RuntimeError(f"Der Stick ließ sich nicht in den WLAN-Modus schalten: {err}")
            elif ident in LOADER_IDS:
                run(["modprobe", "aic_load_fw"])
        name = wait_for_wlan()
        if not name:
            raise RuntimeError("Der Stick hat keine WLAN-Schnittstelle bekommen")
        log(f"Treiber eingerichtet für {NAME}: {name}")
        status(state="ok", ids=need, message=f"Treiber für {NAME} ist eingerichtet. Die WLAN-Schnittstelle heißt {name}.")
    except Exception as e:
        log(f"Treiber nicht eingerichtet: {e!r}")
        status(state="failed", ids=need, message=f"Der {NAME} ließ sich nicht einrichten: {str(e)[:160]}")
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode != "auto":
        log("Unbekannte Anforderung verworfen.")
        return 0
    os.makedirs(RUN, exist_ok=True)
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0
    try:
        return do_auto()
    except Exception as e:
        log(f"Fehler: {e!r}")
        status(state="failed", message=str(e)[:200])
        return 0


if __name__ == "__main__":
    sys.exit(main())
