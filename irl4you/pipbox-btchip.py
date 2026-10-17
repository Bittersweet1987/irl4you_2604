#!/usr/bin/env python3
"""IRL4YOU BOX: prüft den eingebauten Bluetooth-Chip der Radxa ROCK 5B Plus (Realtek RTL8852BE, USB 13d3:3572).

Mit dem Kernel 6.1 braucht der Chip keinen Herstellertreiber mehr: btusb kennt ihn samt Firmware (rtl_bt/rtl8852bu_fw.bin aus linux-firmware).
Der Helfer stellt nur fest, ob der Adapter da ist, und meldet den Zustand (/run/pipbox-btchip/status.json). Auf jedem anderen Board endet er sofort.
"""
import fcntl
import json
import os
import re
import sys
import time

BOARD = "Radxa ROCK 5B Plus"
USB_ID = "13d3:3572"
USB_NAME = "Realtek (RTL8852BE, eingebaut)"
FIRMWARE = ("rtl_bt/rtl8852bu_fw.bin", "rtl_bt/rtl8852bu_config.bin")
FIRMWARE_DIR = "/lib/firmware"
DT_MODEL = "/proc/device-tree/model"
SYSFS_USB = "/sys/bus/usb/devices"
SYSFS_BT = "/sys/class/bluetooth"
RUN = "/run/pipbox-btchip"
STATUS = f"{RUN}/status.json"
LOCK = "/run/pipbox-btchip.lock"
REQ = "/var/lib/pipbox/btchip-request"
WAIT_ADAPTER = 25


def log(msg):
    print(f"pipbox-btchip: {msg}", flush=True)


def read_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def status(**kw):
    os.makedirs(RUN, exist_ok=True)
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(kw, time=int(time.time())), f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATUS)


def board_ok():
    return read_text(DT_MODEL).replace("\0", "").strip() == BOARD


def chip_device(root=SYSFS_USB):
    vid, pid = USB_ID.split(":")
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return None
    for n in names:
        if ":" not in n and read_text(f"{root}/{n}/idVendor").strip().lower() == vid and read_text(f"{root}/{n}/idProduct").strip().lower() == pid:
            return n
    return None


def hci_of(dev, bt_root=SYSFS_BT, usb_root=SYSFS_USB, resolve=os.path.realpath):
    base = resolve(os.path.join(usb_root, dev))
    try:
        names = sorted(n for n in os.listdir(bt_root) if re.fullmatch(r"hci\d+", n))
    except OSError:
        return None
    return next((n for n in names if resolve(os.path.join(bt_root, n, "device")).startswith(base + os.sep)), None)


def firmware_present(root=FIRMWARE_DIR):
    return all(any(os.path.exists(f"{root}/{f}{ext}") for ext in ("", ".zst", ".xz")) for f in FIRMWARE)


def take_request():
    try:
        os.unlink(REQ)
        return True
    except OSError:
        return False


def do_auto(sleep=time.sleep):
    force = take_request()
    if not board_ok():
        return 0
    dev = chip_device()
    if not dev:
        return 0

    def st(**kw):
        status(manual=force, applies=True, name=USB_NAME, **kw)
    end = time.time() + WAIT_ADAPTER
    while not hci_of(dev) and time.time() < end:
        sleep(1)
    hci = hci_of(dev)
    if hci:
        st(state="ok", message=f"Der Bluetooth-Chip auf dem Board ({USB_NAME}, {USB_ID}) läuft ({hci}). Ein Stick ist nicht nötig.")
    elif not firmware_present():
        st(state="failed", message="Die Firmware des Bluetooth-Chips (rtl_bt/rtl8852bu_fw.bin, Paket linux-firmware) fehlt.")
    else:
        st(state="failed", message=f"Der Bluetooth-Chip auf dem Board ({USB_ID}) hat keinen Adapter bekommen.")
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode not in ("auto", "uninstall"):
        log("Unbekannte Anforderung verworfen.")
        return 0
    if mode == "uninstall":
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
        if board_ok():
            status(state="failed", applies=True, name=USB_NAME, message=str(e)[:200])
        return 0


if __name__ == "__main__":
    sys.exit(main())
