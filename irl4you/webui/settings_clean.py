"""IRL4YOU BOX Oberfläche: Einstellungen sichern: Prüfung der einzelnen Abschnitte (Mischklasse von SettingsTransfer)."""

import ipaddress
import json
import os
import re

import hdmi_daemon
from twitch import TwitchStore

from .cameras import DeviceNames
from .camservices import DjiService, HdmiService
from .common import IFACE_NAME_RE, KEY_RE, ROLES, local_macs
from .netstate import SrtlaStore
from .pipeline import PipelineStore
from .wifi import Wifi


SETTINGS_FORMAT = "irl4you-box-einstellungen"


SETTINGS_VERSION = 1


SETTINGS_SECTIONS = (("cameras", "Kameras"), ("pipeline", "Bildaufbau"), ("srtla", "SRTLA-Server und Sendeeinstellungen"),
                     ("autostart", "Automatischer Start"), ("names", "Namen (Verbindungen, WLAN- und Bluetooth-Sticks)"),
                     ("dji", "DJI-Kameras (Einstellungen)"), ("hdmi", "HDMI-Eingang (Einstellungen)"), ("twitch", "Akku-Warnung im Twitch-Chat (Einstellungen)"),
                     ("camnet", "Netzwerk für Kameras (Standard)"),
                     ("hotspots", "Hotspots"), ("wifi", "Gespeicherte WLAN-Netze"))


