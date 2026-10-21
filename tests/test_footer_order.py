"""Fußleiste am Handy: Kamera-Knöpfe immer in der Reihenfolge der Plätze (Hauptkamera, kleines Bild 1, 2, 3)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

KEYS = ["osmo", "s23", "redmi", "ios"]


class FakeCams:
    def __init__(self, order):
        self.order = order

    def listing(self, host):
        return [{"key": k, "state": "live", "name": k} for k in self.order]


class TestFooterOrder(unittest.TestCase):
    def test_reihenfolge_nach_platz_nicht_nach_kameraliste(self):
        d = tempfile.TemporaryDirectory()
        store = irl("webui.pipeline").PipelineStore(os.path.join(d.name, "pipeline.json"))
        store.set({"type": "pip", "main": "redmi", "pip": "ios", "pip2": "osmo", "pip3": "s23"}, KEYS)
        send = irl("webui.send").SendControl.__new__(irl("webui.send").SendControl)
        send.pipeline, send.cams, send.demo = store, FakeCams(KEYS), True
        send._fake_view = None
        send.always_live = lambda: False
        send._detail = lambda: {}
        f = send.footer()
        self.assertEqual([c["key"] for c in f["cams"]], ["redmi", "ios", "osmo", "s23"])
        self.assertEqual([c["slot"] for c in f["cams"]], [0, 1, 2, 3])
        d.cleanup()

    def test_ersatzkamera_erscheint_statt_der_ausgefallenen(self):
        d = tempfile.TemporaryDirectory()
        store = irl("webui.pipeline").PipelineStore(os.path.join(d.name, "pipeline.json"))
        store.set({"type": "pip", "main": "osmo", "pip": "ios", "pip2": "redmi"}, KEYS)
        mod = irl("webui.send")
        send = mod.SendControl.__new__(mod.SendControl)
        send.pipeline, send.cams, send.demo = store, FakeCams(KEYS), True
        send._fake_view = None
        send.always_live = lambda: True
        send._detail = lambda: {"state": "running", "failover": {"live": ["osmo", "s23", "redmi"], "main": "osmo", "sub": {"ios": "s23"}}}
        f = send.footer()
        self.assertEqual([(c["key"], c["slot"]) for c in f["cams"]], [("osmo", 0), ("s23", 1), ("redmi", 2)])
        d.cleanup()


if __name__ == "__main__":
    unittest.main()
