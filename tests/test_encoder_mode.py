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
    """Kamerazweige: H.264 und H.265 (auch alte HEVC-Kennung der Handy-Apps) über pbflvfix, je ein Parser, funnel vor dem Dekoder."""

    def setUp(self):
        self.live = irl("pipbox_live")

    def _build(self, flvfix):
        old = os.environ.get("PIPBOX_FLVFIX")
        os.environ["PIPBOX_FLVFIX"] = "1" if flvfix else "0"
        try:
            return str(self.live.build({"type": "pip", "main": "cam1", "pip": "cam2", "styles": {}}))
        finally:
            if old is None:
                os.environ.pop("PIPBOX_FLVFIX", None)
            else:
                os.environ["PIPBOX_FLVFIX"] = old

    def test_mit_baustein_beide_codecs(self):
        t = self._build(True)
        self.assertIn("rtmpsrc name=cam0_src location=rtmp://127.0.0.1:1935/publish/cam1 ! pbflvfix name=cam0_fix ! flvdemux name=cam0", t)
        self.assertIn("cam0. ! video/x-h264 ! h264parse name=cam0_parse ! funnel name=cam0_vf", t)
        self.assertIn("cam0. ! video/x-h265 ! h265parse name=cam0_parse5 ! video/x-h265,stream-format=byte-stream,alignment=au ! cam0_vf.", t)
        self.assertIn("cam0_vf. ! queue name=cam0_vq", t)      # hier wirkt die Kameraverzögerung (min-threshold-time)
        self.assertIn("cam0.audio !", t)

    def test_ohne_baustein_wie_frueher(self):
        t = self._build(False)
        self.assertNotIn("pbflvfix", t)
        self.assertIn("cam0.video ! queue name=cam0_vq", t)
        self.assertIn("parsebin name=cam0_parse ! mppvideodec", t)

    def test_baustein_erkennung(self):
        with tempfile.TemporaryDirectory() as d:
            so = os.path.join(d, "libgstpbpip.so")
            open(so, "wb").write(b"xx pbround pbtap xx")
            old = self.live.PLUGIN_SO
            self.live.PLUGIN_SO = so
            self.live._FLV.update(mtime=None, ok=False)
            try:
                self.assertFalse(self.live.flvfix_ok())
                open(so, "wb").write(b"xx pbround pbtap pbflvfix xx")
                os.utime(so, (1, 2))
                self.assertTrue(self.live.flvfix_ok())
            finally:
                self.live.PLUGIN_SO = old
                self.live._FLV.update(mtime=None, ok=False)


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


class TestCpuBoost(unittest.TestCase):
    """Hardware-Kodierung lässt die CPU-Regler in Ruhe (kühler); Software-Kodierung nagelt die großen Kerne auf performance und hebt den Deckel an."""

    def setUp(self):
        self.live = irl("pipbox_live")
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        for c in range(8):
            d = f"{t}/cpu/cpu{c}"
            os.makedirs(d + "/cpufreq")
            big = c >= 4
            open(d + "/cpu_capacity", "w").write("1024" if big else "400")
            open(d + "/cpufreq/related_cpus", "w").write("4 5 6 7" if big else "0 1 2 3")
            open(d + "/cpufreq/scaling_governor", "w").write("ondemand")
            open(d + "/cpufreq/scaling_available_governors", "w").write("ondemand performance")
            open(d + "/cpufreq/scaling_max_freq", "w").write("1416000")
        self.sw = f"{t}/sw"
        open(self.sw, "w").write("2016000")
        self.mode = f"{t}/mode"
        self.old_mode = self.live.ENC_MODE_FILE
        self.live.ENC_MODE_FILE = self.mode
        self.boost = self.live.CpuBoost(cpu_dir=f"{t}/cpu", state=f"{t}/state.json", log=lambda m: None)
        self.boost.sw_max_file = self.sw

    def tearDown(self):
        self.live.ENC_MODE_FILE = self.old_mode
        self.tmp.cleanup()

    def gov(self, c=4):
        return open(f"{self.tmp.name}/cpu/cpu{c}/cpufreq/scaling_governor").read()

    def mx(self, c=4):
        return open(f"{self.tmp.name}/cpu/cpu{c}/cpufreq/scaling_max_freq").read()

    def test_hardware_aendert_nichts(self):
        open(self.mode, "w").write("hardware")
        self.boost.on()
        self.assertEqual((self.gov(), self.mx()), ("ondemand", "1416000"))

    def test_software_performance_und_zurueck(self):
        open(self.mode, "w").write("software")
        self.boost.on()
        self.assertEqual((self.gov(), self.mx(), self.gov(0)), ("performance", "2016000", "ondemand"))
        self.boost.off()
        self.assertEqual((self.gov(), self.mx()), ("ondemand", "1416000"))


if __name__ == "__main__":
    unittest.main()
