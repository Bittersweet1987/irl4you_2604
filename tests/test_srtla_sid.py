"""SRTLA-Server bearbeiten: gespeicherte Stream-ID bleibt, wird ersetzt oder entfernt."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


class TestStreamId(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.store = irl("webui.netstate").SrtlaStore(os.path.join(self.d.name, "srtla.json"))
        self.sid = self.store.add({"name": "A", "host": "srt.example.de", "port": 5000, "streamid": "geheim123"})

    def tearDown(self):
        self.d.cleanup()

    def sid_of(self):
        return next(s for s in self.store.data["servers"] if s["id"] == self.sid).get("streamid")

    def test_beibehalten(self):
        self.store.update(self.sid, {"name": "B", "host": "srt.example.de", "port": 5000, "streamid": ""})
        self.assertEqual(self.sid_of(), "geheim123")

    def test_ersetzen(self):
        self.store.update(self.sid, {"name": "A", "host": "srt.example.de", "port": 5000, "streamid": "neu456"})
        self.assertEqual(self.sid_of(), "neu456")

    def test_entfernen(self):
        self.store.update(self.sid, {"name": "A", "host": "srt.example.de", "port": 5000, "streamid": "", "clear_streamid": True})
        self.assertEqual(self.sid_of(), "")
        self.assertFalse(self.store.public()["servers"][0]["has_streamid"])


if __name__ == "__main__":
    unittest.main()
