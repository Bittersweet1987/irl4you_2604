#!/usr/bin/env python3
"""IRL4YOU BOX: trägt Bluetooth-Sticks nach, die der btusb-Treiber des Kernels (6.1) nicht kennt.

Der Kernel kennt die meisten Realtek-Sticks (TP-Link UB500, ASUS BT500, RTL8761B ...) und die Barrot-Sticks (UGREEN BT6.0) selbst, samt
Firmware (linux-firmware) und den Behelfen für deren Eigenheiten. Es fehlen nur wenige Kennungen; für diese wird zur Laufzeit ein Eintrag
im btusb angelegt (new_id, Vorlage 0bda:b009 = Realtek) und der Stick neu angebunden. Es wird nichts gebaut oder dauerhaft verändert;
nach dem Neustart oder Einstecken legt der Dienst den Eintrag erneut an. Zustand: /run/pipbox-btdriver/status.json.
"""
import errno
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import time

RUN = "/run/pipbox-btdriver"
STATUS = f"{RUN}/status.json"
LOCK = "/run/pipbox-btdriver.lock"
REQ = "/var/lib/pipbox/btdriver-request"
SYSFS_USB = "/sys/bus/usb/devices"
SYSFS_BT = "/sys/class/bluetooth"
DRV = "/sys/bus/usb/drivers/btusb"
REF_ID = ("0bda", "b009")           # Realtek-Eintrag der Tabelle im Kernel: Vorlage für die nachgetragenen Kennungen
STEPS = 3

# Im btusb von Linux 6.1.172 (Rockchip-BSP) bereits enthalten, kein Eingriff nötig
BUILTIN = {
    "2357:0604": "TP-Link UB500 (Realtek RTL8761BUV)",
    "2550:8761": "Realtek RTL8761B (2550:8761)",
    "0bda:8771": "Realtek RTL8761B (0bda:8771)",
    "0b05:190e": "ASUS USB-BT500 (Realtek RTL8761B)",
    "33fa:0012": "UGREEN BT6.0 Adapter (Barrot)",
    "33fa:0010": "Barrot Bluetooth-Stick (33fa:0010)",
}
# Fehlen im Kernel 6.1: werden nachgetragen
MISSING = {
    "2c4e:0115": "Mercusys MA530 (Realtek RTL8761B)",
    "0bda:a725": "Realtek (0bda:a725)",
    "2b89:8761": "Realtek RTL8761B (2b89:8761)",
}
CANDIDATES = {**BUILTIN, **MISSING}


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


def step(n, text, **kw):
    status(state="working", step=n, steps=STEPS, step_text=text, **kw)


