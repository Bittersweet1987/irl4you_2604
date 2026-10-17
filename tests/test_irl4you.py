"""Ohne Box: die neuen Teile von IRL4YOU für 26.04 (Belabox-2604/irl4you) als Funktionen prüfen.

Mobilfunk (pipbox_modem), eigenes Passwort mit übernommenem bcrypt-Hash, zusätzliche Tonquellen, feste Kartennamen,
Netzwerk-Dispatcher (mit einem nachgebauten `ip`), Vollständigkeit des Installationsskripts.
Läuft unter Windows und Linux nur mit der Standardbibliothek; der bcrypt-Test braucht das Modul bcrypt (sonst übersprungen).
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IRL = os.path.join(ROOT, "irl4you")
INSTALL = os.path.join(IRL, "install")


def _linux_shims():
    """server.py und hdmi_daemon.py importieren Linux-Module; unter Windows reichen leere Stellvertreter (nur Importe)."""
    if sys.platform != "win32":
        return
    for name in ("pwd", "grp", "fcntl"):
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.getpwnam = m.getgrnam = lambda n: (_ for _ in ()).throw(KeyError(n))
            m.ioctl = lambda *a: (_ for _ in ()).throw(OSError("shim"))
            m.flock = lambda *a: None
            m.LOCK_EX = m.LOCK_NB = m.LOCK_UN = m.LOCK_SH = 0
            sys.modules[name] = m
    import signal
    for n in ("killpg", "getuid", "geteuid", "getpgid", "setsid", "getgid"):
        if not hasattr(os, n):
            setattr(os, n, lambda *a, **k: 0)
    for n in ("SIGKILL", "SIGHUP", "SIGUSR1", "SIGUSR2", "SIGCHLD", "SIGPIPE", "SIGALRM", "SIGQUIT", "SIGCONT", "SIGSTOP"):
        if not hasattr(signal, n):
            setattr(signal, n, signal.SIGTERM)


def irl(name):
    _linux_shims()
    if IRL not in sys.path:
        sys.path.insert(0, IRL)
    return importlib.import_module(name)


def load_script(fname, modname):
    _linux_shims()
    if IRL not in sys.path:
        sys.path.insert(0, IRL)
    spec = importlib.util.spec_from_file_location(modname, os.path.join(IRL, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MMCLI_MODEM = {"modem": {"dbus-path": "/org/freedesktop/ModemManager1/Modem/0", "generic": {
    "device-identifier": "f00dfeed", "manufacturer": "Quectel", "model": "EM12-G", "state": "connected", "state-failed-reason": "--",
    "access-technologies": ["lte"], "signal-quality": {"recent": "yes", "value": "67"},
    "current-modes": "allowed: 3g, 4g; preferred: 4g",
    "supported-modes": ["allowed: 3g; preferred: none", "allowed: 4g; preferred: none", "allowed: 3g, 4g; preferred: 4g",
                        "allowed: 3g, 4g; preferred: 3g", "allowed: 2g, 3g, 4g; preferred: 4g"],
    "ports": ["cdc-wdm0 (qmi)", "ttyUSB2 (at)", "wwan0 (net)"], "sim": "/org/freedesktop/ModemManager1/SIM/0",
    "equipment-identifier": "123456789012345"},
    "3gpp": {"operator-code": "26201", "operator-name": "Telekom.de", "registration-state": "roaming", "imei": "123456789012345"}}}
MMCLI_SIM = {"sim": {"properties": {"operator-code": "26201", "operator-name": "Telekom", "iccid": "8949", "imsi": "26201"}}}


class TestModem(unittest.TestCase):
    def setUp(self):
        self.pm = irl("pipbox_modem")

    def test_netztypen(self):
        pm = self.pm
        self.assertEqual(pm.parse_modes("allowed: 3g, 4g; preferred: 4g"), ("3g|4g", "4g"))
        self.assertEqual(pm.parse_modes("allowed: any; preferred: none"), ("any", ""))
        self.assertEqual(pm.parse_modes("--"), ("", ""))
        self.assertEqual(pm.supported_types(MMCLI_MODEM["modem"]["generic"]["supported-modes"]), ["2g|3g|4g", "3g|4g", "3g", "4g"])
        self.assertEqual(pm.mode_label("3g|4g"), "3G/4G")
        self.assertEqual(pm.mode_label("4g"), "nur 4G (LTE)")

    def test_modem_info_ohne_kennungen(self):
        info = self.pm.modem_info(MMCLI_MODEM, MMCLI_SIM)
        self.assertEqual(info["iface"], "wwan0")
        self.assertEqual(info["state"], "verbunden")
        self.assertEqual(info["signal"], 67)
        self.assertTrue(info["roaming"])
        self.assertEqual(info["tech"], ["4G"])
        self.assertEqual(len(info["id"]), 12)
        text = json.dumps(info)
        for secret in ("123456789012345", "8949", "f00dfeed"):
            self.assertNotIn(secret, text, "IMEI/ICCID/Gerätekennung darf nicht in den Zustand")

    def test_kein_sim(self):
        m = json.loads(json.dumps(MMCLI_MODEM))
        m["modem"]["generic"].update(state="failed", **{"state-failed-reason": "sim-missing"})
        self.assertEqual(self.pm.modem_info(m)["state"], "kein-sim")
        self.assertTrue(self.pm.modem_info(m)["no_sim"])

    def test_netzsuche(self):
        nets = self.pm.parse_scan(["operator-code: 26202, operator-name: Vodafone.de, access-technologies: lte, availability: available",
                                   "operator-code: 26201, operator-name: Telekom.de, access-technologies: gsm, lte, availability: current",
                                   "operator-code: 26203, operator-name: o2 - de, access-technologies: lte, availability: forbidden",
                                   "kaputt"])
        self.assertEqual([n["code"] for n in nets], ["26201", "26202", "26203"])
        self.assertEqual(nets[0]["tech"], ["2G", "4G"])
        self.assertTrue(nets[0]["current"])
        self.assertTrue(nets[2]["forbidden"])

    def test_einstellungen_pruefen(self):
        pm = self.pm
        c = pm.clean_config({"autoconfig": False, "apn": "internet.telekom", "roaming": True, "network": "26201", "network_type": "3g|4g"})
        self.assertEqual((c["apn"], c["roaming"], c["network"], c["network_type"]), ("internet.telekom", True, "26201", "3g|4g"))
        for bad in ({"apn": "a b"}, {"autoconfig": False, "apn": ""}, {"network": "abc"}, {"network_type": "4g|4g"},
                    {"network_type": "6g"}, {"roaming": "ja"}, {"username": "a b"}, {"password": "x" * 65}):
            with self.assertRaises(ValueError, msg=bad):
                pm.clean_config(bad)
        self.assertEqual(pm.clean_config({"network_type": "any"})["network_type"], "")

    def test_nm_profil(self):
        pm = self.pm
        cfg = pm.clean_config({"autoconfig": False, "apn": "web.vodafone.de", "roaming": False})
        a = pm.nm_settings(cfg, "f00dfeed", "geheim")
        kv = dict(zip(a[::2], a[1::2]))
        self.assertEqual(kv["gsm.apn"], "web.vodafone.de")
        self.assertEqual(kv["gsm.home-only"], "yes")
        self.assertEqual(kv["gsm.auto-config"], "no")
        self.assertEqual(kv["gsm.device-id"], "f00dfeed")
        self.assertEqual(kv["gsm.password"], "geheim")
        self.assertNotIn("gsm.password", pm.nm_settings(cfg, "f00dfeed", None), "ohne neues Passwort bleibt das gespeicherte")
        auto = dict(zip(*[iter(pm.nm_settings(pm.clean_config({}), "x"))] * 2))
        self.assertEqual((auto["gsm.auto-config"], auto["gsm.apn"]), ("yes", ""))
        self.assertEqual(pm.mm_modes_args("3g|4g", ["3g|4g"]), ["--set-allowed-modes=3g|4g", "--set-preferred-mode=4g"])
        self.assertEqual(pm.mm_modes_args("5g", ["3g|4g"]), [])

    def test_status_und_auftrag(self):
        pm = self.pm
        calls = {("-L",): {"modem-list": ["/org/freedesktop/ModemManager1/Modem/0"]}, ("-m", "0"): MMCLI_MODEM, ("-i", "0"): MMCLI_SIM}
        d = tempfile.mkdtemp()
        try:
            m = pm.Modems(d, run=lambda *a, **k: calls.get(a))
            st = m.status()
            self.assertEqual(len(st["modems"]), 1)
            mid = st["modems"][0]["id"]
            self.assertTrue(st["modems"][0]["config"]["autoconfig"])
            with self.assertRaises(ValueError):          # Helfer nicht installiert (keine Unit auf diesem Rechner)
                m.request({"action": "config", "id": mid, "roaming": True})
            m.status = lambda: dict(st, helper_installed=True)
            m.request({"action": "config", "id": mid, "autoconfig": False, "apn": "internet", "password": "pw1", "network_type": "3g|4g"})
            req = json.load(open(os.path.join(d, pm.REQ_NAME)))
            self.assertEqual(req["config"]["apn"], "internet")
            self.assertEqual(req["password"], "pw1")
            with self.assertRaises(ValueError):
                m.request({"action": "config", "id": mid, "network_type": "5g"})
            with self.assertRaises(ValueError):
                m.request({"action": "config", "id": "000000000000"})
        finally:
            shutil.rmtree(d)


class TestPasswort(unittest.TestCase):
    """Eigenes Passwort von IRL4YOU mit dem übernommenen bcrypt-Hash aus belaUI."""

    def setUp(self):
        try:
            import bcrypt
        except ImportError:
            self.skipTest("Modul bcrypt fehlt (unter 26.04: python3-bcrypt)")
        self.bcrypt = bcrypt
        self.server = irl("server")
        self.dir = tempfile.mkdtemp()
        self.pw = "Ein-Test-Passwort-1"
        self.h = bcrypt.hashpw(self.pw.encode(), bcrypt.gensalt(rounds=4)).decode()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_uebernommener_hash(self):
        with open(os.path.join(self.dir, "auth.json"), "w") as f:
            json.dump({"bcrypt": self.h}, f)
        a = self.server.Auth(self.dir)
        self.assertEqual(a.mode, "own")
        self.assertTrue(a.configured)
        tok = a.login(self.pw, "10.0.0.1")
        self.assertTrue(a.valid(tok))
        with self.assertRaises(ValueError):
            a.login("falsch", "10.0.0.1")

    def test_gemerkte_anmeldungen_bleiben_gueltig(self):
        """Gleicher Hash wie vorher in belaUI: 'Angemeldet bleiben' aus der 22.04-Zeit gilt weiter (sessions.json wird übernommen)."""
        bela = os.path.join(self.dir, "bela.json")
        with open(bela, "w") as f:
            json.dump({"password_hash": self.h}, f)
        alt = self.server.Auth(os.path.join(self.dir, "alt"), bela)
        neu_dir = os.path.join(self.dir, "neu")
        os.makedirs(neu_dir)
        with open(os.path.join(neu_dir, "auth.json"), "w") as f:
            json.dump({"bcrypt": self.h}, f)
        neu = self.server.Auth(neu_dir)
        self.assertEqual(alt._cred(), neu._cred())

    def test_passwort_aendern(self):
        with open(os.path.join(self.dir, "auth.json"), "w") as f:
            json.dump({"bcrypt": self.h}, f)
        a = self.server.Auth(self.dir)
        old_tok = a.login(self.pw, "10.0.0.2", remember=True)
        with self.assertRaises(ValueError):
            a.change_password("falsch", "Neues-Passwort-99", "10.0.0.2")
        with self.assertRaises(ValueError):
            a.change_password(self.pw, "kurz", "10.0.0.2")
        a.change_password(self.pw, "Neues-Passwort-99", "10.0.0.2")
        self.assertFalse(a.valid(old_tok), "nach dem Wechsel gelten alte Anmeldungen nicht mehr")
        self.assertTrue(a.valid(a.login("Neues-Passwort-99", "10.0.0.2")))
        self.assertNotIn("bcrypt", json.load(open(os.path.join(self.dir, "auth.json"))))
        b = self.server.Auth(self.dir)
        self.assertTrue(b.valid(b.login("Neues-Passwort-99", "10.0.0.3")))


class TestTonquellen(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def card(self, n, cid, usb=False, capture=True):
        base = os.path.join(self.dir, "card%d" % n)
        os.makedirs(os.path.join(base, "pcm0c" if capture else "pcm0p"))
        with open(os.path.join(base, "id"), "w") as f:
            f.write(cid + "\n")
        if usb:
            with open(os.path.join(base, "usbbus"), "w") as f:
                f.write("003/00%d\n" % n)

    def test_quellen_finden(self):
        self.card(0, "rockchiphdmi0", capture=False)
        self.card(3, "rockchiphdmiin")
        self.card(4, "rockchipes8388")
        self.card(5, "OsmoAction5", usb=True)
        self.card(6, "RODEWirelessGO", usb=True)
        self.assertEqual(self.hd.find_extra_audio("analog", self.dir), "plughw:CARD=rockchipes8388")
        self.assertEqual(self.hd.find_extra_audio("usb", self.dir), "plughw:CARD=OsmoAction5")
        self.assertEqual(self.hd.find_extra_audio("usb", self.dir, exclude="plughw:CARD=OsmoAction5"), "plughw:CARD=RODEWirelessGO")
        self.assertIsNone(self.hd.find_extra_audio("hdmi", self.dir))

    def test_einspeisung_mit_usb_ton(self):
        cfg = self.hd.clean_settings({"audio": "usb"})
        argv = self.hd.feeder_argv(cfg, extra_audio="plughw:CARD=RODEWirelessGO")
        self.assertIn("device=plughw:CARD=RODEWirelessGO", argv)
        stumm = self.hd.feeder_argv(cfg, extra_audio=None)
        self.assertIn("audiotestsrc", stumm, "fehlt das Gerät, läuft die Kamera ohne Ton weiter")
        with self.assertRaises(ValueError):
            self.hd.feeder_argv(cfg, extra_audio="hw:0;rm")
        with self.assertRaises(ValueError):
            self.hd.clean_settings({"audio": "mikro"})


def _sh():
    for c in (shutil.which("sh"), r"C:\Program Files\Git\bin\sh.exe", "/bin/sh"):
        if c and os.path.exists(c):
            return c
    return None


class TestKartennamen(unittest.TestCase):
    """Feste Kartennamen nach MAC: nur Dateien (.link), nie im laufenden Betrieb umbenennen (Testbox war am 17.10.2026 deshalb 10 Minuten weg)."""

    def setUp(self):
        self.nn = load_script("pipbox-netnames.py", "pipbox_netnames")

    def test_erste_zuordnung_aus_zuletzt_gesehen(self):
        cards = {"eth0": ("c0:74:2b:ff:53:59", "/pci/0004"), "eth1": ("c0:74:2b:ff:53:58", "/pci/0003")}
        m = self.nn.initial_map(cards, {"eth0": "c0:74:2b:ff:53:58", "eth1": "c0:74:2b:ff:53:59", "wlan0": "00:e0:4c:4f:91:c6"})
        self.assertEqual(m, {"c0:74:2b:ff:53:58": "eth0", "c0:74:2b:ff:53:59": "eth1"})
        m2 = self.nn.initial_map(cards, {})
        self.assertEqual(m2, {"c0:74:2b:ff:53:58": "eth0", "c0:74:2b:ff:53:59": "eth1"}, "ohne Vorwissen nach Bus-Lage")

    def test_link_dateien(self):
        d = tempfile.mkdtemp()
        try:
            m = {"c0:74:2b:ff:53:58": "eth0", "c0:74:2b:ff:53:59": "eth1"}
            written, removed = self.nn.write_links(m, d)
            self.assertEqual(sorted(written), ["10-irl4you-eth0.link", "10-irl4you-eth1.link"])
            text = open(os.path.join(d, "10-irl4you-eth0.link")).read()
            self.assertIn("MACAddress=c0:74:2b:ff:53:58", text)
            self.assertIn("Name=eth0", text)
            self.assertEqual(self.nn.write_links(m, d), ([], []), "zweiter Lauf ändert nichts")
            open(os.path.join(d, "50-fremd.link"), "w").write("[Match]\n")
            written, removed = self.nn.write_links({"c0:74:2b:ff:53:58": "eth0"}, d)
            self.assertEqual(removed, ["10-irl4you-eth1.link"])
            self.assertTrue(os.path.exists(os.path.join(d, "50-fremd.link")), "fremde .link-Dateien bleiben")
        finally:
            shutil.rmtree(d)

    def test_kein_umbenennen_im_betrieb(self):
        for rel in ("pipbox-netnames.py", "install/irl4you-setup.sh", "install/system-install.sh", "install/install-2604.sh"):
            src = open(os.path.join(IRL, rel), encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
            for bad in ("ip link set", "subprocess", "systemctl restart NetworkManager", "nmcli connection add", "nmcli con add"):
                self.assertNotIn(bad, code, "%s: %r verändert im Betrieb das Netz" % (rel, bad))
        self.assertFalse(os.path.exists(os.path.join(INSTALL, "pipbox-netnames.service")), "kein Dienst, der beim Start oder im Betrieb umbenennt")
        setup = open(os.path.join(INSTALL, "irl4you-setup.sh"), encoding="utf-8").read()
        self.assertNotIn("disable --now", setup, "ifplugd/networking nicht im Betrieb anhalten")
        self.assertIn("netnames.py", setup)


class TestNetzPruefung(unittest.TestCase):
    """install/net-check.sh: nach dem Update muss die Standardroute wieder da sein, wenn es vorher eine gab."""

    def setUp(self):
        self.sh = _sh()
        if not self.sh:
            self.skipTest("keine POSIX-Shell")
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_check(self, before, route, addr):
        d = self.dir.replace("\\", "/")
        state = os.path.join(self.dir, "before")
        if before is not None:
            open(state, "w").write("%s\n" % before)
        with open(os.path.join(self.dir, "ip"), "w", newline="\n") as f:
            f.write("#!/bin/sh\ncase \"$*\" in\n  \"-4 route show default\") %s;;\n  \"-4 -o addr show scope global\") %s;;\nesac\nexit 0\n" % (
                "echo 'default via 192.168.1.1 dev eth0'" if route else "true", "echo '2: eth0 inet 192.168.1.5/24'" if addr else "true"))
        os.chmod(os.path.join(self.dir, "ip"), 0o755)
        e = dict(os.environ, PATH=d + os.pathsep + os.environ.get("PATH", ""), IRL4YOU_NET_STATE=state.replace("\\", "/"), IRL4YOU_NET_WAIT="0")
        return subprocess.run([self.sh, os.path.join(INSTALL, "net-check.sh")], env=e, capture_output=True, text=True, timeout=30).returncode

    def test_netz_da(self):
        self.assertEqual(self.run_check(1, True, True), 0)

    def test_netz_weg_rollback(self):
        self.assertEqual(self.run_check(1, False, False), 1)
        self.assertEqual(self.run_check(1, True, False), 1, "Route ohne Adresse zählt nicht")

    def test_vorher_kein_netz_kein_rollback(self):
        self.assertEqual(self.run_check(0, False, False), 0)
        self.assertEqual(self.run_check(None, False, False), 0)

    def test_hooks_verbinden(self):
        self.assertIn("net-check.sh", open(os.path.join(INSTALL, "health.sh"), encoding="utf-8").read())
        sysinst = open(os.path.join(INSTALL, "system-install.sh"), encoding="utf-8").read()
        self.assertIn("/run/irl4you-net-before", sysinst)
        self.assertLess(sysinst.index("/run/irl4you-net-before"), sysinst.index("sh install/system-base-fixes.sh"), "Netz merken, bevor etwas geändert wird")


class TestDispatcher(unittest.TestCase):
    """Die NetworkManager-Skripte mit einem nachgebauten `ip`, das jeden Aufruf mitschreibt."""

    def setUp(self):
        self.sh = _sh()
        if not self.sh:
            self.skipTest("keine POSIX-Shell")
        self.dir = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, "ip.log")
        with open(os.path.join(self.dir, "ip"), "w", newline="\n") as f:
            f.write('#!/bin/sh\necho "ip $*" >> "%s"\n'
                    'case "$*" in "-4 route show table main dev eth0 scope link") echo "192.168.1.0/24 proto kernel scope link src 192.168.1.34 metric 100";; esac\n'
                    'case "$*" in "-4 rule del"*) exit 2;; esac\nexit 0\n' % self.log.replace("\\", "/"))
        for tool in ("logger", "flock"):
            with open(os.path.join(self.dir, tool), "w", newline="\n") as f:
                f.write("#!/bin/sh\nexit 0\n")
        for tool in ("ip", "logger", "flock"):
            os.chmod(os.path.join(self.dir, tool), 0o755)      # unter Linux sonst nicht ausführbar

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_script(self, name, iface, event, **env):
        d = self.dir.replace("\\", "/")
        e = dict(os.environ, PATH=d + os.pathsep + os.environ.get("PATH", ""), IRL4YOU_RT_ETC=d + "/rt", IRL4YOU_RUN=d, **env)
        script = os.path.join(INSTALL, "net", name)
        r = subprocess.run([self.sh, script, iface, event], env=e, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        try:
            return open(self.log).read()
        except OSError:
            return ""

    def test_quell_routing(self):
        out = self.run_script("pipbox-source-routing", "eth0", "up", IP4_NUM_ADDRESSES="1", IP4_ADDRESS_0="192.168.1.34/24 192.168.1.1",
                              IP4_GATEWAY="192.168.1.1")
        self.assertIn("ip -4 route replace default via 192.168.1.1 dev eth0 table eth0", out)
        self.assertIn("ip -4 rule add from 192.168.1.34 lookup eth0 pref 1000", out)
        self.assertIn("ip -4 route replace 192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.34 metric 100 table eth0", out)
        with open(os.path.join(self.dir, "rt", "rt_tables.d", "irl4you.conf")) as f:
            self.assertEqual(f.read().split(), ["100", "eth0"], "Tabelle mit dem Namen der Karte angelegt")

    def test_mobilfunk_ohne_gateway(self):
        out = self.run_script("pipbox-source-routing", "wwan0", "up", IP4_NUM_ADDRESSES="1", IP4_ADDRESS_0="10.1.2.3/30 0.0.0.0", IP4_GATEWAY="")
        self.assertIn("ip -4 route replace default dev wwan0 table wwan0", out)

    def test_ignoriert_virtuelle_karten(self):
        self.assertEqual(self.run_script("pipbox-source-routing", "tailscale0", "up", IP4_GATEWAY="1.2.3.4"), "")
        self.assertEqual(self.run_script("pipbox-source-routing", "eth0;rm", "up", IP4_GATEWAY="1.2.3.4"), "")

    def test_abbau(self):
        out = self.run_script("pipbox-source-routing", "eth0", "down")
        self.assertIn("ip -4 route flush table eth0", out)


class TestInstallation(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(INSTALL, "irl4you-setup.sh"), encoding="utf-8") as f:
            self.sh = f.read()
        with open(os.path.join(INSTALL, "system-install.sh"), encoding="utf-8") as f:
            self.sysinst = f.read()
        with open(os.path.join(INSTALL, "install-2604.sh"), encoding="utf-8") as f:
            self.erst = f.read()

    def test_alle_dateien_vorhanden(self):
        import re
        for block in re.findall(r"for f in ([^;]+); do\n\s+install -m \d+ \"\$HERE/(\w*)/?\$f\"", self.sh):
            names, sub = block
            for n in names.split():
                if "$" in n or "*" in n:
                    continue
                self.assertTrue(os.path.exists(os.path.join(IRL, sub, n)), "fehlt: %s/%s" % (sub, n))
        for p in re.findall(r"\"\$HERE/(install/[\w./-]+)\"", self.sh):
            if "$" not in p:
                self.assertTrue(os.path.exists(os.path.join(IRL, p)), "fehlt: " + p)

    def test_jede_unit_eingeschaltet_oder_ausgeloest(self):
        units = sorted(f for f in os.listdir(INSTALL) if f.endswith((".service", ".path", ".timer", ".socket")))
        enabled = self.sh.split('UNITS="', 1)[1].split('"', 1)[0].split()
        for u in units:
            base = u.rsplit(".", 1)[0]
            started_by = [x for x in enabled if x.rsplit(".", 1)[0] == base] or \
                [x for x in units if x != u and open(os.path.join(INSTALL, x), encoding="utf-8").read().count("Unit=" + u)]
            if u.endswith(".service") and not started_by:
                started_by = [x for x in enabled if x.startswith(base.rsplit("-", 1)[0]) and x.endswith((".timer", ".path"))]
            self.assertTrue(started_by or u in ("pipbox-send.service", "pipbox-preview.service", "pipbox-remote-heal.service",
                                                "pipbox-logrotate.service", "pipbox-modem-apply.service", "pipbox-wlandriver.service"),
                            "Unit wird nie gestartet: " + u)

    def test_keine_belaui_mehr(self):
        for f in os.listdir(INSTALL):
            p = os.path.join(INSTALL, f)
            if os.path.isfile(p) and f.endswith((".service", ".path", ".timer")):
                self.assertNotIn("belaUI", open(p, encoding="utf-8").read(), f)
        self.assertIn("--extra-port 80", open(os.path.join(INSTALL, "pipbox.service"), encoding="utf-8").read())
        self.assertIn("/opt/irl4you/venv/bin/python3", open(os.path.join(INSTALL, "pipbox-dji.service"), encoding="utf-8").read())

    def test_skripte_lf_und_syntax(self):
        sh = _sh()
        for rel in ("install/install-2604.sh", "install/system-install.sh", "install/irl4you-setup.sh", "install/system-base-fixes.sh", "install/zz-irl4you-boot", "install/health.sh", "install/net-check.sh", "install/net/pipbox-source-routing", "install/net/pipbox-fallback-route"):
            p = os.path.join(IRL, rel)
            self.assertNotIn(b"\r\n", open(p, "rb").read(), "CRLF in " + rel)
            if sh:
                r = subprocess.run([sh, "-n", p], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, rel + ": " + r.stderr)

    def test_version_als_verweis(self):
        """Updates: jede Version liegt in /opt/irl4you/releases/<Version>, /opt/pipbox ist ein Verweis; system-install.sh kopiert keine Programmdateien."""
        self.assertIn('ln -sfn "$ROOTDIR/releases/$ID" "$ROOTDIR/current"', self.erst)
        self.assertIn('ln -s "$ROOTDIR/current" /opt/pipbox', self.erst)
        self.assertIn("hooks/install", self.erst)
        self.assertIn("irl4you-setup.sh", self.sysinst, "system-install.sh (Hook des Updaters) ruft die IRL4YOU-Einrichtung")
        self.assertIn("system-base-fixes.sh", self.sysinst)
        self.assertLess(self.sysinst.index("debs/*.deb"), self.sysinst.rindex("irl4you-setup.sh"), "eigene Pakete vor den Diensten")
        for f in ("server.py", "pipbox_send.py", "index.html"):
            self.assertNotRegex(self.sh, r'install -m [0-9]+ "[$]HERE/%s"' % f, "irl4you-setup.sh darf keine Programmdateien kopieren: " + f)
        self.assertNotIn('"$OPT/venv', self.sh, "venv liegt gemeinsam für alle Versionen unter /opt/irl4you/venv")
        self.assertIn("PBOUT=", self.sh, "PiP-Baustein wird in den Ordner der Version gebaut")
        self.assertFalse(os.path.exists(os.path.join(IRL, "pipbox-swupdate.py")))
        self.assertFalse(os.path.exists(os.path.join(INSTALL, "pipbox-swupdate.path")))

    def test_bleak_feste_versionen(self):
        req = open(os.path.join(INSTALL, "requirements.txt"), encoding="utf-8").read()
        self.assertRegex(req, r"(?m)^bleak==[0-9.]+$")
        self.assertRegex(req, r"(?m)^dbus-fast==[0-9.]+$")
        self.assertNotIn("--upgrade", self.sh, "kein pip --upgrade bei jedem Update (ohne Internet bräche das Update ab)")
        self.assertIn("-r \"$HERE/install/requirements.txt\"", self.sh)
        self.assertIn(".requirements.sha256", self.sh, "nur installieren, wenn die Datei sich ändert oder etwas fehlt")

    def test_tailscale_resolute(self):
        rem = load_script("pipbox-remote.py", "pipbox_remote_t")
        self.assertIn("resolute", rem.CODENAMES)

    def test_python_shebang_lf(self):
        """Ausführbare Python-Dateien mit CRLF starten unter Linux nicht (/usr/bin/env: 'python3\\r')."""
        for f in os.listdir(IRL):
            if f.endswith(".py"):
                first = open(os.path.join(IRL, f), "rb").readline()
                if first.startswith(b"#!"):
                    self.assertFalse(first.endswith(b"\r\n"), "CRLF-Zeilenenden in " + f)


class TestSendekette(unittest.TestCase):
    """pipbox_send.py und server.py mit irl4you-encoder (encoder/SCHNITTSTELLE.md) und irl4you-srtla (srtla/README.md)."""

    def setUp(self):
        self.ps = irl("pipbox_send")
        self.server = irl("server")

    def sender(self, spread="best", live=False):
        sv = {"name": "Test", "host": "srtla.example.net", "port": 5000, "streamid": "abc"}
        s = self.ps.Sender(sv, 2000, ["10.0.0.2"], {"cfg": {}, "layout": (), "auto": False, "spread": spread})
        s.live = live
        return s

    def test_aufruf_encoder(self):
        a = self.sender().args("encoder")
        self.assertEqual(a[0], self.ps.ENCODER)
        kv = dict(zip(a[1::2], a[2::2]))
        self.assertEqual(kv["--srt"], "127.0.0.1:%d" % self.ps.LISTEN_PORT)
        self.assertEqual(kv["--latency"], "2000")
        self.assertEqual(kv["--streamid"], "abc")
        self.assertEqual(kv["--stats"], "/run/pipbox-send/encoder-stats.json")
        self.assertTrue(kv["--pipeline"].endswith("/pipeline") and kv["--bitrate-file"].endswith("/bitrate"))
        self.assertNotIn("--control", a, "Steuerkanal nur im Modus alle Kameras immer bereit")

    def test_aufruf_srtla(self):
        a = self.sender(spread="all").args("srtla")
        self.assertEqual(a[a.index("-s") + 1], "srtla.example.net:5000")
        self.assertEqual(a[a.index("-l") + 1], "127.0.0.1:%d" % self.ps.LISTEN_PORT)
        self.assertEqual(a[a.index("-m") + 1], "all")
        self.assertEqual(a[a.index("--status") + 1], "/run/pipbox-send/srtla.json")
        s6 = self.sender()
        s6.sv = dict(s6.sv, host="2001:db8::1")
        a6 = s6.args("srtla")
        self.assertEqual(a6[a6.index("-s") + 1], "[2001:db8::1]:5000")

    def test_bitraten_datei_in_kbit(self):
        d = tempfile.mkdtemp()
        old = self.ps.WORK
        try:
            self.ps.WORK = d
            self.ps.Sender.write_bitrate(800, 6000)
            self.assertEqual(open(os.path.join(d, "bitrate")).read().split(), ["800", "6000"])
            self.assertIsNone(self.ps.Sender.soft_rate(800, 6000), "weicher Start ist aus, solange SOFT_START_KBPS 0 ist")
        finally:
            self.ps.WORK = old
            shutil.rmtree(d)

    def test_statistik_fuer_die_oberflaeche(self):
        d = tempfile.mkdtemp()
        old = self.server.ENC_STATS_FILE
        try:
            self.server.ENC_STATS_FILE = os.path.join(d, "encoder-stats.json")
            with open(self.server.ENC_STATS_FILE, "w") as f:
                json.dump({"v": 1, "t": 1, "fps": 29.9, "rate": {"kbps": 6500, "min": 500, "max": 12000, "state": "ruhig"},
                           "srt": {"connected": True, "rtt_ms": 48, "send_kbps": 6610, "buf_pkts": 12, "buf_ms": 120,
                                   "sent": 10000, "lost": 50, "resent": 60, "dropped": 0}}, f)
            st = self.server.send_stats()
            self.assertEqual((st["fps"], st["bitrate_kbps"], st["rtt_ms"], st["send_mbps"]), (29.9, 6500, 48, 6.61))
            self.assertEqual((st["snd_buf_ms"], st["retrans_total"], st["loss_total"], st["sent_total"]), (120, 60, 50, 10000))
            self.assertEqual(st["loss_pct"], 0.5)
        finally:
            self.server.ENC_STATS_FILE = old
            shutil.rmtree(d)

    def test_leitungszustand(self):
        d = tempfile.mkdtemp()
        old, old_ips = self.server.LINKS_FILE, self.server.iface_ips
        try:
            self.server.LINKS_FILE = os.path.join(d, "srtla.json")
            with open(self.server.LINKS_FILE, "w") as f:
                json.dump({"ev": "stats", "links": [{"ip": "10.0.0.2", "dev": "eth0", "state": "used", "rtt_ms": 38.5},
                                                    {"ip": "10.0.1.2", "dev": "wwan0", "state": "reserve", "rtt_ms": None},
                                                    {"ip": "10.0.2.2", "dev": "wlan0", "state": "down", "rtt_ms": None}]}, f)
            self.server.iface_ips = lambda: [{"iface": "eth0", "ip": "10.0.0.2"}, {"iface": "wwan0", "ip": "10.0.1.2"}, {"iface": "wlan0", "ip": "10.0.2.2"}]
            st = self.server.uplink_states(["eth0", "wwan0", "wlan0"])
            self.assertEqual(st["eth0"], {"state": "an", "srtt": 38})
            self.assertEqual(st["wwan0"], {"state": "reserve", "srtt": None})
            self.assertEqual(st["wlan0"]["state"], "aus")
        finally:
            self.server.LINKS_FILE, self.server.iface_ips = old, old_ips
            shutil.rmtree(d)

    def test_software_update_ueber_helfer(self):
        """Update über irl4you-update: Version = Commit (12 Zeichen), Stichworte check/install/rollback/switch <Commit>."""
        import time
        sw = self.server.SwUpdate
        d = tempfile.mkdtemp()
        A, B, C = "a" * 12, "b" * 12, "c" * 12      # aktiv, vorherige, neuester
        try:
            rel = os.path.join(d, "releases")
            for rid, v in ((A, "2.0.0"), (B, "2.0.0")):
                os.makedirs(os.path.join(rel, rid))
                with open(os.path.join(rel, rid, "manifest.json"), "w") as f:
                    json.dump({"version": v, "commit": rid * 4}, f)
            os.makedirs(os.path.join(rel, "junk"))
            try:
                os.symlink(os.path.join(rel, A), os.path.join(d, "current"))
                link_ok = True
            except OSError:      # Windows ohne Symlink-Recht
                link_ok = False
            with open(os.path.join(d, "previous"), "w") as f:
                f.write(B + "\n")
            stf = os.path.join(d, "status.json")
            releases = [{"version": C[:7], "commit": C * 3 + C[:4], "published": "2026-10-20T10:00:00Z", "prerelease": False, "notes": "Neuer Stand"},
                        {"version": A[:7], "commit": A * 3 + A[:4], "published": "2026-10-18T10:00:00Z", "prerelease": False, "notes": "Aktueller Stand"},
                        {"version": "dddddd1", "commit": "d" * 40, "published": "2026-10-10T10:00:00Z", "prerelease": False, "notes": "Alt"}]
            with open(stf, "w") as f:
                json.dump({"state": "idle", "version": "2.0.0 (aaaaaaa)", "latest": C[:7], "available": True, "notes": "- Neuer Stand", "checked": 5,
                           "time": int(time.time()), "releases": releases}, f)

            class Send:
                @staticmethod
                def _active():
                    return False
            sw.STATUS, sw.RELEASES, sw.CURRENT, sw.PREVIOUS, sw.HELPER = stf, rel, os.path.join(d, "current"), os.path.join(d, "previous"), os.path.join(d, "helfer")
            u = sw(d, False, Send)
            u.version = "2.0.0"
            if not link_ok:
                u.current_id = lambda: A
            st = u.status()
            self.assertEqual((st["latest"], st["newer"], st["state"], st["current"]), (C[:7], True, "idle", "2.0.0 (aaaaaaa)"))
            rel_of = {x["id"]: x["relation"] for x in st["versions"]}
            self.assertEqual((rel_of[C], rel_of[A], rel_of["d" * 12], rel_of[B]), ("neuer", "aktuell", "älter", "älter"))
            self.assertTrue([x for x in st["versions"] if x["id"] == B][0]["local"])
            self.assertEqual(st["backup_version"], "2.0.0 (bbbbbbb)")
            self.assertIn("nicht installiert", st["error"])
            with self.assertRaises(ValueError):
                u.request("install", True)       # ohne Helfer
            open(sw.HELPER, "w").write("")
            u.request("install", True)
            self.assertEqual(open(u.req).read(), "install\n")
            u.request("switch", True, C[:7])
            self.assertEqual(open(u.req).read(), "switch\n" + C + "\n")
            with self.assertRaises(ValueError):
                u.request("switch", True, A[:7])         # schon aktiv
            with self.assertRaises(ValueError):
                u.request("switch", True, B)             # älter: ausdrückliche Bestätigung nötig
            u.request("switch", True, B, older=True)
            with self.assertRaises(ValueError):
                u.request("switch", True, "e" * 12)      # unbekannt
            with self.assertRaises(ValueError):
                u.request("switch", True, "1.2.3")       # keine Commit-Kennung
            with self.assertRaises(ValueError):
                u.request("install", False)
            u.request("rollback", True)
            self.assertEqual(open(u.req).read(), "rollback\n")
            u.check(force=True)
            self.assertEqual(open(u.req).read(), "check\n")
            self.assertIn("Neuer Stand", u.history()["text"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_kamera_zustaende_vom_encoder(self):
        pl = irl("pipbox_live")
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                json.dump({"cams": {"0": {"state": 3, "live": True}, "1": {"state": 2, "live": False}, "2": {"state": 1, "live": False}}}, f)
            self.assertEqual(pl.read_stats(p), {0: 3, 1: 2, 2: 1})
        finally:
            shutil.rmtree(d)
        self.assertIn("[cam 0]\n#idle\n", pl.build({"type": "pip", "main": "a", "pip": "b"}))

    def test_keine_alten_programme(self):
        for f in ("pipbox_send.py",):
            src = open(os.path.join(IRL, f), encoding="utf-8").read()
            for old in ("srtla_send", "/opt/pipbox/bin/belacoder", "belacoder-stats", "SRTLA_LAT_MARGIN_MS"):
                self.assertNotIn(old, src, "%s ruft noch %s" % (f, old))


class TestRtmpEingang(unittest.TestCase):
    """SRS als RTMP-Eingang: die Statistik-Seite (Port 1936) im Format des früheren nginx-rtmp, damit alle Leser unverändert bleiben."""

    def setUp(self):
        self.st = load_script("pipbox-rtmpstat.py", "pipbox_rtmpstat")
        self.server = irl("server")
        self.live = irl("pipbox_live")
        self.t = [100.0]
        self.meter = self.st.Meter(clock=lambda: self.t[0])

    def srs(self, frames, nbytes, publishing=True, name="handy"):
        return [{"id": "x", "name": name, "app": "publish", "live_ms": 5000, "clients": 2 if publishing else 1, "frames": frames, "recv_bytes": nbytes,
                 "publish": {"active": publishing}, "video": {"codec": "H265", "profile": "Main", "level": "4.1", "width": 1920, "height": 1080},
                 "audio": {"codec": "AAC", "sample_rate": 48000, "channels": 2}},
                {"name": "fremd", "app": "live", "publish": {"active": True}}, {"name": "../x", "app": "publish"}]

    def xml(self, frames, nbytes, **kw):
        return self.st.build_xml(self.srs(frames, nbytes, **kw), self.meter)

    def test_messung_und_felder(self):
        import xml.etree.ElementTree as ET
        self.xml(0, 0)
        self.t[0] += 3.0
        root = ET.fromstring(self.xml(90, 3_000_000))      # 30 Bilder/s, 8 Mbit/s
        st = root.find(".//stream")
        self.assertEqual(st.findtext("name"), "handy")
        self.assertIsNotNone(st.find("publishing"))
        self.assertEqual(st.findtext("meta/video/frame_rate"), "30")
        self.assertEqual((st.findtext("meta/video/width"), st.findtext("meta/video/height"), st.findtext("meta/video/codec")), ("1920", "1080", "H265"))
        self.assertEqual(int(st.findtext("bw_in")), 8_000_000)
        self.assertEqual(int(st.findtext("bw_video")) + int(st.findtext("bw_audio")), 8_000_000)
        self.assertEqual(st.findtext("nclients"), "1", "der Sender zählt nicht als Zuschauer")
        self.assertEqual(len(root.findall(".//stream")), 1, "fremde Applikation und ungültiger Name bleiben draußen")
        self.assertEqual(root.findtext(".//application/name"), "publish")

    def test_leere_liste_hat_applikation(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.st.build_xml([], self.meter))
        self.assertEqual([a.findtext("name") for a in root.iter("application")], ["publish"])

    def test_leser_von_irl4you(self):
        import xml.etree.ElementTree as ET
        self.xml(0, 0)
        self.t[0] += 3.0
        text = self.xml(90, 3_000_000)
        # Kameraliste der Oberfläche
        cs = object.__new__(self.server.CameraStore)
        cs.app, cs.stat_url = "publish", "x"
        import io
        old = self.server.urllib.request.urlopen
        self.server.urllib.request.urlopen = lambda *a, **k: io.BytesIO(text.encode())
        try:
            live = cs._live_read()
        finally:
            self.server.urllib.request.urlopen = old
        self.assertEqual((live["handy"]["w"], live["handy"]["h"], live["handy"]["fps"]), (1920, 1080, 30.0))
        self.assertAlmostEqual(live["handy"]["mbit"], 8.0, places=1)
        # Sendekette und Kamera-Zweige
        self.assertEqual(self.live.parse_rtmp_stats(text), {"handy": {"w": 1920, "h": 1080, "audio": True}})
        # DJI- und HDMI-Dienst lesen mit regulären Ausdrücken
        for name in ("dji_daemon", "hdmi_daemon"):
            mod = irl(name)
            old = mod.urllib.request.urlopen
            mod.urllib.request.urlopen = lambda *a, **k: io.BytesIO(text.encode())
            try:
                self.assertTrue(mod.rtmp_publishing("handy"), name)
                self.assertFalse(mod.rtmp_publishing("andere"), name)
            finally:
                mod.urllib.request.urlopen = old
        mod = irl("dji_daemon")
        old = mod.urllib.request.urlopen
        mod.urllib.request.urlopen = lambda *a, **k: io.BytesIO(text.encode())
        try:
            self.assertEqual(mod.rtmp_video_kbps("handy"), 7872)
        finally:
            mod.urllib.request.urlopen = old
        # Protokoll-Bündel
        logs = load_script("pipbox-logs.py", "pipbox_logs_t")
        self.assertIn("handy", logs.rtmp_inputs(text))
        ET.fromstring(text)

    def test_kein_sender_nur_zuschauer(self):
        self.xml(0, 0, publishing=False)
        self.t[0] += 3.0
        text = self.xml(0, 0, publishing=False)
        self.assertNotIn("<publishing/>", text)

    def test_zaehler_zurueckgesetzt(self):
        self.xml(900, 9_000_000)
        self.t[0] += 3.0
        text = self.xml(30, 100_000)             # Sender neu verbunden: Zähler fangen von vorn an
        self.assertNotIn("frame_rate>-", text)
        self.assertNotIn("<bw_in>-", text)

    def test_umstellung_nur_mit_srs(self):
        sh = open(os.path.join(INSTALL, "irl4you-setup.sh"), encoding="utf-8").read()
        self.assertIn("[ -x /usr/bin/irl4you-srs ] && SRS_OK=1", sh)
        i = sh.index("install/nginx/99-irl4you-rtmps.conf")
        self.assertGreater(i, sh.index('if [ "$SRS_OK" = 1 ]; then'), "RTMPS-Konfiguration nur zusammen mit SRS (sonst zwei listen 1934)")

    def test_konfiguration(self):
        srs = open(os.path.join(INSTALL, "srs", "srs.conf"), encoding="utf-8").read()
        for k in ("listen              1935;", "gop_cache       off;", "normal_timeout      15000;", "127.0.0.1:1985", "[app]/[stream].ts"):
            self.assertIn(k, srs)
        ng = open(os.path.join(INSTALL, "nginx", "99-irl4you-rtmps.conf"), encoding="utf-8").read()
        self.assertIn("proxy_pass 127.0.0.1:1935", ng)
        self.assertNotIn("rtmp {", ng)
        unit = open(os.path.join(INSTALL, "irl4you-srs.service"), encoding="utf-8").read()
        self.assertIn("-c /etc/irl4you/srs.conf", unit)
        self.assertNotIn("libnginx-mod-rtmp", open(os.path.join(INSTALL, "irl4you-setup.sh"), encoding="utf-8").read().split("step pakete")[1].split("step ")[0])


if __name__ == "__main__":
    unittest.main()
