"""Sendeteil: Fällt eine Kamera des Bildaufbaus aus und ist eine andere aktive Kamera frei, übernimmt diese den Platz; kommt die erste wieder, bekommt sie ihn zurück."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


def make(cfg):
    live = irl("pipbox_live")
    logs = []
    ctl = live.LiveController(lambda name: dict(cfg) if name == "pipeline.json" else {}, lambda *a, **k: None, "/tmp", lambda c: dict(c),
                              lambda c: (0, -1), log=logs.append, fetch=lambda: {}, stats=lambda: {}, control=lambda lines: True)
    ctl.started = True
    ctl.reload()
    ctl.pub_known = True
    return live, ctl, logs


CFG = {"type": "pip", "main": "osmo", "pip": "s23", "pip2": "", "pip3": "", "auto_failover": True}


class TestFailover(unittest.TestCase):
    def test_freie_kamera_uebernimmt_nach_wartezeit_und_gibt_zurueck(self):
        live, ctl, logs = make(CFG)
        ctl.pub = {"osmo": {}, "s23": {}, "extra": {}}
        self.assertEqual(ctl.failover(0.0), [])
        ctl.pub = {"s23": {}, "extra": {}}                       # Hauptkamera fällt aus
        self.assertEqual(ctl.failover(1.0), [])                  # noch keine Entscheidung (Wartezeit)
        self.assertEqual(ctl.failover(1.0 + live.FAILOVER_S - 0.1), [])
        lines = ctl.failover(1.0 + live.FAILOVER_S + 0.1)
        self.assertEqual((ctl.sub, ctl.desired[0]), ({"osmo": "extra"}, "extra"))
        self.assertTrue(any("set cam" in x and "/extra" in x for x in lines))
        self.assertTrue(any("ausgefallen" in x for x in logs))
        t = 10.0
        ctl.pub = {"osmo": {}, "s23": {}, "extra": {}}           # Hauptkamera ist wieder da
        self.assertEqual(ctl.failover(t), [])
        self.assertEqual(ctl.sub, {"osmo": "extra"})             # erst nach der Rückkehrzeit zurück
        ctl.failover(t + live.FAILBACK_S + 0.1)
        self.assertEqual((ctl.sub, ctl.desired[0]), ({}, "osmo"))

    def test_keine_ersatzkamera_wenn_deaktiviert_oder_bereits_im_bild_oder_aus(self):
        live, ctl, logs = make(dict(CFG, inactive=["extra"]))
        ctl.pub = {"osmo": {}, "s23": {}, "extra": {}}
        ctl.failover(0.0)
        ctl.pub = {"s23": {}, "extra": {}}
        ctl.failover(1.0)
        ctl.failover(20.0)
        self.assertEqual(ctl.sub, {})                            # die einzige freie Kamera ist deaktiviert; s23 ist selbst im Bild
        live, ctl, logs = make(dict(CFG, auto_failover=False))
        ctl.pub = {"osmo": {}, "s23": {}, "extra": {}}
        ctl.failover(0.0)
        ctl.pub = {"s23": {}, "extra": {}}
        ctl.failover(1.0)
        ctl.failover(20.0)
        self.assertEqual(ctl.sub, {})

    def test_kleines_bild_faellt_aus(self):
        live, ctl, logs = make(CFG)
        ctl.pub = {"osmo": {}, "s23": {}, "extra": {}}
        ctl.failover(0.0)
        ctl.pub = {"osmo": {}, "extra": {}}                      # s23 (kleines Bild) fällt aus
        ctl.failover(1.0)
        ctl.failover(1.0 + live.FAILOVER_S + 0.1)
        self.assertEqual((ctl.sub, ctl.desired[1]), ({"s23": "extra"}, "extra"))

    def test_ersatz_faellt_selbst_aus_und_neue_einstellung_setzt_zurueck(self):
        live, ctl, logs = make(CFG)
        ctl.pub = {"osmo": {}, "s23": {}, "extra": {}, "zwei": {}}
        ctl.failover(0.0)
        ctl.pub = {"s23": {}, "extra": {}, "zwei": {}}
        ctl.failover(1.0)
        ctl.failover(7.0)
        self.assertEqual(ctl.sub, {"osmo": "extra"})
        ctl.pub = {"s23": {}, "zwei": {}}                        # der Ersatz fällt aus: eine andere freie Kamera
        ctl.failover(8.0)
        ctl.failover(14.0)
        self.assertEqual(ctl.sub, {"osmo": "zwei"})


if __name__ == "__main__":
    unittest.main()
