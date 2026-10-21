"""Mischer: kurzes Zeitlimit, damit ein ausfallender oder angehaltener Kamera-Zweig das Bild nicht über eine Sekunde einfrieren lässt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

CFG = {"type": "pip", "main": "osmo", "pip": "s23", "always_ready": True, "pip_delay_ms": 0, "main_delay_ms": 0}


class TestMixLatency(unittest.TestCase):
    def setUp(self):
        self.old = {k: os.environ.get(k) for k in ("PIPBOX_SHIFT", "PIPBOX_ENGINE")}

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_kurzes_limit_mit_verschiebung_im_encoder(self):
        os.environ["PIPBOX_SHIFT"] = "1"
        live = irl("pipbox_live")
        self.assertEqual(live.mix_latency_ms(CFG), live.MIX_LATENCY_MS)
        text = live.build(dict(CFG), frame=False)
        self.assertIn("ignore-inactive-pads=true latency=%d" % (live.MIX_LATENCY_MS * 1000000), text)

    def test_ohne_verschiebung_bleibt_der_alte_wert(self):
        os.environ["PIPBOX_SHIFT"] = "0"
        live = irl("pipbox_live")
        self.assertEqual(live.mix_latency_ms(CFG), live.buffer_ms(CFG))


if __name__ == "__main__":
    unittest.main()
