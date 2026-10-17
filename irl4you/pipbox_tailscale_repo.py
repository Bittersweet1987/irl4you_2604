#!/usr/bin/env python3
"""IRL4YOU BOX: Tailscale aus dem offiziellen Paketarchiv (pkgs.tailscale.com) einrichten.

Der Schlüssel des Archivs wird vor dem Eintragen gegen den bekannten Fingerabdruck von Tailscale geprüft (kein Vertrauen allein auf die Übertragung);
die Pakete selbst prüft apt danach gegen diesen Schlüssel. Aufrufer: install/irl4you-setup.sh (Ersteinrichtung, Image) und der Fernzugriff-Helfer
pipbox-remote.py (Knopf "Tailscale installieren"). Aufruf von Hand: python3 pipbox_tailscale_repo.py install
"""
import hashlib
import os
import subprocess
import sys
import urllib.request

CODENAMES = ("resolute", "noble", "jammy", "focal")
BASE = "https://pkgs.tailscale.com/stable/ubuntu/"
KEY_URL = BASE + "{}.noarmor.gpg"
LIST_URL = BASE + "{}.tailscale-keyring.list"
KEYRING = "/usr/share/keyrings/tailscale-archive-keyring.gpg"
SOURCE = "/etc/apt/sources.list.d/tailscale.list"
# Signierschlüssel des Tailscale-Paketarchivs (RSA 4096, vom 25.02.2020): tailscale.com/kb/1039/install-ubuntu
FINGERPRINT = "2596A99EAAB33821893C0A79458CA832957F5868"


def installed():
    return subprocess.run(["which", "tailscale"], capture_output=True).returncode == 0


def codename(path="/etc/os-release"):
    with open(path) as f:
        for line in f:
            if line.startswith("VERSION_CODENAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def get(url, limit=100000):
    if not url.startswith(BASE):
        raise RuntimeError("Unerlaubte Quelle")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "irl4you-box"}), timeout=30) as r:
        return r.read(limit + 1)[:limit]


def key_fingerprint(data):
    """Fingerabdruck (SHA-1 über den öffentlichen Hauptschlüssel, RFC 4880 §12.2) des ersten Pakets einer OpenPGP-Schlüsseldatei, groß geschrieben."""
    if not data or not data[0] & 0x80:
        raise ValueError("kein OpenPGP-Schlüssel")
    tag, pos = (data[0] & 0x3F, 1) if data[0] & 0x40 else ((data[0] >> 2) & 0x0F, 1)
    if data[0] & 0x40:       # neues Format: Länge in 1, 2 oder 5 Bytes
        b = data[pos]
        if b < 192:
            size, pos = b, pos + 1
        elif b < 224:
            size, pos = ((b - 192) << 8) + data[pos + 1] + 192, pos + 2
        elif b == 255:
            size, pos = int.from_bytes(data[pos + 1:pos + 5], "big"), pos + 5
        else:
            raise ValueError("Paketlänge nicht unterstützt")
    else:                    # altes Format: Längenart in den untersten zwei Bits
        n = {0: 1, 1: 2, 2: 4}.get(data[0] & 3)
        if n is None:
            raise ValueError("Paketlänge nicht unterstützt")
        size, pos = int.from_bytes(data[pos:pos + n], "big"), pos + n
    if tag != 6 or data[pos] != 4 or pos + size > len(data):
        raise ValueError("kein öffentlicher Schlüssel (Version 4)")
    body = data[pos:pos + size]
    return hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body).hexdigest().upper()


def install(log=print, status=lambda **kw: None):
    if installed():
        return False
    cn = codename()
    if cn not in CODENAMES:
        raise RuntimeError(f"Dieses System ({cn or '?'}) wird nicht unterstützt (Ubuntu 20.04 bis 26.04).")
    status(state="working", step="Lade die Paketquelle von tailscale.com", message="")
    key = get(KEY_URL.format(cn), 20000)
    if key_fingerprint(key) != FINGERPRINT:
        raise RuntimeError("Der Schlüssel von tailscale.com hat nicht den erwarteten Fingerabdruck, die Installation wird abgebrochen")
    lst = get(LIST_URL.format(cn), 2000).decode()
    if "pkgs.tailscale.com/stable/ubuntu" not in lst or "deb " not in lst:
        raise RuntimeError("Die Quellenliste von tailscale.com sieht unerwartet aus")
    with open(KEYRING, "wb") as f:
        f.write(key)
    os.chmod(KEYRING, 0o644)
    with open(SOURCE, "w") as f:
        f.write(lst)
    os.chmod(SOURCE, 0o644)
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive", LC_ALL="C")
    status(step="Aktualisiere die Paketliste (nur Tailscale)")
    subprocess.run(["apt-get", "update", "-o", "Dir::Etc::sourcelist=sources.list.d/tailscale.list",
                    "-o", "Dir::Etc::sourceparts=-", "-o", "APT::Get::List-Cleanup=0"], env=env, capture_output=True, timeout=300)
    status(step="Installiere Tailscale")
    r = subprocess.run(["apt-get", "install", "-y", "--no-install-recommends", "-o", "DPkg::Lock::Timeout=120", "tailscale"],
                       env=env, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not installed():
        raise RuntimeError("Die Installation von Tailscale ist fehlgeschlagen: " + (r.stdout + r.stderr)[-150:].replace("\n", " "))
    log("Tailscale installiert")
    return True


def main():
    if sys.argv[1:] != ["install"]:
        print("Aufruf: pipbox_tailscale_repo.py install", file=sys.stderr)
        return 2
    try:
        install()
    except Exception as e:
        print(f"Tailscale nicht installiert: {e}", file=sys.stderr)
        return 1
    subprocess.run(["systemctl", "enable", "tailscaled.service"], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
