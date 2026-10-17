"""IRL4YOU BOX Twitch: Konten und Moderator-Sitzungen."""

import os
import threading
import time

from .login import TwitchLogin, TwitchModLogin


class ModSessions:
    MAX = 12

    def __init__(self, state_dir, demo=False, paths=None, id_base=None, client_id=None, clock=time.time, sleep=time.sleep):
        self.dir, self.demo, self.paths = state_dir, demo, paths
        self.kw = {"clock": clock, "sleep": sleep}
        if id_base:
            self.kw["id_base"] = id_base
        if client_id:
            self.kw["client_id"] = client_id
        self.items = {}
        self.lock = threading.Lock()

    def _path(self, h):
        return os.path.join(self.dir, "twitch-mod-%s.json" % h[:32])

    def _make(self, h):
        return TwitchModLogin(self._path(h), demo=self.demo, paths=self.paths, **self.kw)

    def _count(self):
        try:
            return len([n for n in os.listdir(self.dir) if n.startswith("twitch-mod-") and n.endswith(".json")])
        except OSError:
            return 0

    def get(self, key):
        h = TwitchLogin.owner_hash(key)
        if not h:
            return None
        with self.lock:
            s = self.items.get(h)
            if s is None and os.path.exists(self._path(h)):
                s = self.items[h] = self._make(h)
            return s

    def start(self, key, mod=True):
        h = TwitchLogin.owner_hash(key)
        if not h:
            raise ValueError("Dieser Browser kann sich nicht anmelden")
        with self.lock:
            s = self.items.get(h)
            if s is None:
                if self._count() >= self.MAX and not os.path.exists(self._path(h)):
                    raise ValueError("Es sind schon zu viele Moderatoren angemeldet")
                s = self.items[h] = self._make(h)
        return s.start(mod=bool(mod), owner_key=key)

    def logout(self, key):
        s = self.get(key)
        if s is not None:
            s.logout()
        h = TwitchLogin.owner_hash(key)
        if h:
            with self.lock:
                self.items.pop(h, None)
            try:
                os.remove(self._path(h))
            except OSError:
                pass



class TwitchAccounts:
    NONE_STATUS = {"state": "aus", "login": "", "scopes": [], "error": "", "mod": False, "mod_scope": False, "events": False, "helix_chat": False}
    CHECK_TTL = 300.0

    def __init__(self, box, sessions, check=None, clock=time.time, store=None):
        self.box, self.sessions, self.check, self.clock, self.store = box, sessions, check, clock, store
        self.known = {}
        self.lock = threading.Lock()

    def _is_channel_mod(self, acct):
        if self.check is None:
            return None
        uid = acct.user_id()
        now = self.clock()
        with self.lock:
            hit = self.known.get(uid)
            if hit and now - hit[0] < self.CHECK_TTL:
                return hit[1]
        try:
            ans = self.check(uid)
        except Exception:
            ans = None
        with self.lock:
            if len(self.known) > 100:
                self.known.clear()
            self.known[uid] = (now, ans)
        return ans

    def streamer_name(self):
        name = self.box.login()
        if name:
            return name
        if self.store is not None:
            with self.store.lock:
                return str(self.store.data.get("channel") or "").lower()
        return ""

    def pick(self, key):
        if self.box.ready():
            if self.box.is_owner(key):
                return "owner", self.box
        elif not self.streamer_name():
            return "owner", self.box
        s = self.sessions.get(key)
        if s is not None and self.sessions.demo:
            s.status()
        if s is not None and s.ready():
            if s.status()["mod"] and self._is_channel_mod(s) is not False:
                return "mod", s
            return "user", s
        return "none", None

    def status(self, key):
        role, acct = self.pick(key)
        boxlogin = self.box.login()
        if role == "owner":
            st = self.box.status()
        elif role in ("mod", "user"):
            st = acct.status()
            if role == "user":
                st["mod"] = False
        else:
            h = TwitchLogin.owner_hash(key)
            s = self.sessions.get(key)
            st = dict(self.NONE_STATUS, scopes=[])
            if s is not None and s.state != "aus":
                own = s.status()
                st.update({k: own[k] for k in ("state", "error", "code", "uri", "expires_in") if k in own})
            elif h and self.box.state == "wartet" and (self.box.pending or {}).get("owner") == h:
                own = self.box.status()
                st.update({k: own[k] for k in ("state", "code", "uri", "expires_in") if k in own})
            cf = self.box.claim_fail
            if cf and h and cf.get("owner") == h and st["state"] != "wartet":
                st["state"], st["error"] = "fehler", cf["error"]
        name = self.streamer_name()
        st["role"], st["box_login"], st["streamer"] = role, boxlogin, name
        st["need_channel"] = bool(role == "owner" and not self.box.ready() and not name)
        return st
