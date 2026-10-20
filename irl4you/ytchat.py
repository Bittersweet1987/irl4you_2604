"""IRL4YOU BOX YouTube: Anmeldung mit dem YouTube-Konto und Livechat holen.

Der Livechat des laufenden Streams wird automatisch gefunden und in den Chat der Box gemischt (Herkunft "youtube", Twitch-Nachrichten tragen "twitch").
Anmeldung nach dem Geräte-Ablauf von Google (OAuth "TVs and Limited Input devices"): Die Box zeigt einen Code, der Nutzer gibt ihn auf google.com/device ein.
Die OAuth-Zugangsdaten (Client-ID und Geheimnis) legt jeder Betreiber in seinem eigenen Google-Cloud-Projekt an (YouTube Data API v3 einschalten); sie
liegen nur auf der Box. Gelesen wird ausschließlich (Bereich youtube.readonly).
"""

import collections
import datetime
import json
import os
import re
import threading
import time

from twitch.irc import ChatPaths


class YoutubeLogin:
    DEVICE_URL = "https://oauth2.googleapis.com/device/code"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"
    API = "https://www.googleapis.com/youtube/v3/"
    SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
    GRANT = "urn:ietf:params:oauth:grant-type:device_code"
    ID_RE = re.compile(r"[A-Za-z0-9._-]{10,200}")
    SECRET_RE = re.compile(r"[A-Za-z0-9._~-]{8,120}")
    URI_RE = re.compile(r"https://([a-z0-9-]+\.)?google\.com/[A-Za-z0-9/_?=&%.-]{0,200}")
    ERR_NET = "Keine Verbindung zu Google"
    ERR_DENIED = "Die Anmeldung wurde abgelehnt oder ist abgelaufen"

    def __init__(self, path, demo=False, paths=None, clock=time.time, sleep=time.sleep):
        self.path, self.demo = path, demo
        self.paths = paths or ChatPaths()
        self.clock, self.sleep = clock, sleep
        self.lock = threading.RLock()
        self.data = {}
        self.pending = None
        self.state, self.error, self.gen = "aus", "", 0
        try:
            with open(path) as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data = {k: d[k] for k in ("client_id", "client_secret", "refresh", "access", "expires_at", "channel") if k in d}
        except (OSError, ValueError, TypeError):
            pass
        self.state = self._base_state()

    def _base_state(self):
        if self.data.get("refresh"):
            return "angemeldet"
        return "bereit" if self.data.get("client_id") and self.data.get("client_secret") else "kein-client"

    def _write(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(self.data, f)
        os.replace(tmp, self.path)

    def _call(self, url, fields=None, headers=None, once=False):
        import urllib.parse
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        hdr = dict(headers or {}, **{"User-Agent": "irl4you-box"})
        if data is not None:
            hdr["Content-Type"] = "application/x-www-form-urlencoded"
        st, body = self.paths.request("POST" if data is not None else "GET", url, data, hdr, once=once)
        try:
            out = json.loads(body.decode("utf-8", "replace") or "{}")
        except ValueError:
            out = {}
        return st, out if isinstance(out, dict) else {}

    def status(self):
        with self.lock:
            p, d = self.pending, self.data
            out = {"state": self.state, "has_client": bool(d.get("client_id") and d.get("client_secret")), "client_id": str(d.get("client_id", ""))[:200],
                   "secret_set": bool(d.get("client_secret")), "channel": str(d.get("channel", ""))[:100], "error": self.error}
            if p and self.state == "wartet":
                out.update(code=p["user_code"], uri=p["uri"], expires_in=max(0, int(p["expires_at"] - self.clock())))
            return out

    def ready(self):
        return bool(self.data.get("refresh"))

    def save_client(self, client_id, secret):
        client_id = str(client_id or "").strip()
        secret = str(secret or "").strip()
        if not self.ID_RE.fullmatch(client_id):
            raise ValueError("Client-ID: so wie bei Google angezeigt eintragen (endet auf .apps.googleusercontent.com)")
        with self.lock:
            if not secret and client_id == self.data.get("client_id") and self.data.get("client_secret"):
                return self.status()
            if not self.SECRET_RE.fullmatch(secret):
                raise ValueError("Client-Geheimnis: so wie bei Google angezeigt eintragen")
            if client_id != self.data.get("client_id") or secret != self.data.get("client_secret"):
                self.gen += 1
                self.pending = None
                self.data = {"client_id": client_id, "client_secret": secret}
                self.error = ""
                self.state = self._base_state()
                self._write()
            return self.status()

    def start(self):
        with self.lock:
            d = self.data
            if not (d.get("client_id") and d.get("client_secret")):
                raise ValueError("Bitte zuerst Client-ID und Client-Geheimnis eintragen")
            if self.state == "wartet" and self.pending and self.pending["expires_at"] > self.clock():
                return self.status()
            self.gen += 1
            gen = self.gen
            self.error = ""
            if self.demo:
                self.pending = {"device_code": "demo", "user_code": "ABCD-EFGH-IJKL", "uri": "https://www.google.com/device", "expires_at": self.clock() + 1800, "interval": 5}
                self.state = "wartet"
                return self.status()
            st, r = self._call(self.DEVICE_URL, {"client_id": d["client_id"], "scope": self.SCOPE})
            if st != 200 or not all(isinstance(r.get(k), str) for k in ("device_code", "user_code", "verification_url")):
                self.state = self._base_state() if not self.ready() else "angemeldet"
                self.error = self.ERR_NET if st <= 0 else "Google hat die Anmeldung nicht angenommen: " + str(r.get("error_description") or r.get("error") or st)[:160]
                raise ValueError(self.error)
            try:
                interval = max(2, min(30, int(r.get("interval", 5))))
                expires = max(60, min(3600, int(r.get("expires_in", 1800))))
            except (TypeError, ValueError):
                interval, expires = 5, 1800
            uri = r["verification_url"][:300]
            if not self.URI_RE.fullmatch(uri):
                uri = "https://www.google.com/device"
            self.pending = {"device_code": r["device_code"], "user_code": r["user_code"][:30], "uri": uri, "expires_at": self.clock() + expires, "interval": interval}
            self.state = "wartet"
        threading.Thread(target=self._poll, args=(gen,), daemon=True).start()
        return self.status()

    def cancel(self):
        with self.lock:
            self.gen += 1
            self.pending = None
            if self.state == "wartet":
                self.state = self._base_state()
            return self.status()

    def _poll(self, gen):
        while True:
            with self.lock:
                p = self.pending
                if gen != self.gen or not p or self.state != "wartet":
                    return
                if p["expires_at"] <= self.clock():
                    self.state, self.error, self.pending = self._base_state(), self.ERR_DENIED, None
                    return
                wait, device = p["interval"], p["device_code"]
                cid, secret = self.data["client_id"], self.data["client_secret"]
            self.sleep(wait)
            st, r = self._call(self.TOKEN_URL, {"client_id": cid, "client_secret": secret, "device_code": device, "grant_type": self.GRANT}, once=True)
            with self.lock:
                if gen != self.gen or self.state != "wartet":
                    return
                if st == 200 and isinstance(r.get("access_token"), str) and isinstance(r.get("refresh_token"), str):
                    self._adopt(r)
                    return
                err = str(r.get("error", ""))
                if err == "authorization_pending" or st <= 0 or st >= 500:
                    continue
                if err == "slow_down" or st == 429:
                    self.pending["interval"] = min(30, self.pending["interval"] + 5)
                    continue
                self.state, self.error, self.pending = self._base_state(), self.ERR_DENIED, None
                return

    def _adopt(self, r):
        try:
            life = max(60, int(r.get("expires_in", 3600)))
        except (TypeError, ValueError):
            life = 3600
        self.data.update(refresh=r["refresh_token"], access=r["access_token"], expires_at=self.clock() + life)
        self.pending, self.error, self.state = None, "", "angemeldet"
        self._write()
        st, ch = self._call(self.API + "channels?part=snippet&mine=true", headers={"Authorization": "Bearer " + r["access_token"]})
        try:
            title = str(ch["items"][0]["snippet"]["title"])[:100] if st == 200 else ""
        except (KeyError, IndexError, TypeError):
            title = ""
        self.data["channel"] = title
        self._write()

    def token(self):
        """Gültiges Zugriffstoken oder "" (wird bei Bedarf mit dem gespeicherten Erneuerungstoken geholt)."""
        with self.lock:
            d = self.data
            if not d.get("refresh"):
                return ""
            if d.get("access") and float(d.get("expires_at", 0)) - self.clock() > 60:
                return d["access"]
            if self.demo:
                return ""
            st, r = self._call(self.TOKEN_URL, {"client_id": d.get("client_id", ""), "client_secret": d.get("client_secret", ""),
                                                "refresh_token": d["refresh"], "grant_type": "refresh_token"}, once=True)
            if st == 200 and isinstance(r.get("access_token"), str):
                try:
                    life = max(60, int(r.get("expires_in", 3600)))
                except (TypeError, ValueError):
                    life = 3600
                d.update(access=r["access_token"], expires_at=self.clock() + life)
                self._write()
                return d["access"]
            if st == 400 and r.get("error") == "invalid_grant":
                self.data = {k: d[k] for k in ("client_id", "client_secret") if k in d}
                self.state, self.error = "bereit", "Die Anmeldung ist abgelaufen oder wurde widerrufen. Bitte neu anmelden."
                self._write()
            return ""

    def logout(self):
        with self.lock:
            tok = self.data.get("refresh") or self.data.get("access")
            self.gen += 1
            self.pending = None
            self.data = {k: self.data[k] for k in ("client_id", "client_secret") if k in self.data}
            self.state, self.error = self._base_state(), ""
            self._write()
        if tok and not self.demo:
            try:
                self._call(self.REVOKE_URL, {"token": tok}, once=True)
            except Exception:
                pass
        return self.status()


class YoutubeChat:
    """Holt den Livechat des gerade laufenden YouTube-Streams (nur solange jemand den Chat der Box ansieht) und reicht die Nachrichten an den Chat-Leser."""
    FIND_EVERY = 60.0
    MIN_POLL = 6.0
    MAX_POLL = 30.0
    FIRST_KEEP = 25
    BADGES = (("isChatOwner", "broadcaster"), ("isChatModerator", "moderator"), ("isChatSponsor", "subscriber"))

    def __init__(self, login, reader, paths=None, clock=time.monotonic, sleep=time.sleep, wall=time.time):
        self.login, self.reader = login, reader
        self.paths = paths or login.paths
        self.clock, self.sleep, self.wall = clock, sleep, wall
        self.lock = threading.Lock()
        self.thread = None
        self.gen = 0
        self.state, self.error, self.title = "aus", "", ""
        self.seen = collections.deque(maxlen=600)

    def ready(self):
        return self.login.ready()

    def status(self):
        with self.lock:
            return {"state": self.state, "error": self.error, "title": self.title}

    def ensure(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.gen += 1
            gen = self.gen
            self.state = "verbinde"
            t = threading.Thread(target=self._run, args=(gen,), daemon=True)
            self.thread = t
        t.start()

    def _mine(self, gen):
        return self.gen == gen and not self.reader._idle() and self.login.ready()

    def _set(self, state, error="", title=None):
        with self.lock:
            self.state, self.error = state, error
            if title is not None:
                self.title = title

    def _nap(self, seconds, gen):
        end = self.clock() + seconds
        while self.clock() < end and self._mine(gen):
            self.sleep(min(1.0, max(0.0, end - self.clock())))

    def _get(self, path, **params):
        import urllib.parse
        tok = self.login.token()
        if not tok:
            return 401, {}
        url = YoutubeLogin.API + path + "?" + urllib.parse.urlencode(params)
        st, body = self.paths.request("GET", url, None, {"Authorization": "Bearer " + tok, "User-Agent": "irl4you-box"}, once=True)
        try:
            out = json.loads(body.decode("utf-8", "replace") or "{}")
        except ValueError:
            out = {}
        return st, out if isinstance(out, dict) else {}

    @staticmethod
    def _reason(d):
        try:
            return str(d["error"]["errors"][0]["reason"])
        except (KeyError, IndexError, TypeError):
            return ""

    def find(self):
        """(liveChatId, Titel) der gerade laufenden Übertragung oder (None, "")."""
        st, d = self._get("liveBroadcasts", part="snippet,status", broadcastStatus="active", maxResults=5)
        if st != 200:
            raise OSError(st)
        for it in d.get("items") or []:
            sn = it.get("snippet") or {}
            if isinstance(sn.get("liveChatId"), str) and sn["liveChatId"]:
                return sn["liveChatId"], str(sn.get("title", ""))[:100]
        return None, ""

    def _run(self, gen):
        chat_id, token, first = None, "", True
        while self._mine(gen):
            try:
                if not chat_id:
                    chat_id, title = self.find()
                    if not chat_id:
                        self._set("kein-stream", "")
                        self._nap(self.FIND_EVERY, gen)
                        continue
                    token, first = "", True
                    self._set("ok", "", title)
                params = {"liveChatId": chat_id, "part": "snippet,authorDetails", "maxResults": 200}
                if token:
                    params["pageToken"] = token
                st, d = self._get("liveChat/messages", **params)
                if st != 200:
                    why = self._reason(d)
                    if why in ("liveChatEnded", "liveChatNotFound") or st == 404:
                        chat_id = None
                        self._set("kein-stream", "")
                        self._nap(30.0, gen)
                    elif why in ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded"):
                        self._set("kontingent", "Das Tageskontingent der YouTube-Schnittstelle ist aufgebraucht")
                        self._nap(900.0, gen)
                    elif st == 401 or st == 403:
                        self._set("fehler", "YouTube verweigert den Zugriff (%s). Bitte neu anmelden." % (why or st))
                        self._nap(60.0, gen)
                    else:
                        raise OSError(st)
                    continue
                items = d.get("items") or []
                if first and len(items) > self.FIRST_KEEP:
                    items = items[-self.FIRST_KEEP:]
                first = False
                for it in items:
                    for m in self.parse(it):
                        self.reader._add(m)
                token = str(d.get("nextPageToken") or token)
                try:
                    wait = float(d.get("pollingIntervalMillis", 0)) / 1000.0
                except (TypeError, ValueError):
                    wait = 0.0
                self._nap(max(self.MIN_POLL, min(self.MAX_POLL, wait)), gen)
            except (OSError, ValueError, KeyError, TypeError):
                self._set("fehler", "Keine Verbindung zu YouTube")
                self._nap(15.0, gen)
        with self.lock:
            if self.gen == gen:
                self.state = "aus"

    @staticmethod
    def _clean(text, limit):
        out = "".join(" " if ord(c) < 32 else c for c in str(text or ""))
        return " ".join(out.split())[:limit]

    def parse(self, it):
        """Eine Nachricht der Schnittstelle als Chat-Einträge der Box (0, 1 oder mehr)."""
        if not isinstance(it, dict):
            return []
        sn, au = it.get("snippet") or {}, it.get("authorDetails") or {}
        mid = str(it.get("id", ""))[:200]
        kind = sn.get("type", "")
        if kind == "messageDeletedEvent":
            gone = str((sn.get("messageDeletedDetails") or {}).get("deletedMessageId", ""))[:200]
            return [{"type": "del", "meta": True, "mid": gone, "text": "", "emotes": [], "src": "youtube"}] if gone else []
        if mid and mid in self.seen:
            return []
        if mid:
            self.seen.append(mid)
        ts = None
        try:
            ts = int(datetime.datetime.fromisoformat(str(sn.get("publishedAt", "")).replace("Z", "+00:00")).timestamp())
        except ValueError:
            ts = None
        name = self._clean(au.get("displayName"), 40)
        badges = [b for k, b in self.BADGES if au.get(k) is True]
        base = {"src": "youtube", "emotes": []}
        if ts:
            base["ts"] = ts
        text = self._clean(sn.get("displayMessage") or (sn.get("textMessageDetails") or {}).get("messageText"), 500)
        if kind == "textMessageEvent":
            return [dict(base, type="msg", name=name, color="", text=text, badges=badges, mid=mid)] if text else []
        if kind in ("superChatEvent", "superStickerEvent"):
            det = sn.get("superChatDetails") or sn.get("superStickerDetails") or {}
            amount = self._clean(det.get("amountDisplayString"), 30)
            head = ("Super Chat " if kind == "superChatEvent" else "Super Sticker ") + amount
            return [dict(base, type="notice", name="", color="", text=head + (" – " + name if name else "") + (": " + text if text else ""))]
        if kind == "newSponsorEvent":
            return [dict(base, type="sub", name="", color="", text=(name + " ist neues Mitglied") if name else "Neues Mitglied")]
        if kind == "memberMilestoneChatEvent":
            return [dict(base, type="sub", name="", color="", text=(name + ": " if name else "") + (text or "Mitglieds-Meilenstein"))]
        return []
