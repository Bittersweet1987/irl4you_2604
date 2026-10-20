"""YouTube-Chat: Geräte-Anmeldung, Zugriffstoken, Livechat finden, Nachrichten umsetzen und in den Chat mischen."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

CID = "1234567890-abc.apps.googleusercontent.com"


class FakePaths:
    """Ersetzt ChatPaths: Antworten nach URL-Anfang (Liste = nacheinander, die letzte bleibt), Anfragen werden gemerkt."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, data=None, headers=None, timeout=15.0, limit=0, once=False, prefer=False):
        self.calls.append((method, url, data))
        for prefix, resp in self.routes.items():
            if url.startswith(prefix):
                r = resp.pop(0) if len(resp) > 1 else resp[0]
                return r[0], json.dumps(r[1]).encode()
        return 404, b"{}"


class Reader:
    def __init__(self):
        self.items = []

    def _idle(self):
        return False

    def _add(self, item):
        self.items.append(item)


def make(routes, tmp):
    yt = irl("ytchat")
    paths = FakePaths(routes)
    login = yt.YoutubeLogin(os.path.join(tmp, "youtube.json"), paths=paths, sleep=lambda s: None)
    return yt, paths, login


class TestAnmeldung(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.d.cleanup()

    def test_ohne_client_keine_anmeldung(self):
        yt, paths, login = make({}, self.d.name)
        self.assertEqual(login.status()["state"], "kein-client")
        with self.assertRaises(ValueError):
            login.start()
        with self.assertRaises(ValueError):
            login.save_client("kurz", "geheim123")

    def test_client_speichern_geheimnis_bleibt(self):
        yt, paths, login = make({}, self.d.name)
        login.save_client(CID, "geheimnis-123")
        st = login.status()
        self.assertEqual((st["state"], st["has_client"], st["secret_set"]), ("bereit", True, True))
        self.assertNotIn("geheimnis-123", json.dumps(st))
        login.save_client(CID, "")           # leeres Geheimnis = behalten
        self.assertEqual(login.data["client_secret"], "geheimnis-123")

    def test_geraete_ablauf(self):
        routes = {"https://oauth2.googleapis.com/device/code": [(200, {"device_code": "dc", "user_code": "AAAA-BBBB", "verification_url": "https://www.google.com/device", "expires_in": 1800, "interval": 5})],
                  "https://oauth2.googleapis.com/token": [(428, {"error": "authorization_pending"}), (200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})],
                  "https://www.googleapis.com/youtube/v3/channels": [(200, {"items": [{"snippet": {"title": "Mein Kanal"}}]})]}
        yt, paths, login = make(routes, self.d.name)
        login.save_client(CID, "geheimnis-123")
        st = login.start()        # die Abfrage läuft im Test ohne Wartezeit und kann schon fertig sein
        if st["state"] == "wartet":
            self.assertEqual(st["code"], "AAAA-BBBB")
        for _ in range(200):
            if login.state == "angemeldet" and login.data.get("channel"):
                break
            time.sleep(0.02)
        st = login.status()
        self.assertEqual((st["state"], st["channel"]), ("angemeldet", "Mein Kanal"))
        self.assertTrue(login.ready())
        self.assertEqual(login.token(), "AT")
        again = yt.YoutubeLogin(login.path, paths=paths)
        self.assertEqual((again.state, again.ready()), ("angemeldet", True))

    def test_token_erneuern_und_abgelaufen(self):
        routes = {"https://oauth2.googleapis.com/token": [(200, {"access_token": "NEU", "expires_in": 3600})]}
        yt, paths, login = make(routes, self.d.name)
        login.data = {"client_id": CID, "client_secret": "geheimnis-123", "refresh": "RT", "access": "ALT", "expires_at": 0}
        self.assertEqual(login.token(), "NEU")
        routes["https://oauth2.googleapis.com/token"] = [(400, {"error": "invalid_grant"})]
        login.data["expires_at"] = 0
        self.assertEqual(login.token(), "")
        self.assertEqual((login.state, login.ready()), ("bereit", False))

    def test_abmelden_behaelt_client(self):
        yt, paths, login = make({"https://oauth2.googleapis.com/revoke": [(200, {})]}, self.d.name)
        login.data = {"client_id": CID, "client_secret": "geheimnis-123", "refresh": "RT", "access": "AT", "expires_at": 9e12}
        login.state = "angemeldet"
        st = login.logout()
        self.assertEqual((st["state"], login.ready(), login.data["client_id"]), ("bereit", False, CID))


