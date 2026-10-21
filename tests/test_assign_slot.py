"""Bildaufbau: Kamera per Wischen auf einen Platz legen (Tausch mit der Kamera, die dort liegt, oder Ersatz durch eine Kamera, die noch nicht im Bild war)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

KEYS = ["osmo", "s23", "redmi", "ios", "extra"]


class FakeCams:
    def __init__(self, offline=()):
        self.cams = [{"key": k} for k in KEYS]
        self.offline = offline

    def listing(self, host):
        return [{"key": k, "state": "offline" if k in self.offline else "live", "name": k} for k in KEYS]


class FakeSend:
    def __init__(self, always=False):
        self.always, self.restarts = always, 0

    def always_live(self):
        return self.always

    def swap_live(self):
        return False

    def view_live(self):
        return False

    def view_state(self):
        return None

    def restart_if_live(self):
        self.restarts += 1
        return True, "Neustart"


class TestAssign(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.store = irl("webui.pipeline").PipelineStore(os.path.join(self.d.name, "pipeline.json"))
        self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "pip2": "redmi", "pip3": "ios"}, KEYS)
        self.actions = irl("webui.actions")

    def tearDown(self):
        self.d.cleanup()

    def slots(self):
        c = self.store.cfg
        return [c["main"], c["pip"], c["pip2"], c["pip3"]]

    def test_tausch_zweier_kleiner_bilder_mit_verzoegerung(self):
        self.store.cfg.update(pip_delay_ms=100, pip3_delay_ms=300)
        kind, shown = self.store.assign_slot("pip", "ios", KEYS)
        self.assertEqual((kind, self.slots()), ("swap", ["osmo", "ios", "redmi", "s23"]))
        self.assertEqual((self.store.cfg["pip_delay_ms"], self.store.cfg["pip3_delay_ms"]), (300, 100))      # die Verzögerung wandert mit der Kamera

    def test_hauptbild_tauschen(self):
        self.assertEqual(self.store.assign_slot("main", "redmi", KEYS)[0], "swap")
        self.assertEqual(self.slots(), ["redmi", "s23", "osmo", "ios"])

    def test_neue_kamera_ersetzt_und_wird_aktiviert(self):
        self.store.cfg["inactive"] = ["extra"]
        kind, shown = self.store.assign_slot("pip2", "extra", KEYS)
        self.assertEqual((kind, self.slots()), ("replace", ["osmo", "s23", "extra", "ios"]))
        self.assertNotIn("extra", self.store.cfg.get("inactive") or [])

    def test_gleiche_kamera_und_fehler(self):
        self.assertEqual(self.store.assign_slot("pip", "s23", KEYS)[0], "same")
        with self.assertRaises(ValueError):
            self.store.assign_slot("pip", "gibtsnicht", KEYS)
        with self.assertRaises(ValueError):
            self.store.assign_slot("daneben", "osmo", KEYS)

    def test_aktion_tausch_ohne_unterbrechung_und_ersatz_mit_neustart(self):
        send = FakeSend(always=True)
        r = self.actions.scene_assign(self.store, FakeCams(), send, "pip", "ios")
        self.assertEqual((r["restarted"], send.restarts), (False, 0))
        r = self.actions.scene_assign(self.store, FakeCams(), send, "pip", "extra")
        self.assertEqual((r["restarted"], send.restarts), (True, 1))
        with self.assertRaises(ValueError):
            self.actions.scene_assign(self.store, FakeCams(offline=("extra",)), send, "pip2", "extra")


if __name__ == "__main__":
    unittest.main()
