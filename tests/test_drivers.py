"""Tests für die Treiber-Helfer (WLAN-Stick umschalten, Bluetooth-Kennungen nachtragen, Chip der ROCK 5B Plus).
Sysfs-Bäume werden in einem Temp-Ordner nachgebaut; es wird nichts auf dem Rechner verändert.

Aufruf: python3 -m unittest discover -s tests -v
"""
import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
IRL = os.path.join(os.path.dirname(HERE), "irl4you")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(IRL, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def put(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def usb(root, name, vid, pid):
    put(f"{root}/{name}/idVendor", vid + "\n")
    put(f"{root}/{name}/idProduct", pid + "\n")


class Wlan(unittest.TestCase):
    def setUp(self):
        self.m = load("pipbox-wlandriver")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_erkennt_nur_aic_sticks(self):
        usb(self.root, "1-1.4", "a69c", "5723")
        usb(self.root, "4-1", "0bda", "c811")
        usb(self.root, "1-1.4:1.0", "ffff", "ffff")
        present = self.m.usb_ids_present(self.root)
        self.assertEqual(present, {"a69c:5723", "0bda:c811"})
        self.assertEqual(self.m.wanted(present), ["a69c:5723"])

    def test_umschaltbefehl(self):
        self.assertEqual(self.m.switch_cmd("a69c:5723"), ["usb_modeswitch", "-KW", "-v", "a69c", "-p", "5723"])
        self.assertEqual(self.m.switch_cmd("1111:1111")[:2], ["usb_modeswitch", "-c"])

    def test_umschalten_wartet_bis_der_laufwerkmodus_weg_ist(self):
        class R:
            stdout, stderr = "", "fehler"
        seen = iter([{"a69c:5723"}, set()])
        self.assertEqual(self.m.switch_mode("a69c:5723", present=lambda: next(seen), run_cmd=lambda *a, **k: R(), sleep=lambda s: None), "")
        t = iter(range(0, 100, 10))
        err = self.m.switch_mode("a69c:5723", present=lambda: {"a69c:5723"}, run_cmd=lambda *a, **k: R(), sleep=lambda s: None, now=lambda: next(t))
        self.assertEqual(err, "fehler")

    def test_schnittstelle_zum_stick(self):
        usb(self.root, "usb/1-1.4", "a69c", "8d81")
        os.makedirs(f"{self.root}/net/wlan1")
        os.makedirs(f"{self.root}/net/wlan0")
        links = {f"{self.root}/net/wlan1/device": f"{self.root}/usb/1-1.4/1-1.4:1.0", f"{self.root}/net/wlan0/device": f"{self.root}/pci"}
        usb(self.root, "usb/1-1.4/1-1.4:1.0", "x", "y")
        os.remove(f"{self.root}/usb/1-1.4/1-1.4:1.0/idVendor")
        os.remove(f"{self.root}/usb/1-1.4/1-1.4:1.0/idProduct")
        name = self.m.netdev_for_usb(("a69c:8d81",), net_root=f"{self.root}/net", resolve=lambda p: links.get(p, p))
        self.assertEqual(name, "wlan1")
        self.assertEqual(self.m.netdev_for_usb(("1111:2222",), net_root=f"{self.root}/net", resolve=lambda p: links.get(p, p)), "")


class Bluetooth(unittest.TestCase):
    def setUp(self):
        self.m = load("pipbox-btdriver")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_kandidaten_und_fehlende_ids(self):
        self.assertTrue(set(self.m.MISSING).isdisjoint(self.m.BUILTIN))
        usb(self.root, "5-1", "2357", "0604")
        usb(self.root, "1-1.3", "33fa", "0012")
        usb(self.root, "2-1", "2c4e", "0115")
        usb(self.root, "2-2", "1234", "5678")
        devs = self.m.usb_devices(self.root)
        self.assertEqual(sorted(self.m.wanted(devs)), ["2357:0604", "2c4e:0115", "33fa:0012"])

    def test_dynid_vorlage_ist_realtek(self):
        self.assertEqual(self.m.dynid_line("2c4e:0115"), "2c4e 0115 0 0bda b009")
        self.assertTrue(self.m.has_dynid("2c4e:0115", "2c4e 0115\n"))
        self.assertTrue(self.m.has_dynid("2c4e:0115", "1234 5678\n2c4e 0115 0 0bda b009\n"))
        self.assertFalse(self.m.has_dynid("2c4e:0115", ""))

    def test_adapter_zum_stick(self):
        bt, ub = f"{self.root}/bt", f"{self.root}/usb"
        usb(ub, "1-1.3", "33fa", "0012")
        os.makedirs(f"{bt}/hci1")
        os.makedirs(f"{bt}/hci0")
        links = {f"{bt}/hci1/device": f"{ub}/1-1.3/1-1.3:1.0", f"{bt}/hci0/device": f"{ub}/5-1/5-1:1.0"}
        resolve = lambda p: links.get(p, p)  # noqa: E731
        self.assertEqual(self.m.hci_for_dev("1-1.3", bt_root=bt, usb_root=ub, resolve=resolve), "hci1")
        self.assertEqual(self.m.hci_for_dev("9-9", bt_root=bt, usb_root=ub, resolve=resolve), "")

    def test_funksperre_wird_aufgehoben(self):
        put(f"{self.root}/hci0/rfkill3/soft", "1\n")
        put(f"{self.root}/hci1/rfkill4/soft", "0\n")
        self.assertTrue(self.m.unblock_hci("hci0", bt_root=self.root))
        self.assertEqual(open(f"{self.root}/hci0/rfkill3/soft").read(), "0")
        self.assertFalse(self.m.unblock_hci("hci1", bt_root=self.root))
        self.assertFalse(self.m.unblock_hci("hci9", bt_root=self.root))

    def test_anfrage_nur_mit_inhalt_install(self):
        p = os.path.join(self.root, "req")
        put(p, "install\n")
        self.assertTrue(self.m.take_request(p))
        self.assertFalse(os.path.exists(p))
        put(p, "etwas anderes\n")
        self.assertFalse(self.m.take_request(p))


class Chip(unittest.TestCase):
    def test_firmware_pruefung(self):
        m = load("pipbox-btchip")
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(m.firmware_present(d))
            put(f"{d}/rtl_bt/rtl8852bu_fw.bin.zst")
            self.assertFalse(m.firmware_present(d))
            put(f"{d}/rtl_bt/rtl8852bu_config.bin.zst")
            self.assertTrue(m.firmware_present(d))


if __name__ == "__main__":
    unittest.main()
