"""IRL4YOU BOX YouTube: öffentlichen Livechat ohne Anmeldung lesen.

Der Nutzer trägt nur seinen Kanal ein (@name, Kanal-Link oder UC-Kennung). Die Box ruft die öffentliche Livechat-Seite von YouTube auf (wie ein Browser ohne
Konto), findet den laufenden Stream des Kanals selbst, holt dessen Chat und sucht nach dem Ende automatisch den nächsten Stream. Es gibt keine Anmeldung, keine
Google-Zugangsdaten und keine Moderation. Das ist eine inoffizielle Schnittstelle von YouTube und kann sich ändern.
"""

import collections
import json
import os
import re
import threading
import time
import urllib.parse

from twitch.irc import ChatPaths


class YoutubePublic:
    HOST = "https://www.youtube.com"
    UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    COOKIE = "SOCS=CAI; CONSENT=YES+cb"
    FIND_EVERY = 45.0
    MIN_POLL, MAX_POLL = 2.5, 10.0
    FIRST_KEEP = 25
    PAGE_LIMIT = 4_000_000
    HANDLE_RE = re.compile(r"@[A-Za-z0-9._-]{3,60}")
    CHAN_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")
    VIDEO_RE = re.compile(r"[A-Za-z0-9_-]{11}")
    BADGE_ICONS = {"OWNER": "broadcaster", "MODERATOR": "moderator"}

    def __init__(self, path, reader, paths=None, clock=time.monotonic, sleep=time.sleep):
        self.path, self.reader = path, reader
        self.paths = paths or ChatPaths()
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.thread, self.gen = None, 0
        self.state, self.error, self.title = "aus", "", ""
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
        """'@name', Kanal-Link oder UC-Kennung -> '@name' oder 'UC…'; leer bei Ungültigem."""
        t = str(text or "").strip()
        if not t:
            return ""
        if "/" in t or "." in t.split("@")[0]:
            u = urllib.parse.urlsplit(t if "//" in t else "https://" + t)
            host = (u.hostname or "").lower()
            if host not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
                return ""
            parts = [p for p in u.path.split("/") if p]
            if parts and parts[0].startswith("@"):
                t = parts[0]
            elif len(parts) >= 2 and parts[0] == "channel":
                t = parts[1]
            else:
                return ""
        if t.startswith("@") and cls.HANDLE_RE.fullmatch(t):
            return t
        if cls.CHAN_RE.fullmatch(t):
            return t
        if cls.HANDLE_RE.fullmatch("@" + t):
            return "@" + t
        return ""

    def set_channel(self, text):
        norm = self.normalize(text)
        if text and not norm:
            raise ValueError("Kanal: @name, der Link zum Kanal oder die Kanal-Kennung (beginnt mit UC)")
        with self.lock:
            self.channel = norm
            self.gen += 1
            self.state, self.error, self.title = ("aus" if not norm else "verbinde"), "", ""
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"channel": norm}, f)
            os.replace(tmp, self.path)

    def ready(self):
        return bool(self.channel)

    def status(self):
        with self.lock:
            return {"state": self.state, "error": self.error, "title": self.title, "channel": self.channel, "mod": False}

    def ensure(self):
        with self.lock:
            if not self.channel or (self.thread is not None and self.thread.is_alive()):
                return
            self.gen += 1
            gen = self.gen
            self.state = "verbinde"
            t = threading.Thread(target=self._run, args=(gen,), daemon=True)
            self.thread = t
        t.start()

    def _mine(self, gen):
        return self.gen == gen and bool(self.channel) and not self.reader._idle()

    def _set(self, state, error="", title=None):
        with self.lock:
            self.state, self.error = state, error
            if title is not None:
                self.title = title

    def _nap(self, seconds, gen):
        end = self.clock() + seconds
        while self.clock() < end and self._mine(gen):
            self.sleep(min(1.0, max(0.0, end - self.clock())))

    def _fetch(self, method, url, body=None, hops=4):
        hdr = {"User-Agent": self.UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8", "Cookie": self.COOKIE}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            hdr.update({"Content-Type": "application/json", "Origin": self.HOST, "X-Origin": self.HOST})
        for _ in range(hops + 1):
            rh = {}
            st, raw = self.paths.request(method, url, data, hdr, limit=self.PAGE_LIMIT, once=True, rh=rh)
            if st in (301, 302, 303, 307, 308) and rh.get("location"):
                nxt = urllib.parse.urljoin(url, rh["location"])
                if urllib.parse.urlsplit(nxt).hostname not in ("www.youtube.com", "youtube.com", "m.youtube.com"):
                    return -2, ""
                url = nxt
                if st == 303:
                    method, data = "GET", None
                continue
            return st, raw.decode("utf-8", "replace")
        return -1, ""

    def find(self):
        """(Video-Kennung, Titel) des gerade laufenden Streams des Kanals oder (None, "")."""
        path = self.channel if self.channel.startswith("@") else "channel/" + self.channel
        st, html = self._fetch("GET", self.HOST + "/" + path + "/live")
        if st != 200:
            raise OSError(st)
        m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"', html)
        if not m or not ('"isLiveNow":true' in html or '"isLive":true' in html):
            return None, ""
        t = re.search(r'<meta name="title" content="([^"]*)"', html)
        import html as htmlmod
        return m.group(1), (htmlmod.unescape(t.group(1)) if t else "")[:100]

    @staticmethod
    def _cont(node):
        for c in (node or {}).get("continuations") or []:
            for k in ("invalidationContinuationData", "timedContinuationData", "reloadContinuationData"):
                d = c.get(k)
                if isinstance(d, dict) and isinstance(d.get("continuation"), str):
                    return d["continuation"], d.get("timeoutMs")
        return "", None

    def open_chat(self, video):
        """(API-Schlüssel der Seite, Client-Version, erste Fortsetzung, erste Aktionen)."""
        st, html = self._fetch("GET", self.HOST + "/live_chat?is_popout=1&v=" + video)
        if st != 200:
            raise OSError(st)
        key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
        ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', html) or re.search(r'"clientVersion":"([^"]+)"', html)
        m = re.search(r'ytInitialData"?\]?\s*=\s*(\{.+?\})\s*;\s*</script>', html, re.S)
        if not (key and ver and m):
            raise OSError(-3)
        data = json.loads(m.group(1))
        node = (data.get("contents") or {}).get("liveChatRenderer") or {}
        cont, _ = self._cont(node)
        if not cont:
            raise OSError(-3)
        return key.group(1), ver.group(1), cont, node.get("actions") or []

    def _run(self, gen):
        video, key, ver, cont, first, actions = None, "", "", "", True, []
        while self._mine(gen):
            wait = None
            try:
                if not video:
                    video, title = self.find()
                    if not video:
                        self._set("kein-stream", "")
                        self._nap(self.FIND_EVERY, gen)
                        continue
                    key, ver, cont, actions = self.open_chat(video)
                    first = True
                    self._set("ok", "", title)
                else:
                    body = {"context": {"client": {"hl": "de", "gl": "DE", "clientName": "WEB", "clientVersion": ver}}, "continuation": cont}
                    st, text = self._fetch("POST", self.HOST + "/youtubei/v1/live_chat/get_live_chat?prettyPrint=false&key=" + urllib.parse.quote(key), body)
                    if st in (400, 404, 410):
                        video = None
                        self._nap(10.0, gen)
                        continue
                    if st != 200:
                        raise OSError(st)
                    node = (json.loads(text).get("continuationContents") or {}).get("liveChatContinuation") or {}
                    actions = node.get("actions") or []
                    cont, _ = self._cont(node)
                    if not cont:           # Chat beendet
                        video = None
                        self._set("kein-stream", "")
                        self._nap(15.0, gen)
                        continue
                    wait = self._cont(node)[1]
                if first and len(actions) > self.FIRST_KEEP:
                    actions = actions[-self.FIRST_KEEP:]
                first = False
                for a in actions:
                    for m in self.parse(a):
                        self.reader._add(m)
                try:
                    wait = float(wait) / 1000.0
                except (TypeError, ValueError):
                    wait = 5.0
                self._nap(max(self.MIN_POLL, min(self.MAX_POLL, wait)), gen)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                self._set("fehler", "Keine Verbindung zu YouTube")
                if first and video:
                    video = None
                self._nap(15.0, gen)
        with self.lock:
            if self.gen == gen:
                self.state = "aus"

    @staticmethod
    def _clean(text, limit):
        out = "".join(" " if ord(c) < 32 else c for c in str(text or ""))
        return " ".join(out.split())[:limit]

    @classmethod
    def _runs(cls, node, limit=500):
        out = []
        for r in (node or {}).get("runs") or []:
            if "text" in r:
                out.append(str(r["text"]))
            elif isinstance(r.get("emoji"), dict):
                e = r["emoji"]
                sc = (e.get("shortcuts") or [""])[0]
                out.append(sc if e.get("isCustomEmoji") else str(e.get("emojiId") or sc))
        return cls._clean("".join(out), limit)

    def parse(self, action):
        """Eine Aktion der Chat-Antwort als Einträge der Box (0, 1 oder mehr)."""
        if not isinstance(action, dict):
            return []
        d = action.get("markChatItemAsDeletedAction")
        if d:
            gone = str(d.get("targetItemId", ""))[:200]
            return [{"type": "del", "meta": True, "mid": gone, "text": "", "emotes": [], "src": "youtube"}] if gone else []
        d = action.get("markChatItemsByAuthorAsDeletedAction")
        if d:
            ch = str(d.get("externalChannelId", ""))[:60]
            return [{"type": "clear", "meta": True, "uid": ch, "seconds": 0, "text": "", "emotes": [], "src": "youtube"}] if ch else []
        item = (action.get("addChatItemAction") or {}).get("item") or {}
        for kind, r in item.items():
            if not isinstance(r, dict):
                continue
            mid = str(r.get("id", ""))[:200]
            if mid and mid in self.seen:
                return []
            if mid:
                self.seen.append(mid)
            name = self._clean((r.get("authorName") or {}).get("simpleText"), 40)
            ch = str(r.get("authorExternalChannelId", ""))[:60]
            base = {"src": "youtube", "emotes": []}
            try:
                base["ts"] = int(r.get("timestampUsec")) // 1_000_000
            except (TypeError, ValueError):
                pass
            if kind == "liveChatTextMessageRenderer":
                text = self._runs(r.get("message"))
                badges = []
                for b in r.get("authorBadges") or []:
                    br = b.get("liveChatAuthorBadgeRenderer") or {}
                    icon = (br.get("icon") or {}).get("iconType")
                    if icon in self.BADGE_ICONS:
                        badges.append(self.BADGE_ICONS[icon])
                    elif br.get("customThumbnail"):
                        badges.append("subscriber")
                extra = {"uid": ch, "login": name} if self.CHAN_RE.fullmatch(ch) else {}
                return [dict(base, type="msg", name=name, color="", text=text, badges=badges, mid=mid, **extra)] if text else []
            if kind in ("liveChatPaidMessageRenderer", "liveChatPaidStickerRenderer"):
                amount = self._clean((r.get("purchaseAmountText") or {}).get("simpleText"), 30)
                head = ("Super Chat " if kind == "liveChatPaidMessageRenderer" else "Super Sticker ") + amount
                text = self._runs(r.get("message"))
                return [dict(base, type="notice", name="", color="", text=head + (" – " + name if name else "") + (": " + text if text else ""))]
            if kind == "liveChatMembershipItemRenderer":
                sub = self._runs(r.get("headerSubtext"), 200)
                return [dict(base, type="sub", name="", color="", text=(name + ": " if name else "") + (sub or "Neues Mitglied"))]
        return []