class SettingsClean:
    @staticmethod
    def _text(v, lo, hi, what):
        if not isinstance(v, str) or not lo <= len(v.strip()) <= hi or any(not ch.isprintable() for ch in v):
            raise ValueError("%s ungültig" % what)
        return v.strip()

    def _clean_cameras(self, raw):
        if not isinstance(raw, list) or len(raw) > 40:
            raise ValueError("Die Kameraliste ist ungültig (höchstens 40 Kameras)")
        out, keys, roles, names, notes = [], set(), set(), set(), []
        for c in raw:
            if not isinstance(c, dict):
                raise ValueError("Die Kameraliste ist ungültig")
            name = self._text(c.get("name"), 1, 40, "Kameraname")
            key = c.get("key")
            if not isinstance(key, str) or not KEY_RE.match(key):
                raise ValueError("Ein Kamera-Schlüssel ist ungültig")
            if key in keys:
                raise ValueError("Der Kamera-Schlüssel „%s“ kommt doppelt vor" % key)
            role = c.get("role") if c.get("role") in ROLES else "extra"
            if role in ("main", "pip") and role in roles:
                role = "extra"
                notes.append("Rolle von „%s“ auf „extra“ gestellt (die Rolle war doppelt)" % name)
            if name.casefold() in names:
                name = (name[:34] + " " + key[-5:]).strip()
            iface = c.get("iface") if isinstance(c.get("iface"), str) and IFACE_NAME_RE.match(c.get("iface", "")) else ""
            keys.add(key)
            roles.add(role)
            names.add(name.casefold())
            out.append({"name": name, "key": key, "role": role, "iface": iface})
        return out, notes

    def _clean_pipeline(self, raw, keys):
        if not isinstance(raw, dict):
            raise ValueError("Der Bildaufbau ist ungültig")
        tmp = PipelineStore(os.devnull)
        tmp.save = lambda: None
        tmp.set(dict(raw), list(keys))
        return dict(raw), []

    def _clean_srtla(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("servers"), list) or len(raw["servers"]) > 30:
            raise ValueError("Die SRTLA-Server sind ungültig (höchstens 30)")
        servers, notes = [], []
        for s in raw["servers"]:
            if not isinstance(s, dict):
                raise ValueError("Die SRTLA-Server sind ungültig")
            servers.append(SrtlaStore.check({"name": s.get("name"), "host": s.get("host"), "port": s.get("port"), "streamid": s.get("streamid") or ""}))
        sel = raw.get("selected")
        if isinstance(sel, bool) or not (sel is None or isinstance(sel, int)) or (isinstance(sel, int) and not 0 <= sel < len(servers)):
            sel = 0 if servers else None
        st = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
        cur = SrtlaStore.DEFAULT_SETTINGS
        try:
            mn, mx, lat = int(st.get("min_kbps", cur["min_kbps"])), int(st.get("max_kbps", cur["max_kbps"])), int(st.get("latency_ms", cur["latency_ms"]))
        except (TypeError, ValueError):
            raise ValueError("Bitrate und Latenz sind ungültig")
        if not 100 <= mn < mx <= 20000 or not 100 <= lat <= 10000:
            raise ValueError("Bitrate oder Latenz außerhalb des erlaubten Bereichs")
        spread = st.get("spread", "best")
        if spread not in ("best", "all"):
            raise ValueError("Verteilung ungültig")
        ups = st.get("uplinks", [])
        if not isinstance(ups, list) or len(ups) > 20 or any(not isinstance(u, str) or not IFACE_NAME_RE.match(u) for u in ups):
            raise ValueError("Die Netze zum Senden sind ungültig")
        return {"servers": servers, "selected": sel, "settings": {"min_kbps": mn, "max_kbps": mx, "latency_ms": lat, "spread": spread,
                                                                  "uplinks": sorted(set(ups))}}, notes

    def _clean_autostart(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("enabled"), bool):
            raise ValueError("Der automatische Start ist ungültig")
        return {"enabled": raw["enabled"]}, []

    def _clean_names(self, raw):
        if not isinstance(raw, dict) or len(raw) > 60:
            raise ValueError("Die Namen der Sticks sind ungültig")
        out = {}
        for k, v in raw.items():
            if not isinstance(k, str) or not DeviceNames.KEY_RE.match(k) or not isinstance(v, str):
                raise ValueError("Die Namen der Sticks sind ungültig")
            v = " ".join(v.split())
            if len(v) > 40 or any(not ch.isprintable() for ch in v):
                raise ValueError("Ein Name eines Sticks ist ungültig")
            if v:
                out[k] = v
        return out, []

    def _clean_dji(self, raw):
        if not isinstance(raw, list) or len(raw) > 20:
            raise ValueError("Die DJI-Kameras sind ungültig (höchstens 20)")
        out, seen = [], set()
        for c in raw:
            if not isinstance(c, dict) or not isinstance(c.get("addr"), str) or not DjiService.MAC_RE.match(c["addr"]):
                raise ValueError("Eine DJI-Kamera hat keine gültige Geräteadresse")
            addr = c["addr"].upper()
            if addr in seen:
                raise ValueError("Eine DJI-Kamera kommt doppelt vor")
            seen.add(addr)
            e = {"addr": addr, "name": self._text(c.get("name") or c.get("model") or addr, 1, 40, "Kameraname"),
                 "model": self._text(c.get("model") or "", 0, 60, "Modell"), "kind": c.get("kind") if isinstance(c.get("kind"), str) and re.fullmatch(r"[a-z0-9_]{1,20}", c["kind"]) else "unknown"}
            wi = c.get("wifi_ifname", "")
            if wi not in ("", "manual") and not (isinstance(wi, str) and IFACE_NAME_RE.match(wi)):
                raise ValueError("Die Verbindung einer DJI-Kamera ist ungültig")
            e["wifi_ifname"] = wi
            ip = c.get("ip", "")
            if ip:
                try:
                    ipaddress.IPv4Address(ip)
                except (ValueError, TypeError):
                    raise ValueError("Die Adresse einer DJI-Kamera ist ungültig")
            e["ip"] = ip or ""
            ssid = c.get("ssid", "")
            if not isinstance(ssid, str) or len(ssid.encode("utf-8")) > 32 or any(ord(ch) < 32 or ord(ch) == 127 for ch in ssid):
                raise ValueError("Das WLAN einer DJI-Kamera ist ungültig")
            e["ssid"] = ssid
            pw = c.get("password", "")
            if not isinstance(pw, str) or len(pw) > 64 or any(ord(ch) < 32 or ord(ch) == 127 for ch in pw):
                raise ValueError("Das WLAN-Passwort einer DJI-Kamera ist ungültig")
            if pw:
                e["password"] = pw
            for k, lo, hi in (("fps", 1, 120), ("bitrate", 100, 40000)):
                v = c.get(k)
                if v is not None:
                    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                        raise ValueError("Ein Wert einer DJI-Kamera ist ungültig (%s)" % k)
                    e[k] = v
            for k in ("resolution", "stabilization"):
                v = c.get(k)
                if v is not None:
                    if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_+.-]{1,20}", v):
                        raise ValueError("Ein Wert einer DJI-Kamera ist ungültig (%s)" % k)
                    e[k] = v
            if c.get("autoconnect") is not None:
                if not isinstance(c["autoconnect"], bool):
                    raise ValueError("Ein Wert einer DJI-Kamera ist ungültig (autoconnect)")
                e["autoconnect"] = c["autoconnect"]
            if c.get("status_only") is not None:
                if not isinstance(c["status_only"], bool):
                    raise ValueError("Ein Wert einer DJI-Kamera ist ungültig (status_only)")
                e["status_only"] = c["status_only"]
            out.append(e)
        return out, ["Die Bluetooth-Kopplung lässt sich nicht mitnehmen: Die Kameras müssen nach dem Einspielen einmal neu verbunden werden"] if out else []

    def _clean_hdmi(self, raw):
        if not isinstance(raw, dict):
            raise ValueError("Die HDMI-Einstellungen sind ungültig")
        want = {k: raw[k] for k in HdmiService.ALLOWED if k in raw}
        out = hdmi_daemon.clean_settings(want, None)
        return {k: out[k] for k in HdmiService.ALLOWED}, []

    def _clean_twitch(self, raw):
        if not isinstance(raw, dict):
            raise ValueError("Die Einstellungen der Akku-Warnung sind ungültig")
        for k in ("enabled", "only_live"):
            if not isinstance(raw.get(k), bool):
                raise ValueError("Die Einstellungen der Akku-Warnung sind ungültig")
        out = {"enabled": raw["enabled"], "only_live": raw["only_live"],
               "channel": TwitchStore._name(raw.get("channel", ""), TwitchStore.ERR_CHANNEL), "login": TwitchStore._name(raw.get("login", ""), TwitchStore.ERR_LOGIN),
               "threshold": TwitchStore._threshold(raw.get("threshold")), "message": TwitchStore._message(raw.get("message"))}
        return out, ["Token und Twitch-Anmeldung werden nie mitgenommen: bitte hier neu anmelden"]

    def _clean_camnet(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("iface"), str) or not IFACE_NAME_RE.match(raw["iface"]):
            raise ValueError("Das Netzwerk für Kameras ist ungültig")
        return {"iface": raw["iface"]}, []

    def _clean_hotspots(self, raw):
        if not isinstance(raw, dict) or len(raw) > 8:
            raise ValueError("Die Hotspots sind ungültig")
        out, notes = {}, []
        for iface, h in raw.items():
            if not isinstance(iface, str) or not re.fullmatch(r"[a-z][a-z0-9]{1,14}", iface) or not isinstance(h, dict):
                raise ValueError("Die Hotspots sind ungültig")
            ssid, pw, band, ch = h.get("ssid"), h.get("password", ""), h.get("band", "bg"), h.get("channel", 0)
            if (not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32 or ssid != ssid.strip() or any(ord(c) < 32 or ord(c) == 127 for c in ssid)
                    or ssid.startswith(Wifi.HS_PREFIX)):
                raise ValueError("Der Name eines Hotspots ist ungültig")
            if not isinstance(pw, str) or (pw and (not 8 <= len(pw) <= 63 or any(not 32 <= ord(c) < 127 for c in pw))):
                raise ValueError("Das Passwort eines Hotspots ist ungültig")
            if band not in Wifi.HS_BANDS or isinstance(ch, bool) or not isinstance(ch, int) or (ch != 0 and ch not in Wifi.HS_BANDS[band]):
                raise ValueError("Band oder Kanal eines Hotspots ist ungültig")
            out[iface] = {"ssid": ssid, "password": pw, "band": band, "channel": ch}
        return out, notes

    def _clean_wifi(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("networks"), list) or len(raw["networks"]) > 50:
            raise ValueError("Die gespeicherten WLAN-Netze sind ungültig (höchstens 50)")
        out, notes, seen = [], [], set()
        for n in raw["networks"]:
            if not isinstance(n, dict):
                raise ValueError("Die gespeicherten WLAN-Netze sind ungültig")
            ssid, pw = n.get("ssid"), n.get("password", "")
            if not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32 or any(ord(c) < 32 or ord(c) == 127 for c in ssid):
                raise ValueError("Der Name eines WLAN-Netzes ist ungültig")
            if ssid.startswith(Wifi.HS_PREFIX) or ssid in seen:
                continue
            seen.add(ssid)
            if not isinstance(pw, str) or (pw and not (8 <= len(pw) <= 63 and all(32 <= ord(c) < 127 for c in pw) or re.fullmatch(r"[0-9a-fA-F]{64}", pw))):
                raise ValueError("Ein WLAN-Passwort ist ungültig")
            sec = n.get("security", "none" if n.get("open") is True else "wpa-psk")
            if sec not in ("wpa-psk", "sae", "none"):
                raise ValueError("Die Sicherheitsart eines WLAN-Netzes ist ungültig")
            open_net = n.get("open") is True or sec == "none"
            if open_net and pw:
                raise ValueError("Ein offenes WLAN-Netz hat kein Passwort")
            if not pw and not open_net:
                notes.append("„%s“ ohne Passwort gesichert: bitte neu verbinden" % ssid)
                continue
            out.append({"ssid": ssid, "password": pw, "hidden": n.get("hidden") is True, "open": open_net, "security": "none" if open_net else sec})
        return {"networks": out}, notes

    def _iface_map(self, doc):
        old = doc.get("ifaces")
        if not isinstance(old, dict):
            return {}
        mine = {mac: name for name, mac in local_macs().items()}
        out = {}
        for name, mac in old.items():
            if isinstance(name, str) and IFACE_NAME_RE.match(name) and isinstance(mac, str) and mine.get(mac.lower()) not in (None, name):
                out[name] = mine[mac.lower()]
        return out

    @staticmethod
    def _remap_ifaces(doc, m):
        d = json.loads(json.dumps(doc))
        r = lambda n: m.get(n, n) if isinstance(n, str) else n
        for c in d.get("cameras", []) if isinstance(d.get("cameras"), list) else []:
            if isinstance(c, dict) and c.get("iface"):
                c["iface"] = r(c["iface"])
        if isinstance(d.get("camnet"), dict) and d["camnet"].get("iface"):
            d["camnet"]["iface"] = r(d["camnet"]["iface"])
        st = d.get("srtla", {}).get("settings") if isinstance(d.get("srtla"), dict) else None
        if isinstance(st, dict):
            if isinstance(st.get("uplinks"), list):
                st["uplinks"] = [r(u) for u in st["uplinks"]]
            if isinstance(st.get("min_share"), dict):
                st["min_share"] = {r(k): v for k, v in st["min_share"].items()}
        if isinstance(d.get("hotspots"), dict):
            d["hotspots"] = {r(k): v for k, v in d["hotspots"].items()}
        if isinstance(d.get("dji"), list):
            for e in d["dji"]:
                if isinstance(e, dict) and e.get("wifi_ifname"):
                    e["wifi_ifname"] = r(e["wifi_ifname"])
        if isinstance(d.get("names"), dict):
            d["names"] = {("net:" + r(k[4:]) if isinstance(k, str) and k.startswith("net:") else ("if:" + r(k[3:]) if isinstance(k, str) and k.startswith("if:") else k)): v
                          for k, v in d["names"].items()}
        return d

    def clean(self, doc):
        clean, report, labels = {}, [], dict(SETTINGS_SECTIONS)
        self.iface_map = self._iface_map(doc)
        if self.iface_map:
            doc = self._remap_ifaces(doc, self.iface_map)
        for sid, label in SETTINGS_SECTIONS:
            if sid not in doc:
                continue
            raw = doc[sid]
            try:
                if sid == "cameras":
                    data, notes = self._clean_cameras(raw)
                    count = len(data)
                elif sid == "pipeline":
                    keys = [c["key"] for c in clean["cameras"]] if "cameras" in clean else [c["key"] for c in self.cams.cams]
                    data, notes = self._clean_pipeline(raw, keys)
                    count = 1
                elif sid == "srtla":
                    data, notes = self._clean_srtla(raw)
                    count = len(data["servers"])
                elif sid == "autostart":
                    data, notes = self._clean_autostart(raw)
                    count = 1
                elif sid == "names":
                    data, notes = self._clean_names(raw)
                    count = len(data)
                elif sid == "dji":
                    data, notes = self._clean_dji(raw)
                    count = len(data)
                elif sid == "hdmi":
                    data, notes = self._clean_hdmi(raw)
                    count = 1
                elif sid == "twitch":
                    data, notes = self._clean_twitch(raw)
                    count = 1
                elif sid == "camnet":
                    data, notes = self._clean_camnet(raw)
                    count = 1
                elif sid == "hotspots":
                    data, notes = self._clean_hotspots(raw)
                    count = len(data)
                else:
                    data, notes = self._clean_wifi(raw)
                    count = len(data["networks"])
                clean[sid] = data
                report.append({"id": sid, "label": label, "count": count, "ok": True, "note": "; ".join(notes)})
            except ValueError as e:
                report.append({"id": sid, "label": label, "count": 0, "ok": False, "note": str(e)})
        return clean, report
