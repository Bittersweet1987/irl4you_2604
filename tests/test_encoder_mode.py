"""Wahl der Videokodierung (Hardware/Software): Pipeline-Text, Datei, Menü Entwickler."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


class FakeSend:
    def __init__(self, active):
        self.active, self.restarts = active, 0

    def _active(self):
        return self.active

    def restart_if_live(self):
        self.restarts += 1
        return True, "neu gestartet"


class TestKodierkette(unittest.TestCase):
    def setUp(self):
        self.live = irl("pipbox_live")

    def test_hardware_ist_standard(self):
        self.assertEqual(self.live.encoder_mode("/gibt/es/nicht"), "hardware")
        t = self.live.venc_chain("queue", "hardware")
        self.assertIn("mpph265enc", t)
        self.assertIn("h265parse", t)
        self.assertIn("name=venc", t)

    def test_software_nutzt_x264(self):
        t = self.live.venc_chain("queue", "software")
        self.assertIn("x264enc name=venc", t)
        self.assertIn("h264parse", t)
        self.assertNotIn("mpph265enc", t)
        self.assertIn("sliced-threads=true", t)   # Last auf mehrere Kerne verteilt
        self.assertIn("tune=zerolatency", t)

    def test_datei_waehlt_modus(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "encoder-mode")
            open(p, "w").write("software\n")
            self.assertEqual(self.live.encoder_mode(p), "software")
            open(p, "w").write("irgendwas\n")
            self.assertEqual(self.live.encoder_mode(p), "hardware")


class TestKameraEingang(unittest.TestCase):
    def test_kamerakette_erkennt_h264_und_h265(self):
        """Die Kamerazweige nehmen H.264 und H.265 (Enhanced RTMP) an: parsebin erkennt den Strom, der Hardware-Decoder dekodiert beides."""
        live = irl("pipbox_live")
        txt = live.build({"type": "pip", "main": "cam1", "pip": "cam2", "styles": {}})
        text = str(txt)
        self.assertIn("parsebin name=cam0_parse ! mppvideodec", text)
        self.assertNotIn("h264parse name=cam0_parse", text)


class TestMenue(unittest.TestCase):
    def setUp(self):
        self.mod = irl("webui.encoder_mode")
        self.d = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.d.cleanup()

    def make(self, active=False):
        self.send = FakeSend(active)
        em = self.mod.EncoderMode(self.d.name, False, self.send)
        em.software_available = staticmethod(lambda: True)
        return em

    def test_setzen_und_lesen(self):
        em = self.make()
        self.assertEqual(em.mode(), "hardware")
        r = em.set("software")
        self.assertTrue(r["ok"])
        self.assertEqual(em.mode(), "software")
        self.assertEqual(open(os.path.join(self.d.name, "encoder-mode")).read().strip(), "software")
        self.assertEqual(self.send.restarts, 0)

    def test_ungueltiger_wert(self):
        with self.assertRaises(ValueError):
            self.make().set("gpu")

    def test_waehrend_der_sendung_neustart(self):
        em = self.make(active=True)
        r = em.set("software")
        self.assertTrue(r["restarted"])
        self.assertEqual(self.send.restarts, 1)
        em.set("software")           # unverändert: kein weiterer Neustart
        self.assertEqual(self.send.restarts, 1)

    def test_software_nicht_verfuegbar(self):
        em = self.make()
        em.software_available = staticmethod(lambda: False)
        with self.assertRaises(ValueError):
            em.set("software")


if __name__ == "__main__":
    unittest.main()
