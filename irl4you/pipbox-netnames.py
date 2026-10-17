#!/usr/bin/env python3
"""IRL4YOU BOX: feste Namen für die LAN-Karten (eth0, eth1, …) nach ihrer MAC-Adresse.

Mit net.ifnames=0 vergibt der Kernel eth0/eth1 in der Reihenfolge, in der die Karten bereit werden. Auf dem Orange Pi 5 Plus
tauschen die beiden Karten dabei manchmal die Namen (gesehen am 17.10.2026). Dieser Dienst läuft beim Booten vor NetworkManager
und benennt die Karten nach /etc/pipbox/netnames.json um ({"<mac>": "eth0", …}).

Fehlt die Datei, wird sie einmal angelegt: zuerst aus den Namen, die IRL4YOU zuletzt gesehen hat (/var/lib/pipbox/iface-macs.json),
sonst nach der Lage der Karte am Bus (gleich auf jeder Box desselben Boards).

Umbenennen geht nur, solange die Karte aus ist, und zwei Karten können ihre Namen nicht direkt tauschen. Darum zuerst alle
betroffenen Karten auf Zwischennamen, dann auf die Zielnamen.

  pipbox-netnames.py           anwenden (Dienst beim Booten)
  pipbox-netnames.py --show    Zuordnung anzeigen, nichts ändern
"""
import json
import os
import re
import subprocess
import sys

SYS_NET = "/sys/class/net"
CONF = "/etc/pipbox/netnames.json"
SEEN = "/var/lib/pipbox/iface-macs.json"
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
        if not NAME_RE.match(n) and not n.startswith("irltmp"):
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


def plan(cards, mapping):
    """Liste der Umbenennungen [(alt, neu)], zuerst auf Zwischennamen, dann auf Ziele. Leer, wenn alles passt."""
    by_mac = {mac: n for n, (mac, _p) in cards.items()}
    want = {n: mapping[mac] for mac, n in by_mac.items() if mac in mapping}
    wrong = [n for n, w in want.items() if n != w]
    if not wrong:
        return []
    # Karten ohne Eintrag, die einen Zielnamen belegen, müssen auch weichen
    targets = set(want[n] for n in wrong)
    blockers = [n for n in cards if n in targets and n not in want]
    steps, tmp_of = [], {}
    for k, n in enumerate(sorted(wrong + blockers)):
        tmp_of[n] = "irltmp%d" % k
        steps.append((n, tmp_of[n]))
    used = set(n for n in cards if n not in tmp_of) | set(want[n] for n in wrong)
    for n in sorted(wrong):
        steps.append((tmp_of[n], want[n]))
    i = 0
    for n in sorted(blockers):
        while "eth%d" % i in used:
            i += 1
        steps.append((tmp_of[n], "eth%d" % i))
        used.add("eth%d" % i)
    return steps


def load_conf():
    try:
        with open(CONF) as f:
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
        if "--show" not in argv and mapping:
            os.makedirs(os.path.dirname(CONF), exist_ok=True)
            with open(CONF + ".tmp", "w") as f:
                json.dump(mapping, f, indent=1, sort_keys=True)
            os.replace(CONF + ".tmp", CONF)
            print("pipbox-netnames: Zuordnung angelegt: " + ", ".join("%s=%s" % (v, k) for k, v in sorted(mapping.items(), key=lambda x: x[1])))
    steps = plan(cards, mapping)
    if "--show" in argv:
        print(json.dumps({"cards": {n: m for n, (m, _p) in cards.items()}, "mapping": mapping, "steps": steps}, indent=1))
        return 0
    for old, new in steps:
        subprocess.run(["ip", "link", "set", "dev", old, "down"], capture_output=True, timeout=10)
        r = subprocess.run(["ip", "link", "set", "dev", old, "name", new], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            print("pipbox-netnames: %s -> %s fehlgeschlagen: %s" % (old, new, r.stderr.strip()[:200]))
    if steps:
        print("pipbox-netnames: " + ", ".join("%s->%s" % s for s in steps if not s[1].startswith("irltmp")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