class TestChat(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        yt, paths, login = make({}, self.d.name)
        login.data = {"client_id": CID, "client_secret": "geheimnis-123", "refresh": "RT", "access": "AT", "expires_at": 9e12}
        self.chat = yt.YoutubeChat(login, Reader(), paths=paths)

    def tearDown(self):
        self.d.cleanup()

    def test_nachricht_mit_abzeichen(self):
        it = {"id": "m1", "snippet": {"type": "textMessageEvent", "displayMessage": "Hallo Welt", "publishedAt": "2026-10-20T10:00:00.123456+00:00"},
              "authorDetails": {"displayName": "Anna", "isChatModerator": True, "isChatSponsor": True}}
        out = self.chat.parse(it)
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual((m["src"], m["type"], m["name"], m["text"], m["badges"], m["mid"]), ("youtube", "msg", "Anna", "Hallo Welt", ["moderator", "subscriber"], "m1"))
        self.assertGreater(m["ts"], 1_700_000_000)
        self.assertEqual(self.chat.parse(it), [])           # doppelt geliefert

    def test_super_chat_mitglied_und_loeschen(self):
        sc = {"id": "m2", "snippet": {"type": "superChatEvent", "displayMessage": "Danke", "superChatDetails": {"amountDisplayString": "5,00 €"}}, "authorDetails": {"displayName": "Ben"}}
        m = self.chat.parse(sc)[0]
        self.assertEqual(m["type"], "notice")
        self.assertIn("5,00 €", m["text"])
        sp = {"id": "m3", "snippet": {"type": "newSponsorEvent"}, "authorDetails": {"displayName": "Cem"}}
        self.assertEqual(self.chat.parse(sp)[0]["text"], "Cem ist neues Mitglied")
        gone = {"id": "m4", "snippet": {"type": "messageDeletedEvent", "messageDeletedDetails": {"deletedMessageId": "m1"}}}
        d = self.chat.parse(gone)[0]
        self.assertEqual((d["type"], d["mid"], d["meta"]), ("del", "m1", True))
        self.assertEqual(self.chat.parse({"id": "m5", "snippet": {"type": "chatEndedEvent"}}), [])

    def test_livechat_finden(self):
        paths = self.chat.paths
        paths.routes["https://www.googleapis.com/youtube/v3/liveBroadcasts"] = [(200, {"items": [{"snippet": {"liveChatId": "CHAT1", "title": "Mein Stream"}}]})]
        self.assertEqual(self.chat.find(), ("CHAT1", "Mein Stream"))
        paths.routes["https://www.googleapis.com/youtube/v3/liveBroadcasts"] = [(200, {"items": []})]
        self.assertEqual(self.chat.find(), (None, ""))

    def test_lauf_mischt_in_den_leser(self):
        chat = self.chat
        chat.paths.routes["https://www.googleapis.com/youtube/v3/liveBroadcasts"] = [(200, {"items": [{"snippet": {"liveChatId": "CHAT1", "title": "S"}}]})]
        msgs = {"items": [{"id": "a", "snippet": {"type": "textMessageEvent", "displayMessage": "eins"}, "authorDetails": {"displayName": "X"}}], "nextPageToken": "T", "pollingIntervalMillis": 100}
        chat.paths.routes["https://www.googleapis.com/youtube/v3/liveChat/messages"] = [(200, msgs)]

        def nap(seconds, gen):            # nach der ersten Runde anhalten
            chat.gen += 1
        chat._nap = nap
        chat._run(chat.gen)
        self.assertEqual([m["text"] for m in chat.reader.items], ["eins"])
        self.assertEqual(chat.reader.items[0]["src"], "youtube")


class TestEingebauterClient(unittest.TestCase):
    def test_anmeldung_nur_mit_dem_konto(self):
        d = tempfile.TemporaryDirectory()
        yt = irl("ytchat")
        routes = {"https://oauth2.googleapis.com/device/code": [(200, {"device_code": "dc", "user_code": "AAAA-BBBB", "verification_url": "https://www.google.com/device", "expires_in": 1800, "interval": 5})]}
        paths = FakePaths(routes)
        login = yt.YoutubeLogin(os.path.join(d.name, "y.json"), paths=paths, sleep=lambda s: None)
        login.builtin = ("projekt.apps.googleusercontent.com", "projekt-geheimnis")
        login.state = login._base_state()
        st = login.status()
        self.assertEqual((st["state"], st["builtin"], st["has_client"]), ("bereit", True, True))
        login.start()
        sent = paths.calls[0][2].decode()
        self.assertIn("projekt.apps.googleusercontent.com", sent)
        self.assertIn("youtube.force-ssl", sent)           # lesen und moderieren
        d.cleanup()

    def test_ohne_client_klare_meldung(self):
        d = tempfile.TemporaryDirectory()
        yt = irl("ytchat")
        login = yt.YoutubeLogin(os.path.join(d.name, "y.json"), paths=FakePaths({}))
        login.builtin = ("", "")
        with self.assertRaises(ValueError):
            login.start()
        d.cleanup()


class TestModeration(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        routes = {"https://www.googleapis.com/youtube/v3/liveChat/messages": [(204, {})],
                  "https://www.googleapis.com/youtube/v3/liveChat/bans": [(200, {"id": "BANID123"})]}
        yt, paths, login = make(routes, self.d.name)
        login.data = {"client_id": CID, "client_secret": "geheimnis-123", "refresh": "RT", "access": "AT", "expires_at": 9e12}
        self.chat = yt.YoutubeChat(login, Reader(), paths=paths)
        self.paths = paths

    def tearDown(self):
        self.d.cleanup()

    def test_ohne_livechat_keine_moderation(self):
        with self.assertRaises(ValueError):
            self.chat.moderate({"action": "delete", "message_id": "abcde12345"})

    def test_loeschen_timeout_bann_und_aufheben(self):
        self.chat.chat_id = "CHAT1"
        self.assertTrue(self.chat.moderate({"action": "delete", "message_id": "LCC.abc123"})["ok"])
        self.assertEqual(self.paths.calls[-1][0], "DELETE")
        self.assertIn("id=LCC.abc123", self.paths.calls[-1][1])
        r = self.chat.moderate({"action": "timeout", "user_id": "UCabcdefghijklmnopqrstuv", "seconds": 600})
        body = json.loads(self.paths.calls[-1][2].decode())["snippet"]
        self.assertEqual((body["type"], body["banDuration"], body["liveChatId"], r["user_id"]), ("temporary", 600, "CHAT1", "BANID123"))
        self.chat.moderate({"action": "ban", "user_id": "UCabcdefghijklmnopqrstuv"})
        self.assertEqual(json.loads(self.paths.calls[-1][2].decode())["snippet"]["type"], "permanent")
        self.chat.moderate({"action": "unban", "user_id": "BANID123"})
        self.assertEqual((self.paths.calls[-1][0], "id=BANID123" in self.paths.calls[-1][1]), ("DELETE", True))

    def test_ungueltige_eingaben(self):
        self.chat.chat_id = "CHAT1"
        for bad in ({"action": "delete", "message_id": "../x"}, {"action": "timeout", "user_id": "x", "seconds": 5},
                    {"action": "timeout", "user_id": "UCabcdefghijklmnopqrstuv", "seconds": 0}, {"action": "kick"}):
            with self.assertRaises(ValueError):
                self.chat.moderate(bad)

    def test_nachricht_traegt_autorkennung(self):
        it = {"id": "m1", "snippet": {"type": "textMessageEvent", "displayMessage": "hi"}, "authorDetails": {"displayName": "Anna", "channelId": "UCabcdefghijklmnopqrstuv"}}
        m = self.chat.parse(it)[0]
        self.assertEqual((m["uid"], m["login"]), ("UCabcdefghijklmnopqrstuv", "Anna"))


class TestLeser(unittest.TestCase):
    def test_twitch_nachrichten_tragen_herkunft(self):
        tw = irl("twitch")
        r = tw.TwitchReader(None, demo=True)
        item = r.parse("@display-name=Zoe;color=#FF0000;id=0123456789abcdef0123;user-id=1 :zoe!zoe@zoe.tmi.twitch.tv PRIVMSG #kanal :hi")
        self.assertEqual(item["src"], "twitch")


if __name__ == "__main__":
    unittest.main()
