#!/usr/bin/env python3
"""IRL4YOU BOX: feste Namen für die LAN-Karten (eth0, eth1, …) nach ihrer MAC-Adresse.

Mit net.ifnames=0 vergibt der Kernel eth0/eth1 in der Reihenfolge, in der die Karten bereit werden. Auf dem Orange Pi 5 Plus tauschen die beiden
Karten dabei manchmal die Namen (gesehen am 17.10.2026). Dieses Programm legt die Zuordnung MAC -> Name fest und schreibt sie als systemd-.link-Dateien
(/etc/systemd/network/10-irl4you-<name>.link). udev wendet sie beim nächsten Start an, wenn die Karten erscheinen.

WICHTIG: Es benennt nie im laufenden Betrieb um. Ein Umbenennen im Betrieb (per ip-Befehl) trennt die Karte, NetworkManager bricht DHCP ab und die Box ist
nicht mehr erreichbar (so geschehen beim ersten Update-Test am 17.10.2026). Darum nur Dateien schreiben; wirksam wird es beim Start.

Quelle der Zuordnung, in dieser Reihenfolge:
  1. /etc/pipbox/netnames.json  ({"<mac>": "eth0", …}), wenn vorhanden
  2. die Namen, die IRL4YOU zuletzt gesehen hat (/var/lib/pipbox/iface-macs.json)
  3. die Lage der Karte am Bus (gleich auf jeder Box desselben Boards)

  pipbox-netnames.py           Zuordnung anlegen (falls noch keine da ist) und .link-Dateien schreiben
  pipbox-netnames.py --show    Zuordnung anzeigen, nichts schreiben
"""
import json
import os
import re
import sys

SYS_NET = "/sys/class/net"
CONF = "/etc/pipbox/netnames.json"
SEEN = "/var/lib/pipbox/iface-macs.json"
LINK_DIR = "/etc/systemd/network"
LINK_PREFIX = "10-irl4you-"
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
NAME_RE = re.compile(r"^eth\d{1,2}$")


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def wired_cards(sysnet=SYS_NET):
    """Eingebaute und USB-LAN-Karten: {name: (mac, bus_path)}; ohne WLAN, Brücken, virtuelle Karten."""
    out = {}
    try:
        names = sorted(os.listdir(sysnet))
    except OSError:
        return out
    for n in names:
        base = os.path.join(sysnet, n)
        if _read(os.path.join(base, "type")) != "1" or not os.path.exists(os.path.join(base, "device")):
            continue
        if any(os.path.isdir(os.path.join(base, d)) for d in ("wireless", "phy80211", "bridge")):
            continue
        if not NAME_RE.match(n):
            continue
        mac = _read(os.path.join(base, "address")).lower()
        if MAC_RE.match(mac):
            out[n] = (mac, os.path.realpath(os.path.join(base, "device")))
    return out


def initial_map(cards, seen):
    """Erste Zuordnung: zuletzt gesehene Namen, sonst nach Bus-Lage."""
    m = {}
    for name, mac in (seen or {}).items():
        if isinstance(name, str) and NAME_RE.match(name) and isinstance(mac, str) and MAC_RE.match(mac.lower()):
            if mac.lower() not in m and name not in m.values():
                m[mac.lower()] = name
    rest = sorted((path, mac) for mac, path in cards.values() if mac not in m)
    i = 0
    for _path, mac in rest:
        while "eth%d" % i in m.values():
            i += 1
        m[mac] = "eth%d" % i
    return m


def link_text(mac, name):
    return ("# IRL4YOU BOX: feste Kartennamen nach MAC (pipbox-netnames.py). Gilt ab dem nächsten Start, nie im laufenden Betrieb.\n"
            "[Match]\nMACAddress=%s\nType=ether\n\n[Link]\nName=%s\n" % (mac, name))


def write_links(mapping, link_dir=LINK_DIR):
    """Schreibt je Karte eine .link-Datei und entfernt veraltete eigene. Gibt (geschrieben, entfernt) zurück."""
    os.makedirs(link_dir, exist_ok=True)
    want = {LINK_PREFIX + name + ".link": link_text(mac, name) for mac, name in mapping.items()}
    written, removed = [], []
    for fn, text in want.items():
        p = os.path.join(link_dir, fn)
        if _read(p) != text.strip():
            with open(p + ".tmp", "w") as f:
                f.write(text)
            os.replace(p + ".tmp", p)
            written.append(fn)
    for fn in os.listdir(link_dir):
        if fn.startswith(LINK_PREFIX) and fn.endswith(".link") and fn not in want:
            os.remove(os.path.join(link_dir, fn))
            removed.append(fn)
    return written, removed


def load_conf(path=CONF):
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    return {k.lower(): v for k, v in d.items() if isinstance(k, str) and MAC_RE.match(k.lower()) and isinstance(v, str) and NAME_RE.match(v)}


def main(argv):
    cards = wired_cards()
    mapping = load_conf()
    if mapping is None:
        try:
            with open(SEEN) as f:
                seen = json.load(f)
        except (OSError, ValueError):
            seen = {}
        mapping = initial_map(cards, seen if isinstance(seen, dict) else {})
    if "--show" in argv:
        print(json.dumps({"cards": {n: m for n, (m, _p) in cards.items()}, "mapping": mapping}, indent=1))
        return 0
    if not mapping:
        return 0
    if load_conf() is None:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF + ".tmp", "w") as f:
            json.dump(mapping, f, indent=1, sort_keys=True)
        os.replace(CONF + ".tmp", CONF)
        print("pipbox-netnames: Zuordnung angelegt: " + ", ".join("%s=%s" % (v, k) for k, v in sorted(mapping.items(), key=lambda x: x[1])))
    written, removed = write_links(mapping)
    if written or removed:
        print("pipbox-netnames: .link-Dateien geschrieben: %s (gilt ab dem nächsten Start)" % (", ".join(written + ["-" + r for r in removed])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
