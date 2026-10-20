"""WLAN-Menü: AIC8800-Stick ist kein Bluetooth-Gerät, gespeicherte Netze kommen live aus dem NetworkManager."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


def usb_dev(root, name, vid, pid, bt=False):
    d = os.path.join(root, name)
    os.makedirs(d)
    open(os.path.join(d, "idVendor"), "w").write(vid)
    open(os.path.join(d, "idProduct"), "w").write(pid)
    open(os.path.join(d, "product"), "w").write("Stick " + pid)
    if bt:
        i = os.path.join(d, name + ":1.0")
        os.makedirs(i)
        for f, v in (("bInterfaceClass", "e0"), ("bInterfaceSubClass", "01"), ("bInterfaceProtocol", "01")):
            open(os.path.join(i, f), "w").write(v)


class TestAicKeinBluetooth(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Verzeichnisnamen mit Doppelpunkt gibt es nur unter Linux")
    def test_wlan_stick_nicht_in_der_bluetooth_liste(self):
        dji = irl("dji")
        with tempfile.TemporaryDirectory() as root:
            usb_dev(root, "4-1.2", "a69c", "8d81", bt=True)     # AIC8800D80: Treiber meldet eine Bluetooth-Schnittstelle
            usb_dev(root, "4-1.3", "2357", "0604", bt=True)     # echter Bluetooth-Stick
            ids = [d["id"] for d in dji.usb_bluetooth_devices(root)]
        self.assertEqual(ids, ["2357:0604"])

    def test_wlan_stick_nicht_als_adapter(self):
        dji = irl("dji")
        objs = {"/org/bluez/hci2": {"org.bluez.Adapter1": {"Address": "AA:BB:CC:00:00:01", "Powered": False}}}
        with mock.patch.object(dji, "usb_info_for_hci", return_value={"usb_id": "a69c:8d81", "name": "AIC 8800D80", "vendor": "AICSemi"}):
            self.assertEqual(dji.adapter_info(objs)["adapters"], [])
        with mock.patch.object(dji, "usb_info_for_hci", return_value={"usb_id": "2357:0604", "name": "UB500", "vendor": "TP-Link"}):
            self.assertEqual(len(dji.adapter_info(objs)["adapters"]), 1)


class TestGespeicherteNetze(unittest.TestCase):
    def test_liste_aus_networkmanager(self):
        wifi = irl("webui.wifi")
        out = ("Bittersweet 5G:802-11-wireless\nGast\:Netz:802-11-wireless\npipbox-hotspot-wlan1:802-11-wireless\n"
               "irl4you-eth0:802-3-ethernet\nlo:loopback\n")
        res = mock.Mock(stdout=out, returncode=0)
        w = wifi.Wifi(tempfile.mkdtemp(), False, mock.Mock(iface=""))
        with mock.patch.object(wifi.subprocess, "run", return_value=res), mock.patch.object(wifi, "ttl_cached", side_effect=lambda k, t, fn: fn()):
            self.assertEqual(w.saved_networks(), ["Bittersweet 5G", "Gast:Netz"])


if __name__ == "__main__":
    unittest.main()
