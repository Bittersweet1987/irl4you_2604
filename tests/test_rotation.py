"""Rotierende Kameras: Einstellung und Ablauf im Sendeteil (nur gewählte Plätze wechseln, Kameras auf festen Plätzen bleiben tabu)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

KEYS = ["osmo", "s23", "redmi", "ios", "htc"]


class TestEinstellung(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.mod = irl("webui.pipeline")
        self.store = self.mod.PipelineStore(os.path.join(self.d.name, "pipeline.json"))
        self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "pip2": "redmi"}, KEYS)

    def tearDown(self):
        self.d.cleanup()

    def test_standard_aus_und_werte_pruefen(self):
        self.assertNotIn("rotation", self.store.cfg)
        r = self.store.set_rotation({"on": True, "slots": ["pip", "quatsch"], "seconds": 20, "pool": ["s23", "ios", "gibtsnicht"]}, KEYS)
        self.assertEqual((r["on"], r["all"], r["slots"], r["seconds"], r["pool"]), (True, False, ["pip"], 20, ["s23", "ios"]))
        with self.assertRaises(ValueError):
            self.store.set_rotation({"seconds": 1}, KEYS)
        with self.assertRaises(ValueError):
            self.store.set_rotation({"seconds": "abc"}, KEYS)

    def test_teiländerung_behaelt_rest_und_bildaufbau_speichern_behaelt_rotation(self):
        self.store.set_rotation({"on": True, "slots": ["pip2"], "seconds": 45}, KEYS)
        self.store.set_rotation({"on": False}, KEYS)
        self.assertEqual((self.store.cfg["rotation"]["slots"], self.store.cfg["rotation"]["seconds"], self.store.cfg["rotation"]["on"]), (["pip2"], 45, False))
        self.store.set({"type": "pip", "main": "osmo", "pip": "s23", "pip2": "redmi"}, KEYS)
        self.assertEqual(self.store.cfg["rotation"]["seconds"], 45)
        self.store.set({"type": "pip", "main": "osmo", "pip": ""}, KEYS)                  # eine Kamera: keine Rotation
        self.assertNotIn("rotation", self.store.cfg)

    def test_aenderung_ist_keine_bildaufbau_aenderung(self):
        a = dict(self.store.cfg)
        self.store.set_rotation({"on": True}, KEYS)
        self.assertTrue(self.mod.view_only_change(a, self.store.cfg))
        self.assertTrue(self.mod.always_compatible(a, self.store.cfg))


def make(cfg):
    live = irl("pipbox_live")
    logs = []
    ctl = live.LiveController(lambda name: dict(cfg) if name == "pipeline.json" else {}, lambda *a, **k: None, "/tmp", lambda c: dict(c),
                              lambda c: (0, -1), log=logs.append, fetch=lambda: {}, stats=lambda: {}, control=lambda lines: True)
    ctl.started = True
    ctl.reload()
    ctl.pub_known = True
    return live, ctl, logs


def cfg(**rot):
    return {"type": "pip", "main": "osmo", "pip": "s23", "pip2": "redmi", "pip3": "", "auto_failover": True,
            "rotation": dict({"on": True, "all": False, "slots": ["pip"], "seconds": 30, "pool": None}, **rot)}


class TestSendeteil(unittest.TestCase):
    def pubs(self, ctl, *keys):
        ctl.pub = {k: {} for k in keys}

    def test_nur_das_gewaehlte_bild_wechselt_und_feste_kameras_bleiben_tabu(self):
        live, ctl, logs = make(cfg())
        self.pubs(ctl, "osmo", "s23", "redmi", "ios", "htc")
        ctl.rotate(0.0)
        self.assertEqual(ctl.desired, ["osmo", "s23", "redmi", ""])
        seen = [ctl.desired[1]]
        for t in (31.0, 62.0, 93.0, 124.0, 155.0):
            ctl.rotate(t)
            seen.append(ctl.desired[1])
            self.assertEqual((ctl.desired[0], ctl.desired[2]), ("osmo", "redmi"))
        self.assertEqual(seen, ["s23", "htc", "ios", "s23", "htc", "ios"])                       # reihum durch alle frei verfügbaren Kameras
        self.assertNotIn("osmo", seen)
        self.assertNotIn("redmi", seen)

    def test_zeit_und_pool_und_deaktivierte_kameras(self):
        live, ctl, logs = make(cfg(pool=["ios", "htc"], seconds=10))
        ctl.inactive = ["htc"]
        self.pubs(ctl, "osmo", "s23", "redmi", "ios", "htc")
        ctl.rotate(0.0)
        ctl.rotate(9.0)
        self.assertEqual(ctl.desired[1], "s23")                  # noch nicht 10 Sekunden
        ctl.rotate(10.5)
        self.assertEqual(ctl.desired[1], "ios")                  # htc ist deaktiviert, s23 kommt als Kamera des Platzes dazu
        ctl.inactive = []                                        # später aktiviert: nimmt an der Rotation teil
        got = set()
        for t in (21.0, 32.0, 43.0, 54.0, 65.0, 76.0):
            ctl.rotate(t)
            got.add(ctl.desired[1])
        self.assertEqual(got, {"s23", "ios", "htc"})

    def test_alle_bilder_wechseln_nie_zwei_gleiche(self):
        live, ctl, logs = make(cfg(all=True, seconds=10))
        self.pubs(ctl, "osmo", "s23", "redmi", "ios", "htc")
        ctl.rotate(0.0)
        for t in range(10, 100, 10):
            ctl.rotate(float(t) + 0.5)
            shown = [k for k in ctl.desired if k]
            self.assertEqual(len(shown), len(set(shown)))
            self.assertEqual(len(shown), 3)

    def test_aus_oder_ohne_kameras_bleibt_die_einstellung(self):
        live, ctl, logs = make(cfg(on=False))
        self.pubs(ctl, "osmo", "s23", "redmi", "ios")
        ctl.rotate(0.0)
        ctl.rotate(100.0)
        self.assertEqual(ctl.desired, ["osmo", "s23", "redmi", ""])
        live, ctl, logs = make(cfg())
        self.pubs(ctl, "osmo", "redmi")                          # s23 nicht verbunden und sonst keine frei: nichts zum Wechseln
        ctl.rotate(0.0)
        ctl.rotate(100.0)
        self.assertEqual(ctl.desired[0], "osmo")


if __name__ == "__main__":
    unittest.main()
