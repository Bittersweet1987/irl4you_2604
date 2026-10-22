"""YouTube ohne Anmeldung: Kanal eintragen, laufenden Stream finden, öffentlichen Livechat lesen und in den Chat der Box mischen."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

UC = "UCabcdefghijklmnopqrstuv"
VID = "dQw4w9WgXcQ"

LIVE_PAGE = ('<html><head><link rel="canonical" href="https://www.youtube.com/watch?v=' + VID + '"><meta name="title" content="Mein &amp; Stream"></head>'
             '<body>{"isLiveNow":true}</body></html>')
NOT_LIVE_PAGE = '<html><head><link rel="canonical" href="https://www.youtube.com/@kanal"></head><body></body></html>'
INIT = {"contents": {"liveChatRenderer": {"continuations": [{"invalidationContinuationData": {"continuation": "C0", "timeoutMs": 100}}],
                                         "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
                                             "id": "h1", "message": {"runs": [{"text": "Alt"}]}, "authorName": {"simpleText": "Hist"}}}}}]}}}
CHAT_PAGE = ('<script>"INNERTUBE_API_KEY":"KEY123","INNERTUBE_CONTEXT_CLIENT_VERSION":"2.20260101.00.00"</script>'
             '<script>window["ytInitialData"] = ' + json.dumps(INIT) + ';</script>')


def text_msg(mid, text, name="Anna", badges=None):
    return {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
        "id": mid, "timestampUsec": "1792000000000000", "message": {"runs": [{"text": text}]}, "authorName": {"simpleText": name},
        "authorExternalChannelId": UC, "authorBadges": badges or []}}}}


class FakePaths:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, data=None, headers=None, timeout=15.0, limit=0, once=False, prefer=False, rh=None):
        self.calls.append((method, url, data, headers))
        for prefix, resp in self.routes.items():
            if url.startswith(prefix):
                r = resp.pop(0) if len(resp) > 1 else resp[0]
                if rh is not None and len(r) > 2:
                    rh.update(r[2])
                body = r[1] if isinstance(r[1], str) else json.dumps(r[1])
                return r[0], body.encode()
        return 404, b""


class Reader:
    def __init__(self):
        self.items = []

    def _idle(self):
        return False

    def source_on(self, name):
        return True

    def _add(self, item):
        self.items.append(item)


def make(routes, tmp):
    yw = irl("ytweb")
    paths = FakePaths(routes)
    pub = yw.YoutubePublic(os.path.join(tmp, "yp.json"), Reader(), paths=paths, sleep=lambda s: None)
    return yw, paths, pub


class TestKanal(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.yw, self.paths, self.pub = make({}, self.d.name)

    def tearDown(self):
        self.d.cleanup()

    def test_eingaben_werden_vereinheitlicht(self):
        n = self.yw.YoutubePublic.normalize
        for text in ("@meinkanal", "meinkanal", "https://www.youtube.com/@meinkanal", "youtube.com/@meinkanal/streams", "https://m.youtube.com/@meinkanal?si=x"):
            self.assertEqual(n(text), "@meinkanal", text)
        self.assertEqual(n("https://www.youtube.com/channel/" + UC), UC)
        self.assertEqual(n(UC), UC)
        for bad in ("", "ab", "@", "https://evil.example/@meinkanal", "https://www.youtube.com/watch?v=" + VID, "a b", "../x"):
            self.assertEqual(n(bad), "", bad)

    def test_speichern_und_laden(self):
        self.pub.set_channel("https://www.youtube.com/@meinkanal")
        again = self.yw.YoutubePublic(self.pub.path, Reader(), paths=self.paths)
        self.assertEqual((again.channel, again.ready()), ("@meinkanal", True))
        with self.assertRaises(ValueError):
            self.pub.set_channel("https://evil.example/@x")
        self.pub.set_channel("")
        self.assertFalse(self.pub.ready())


class TestFinden(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.d.cleanup()

    def test_laufender_stream(self):
        yw, paths, pub = make({"https://www.youtube.com/@kanal/live": [(200, LIVE_PAGE)]}, self.d.name)
        pub.channel = "@kanal"
        self.assertEqual(pub.find(), (VID, "Mein & Stream"))
        self.assertIn("SOCS=CAI", paths.calls[0][3]["Cookie"])

    def test_kein_stream_und_weiterleitung(self):
        yw, paths, pub = make({"https://www.youtube.com/@kanal/live": [(200, NOT_LIVE_PAGE)]}, self.d.name)
        pub.channel = "@kanal"
        self.assertEqual(pub.find(), (None, ""))
        yw, paths, pub = make({"https://www.youtube.com/@kanal/live": [(302, "", {"location": "/watch?v=" + VID})],
                               "https://www.youtube.com/watch": [(200, LIVE_PAGE)]}, self.d.name)
        pub.channel = "@kanal"
        self.assertEqual(pub.find()[0], VID)
        yw, paths, pub = make({"https://www.youtube.com/@kanal/live": [(302, "", {"location": "https://evil.example/x"})]}, self.d.name)
        pub.channel = "@kanal"
        with self.assertRaises(OSError):
            pub.find()

    def test_chat_oeffnen(self):
        yw, paths, pub = make({"https://www.youtube.com/live_chat": [(200, CHAT_PAGE)]}, self.d.name)
        key, ver, cont, actions = pub.open_chat(VID)
        self.assertEqual((key, ver, cont, len(actions)), ("KEY123", "2.20260101.00.00", "C0", 1))


class TestNachrichten(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.yw, self.paths, self.pub = make({}, self.d.name)

    def tearDown(self):
        self.d.cleanup()

    def test_text_mit_emoji_und_abzeichen(self):
        a = text_msg("m1", "x", badges=[{"liveChatAuthorBadgeRenderer": {"icon": {"iconType": "MODERATOR"}}},
                                        {"liveChatAuthorBadgeRenderer": {"customThumbnail": {"thumbnails": []}}}])
        a["addChatItemAction"]["item"]["liveChatTextMessageRenderer"]["message"] = {"runs": [{"text": "Hallo "}, {"emoji": {"emojiId": "😀", "shortcuts": [":grin:"]}},
                                                                                         {"text": " "}, {"emoji": {"isCustomEmoji": True, "shortcuts": [":kanal-hype:"]}}]}
        m = self.pub.parse(a)[0]
        self.assertEqual((m["src"], m["type"], m["name"], m["text"], m["badges"], m["uid"], m["mid"]), ("youtube", "msg", "Anna", "Hallo 😀 :kanal-hype:", ["moderator", "subscriber"], UC, "m1"))
        self.assertEqual(m["ts"], 1_792_000_000)
        self.assertEqual(self.pub.parse(a), [])

    def test_super_chat_mitglied_und_loeschen(self):
        paid = {"addChatItemAction": {"item": {"liveChatPaidMessageRenderer": {"id": "p1", "purchaseAmountText": {"simpleText": "5,00 €"}, "message": {"runs": [{"text": "Danke"}]},
                                                                              "authorName": {"simpleText": "Ben"}}}}}
        m = self.pub.parse(paid)[0]
        self.assertEqual(m["type"], "notice")
        self.assertIn("5,00 €", m["text"])
        mem = {"addChatItemAction": {"item": {"liveChatMembershipItemRenderer": {"id": "s1", "authorName": {"simpleText": "Cem"}, "headerSubtext": {"runs": [{"text": "Neues Mitglied"}]}}}}}
        self.assertEqual(self.pub.parse(mem)[0]["text"], "Cem: Neues Mitglied")
        gone = self.pub.parse({"markChatItemAsDeletedAction": {"targetItemId": "m1"}})[0]
        self.assertEqual((gone["type"], gone["mid"], gone["meta"]), ("del", "m1", True))
        ban = self.pub.parse({"markChatItemsByAuthorAsDeletedAction": {"externalChannelId": UC}})[0]
        self.assertEqual((ban["type"], ban["uid"]), ("clear", UC))
        self.assertEqual(self.pub.parse({"addChatItemAction": {"item": {"liveChatViewerEngagementMessageRenderer": {"id": "v1"}}}}), [])


class TestLauf(unittest.TestCase):
    def test_lauf_mischt_in_den_leser_und_findet_neuen_stream(self):
        d = tempfile.TemporaryDirectory()
        resp = {"continuationContents": {"liveChatContinuation": {"actions": [text_msg("a", "eins"), text_msg("b", "zwei")],
                                                                  "continuations": [{"timedContinuationData": {"continuation": "C1", "timeoutMs": 100}}]}}}
        yw, paths, pub = make({"https://www.youtube.com/@kanal/live": [(200, LIVE_PAGE)], "https://www.youtube.com/live_chat": [(200, CHAT_PAGE)],
                               "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat": [(200, resp)]}, d.name)
        pub.channel = "@kanal"
        runs = {"n": 0}

        def nap(seconds, gen):
            runs["n"] += 1
            if runs["n"] >= 2:                 # erste Runde (Verlauf), zweite Runde (neue Nachrichten), dann anhalten
                pub.gen += 1
        pub._nap = nap
        pub._run(pub.gen)
        texts = [m["text"] for m in pub.reader.items]
        self.assertEqual(texts, ["Alt", "eins", "zwei"])
        self.assertTrue(all(m["src"] == "youtube" for m in pub.reader.items))
        post = [c for c in paths.calls if c[0] == "POST"][0]
        self.assertIn("key=KEY123", post[1])
        self.assertEqual(json.loads(post[2].decode())["continuation"], "C0")
        d.cleanup()

    def test_kein_stream_status(self):
        d = tempfile.TemporaryDirectory()
        yw, paths, pub = make({"https://www.youtube.com/@kanal/live": [(200, NOT_LIVE_PAGE)]}, d.name)
        pub.channel = "@kanal"

        def nap(seconds, gen):
            pub.gen += 1
        pub._nap = nap
        pub._run(pub.gen)
        self.assertEqual(pub.status()["state"], "kein-stream")
        d.cleanup()


if __name__ == "__main__":
    unittest.main()
