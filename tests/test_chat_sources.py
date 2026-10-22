import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "irl4you"))

from twitch.reader import TwitchReader


class Yt:
    def __init__(self):
        self.runs = 0

    def ready(self):
        return True

    def ensure(self):
        self.runs += 1


class Store:
    data = {"channel": ""}


class ChatSources(unittest.TestCase):
    def reader(self):
        r = TwitchReader(Store(), paths=None)
        r.youtube = Yt()
        r._add({"type": "msg", "text": "tw"})
        r._add({"type": "msg", "text": "yt", "src": "youtube"})
        return r

    def test_filter_nach_quelle(self):
        r = self.reader()
        self.assertEqual([i["text"] for i in r.poll()["items"]], ["tw", "yt"])
        r.set_sources({"twitch": False})
        self.assertEqual([i["text"] for i in r.poll()["items"]], ["yt"])
        r.set_sources({"twitch": True, "youtube": False})
        out = r.poll()
        self.assertEqual(out["items"], [])
        self.assertEqual(out["state"], "kein-kanal")
        r.set_sources({"twitch": False})
        self.assertEqual(r.poll()["state"], "aus")

    def test_speichern_und_laden(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            r = self.reader()
            r.load_sources(p)
            r.set_sources({"youtube": False})
            r2 = self.reader()
            r2.load_sources(p)
            self.assertEqual(r2.src_on, {"twitch": True, "youtube": False})

    def test_ungueltig(self):
        r = self.reader()
        with self.assertRaises(ValueError):
            r.set_sources({"twitch": "ja"})


if __name__ == "__main__":
    unittest.main()