def take_request(path=None):
    try:
        fd = os.open(path or REQ, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return False
    try:
        ok = stat.S_ISREG(os.fstat(fd).st_mode) and os.read(fd, 16).strip() == b"install"
    except OSError:
        ok = False
    finally:
        os.close(fd)
    try:
        os.unlink(path or REQ)
    except OSError:
        pass
    return ok


def read_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def write_sysfs(path, text):
    with open(path, "w") as f:
        f.write(text)


def usb_devices(root=SYSFS_USB):
    """{usb-id: [Gerätename, ...]} der angesteckten Geräte."""
    out = {}
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for n in names:
        if ":" in n:
            continue
        v = read_text(f"{root}/{n}/idVendor").strip().lower()
        p = read_text(f"{root}/{n}/idProduct").strip().lower()
        if v and p:
            out.setdefault(f"{v}:{p}", []).append(n)
    return out


def wanted(devs=None):
    devs = usb_devices() if devs is None else devs
    return {i: CANDIDATES[i] for i in sorted(CANDIDATES) if i in devs}


def hci_for_dev(dev, bt_root=SYSFS_BT, usb_root=SYSFS_USB, resolve=os.path.realpath):
    base = resolve(os.path.join(usb_root, dev))
    try:
        names = sorted(n for n in os.listdir(bt_root) if re.fullmatch(r"hci\d+", n))
    except OSError:
        return ""
    return next((n for n in names if resolve(os.path.join(bt_root, n, "device")).startswith(base + os.sep)), "")


def wait_hci(dev, timeout=20, find=hci_for_dev, sleep=time.sleep, now=time.time):
    end = now() + timeout
    while True:
        name = find(dev)
        if name or now() >= end:
            return name
        sleep(1)


def dynid_line(ident):
    v, p = ident.split(":")
    return f"{v} {p} 0 {REF_ID[0]} {REF_ID[1]}"


def has_dynid(ident, text=None):
    v, p = ident.split(":")
    text = read_text(DRV + "/new_id") if text is None else text
    return any(line.split()[:2] == [v, p] for line in text.splitlines())


def add_dynid(ident):
    try:
        write_sysfs(DRV + "/new_id", dynid_line(ident))
    except OSError as e:
        # ENODEV: kein ungebundenes Gerät passte (der Stick hängt schon am allgemeinen Treiber); der Eintrag steht trotzdem
        if e.errno != errno.ENODEV or not has_dynid(ident):
            raise


def rebind(dev, drv=DRV, usb_root=SYSFS_USB):
    """Schnittstellen des Sticks vom btusb lösen und neu anbinden, damit der neue Tabelleneintrag greift."""
    try:
        ifs = sorted(n for n in os.listdir(f"{usb_root}/{dev}") if n.startswith(dev + ":"))
    except OSError:
        return
    for i in ifs:
        if os.path.exists(f"{drv}/{i}"):
            write_sysfs(f"{drv}/unbind", i)
        try:
            write_sysfs(f"{drv}/bind", i)
        except OSError:
            pass


def unblock_hci(hci, bt_root=SYSFS_BT):
    """Hebt eine Funksperre (rfkill, "soft") des Adapters auf: ein gespeicherter Sperrzustand aus dem Image würde sonst jedes Einschalten verhindern."""
    done = False
    try:
        subs = os.listdir(f"{bt_root}/{hci}")
    except OSError:
        return False
    for n in subs:
        soft = f"{bt_root}/{hci}/{n}/soft"
        if n.startswith("rfkill") and read_text(soft).strip() == "1":
            write_sysfs(soft, "0")
            done = True
    return done


def stream_running():
    return subprocess.run(["pgrep", "-x", "irl4you-encoder"], capture_output=True).returncode == 0


def do_auto(force=False):
    need = wanted()

    def st(**kw):
        status(manual=bool(force), **kw)
    if not need:
        if force:
            st(state="none", ids=[], message="Es steckt kein Bluetooth-Stick, den dieser Helfer betreut.")
        return 0
    names = ", ".join(need.values())
    ids = sorted(need)
    devs = usb_devices()
    problems = []
    try:
        for ident in ids:
            for dev in devs[ident]:
                if ident in MISSING and not has_dynid(ident):
                    if stream_running():
                        st(state="waiting", ids=ids, message=f"Der Stick {need[ident]} wird nach der Übertragung eingerichtet (Bluetooth fehlt dabei kurz).")
                        return 0
                    step(1, "Stick wird eingetragen", ids=ids, message=f"{need[ident]} wird dem Bluetooth-Treiber bekannt gemacht …")
                    add_dynid(ident)
                    step(2, "Stick wird neu angebunden")
                    rebind(dev)
                elif not hci_for_dev(dev):
                    step(2, "Stick wird neu angebunden", ids=ids)
                    rebind(dev)
                step(3, "Stick wird geprüft")
                hci = wait_hci(dev)
                if not hci:
                    problems.append(f"{need[ident]}: es entsteht kein Bluetooth-Adapter")
                elif unblock_hci(hci):
                    log(f"{hci}: Funksperre aufgehoben")
    except OSError as e:
        problems.append(f"Zugriff auf den Treiber nicht möglich: {str(e)[:100]}")
    if problems:
        log("Bluetooth: " + "; ".join(problems))
        st(state="failed", ids=ids, step=STEPS, message=f"Der Stick ließ sich nicht einrichten: {problems[-1][:160]}")
    else:
        log(f"Bluetooth-Stick eingerichtet: {names}")
        st(state="ok", ids=ids, step=STEPS, message=f"Treiber für {names} ist eingerichtet. Eine Kamera fragt nach dem Wechsel des Sticks eventuell einmal nach der Kopplung.")
    return 0


def do_uninstall():
    for ident in MISSING:
        if has_dynid(ident):
            write_sysfs(DRV + "/remove_id", " ".join(ident.split(":")))
    log("Nachgetragene Kennungen entfernt")
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode not in ("auto", "uninstall"):
        log("Unbekannte Anforderung verworfen.")
        return 0
    os.makedirs(RUN, exist_ok=True)
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0
    try:
        return do_auto(force=take_request()) if mode == "auto" else do_uninstall()
    except Exception as e:
        log(f"Fehler: {e!r}")
        status(state="failed", message=str(e)[:200])
        return 0


if __name__ == "__main__":
    sys.exit(main())
