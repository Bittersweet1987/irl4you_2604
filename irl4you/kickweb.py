"""IRL4YOU BOX Kick: öffentlichen Chat ohne Anmeldung lesen.

Der Nutzer trägt nur seinen Kanal ein (Name oder Link). Die Box fragt bei Kick wie ein Browser ohne Konto nach den Kennungen des Kanals und den Zugangsdaten
für den Echtzeit-Dienst (Pusher) und liest darüber den Chat mit. Es gibt keine Anmeldung und kein Schreiben. Das ist eine inoffizielle Schnittstelle von Kick
und kann sich ändern.
"""

import calendar
import collections
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.parse

from twitch.irc import ChatPaths
from twitch.websocket import WebSocketLite


class KickPublic:
    API = "https://kick.com/api/v1/channels/"
    REALTIME = "https://web.kick.com/api/v1/realtime/channels/%d/chat/connection"
    HISTORY = "https://web.kick.com/api/v1/chat/%d/history"
    HIST_EVERY = 4.0
    FIRST_KEEP = 25
    UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
    KEY_RE = re.compile(r"[0-9a-f]{16,32}")
    CLUSTER_RE = re.compile(r"[a-z0-9]{2,10}")
    EMOTE_RE = re.compile(r"\[emote:(\d{1,12}):([^\]\[:]{1,60})\]")
    EMOTE_URL = "https://files.kick.com/emotes/%s/fullsize"
    BADGES = {"broadcaster": "broadcaster", "moderator": "moderator", "vip": "vip", "subscriber": "subscriber", "founder": "founder", "owner": "broadcaster"}
    RETRY = (5.0, 10.0, 30.0, 60.0)
    PING_EVERY = 50.0

    def __init__(self, path, reader, paths=None, clock=time.monotonic, sleep=time.sleep):
        self.path, self.reader = path, reader
        self.paths = paths or ChatPaths()
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.thread, self.hthread, self.gen = None, None, 0
        self.state, self.error, self.title = "aus", "", ""
        self.msgs, self.last, self.other = 0, None, {}
        self.via = {"ws": 0, "hist": 0}
        self.hist_ok = False
        self.seen = collections.deque(maxlen=600)
        self.channel = ""
        try:
            with open(path) as f:
                d = json.load(f)
            self.channel = self.normalize(d.get("channel", "")) if isinstance(d, dict) else ""
        except (OSError, ValueError):
            self.channel = ""

    @classmethod
    def normalize(cls, text):
        """Kanalname oder Link (kick.com/name) -> Kanalname; leer bei Ungültigem."""
        t = str(text or "").strip()
        if not t:
            return ""
        if "/" in t or "." in t:
            u = urllib.parse.urlsplit(t if "//" in t else "https://" + t)
            if (u.hostname or "").lower() not in ("kick.com", "www.kick.com"):
                return ""
            parts = [p for p in u.path.split("/") if p]
            t = parts[0] if parts else ""
        t = t.lstrip("@")
        return t.lower() if cls.SLUG_RE.fullmatch(t) else ""

    def set_channel(self, text):
        norm = self.normalize(text)
        if text and not norm:
            raise ValueError("Kanal: der Name auf Kick oder der Link zum Kanal (kick.com/name)")
        with self.lock:
            self.channel = norm
            self.gen += 1
            self.state, self.error, self.title = ("aus" if not norm else "verbinde"), "", ""
            self.hist_ok, self.seen = False, collections.deque(maxlen=600)
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"channel": norm}, f)
            os.replace(tmp, self.path)

    def ready(self):
        return bool(self.channel)

    def status(self):
        with self.lock:
            state, error = self.state, self.error
            if self.hist_ok and state in ("fehler", "verbinde"):
                state, error = "ok", ""        # der Verlauf liefert, auch wenn die Echtzeit-Verbindung gerade fehlt
            return {"state": state, "error": error, "title": self.title or self.channel, "channel": self.channel, "mod": False, "msgs": self.msgs,
                    "age": None if self.last is None else int(self.clock() - self.last), "other": dict(self.other), "via": dict(self.via)}

    def ensure(self):
        with self.lock:
            if not self.channel or (self.thread is not None and self.thread.is_alive()):
                return
            self.gen += 1
            gen = self.gen
            self.state = "verbinde"
            self.hist_ok = False
            t = threading.Thread(target=self._run, args=(gen,), daemon=True)
            h = threading.Thread(target=self._history, args=(gen,), daemon=True)
            self.thread, self.hthread = t, h
        t.start()
        h.start()

    def _mine(self, gen):
        return self.gen == gen and bool(self.channel) and not self.reader._idle() and self.reader.source_on("kick")

    def _emit(self, items, via):
        """Neue Einträge an den Chat der Box geben; was schon da war (Echtzeit und Verlauf liefern dieselben Nachrichten), wird übersprungen."""
        fresh = []
        with self.lock:
            for m in items:
                mid = m.get("mid")
                if mid and not m.get("meta"):
                    if mid in self.seen:
                        continue
                    self.seen.append(mid)
                fresh.append(m)
            if fresh:
                self.msgs, self.last = self.msgs + sum(1 for m in fresh if not m.get("meta")), self.clock()
                self.via[via] += len(fresh)
        for m in fresh:
            self.reader._add(m)

    def _history(self, gen):
        """Verlauf des Chats alle paar Sekunden abfragen (wie die Webseite, ohne Anmeldung): Das zeigt auch bei ruhiger oder fehlender Echtzeit-Verbindung
        und bei einem Kanal, der gerade nicht sendet, die letzten Nachrichten."""
        cid, first = None, True
        while self._mine(gen):
            try:
                if cid is None:
                    cid = self.lookup()[0]
                st, text = self._fetch("GET", self.HISTORY % cid)
                if st != 200:
                    raise OSError(st)
                msgs = ((json.loads(text).get("data") or {}).get("messages")) or []
                items = []
                for m in sorted((x for x in msgs if isinstance(x, dict)), key=lambda x: str(x.get("created_at", ""))):
                    items += self.parse("ChatMessageEvent", m)
                if first and len(items) > self.FIRST_KEEP:
                    items = items[-self.FIRST_KEEP:]
                first = False
                self._emit(items, "hist")
                with self.lock:
                    self.hist_ok = True
            except LookupError:
                self._nap(60.0, gen)
                continue
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                with self.lock:
                    self.hist_ok = False
                self._nap(15.0, gen)
                continue
            self._nap(self.HIST_EVERY, gen)

    def _set(self, state, error="", title=None):
        with self.lock:
            self.state, self.error = state, error
            if title is not None:
                self.title = title

    def _nap(self, seconds, gen):
        end = self.clock() + seconds
        while self.clock() < end and self._mine(gen):
            self.sleep(min(1.0, max(0.0, end - self.clock())))

    def _fetch(self, method, url, body=None):
        hdr = {"User-Agent": self.UA, "Accept": "application/json", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            hdr["Content-Type"] = "application/json"
        st, raw = self.paths.request(method, url, data, hdr, limit=2_000_000, once=True)
        return st, raw.decode("utf-8", "replace")

    def lookup(self):
        """(Kanal-Nummer, Chatraum-Nummer, Titel des laufenden Streams oder "")."""
        st, text = self._fetch("GET", self.API + urllib.parse.quote(self.channel))
        if st == 404:
            raise LookupError("Kanal nicht gefunden")
        if st != 200:
            raise OSError(st)
        d = json.loads(text)
        cid, rid = d.get("id"), (d.get("chatroom") or {}).get("id")
        if not (isinstance(cid, int) and isinstance(rid, int) and cid > 0 and rid > 0):
            raise OSError(-3)
        live = d.get("livestream")
        return cid, rid, (self._clean((live or {}).get("session_title"), 100) if isinstance(live, dict) else "")

    def credentials(self, cid):
        """(App-Schlüssel, Cluster) des Echtzeit-Dienstes für den Chat des Kanals."""
        body = {"client": {"id": "irl4you-box", "type": "web"}, "capabilities": {"accepted_providers": [{"provider": "pusher"}]}}
        st, text = self._fetch("POST", self.REALTIME % cid, body)
        if st != 200:
            raise OSError(st)
        for c in (json.loads(text).get("data") or {}).get("connections") or []:
            cr = c.get("credentials") or {}
            key, cluster = cr.get("app_key"), cr.get("cluster")
            if c.get("provider") == "pusher" and isinstance(key, str) and self.KEY_RE.fullmatch(key) and isinstance(cluster, str) and self.CLUSTER_RE.fullmatch(cluster):
                return key, cluster
        raise OSError(-3)

    def _open(self, key, cluster):
        host = "ws-%s.pusher.com" % cluster
        sock, _ = self.paths.connect(host, 443, timeout=8)
        try:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            return WebSocketLite.handshake(sock, host, "/app/%s?protocol=7&client=js&version=8.4.0&flash=false" % key, self.clock)
        except BaseException:
            try:
                sock.close()
            except OSError:
                pass
            raise

    @staticmethod
    def _send(ws, event, data):
        ws.sock.sendall(ws.frame(1, json.dumps({"event": event, "data": data}).encode()))

    def _session(self, gen):
        cid, rid, title = self.lookup()
        key, cluster = self.credentials(cid)
        ws = self._open(key, cluster)
        try:
            self._send(ws, "pusher:subscribe", {"auth": "", "channel": "chatrooms.%d.v2" % rid})
            pinged = self.clock()
            while self._mine(gen):
                msg = ws.recv_message(1.0)
                now = self.clock()
                if msg is None:
                    if now - ws.last_rx > 150.0:
                        raise OSError("still")
                    if now - pinged > self.PING_EVERY:
                        self._send(ws, "pusher:ping", {})
                        pinged = now
                    continue
                try:
                    d = json.loads(msg)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                ev = d.get("event")
                if ev == "pusher:ping":
                    self._send(ws, "pusher:pong", {})
                elif ev == "pusher:error":
                    raise OSError("pusher")
                elif ev == "pusher_internal:subscription_succeeded":
                    self._set("ok", "", title or self.channel)
                elif isinstance(ev, str) and ev.startswith("App\\Events\\"):
                    try:
                        data = json.loads(d.get("data")) if isinstance(d.get("data"), str) else d.get("data")
                    except ValueError:
                        continue
                    name = ev[len("App\\Events\\"):]
                    got = self.parse(name, data)
                    if got:
                        self._emit(got, "ws")
                    else:
                        with self.lock:
                            if len(self.other) < 20 or name in self.other:
                                self.other[name] = self.other.get(name, 0) + 1
        finally:
            ws.close()

    def _run(self, gen):
        tries = 0
        while self._mine(gen):
            began = self.clock()
            try:
                self._session(gen)
                tries = 0
            except LookupError as e:
                self._set("kein-kanal", str(e))
                self._nap(60.0, gen)
                continue
            except (OSError, EOFError, ValueError, KeyError, TypeError, AttributeError, socket.timeout) as e:
                blocked = isinstance(e, OSError) and e.args and e.args[0] in (403, 429)
                self._set("fehler", "Kick lässt die Box nicht herein (Sperre durch Kick)" if blocked else "Keine Verbindung zu Kick")
            if self.clock() - began > 60:
                tries = 0
            self._nap(self.RETRY[min(tries, len(self.RETRY) - 1)], gen)
            tries += 1
        with self.lock:
            if self.gen == gen:
                self.state = "aus"

    @staticmethod
    def _clean(text, limit):
        out = "".join(" " if ord(c) < 32 else c for c in str(text or ""))
        return " ".join(out.split())[:limit]

    @classmethod
    def _text(cls, content):
        """Text der Nachricht mit den Emotes ([emote:ID:name] -> name) und deren Stellen (in Zeichen)."""
        raw = "".join(" " if ord(c) < 32 else c for c in str(content or "")[:1500])
        out, emotes, last, n = [], [], 0, 0
        for m in cls.EMOTE_RE.finditer(raw):
            seg = raw[last:m.start()]
            out.append(seg)
            n += len(seg)
            emotes.append([cls.EMOTE_URL % m.group(1), n, n + len(m.group(2)) - 1])
            out.append(m.group(2))
            n += len(m.group(2))
            last = m.end()
        out.append(raw[last:])
        return "".join(out)[:500], [e for e in emotes if e[2] < 500]

    def parse(self, event, d):
        """Ein Ereignis des Chats als Einträge der Box (0, 1 oder mehr)."""
        if not isinstance(d, dict):
            return []
        if event == "ChatMessageEvent":
            s = d.get("sender") or {}
            ident = s.get("identity") or {}
            text, emotes = self._text(d.get("content"))
            if not text.strip():
                return []
            badges = []
            for b in ident.get("badges") or []:
                k = self.BADGES.get(str((b or {}).get("type", "")))
                if k and k not in badges:
                    badges.append(k)
            color = ident.get("color") if isinstance(ident.get("color"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", ident.get("color")) else ""
            item = {"src": "kick", "type": "msg", "name": self._clean(s.get("username"), 40), "color": color, "text": text, "emotes": emotes, "badges": badges,
                    "mid": str(d.get("id", ""))[:60]}
            try:
                item["ts"] = calendar.timegm(time.strptime(str(d.get("created_at"))[:19], "%Y-%m-%dT%H:%M:%S"))
            except (ValueError, OverflowError):
                pass
            return [item]
        if event == "MessageDeletedEvent":
            mid = str(((d.get("message") or {}).get("id")) or d.get("id") or "")[:60]
            return [{"type": "del", "meta": True, "mid": mid, "text": "", "emotes": [], "src": "kick"}] if mid else []
        if event == "ChatroomClearEvent":
            return [{"type": "clear", "meta": True, "uid": "", "seconds": 0, "text": "", "emotes": [], "src": "kick"}]
        return []
