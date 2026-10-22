import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "irl4you"))

from kickweb import KickPublic


class Reader:
    def _idle(self):
        return False

    def source_on(self, name):
        return True

    def _add(self, item):
        pass


class Kick(unittest.TestCase):
    def test_normalize(self):
        n = KickPublic.normalize
        self.assertEqual(n("XQC"), "xqc")
        self.assertEqual(n("@xqc"), "xqc")
        self.assertEqual(n("https://kick.com/Mein-Kanal/videos"), "mein-kanal")
        self.assertEqual(n("kick.com/abc"), "abc")
        self.assertEqual(n("https://evil.example/abc"), "")
        self.assertEqual(n("a b"), "")
        self.assertEqual(n(""), "")

    def test_kanal_speichern(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k.json")
            k = KickPublic(p, Reader())
            k.set_channel("kick.com/Test_1")
            self.assertEqual(KickPublic(p, Reader()).channel, "test_1")
            with self.assertRaises(ValueError):
                k.set_channel("http://x.de/y")

    def test_nachricht_mit_emotes(self):
        k = KickPublic(os.path.join(tempfile.gettempdir(), "kick-test-nonexistent.json"), Reader())
        ev = {"id": "abc", "content": "hi [emote:123:Kappa] da", "created_at": "2026-10-22T23:48:23+00:00",
              "sender": {"username": "Bob", "identity": {"color": "#BC66FF", "badges": [{"type": "moderator"}, {"type": "subscriber"}, {"type": "x"}]}}}
        (m,) = k.parse("ChatMessageEvent", ev)
        self.assertEqual((m["src"], m["name"], m["text"], m["badges"], m["color"]), ("kick", "Bob", "hi Kappa da", ["moderator", "subscriber"], "#BC66FF"))
        self.assertEqual(m["emotes"], [["https://files.kick.com/emotes/123/fullsize", 3, 7]])
        self.assertEqual(m["ts"], 1792712903)

    def test_loeschen_und_leer(self):
        k = KickPublic(os.path.join(tempfile.gettempdir(), "kick-test-nonexistent.json"), Reader())
        self.assertEqual(k.parse("MessageDeletedEvent", {"message": {"id": "x1"}})[0]["mid"], "x1")
        self.assertEqual(k.parse("ChatMessageEvent", {"content": "   ", "sender": {}}), [])
        self.assertEqual(k.parse("Unbekannt", {}), [])
        self.assertEqual(k.parse("ChatMessageEvent", "kaputt"), [])


if __name__ == "__main__":
    unittest.main()
