"""Feste Zusatzadresse: Entfernen auch ohne Einstellung, Warnung bei gleichem Adressbereich zweier AnschlÃ¼sse."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl, load_script  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


def _ip_out(lines):
    return mock.Mock(stdout="\n".join(lines) + "\n", returncode=0)


class TestUeberschneidung(unittest.TestCase):
    def setUp(self):
        ExtraAddress = irl("webui.access").ExtraAddress
        self.ea = ExtraAddress("/nonexistent")

    def test_getrennte_netze(self):
        self.assertEqual(self.ea.overlaps([("eth0", "192.168.178.110/24"), ("eth1", "192.168.1.20/24"), ("usb0", "192.168.8.100/24")]), [])

    def test_gleicher_bereich(self):
        r = self.ea.overlaps([("eth0", "192.168.1.100/24"), ("eth1", "192.168.1.20/24")])
        self.assertEqual(len(r), 1)
        self.assertEqual({r[0]["a"], r[0]["b"]}, {"eth0", "eth1"})
        self.assertEqual(r[0]["net"], "192.168.1.0/24")

    def test_zwei_adressen_auf_einer_karte_sind_kein_konflikt(self):
        self.assertEqual(self.ea.overlaps([("eth0", "192.168.1.20/24"), ("eth0", "192.168.1.100/24")]), [])

    def test_meldung_nur_bei_konflikt(self):
        out = ["2: eth0    inet 192.168.1.100/24 scope global eth0\\       valid_lft forever", "3: eth1    inet 192.168.1.20/24 scope global eth1\\       valid_lft forever",
               "4: tailscale0    inet 100.64.0.1/32 scope global tailscale0\\       valid_lft forever"]
        with mock.patch("subprocess.run", return_value=_ip_out(out)):
            w = self.ea.warning()
        self.assertEqual(w[0]["kind"], "net")
        self.assertEqual(w[0]["level"], "warn")
        with mock.patch("subprocess.run", return_value=_ip_out(out[:1])):
            self.ea._warn = (-1e9, [])
            self.assertEqual(self.ea.warning(), [])


class TestEntfernen(unittest.TestCase):
    def test_label_adresse_ohne_einstellung_wird_entfernt(self):
        mod = load_script("pipbox-netaddr.py", "pipbox_netaddr")
        out = ["2: eth0    inet 192.168.1.100/24 scope global secondary eth0:pb\\       valid_lft forever preferred_lft forever",
               "2: eth0    inet 192.168.178.110/24 brd 192.168.178.255 scope global dynamic eth0\\       valid_lft 600sec"]
        calls = []

        def fake(*a):
            calls.append(a)
            return _ip_out(out) if a[:1] == ("-4",) else _ip_out([])
        with mock.patch.object(mod, "ip", fake), mock.patch.object(mod, "current", lambda: None):
            mod.remove_address()
        self.assertIn(("addr", "del", "192.168.1.100/24", "dev", "eth0"), calls)
        self.assertEqual(len([c for c in calls if c[:2] == ("addr", "del")]), 1)


if __name__ == "__main__":
    unittest.main()
