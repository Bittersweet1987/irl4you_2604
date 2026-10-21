"""Bildaufbau: immer Bild-in-Bild; eine Kamera ohne kleines Bild geht ohne Fehler; mit kleinem Bild gilt immer-bereit und Tausch über alle Kameras."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

KEYS = ["osmo", "s23", "redmi"]


class TestBildaufbau(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.store = irl("webui.pipeline").PipelineStore(os.path.join(self.d.name, "pipeline.json"))

    def tearDown(self):
        self.d.cleanup()

    def test_eine_kamera_ohne_kleines_bild(self):
        self.store.set({"type": "pip", "main": "osmo", "pip": ""}, ["osmo"])
        self.assertEqual((self.store.cfg["type"], self.store.cfg["pip"]), ("single", ""))
        self.assertFalse(self.store.cfg["always_ready"])

    def test_art_wird_nicht_mehr_gesendet(self):
        self.store.set({"main": "osmo", "pip": ""}, ["osmo"])
        self.assertEqual(self.store.cfg["type"], "single")

    def test_mit_kleinem_bild_immer_bereit_und_tausch_alle(self):
        self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "always_ready": False, "swap_cams": 0}, KEYS)
        c = self.store.cfg
        self.assertEqual((c["type"], c["pip"], c["always_ready"], c["swap_cams"]), ("pip", "s23", True, 4))

    def test_jedes_kleine_bild_ist_eigenstaendig(self):
        self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "pip2": "", "pip3": "redmi", "corner3": 0}, KEYS)
        c = self.store.cfg
        self.assertEqual((c["pip"], c["pip2"], c["pip3"]), ("s23", "", "redmi"))
        pip, pip2, pip3, multi = self.store._layout(c)
        self.assertEqual((pip, pip2), (True, False))
        if multi:
            self.assertTrue(pip3)
        with self.assertRaises(ValueError):
            self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "pip3": "osmo"}, KEYS)         # dieselbe Kamera wie das Hauptbild
        with self.assertRaises(ValueError):
            self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "corner": 3, "pip3": "redmi", "corner3": 3}, KEYS)  # gleiche Position

    def test_ungueltiges_kleines_bild_bleibt_ein_fehler(self):
        with self.assertRaises(ValueError):
            self.store.set({"type": "pip", "main": "osmo", "pip": "osmo"}, KEYS)
        with self.assertRaises(ValueError):
            self.store.set({"type": "pip", "main": "osmo", "pip": "gibtsnicht"}, KEYS)

    def test_altes_profil_wird_umgestellt(self):
        c = self.store._safe_cfg({"type": "pip", "main": "osmo", "pip": "s23", "always_ready": False, "swap_cams": 0})
        self.assertEqual((c["always_ready"], c["swap_cams"]), (True, 4))


if __name__ == "__main__":
    unittest.main()
