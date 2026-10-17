"""IRL4YOU BOX Twitch: Chat-Nachrichten senden."""

import threading
import time

from .irc import TwitchChat, _ascii_digits


class TwitchSender:
    COMMANDS = ("ban", "timeout", "unban")
    NAMED = ("vip", "unvip", "mod", "unmod", "raid")
    PLAIN = ("clear", "slowoff", "followersoff", "subscribers", "subscribersoff", "emoteonly", "emoteonlyoff", "unraid")
    NUMBER = ("slow", "followers")
    TEXT = ("announce", "title", "game")
    HELP = ("Befehle: /ban, /timeout, /unban, /vip, /unvip, /mod, /unmod, /clear, /slow, /slowoff, /followers, /followersoff, /subscribers, /subscribersoff, "
            "/emoteonly, /emoteonlyoff, /announce, /raid, /unraid, /marker, /title, /game")
    MIN_GAP = 1.0

    def __init__(self, store, chat=None, clock=time.monotonic, demo_reader=None, mod=None, helix=None):
        self.store, self.chat, self.clock, self.mod, self.helix = store, chat or TwitchChat(), clock, mod, helix
        self.demo_reader = demo_reader
        self.last = -1e9
        self.lock = threading.Lock()

    def _command(self, t, owner_key=None, mod=None):
        mod = mod or self.mod
        parts = t[1:].split()
        cmd = parts[0].lower() if t[0] == "/" and parts else ""
        known = self.COMMANDS + self.NAMED + self.PLAIN + self.NUMBER + self.TEXT + ("marker",)
        if cmd not in known or mod is None:
            raise ValueError(self.HELP)
        if cmd in self.COMMANDS + self.NAMED + self.TEXT and len(parts) < 2:
            raise ValueError(self.HELP)
        with self.lock:
            now = self.clock()
            if now - self.last < self.MIN_GAP:
                raise ValueError("Bitte kurz warten")
            self.last = now
        if cmd in self.COMMANDS:
            req = {"action": cmd, "user": parts[1]}
            rest = parts[2:]
            if cmd == "timeout" and rest and _ascii_digits(rest[0]):
                req["seconds"] = int(rest[0])
                rest = rest[1:]
            if cmd != "unban" and rest:
                req["reason"] = " ".join(rest)
            out = mod.do(req, owner_key)
            return {"ok": True, "message": "%s: %s" % (out.get("message", ""), parts[1].lstrip("@"))}
        req = {"action": cmd}
        if cmd in self.NAMED:
            req["user"] = parts[1]
        elif cmd in self.NUMBER and len(parts) > 1:
            if not _ascii_digits(parts[1]):
                raise ValueError("Die Zahl ist ungültig")
            req["number"] = int(parts[1])
        elif cmd in self.TEXT or cmd == "marker":
            req["text"] = " ".join(parts[1:])
        out = mod.do(req, owner_key)
        who = ": " + parts[1].lstrip("@") if cmd in self.NAMED else ""
        return {"ok": True, "message": out.get("message", "") + who}

    def say_as(self, mod, helix, text, owner_key=None, commands=True):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Nachricht fehlt")
        t = text.strip()
        if t[0] in "/.":
            if not commands:
                raise ValueError("Befehle gibt es nur für den Streamer und Moderatoren")
            return self._command(t, owner_key, mod)
        if not helix.account.ready():
            raise ValueError("Zuerst mit Twitch anmelden")
        with self.lock:
            now = self.clock()
            if now - self.last < self.MIN_GAP:
                raise ValueError("Bitte kurz warten")
            self.last = now
        if self.demo_reader is not None:
            self.demo_reader._add({"type": "msg", "name": helix.account.login(), "color": "#9146FF", "text": TwitchChat.clean_text(t) or "", "emotes": []})
            return {"ok": True, "message": TwitchChat.OK}
        t = TwitchChat.clean_text(t)
        if not t:
            raise ValueError("Nachricht ungültig")
        if not helix.usable():
            raise ValueError("Für das Schreiben fehlt ein Recht: bitte neu anmelden")
        return {"ok": True, "message": helix.send(self.store.channel_name(), t)}

    def say(self, text, owner_key=None):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Nachricht fehlt")
        t = text.strip()
        if t[0] in "/.":
            return self._command(t, owner_key)
        cfg = self.store.settings()
        if not (cfg["login"] and cfg["token"] and cfg["channel"]):
            raise ValueError("Zuerst mit Twitch anmelden")
        with self.lock:
            now = self.clock()
            if now - self.last < self.MIN_GAP:
                raise ValueError("Bitte kurz warten")
            self.last = now
        if self.demo_reader is not None:
            self.demo_reader._add({"type": "msg", "name": cfg["login"], "color": "#9146FF", "text": TwitchChat.clean_text(t) or "", "emotes": []})
            return {"ok": True, "message": TwitchChat.OK}
        t = TwitchChat.clean_text(t)
        if not t:
            raise ValueError("Nachricht ungültig")
        if self.helix is not None and self.helix.usable():
            return {"ok": True, "message": self.helix.send(cfg["channel"], t)}
        ok, msg = self.chat.send(cfg["login"], cfg["token"], cfg["channel"], t)
        if not ok:
            raise ValueError(msg)
        return {"ok": True, "message": msg}
