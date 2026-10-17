"""IRL4YOU BOX Oberfläche: Einstellungen sichern und wiederherstellen (Export, Import, Zugangsdaten-Tresor)."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time

from .camservices import HdmiService
from .common import APP_DIR, iface_ips, local_macs, read
from .settings_clean import SETTINGS_FORMAT, SETTINGS_SECTIONS, SETTINGS_VERSION, SettingsClean


class Vault:
    ITERATIONS = 600000
    MIN_ITER, MAX_ITER = 100000, 2000000
    TAG = b"IRL4YOU-BOX-SETTINGS-1|"
    MIN_PASSWORD, MAX_PASSWORD = 8, 128
    _TABLES = None

    @classmethod
    def _tables(cls):
        if cls._TABLES:
            return cls._TABLES
        sbox = [0] * 256
        rot = lambda v, n: ((v << n) | (v >> (8 - n))) & 0xFF
        p = q = 1
        while True:
            p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
            q ^= (q << 1) & 0xFF
            q ^= (q << 2) & 0xFF
            q ^= (q << 4) & 0xFF
            if q & 0x80:
                q ^= 0x09
            sbox[p] = (q ^ rot(q, 1) ^ rot(q, 2) ^ rot(q, 3) ^ rot(q, 4) ^ 0x63) & 0xFF
            if p == 1:
                break
        sbox[0] = 0x63
        t0 = []
        for a in range(256):
            s = sbox[a]
            s2 = ((s << 1) ^ (0x1B if s & 0x80 else 0)) & 0xFF
            t0.append((s2 << 24) | (s << 16) | (s << 8) | (s2 ^ s))
        ror = lambda w, n: ((w >> n) | (w << (32 - n))) & 0xFFFFFFFF
        cls._TABLES = (sbox, t0, [ror(w, 8) for w in t0], [ror(w, 16) for w in t0], [ror(w, 24) for w in t0])
        return cls._TABLES

    @classmethod
    def _round_keys(cls, key):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("AES-256 braucht einen Schlüssel von 32 Byte")
        sbox = cls._tables()[0]
        sub = lambda w: (sbox[w >> 24] << 24) | (sbox[(w >> 16) & 255] << 16) | (sbox[(w >> 8) & 255] << 8) | sbox[w & 255]
        w = [int.from_bytes(key[i:i + 4], "big") for i in range(0, 32, 4)]
        rcon = 1
        for i in range(8, 60):
            t = w[i - 1]
            if i % 8 == 0:
                t = sub(((t << 8) | (t >> 24)) & 0xFFFFFFFF) ^ (rcon << 24)
                rcon = ((rcon << 1) ^ (0x11B if rcon & 0x80 else 0)) & 0xFF
            elif i % 8 == 4:
                t = sub(t)
            w.append(w[i - 8] ^ t)
        return w

    @classmethod
    def aes256_block(cls, rk, block):
        sbox, t0, t1, t2, t3 = cls._tables()
        s0, s1, s2, s3 = (int.from_bytes(block[i:i + 4], "big") ^ rk[i // 4] for i in (0, 4, 8, 12))
        for r in range(1, 14):
            k = 4 * r
            s0, s1, s2, s3 = (t0[s0 >> 24] ^ t1[(s1 >> 16) & 255] ^ t2[(s2 >> 8) & 255] ^ t3[s3 & 255] ^ rk[k],
                              t0[s1 >> 24] ^ t1[(s2 >> 16) & 255] ^ t2[(s3 >> 8) & 255] ^ t3[s0 & 255] ^ rk[k + 1],
                              t0[s2 >> 24] ^ t1[(s3 >> 16) & 255] ^ t2[(s0 >> 8) & 255] ^ t3[s1 & 255] ^ rk[k + 2],
                              t0[s3 >> 24] ^ t1[(s0 >> 16) & 255] ^ t2[(s1 >> 8) & 255] ^ t3[s2 & 255] ^ rk[k + 3])
        k = 56
        out = ((sbox[s0 >> 24] << 24) | (sbox[(s1 >> 16) & 255] << 16) | (sbox[(s2 >> 8) & 255] << 8) | sbox[s3 & 255]) ^ rk[k], \
              ((sbox[s1 >> 24] << 24) | (sbox[(s2 >> 16) & 255] << 16) | (sbox[(s3 >> 8) & 255] << 8) | sbox[s0 & 255]) ^ rk[k + 1], \
              ((sbox[s2 >> 24] << 24) | (sbox[(s3 >> 16) & 255] << 16) | (sbox[(s0 >> 8) & 255] << 8) | sbox[s1 & 255]) ^ rk[k + 2], \
              ((sbox[s3 >> 24] << 24) | (sbox[(s0 >> 16) & 255] << 16) | (sbox[(s1 >> 8) & 255] << 8) | sbox[s2 & 255]) ^ rk[k + 3]
        return b"".join(v.to_bytes(4, "big") for v in out)

    @classmethod
    def ctr(cls, key, counter, data):
        rk = cls._round_keys(key)
        out = bytearray()
        for i in range(0, len(data), 16):
            ks = cls.aes256_block(rk, ((counter + i // 16) & ((1 << 128) - 1)).to_bytes(16, "big"))
            chunk = data[i:i + 16]
            n = len(chunk)
            out += (int.from_bytes(chunk, "big") ^ int.from_bytes(ks[:n], "big")).to_bytes(n, "big")
        return bytes(out)

    @classmethod
    def _keys(cls, password, salt, iterations):
        k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, 64)
        return k[:32], k[32:]

    @classmethod
    def _mac(cls, mac_key, iterations, salt, nonce, data):
        return hmac.new(mac_key, cls.TAG + iterations.to_bytes(8, "big") + salt + nonce + data, hashlib.sha256).digest()

    @classmethod
    def check_password(cls, password):
        if not isinstance(password, str) or not cls.MIN_PASSWORD <= len(password) <= cls.MAX_PASSWORD:
            raise ValueError("Passwort: %d bis %d Zeichen" % (cls.MIN_PASSWORD, cls.MAX_PASSWORD))

    @classmethod
    def seal(cls, plain, password, header, iterations=None):
        cls.check_password(password)
        iterations = iterations or cls.ITERATIONS
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        enc_key, mac_key = cls._keys(password, salt, iterations)
        data = cls.ctr(enc_key, int.from_bytes(nonce + b"\0\0\0\0", "big"), plain)
        b64 = lambda b: base64.b64encode(b).decode("ascii")
        return dict(header, encrypted=True, cipher="AES-256-CTR", kdf="PBKDF2-HMAC-SHA256", iterations=iterations,
                    salt=b64(salt), nonce=b64(nonce), data=b64(data), mac=b64(cls._mac(mac_key, iterations, salt, nonce, data)))

    @classmethod
    def open(cls, doc, password):
        cls.check_password(password)
        try:
            if doc.get("cipher") != "AES-256-CTR" or doc.get("kdf") != "PBKDF2-HMAC-SHA256":
                raise ValueError
            iterations = doc.get("iterations")
            if isinstance(iterations, bool) or not isinstance(iterations, int) or not cls.MIN_ITER <= iterations <= cls.MAX_ITER:
                raise ValueError
            salt, nonce, data, mac = (base64.b64decode(str(doc.get(k, "")), validate=True) for k in ("salt", "nonce", "data", "mac"))
            if len(salt) != 16 or len(nonce) != 12 or len(mac) != 32:
                raise ValueError
        except (ValueError, TypeError, binascii.Error):
            raise ValueError("Die Datei ist keine gültige verschlüsselte Sicherung")
        enc_key, mac_key = cls._keys(password, salt, iterations)
        if not hmac.compare_digest(mac, cls._mac(mac_key, iterations, salt, nonce, data)):
            raise ValueError("Das Passwort ist falsch oder die Datei wurde verändert")
        return cls.ctr(enc_key, int.from_bytes(nonce + b"\0\0\0\0", "big"), data)


class SettingsTransfer(SettingsClean):
    MAX_BODY = 262144

    def __init__(self, state_dir, cams, pipeline, srtla, autostart, names, djisvc, wifi, send, demo=False):
        self.cams, self.pipeline, self.srtla, self.autostart = cams, pipeline, srtla, autostart
        self.names, self.djisvc, self.wifi, self.send, self.demo = names, djisvc, wifi, send, demo
        self.progress = {"state": "idle"}
        self.iface_map = {}
        self.hdmi = self.twitch = self.netchoice = None
        self.backup_dir = os.path.join(state_dir, "backup")
        self.backup_path = os.path.join(self.backup_dir, "vor-einspielen.json")
        self.version = (read(os.path.join(APP_DIR, "VERSION"), "") or "").strip()

    def make_document(self, secrets_on, wifi_data=None):
        doc = {"format": SETTINGS_FORMAT, "version": SETTINGS_VERSION, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "box_version": self.version, "secrets": bool(secrets_on)}
        with self.cams.lock:
            doc["cameras"] = [dict({"name": c["name"], "key": c["key"], "role": c["role"]}, **({"iface": c["iface"]} if c.get("iface") else {}))
                              for c in self.cams.cams]
        doc["pipeline"] = {k: v for k, v in self.pipeline.cfg.items()}
        with self.srtla.lock:
            data = self.srtla.data
            servers = [dict({"name": s["name"], "host": s["host"], "port": s["port"]}, **({"streamid": s.get("streamid", "")} if secrets_on else {}))
                       for s in data["servers"]]
            sel = next((i for i, s in enumerate(data["servers"]) if s["id"] == data.get("selected")), None)
            doc["srtla"] = {"servers": servers, "selected": sel, "settings": dict(data["settings"])}
        doc["autostart"] = {"enabled": bool(self.autostart.enabled())}
        doc["names"] = self.names._all()
        dj = []
        for addr, c in sorted(self.djisvc._config().items()):
            if isinstance(c, dict):
                e = {k: c.get(k) for k in ("name", "model", "kind", "wifi_ifname", "ip", "resolution", "fps", "bitrate", "stabilization", "autoconnect", "ssid", "status_only")
                     if c.get(k) is not None}
                e["addr"] = str(addr).upper()
                if secrets_on and c.get("password"):
                    e["password"] = c["password"]
                dj.append(e)
        doc["dji"] = dj
        hs = {}
        for iface, h in sorted(self.wifi.hotspots().items()):
            e = {k: h.get(k) for k in ("ssid", "band", "channel") if h.get(k) is not None}
            if secrets_on and h.get("password"):
                e["password"] = h["password"]
            hs[iface] = e
        doc["hotspots"] = hs
        doc["ifaces"] = local_macs()
        if self.hdmi is not None:
            try:
                st = self.hdmi.status()
            except Exception:
                st = {}
            if st.get("service"):
                doc["hdmi"] = {k: st["settings"][k] for k in HdmiService.ALLOWED}
        if self.twitch is not None:
            with self.twitch.lock:
                t = self.twitch.data
                doc["twitch"] = {"enabled": bool(t["enabled"]), "channel": t["channel"], "login": t["login"], "threshold": t["threshold"],
                                 "message": t["message"], "only_live": bool(t["only_live"])}
        if self.netchoice is not None and self.netchoice.iface:
            doc["camnet"] = {"iface": self.netchoice.iface}
        if wifi_data is not None:
            doc["wifi"] = {"networks": [{k: v for k, v in n.items() if secrets_on or k != "password"} for n in wifi_data.get("networks", [])],
                           "skipped": list(wifi_data.get("skipped", []))}
        return doc

    def export(self, secrets_on, password=None, with_wifi=True):
        if secrets_on and not password:
            raise ValueError("Eine Datei mit Passwörtern wird immer verschlüsselt: bitte ein Passwort zum Verschlüsseln eingeben")
        if password:
            Vault.check_password(password)
        notes, wifi_data = [], None
        if with_wifi:
            try:
                wifi_data = self.wifi.export_saved(secrets_on)
            except (ValueError, RuntimeError) as e:
                notes.append("Die gespeicherten WLAN-Netze sind nicht dabei: " + str(e))
        doc = self.make_document(secrets_on, wifi_data)
        if wifi_data and wifi_data.get("skipped"):
            notes.append("Nicht übertragbar: " + ", ".join("„%s“ (%s)" % (s.get("ssid", "?"), s.get("why", "?")) for s in wifi_data["skipped"][:10]))
        header = {k: doc[k] for k in ("format", "version", "created", "box_version", "secrets")}
        if password:
            out = Vault.seal(json.dumps(doc, ensure_ascii=False).encode("utf-8"), password, header)
        else:
            out = doc
        return {"document": out, "encrypted": bool(password), "notes": notes}

    def read_document(self, raw, password=None):
        if not isinstance(raw, dict) or raw.get("format") != SETTINGS_FORMAT:
            raise ValueError("Das ist keine Sicherung der IRL4YOU BOX")
        ver = raw.get("version")
        if isinstance(ver, bool) or not isinstance(ver, int) or ver < 1:
            raise ValueError("Die Version der Sicherung ist ungültig")
        if ver > SETTINGS_VERSION:
            raise ValueError("Die Sicherung stammt von einer neueren Version (%s). Bitte zuerst die Box aktualisieren." % ver)
        if len(json.dumps(raw)) > self.MAX_BODY:
            raise ValueError("Die Datei ist zu groß")
        if raw.get("encrypted") is True:
            if not password:
                raise ValueError("Die Datei ist verschlüsselt: bitte das Passwort eingeben")
            try:
                doc = json.loads(Vault.open(raw, password).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                if isinstance(e, ValueError) and ("Passwort" in str(e) or "Datei" in str(e)):
                    raise
                raise ValueError("Der Inhalt der Sicherung ist beschädigt")
            if not isinstance(doc, dict) or doc.get("format") != SETTINGS_FORMAT or doc.get("version") != ver:
                raise ValueError("Der Inhalt der Sicherung passt nicht zur Kennung")
            return doc, True
        if raw.get("secrets") is True:
            raise ValueError("Eine Sicherung mit Passwörtern muss verschlüsselt sein")
        return raw, False

    def preview(self, raw, password=None):
        doc, encrypted = self.read_document(raw, password)
        _, report = self.clean(doc)
        if not report:
            raise ValueError("In der Datei steht nichts, was sich einspielen lässt")
        return {"ok": True, "encrypted": encrypted, "created": str(doc.get("created", ""))[:32], "box_version": str(doc.get("box_version", ""))[:16],
                "secrets": doc.get("secrets") is True, "sections": report, "has_backup": os.path.isfile(self.backup_path)}

    def _guard(self):
        if self.send._active():
            raise ValueError("Es wird gerade gesendet. Bitte zuerst die Sendung beenden, dann einspielen.")

    def _write_backup(self):
        doc = self.make_document(True)
        os.makedirs(self.backup_dir, mode=0o700, exist_ok=True)
        tmp = self.backup_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f)
        os.replace(tmp, self.backup_path)

    def apply(self, raw, password=None, sections=None):
        self._guard()
        doc, _ = self.read_document(raw, password)
        return self._apply_doc(doc, sections)

    def _apply_doc(self, doc, sections):
        clean, report = self.clean(doc)
        wanted = [s for s, _ in SETTINGS_SECTIONS if s in clean and (sections is None or s in sections)]
        if not wanted:
            raise ValueError("Nichts zum Einspielen gewählt")
        results, labels = [], dict(SETTINGS_SECTIONS)
        total = len(wanted)
        self.progress = {"state": "running", "done": 0, "total": total, "label": ""}
        try:
            self._write_backup()
            for i, sid in enumerate(wanted):
                self.progress = {"state": "running", "done": i, "total": total, "label": labels[sid]}
                try:
                    msg = getattr(self, "_apply_" + sid)(clean[sid])
                    results.append({"id": sid, "label": labels[sid], "ok": True, "message": msg})
                except Exception as e:
                    results.append({"id": sid, "label": labels[sid], "ok": False, "message": str(e) or type(e).__name__})
        finally:
            self.progress = {"state": "done", "done": total, "total": total, "label": ""}
        if self.iface_map:
            results.insert(0, {"id": "ifaces", "label": "Netzwerkkarten", "ok": True,
                               "message": "Namen der Netzwerkkarten anhand der MAC-Adressen angepasst: %s" % ", ".join("%s → %s" % (a, b) for a, b in sorted(self.iface_map.items()))})
        if "cameras" in wanted and "dji" in wanted:
            self._restore_camera_names(clean["cameras"])
        for r in report:
            if not r["ok"] and (sections is None or r["id"] in sections):
                results.append({"id": r["id"], "label": r["label"], "ok": False, "message": "Nicht eingespielt: " + r["note"]})
        return {"ok": True, "results": results, "backup": True}

    def _restore_camera_names(self, cams):
        want = {c["key"]: c["name"] for c in cams}
        with self.cams.lock:
            changed = False
            for c in self.cams.cams:
                n = want.get(c["key"])
                if n and c["name"] != n:
                    c["name"] = n
                    changed = True
            if changed:
                self.cams.save()

    def restore(self):
        self._guard()
        try:
            with open(self.backup_path) as f:
                doc = json.load(f)
        except (OSError, ValueError):
            raise ValueError("Es gibt keinen gesicherten Stand")
        if not isinstance(doc, dict) or doc.get("format") != SETTINGS_FORMAT:
            raise ValueError("Der gesicherte Stand ist beschädigt")
        doc.pop("wifi", None)
        return self._apply_doc(doc, None)

    def _apply_cameras(self, cams):
        with self.cams.lock:
            old = {c["key"]: c for c in self.cams.cams}
            new = []
            for c in cams:
                cam = {"id": old[c["key"]]["id"] if c["key"] in old else secrets.token_hex(4), "name": c["name"], "key": c["key"], "role": c["role"]}
                if c.get("iface") and self.cams.host_for_iface(c["iface"]) is not None:
                    cam["iface"] = c["iface"]
                new.append(cam)
            gone = len([k for k in old if k not in {c["key"] for c in cams}])
            self.cams.cams = new
            self.cams.save()
        return "%d Kameras eingespielt%s" % (len(new), (", %d nicht in der Sicherung entfernt" % gone) if gone else "")

    def _apply_pipeline(self, req):
        self.pipeline.set(dict(req), [c["key"] for c in self.cams.cams])
        return "Bildaufbau eingespielt"

    def _apply_srtla(self, new):
        valid = [o["iface"] for o in iface_ips()]
        with self.srtla.lock:
            old = list(self.srtla.data["servers"])
            servers = []
            for s in new["servers"]:
                same = next((o for o in old if (o["name"], o["host"], o["port"]) == (s["name"], s["host"], s["port"])), None)
                servers.append({"id": same["id"] if same else secrets.token_hex(4), "name": s["name"], "host": s["host"], "port": s["port"],
                                "streamid": s["streamid"] or ((same or {}).get("streamid", ""))})
            self.srtla.data["servers"] = servers
            self.srtla.data["selected"] = servers[new["selected"]]["id"] if servers and new["selected"] is not None else (servers[0]["id"] if servers else None)
            st = dict(new["settings"])
            ups = [u for u in st["uplinks"] if u in valid]
            st["uplinks"] = ups or list(self.srtla.data["settings"].get("uplinks", []))
            self.srtla.data["settings"] = st
            self.srtla.save()
        skipped = len(new["settings"]["uplinks"]) - len(ups)
        return "%d SRTLA-Server eingespielt%s" % (len(servers), (", %d Netze zum Senden gibt es hier nicht (ausgelassen)" % skipped) if skipped else "")

    def _apply_autostart(self, d):
        self.autostart.set_enabled(d["enabled"])
        return "Automatischer Start: " + ("an" if d["enabled"] else "aus")

    def _apply_names(self, names):
        for k, v in names.items():
            self.names.set(k, v)
        return "%d Namen eingespielt" % len(names)

    def _apply_dji(self, cams):
        done, problems = 0, []
        for c in cams:
            try:
                self.djisvc.command({"cmd": "add", "addr": c["addr"], "name": c["name"], "model": c["model"], "kind": c["kind"]})
                upd = {"cmd": "update"}
                upd.update({k: v for k, v in c.items() if k not in ("kind", "model")})
                self.djisvc.command(upd)
                done += 1
            except (ValueError, RuntimeError) as e:
                problems.append("%s: %s" % (c["name"], e))
                if isinstance(e, RuntimeError):
                    break
        if problems and not done:
            raise RuntimeError("; ".join(problems))
        return "%d DJI-Kameras eingespielt (bitte einmal verbinden)" % done + ((", Probleme: " + "; ".join(problems)) if problems else "")

    def _apply_hdmi(self, d):
        if self.hdmi is None:
            raise RuntimeError("Der HDMI-Dienst ist hier nicht verfügbar")
        self.hdmi.set(dict(d))
        return "HDMI-Einstellungen eingespielt"

    def _apply_twitch(self, d):
        if self.twitch is None:
            raise RuntimeError("Die Akku-Warnung ist hier nicht verfügbar")
        self.twitch.set(dict({k: d[k] for k in ("channel", "login", "threshold", "message", "only_live")}, enabled=False))
        if not d["enabled"]:
            return "Akku-Warnung: Einstellungen eingespielt (aus)"
        try:
            self.twitch.set({"enabled": True})
        except ValueError:
            return "Akku-Warnung: eingespielt, bleibt aber ausgeschaltet (Token oder Twitch-Anmeldung fehlt auf dieser Box)"
        return "Akku-Warnung: eingespielt (an)"

    def _apply_camnet(self, d):
        if self.netchoice is None:
            raise RuntimeError("Das Netzwerk für Kameras ist hier nicht verfügbar")
        try:
            self.netchoice.select(d["iface"])
        except ValueError:
            return "Netzwerk für Kameras: „%s“ gibt es hier nicht (ausgelassen)" % d["iface"]
        return "Netzwerk für Kameras eingespielt"

    def _apply_hotspots(self, hs):
        return self.wifi.hotspot_import(hs)

    def _apply_wifi(self, d):
        return self.wifi.import_saved(d["networks"])


def client_wifi_list():
    def run(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=4).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    out = []
    for line in run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"]).splitlines():
        parts = line.replace("\\:", "\x00").split(":")
        if len(parts) < 4 or parts[1] != "wifi" or parts[2] != "connected":
            continue
        conn = parts[3].replace("\x00", ":")
        if run(["nmcli", "-g", "802-11-wireless.mode", "connection", "show", conn]) == "ap":
            continue
        ip = run(["nmcli", "-g", "IP4.ADDRESS", "dev", "show", parts[0]]).split("/")[0].split("\n")[0]
        if ip:
            out.append({"iface": parts[0], "ip": ip})
    return out
