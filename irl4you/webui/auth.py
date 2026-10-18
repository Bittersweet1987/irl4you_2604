"""IRL4YOU BOX Oberfläche: Anmeldung an der Oberfläche (eigenes Passwort, bcrypt-Hash, Sitzungen)."""

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import threading
import time


SESSION_SECONDS = 12 * 3600


REMEMBER_SECONDS = 30 * 24 * 3600


MAX_FAILS, FAIL_WINDOW = 5, 300


MAX_CHECKS = 2


class Auth:

    DEMO_PASSWORD = "demo"

    def __init__(self, state_dir, demo=False):
        self.demo = bool(demo)
        self.dir = state_dir
        self.path = os.path.join(state_dir, "auth.json")
        self.sessions = {}
        self.store_path = os.path.join(state_dir, "sessions.json")
        self.fails = {}
        self.lock = threading.Lock()
        self.checks = threading.BoundedSemaphore(MAX_CHECKS)
        os.makedirs(state_dir, exist_ok=True)
        self.cfg = None
        try:
            with open(self.path) as f:
                self.cfg = json.load(f)
        except (OSError, ValueError):
            pass
        if self.demo:
            salt = secrets.token_bytes(16)
            self.cfg = {"salt": salt.hex(), "hash": self._hash(self.DEMO_PASSWORD, salt).hex()}

    def _cred(self):
        h = self.own_bcrypt() or ("demo" if self.demo else (self.cfg or {}).get("hash")) or ""
        return hashlib.sha256(("pbcred:" + h).encode()).hexdigest()

    @staticmethod
    def _tok_id(tok):
        return hashlib.sha256(tok.encode()).hexdigest()

    def _remembered(self):
        try:
            with open(self.store_path) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def _save_remembered(self, d):
        tmp = self.store_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(d, f)
        os.replace(tmp, self.store_path)

    def own_bcrypt(self):
        h = (self.cfg or {}).get("bcrypt")
        return h if isinstance(h, str) and h.startswith("$2") else None

    @staticmethod
    def bcrypt_ok(pw, h):
        try:
            import bcrypt
        except ImportError:
            raise RuntimeError("Passwortprüfung nicht möglich (python3-bcrypt fehlt)")
        try:
            return bcrypt.checkpw(pw.encode("utf-8"), h.encode("ascii"))
        except (ValueError, TypeError):
            raise RuntimeError("Passwortprüfung nicht möglich")

    @property
    def mode(self):
        return "demo" if self.demo and self.cfg and not self.own_bcrypt() else "own"

    @property
    def configured(self):
        return bool(self.cfg)

    @property
    def setup_needed(self):
        return not self.configured and self.mode == "own"

    @staticmethod
    def _hash(pw, salt):
        return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 300000, dklen=32)

    def throttled(self, ip):
        now = time.time()
        with self.lock:
            f = [t for t in self.fails.get(ip, []) if now - t < FAIL_WINDOW]
            self.fails[ip] = f
            return len(f) >= MAX_FAILS

    def fail(self, ip):
        with self.lock:
            self.fails.setdefault(ip, []).append(time.time())

    def reserve(self, ip):
        now = time.time()
        with self.lock:
            f = [t for t in self.fails.get(ip, []) if now - t < FAIL_WINDOW]
            if len(f) >= MAX_FAILS:
                self.fails[ip] = f
                return None
            f.append(now)
            self.fails[ip] = f
            return now

    def unreserve(self, ip, mark):
        with self.lock:
            f = self.fails.get(ip, [])
            if mark in f:
                f.remove(mark)

    def check_password(self, ip, verify):
        mark = self.reserve(ip)
        if mark is None:
            raise PermissionError("Zu viele Versuche, bitte 5 Minuten warten")
        if not self.checks.acquire(blocking=False):
            self.unreserve(ip, mark)
            raise PermissionError("Die Box prüft gerade andere Anmeldungen, bitte gleich noch einmal versuchen")
        try:
            good = verify()
        except BaseException:
            self.unreserve(ip, mark)
            raise
        finally:
            self.checks.release()
        if good:
            self.unreserve(ip, mark)
        return good

    TAILSCALE = ipaddress.ip_network("100.64.0.0/10")

    @classmethod
    def local_ip(cls, ip):
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        a = getattr(a, "ipv4_mapped", None) or a
        return a.is_private or a.is_loopback or a.is_link_local or a in cls.TAILSCALE

    def set_password(self, pw, ip):
        if not self.local_ip(ip):
            raise ValueError("Die Ersteinrichtung ist nur aus dem lokalen Netz möglich")
        with self.lock:
            if not self.setup_needed:
                raise ValueError("Passwort ist schon gesetzt")
            if len(pw or "") < 10:
                raise ValueError("Passwort: mindestens 10 Zeichen")
            salt = secrets.token_bytes(16)
            cfg = {"salt": salt.hex(), "hash": self._hash(pw, salt).hex()}
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(cfg, f)
            os.replace(tmp, self.path)
            self.cfg = cfg

    def change_password(self, old, new, ip):
        if self.mode != "own" or self.demo:
            raise ValueError("Das Passwort wird hier nicht verwaltet" if not self.demo else "In der Vorschau nicht möglich")
        if not isinstance(new, str) or len(new) < 10:
            raise ValueError("Neues Passwort: mindestens 10 Zeichen")
        if len(new.encode("utf-8")) > 72:
            raise ValueError("Neues Passwort: höchstens 72 Byte")
        bh = self.own_bcrypt()
        if bh:
            verify = lambda: self.bcrypt_ok(old or "", bh)
        else:
            verify = lambda: hmac.compare_digest(self._hash(old or "", bytes.fromhex(self.cfg["salt"])), bytes.fromhex(self.cfg["hash"]))
        if not self.check_password(ip, verify):
            raise ValueError("Bisheriges Passwort falsch")
        salt = secrets.token_bytes(16)
        cfg = {"salt": salt.hex(), "hash": self._hash(new, salt).hex()}
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f)
        os.replace(tmp, self.path)
        with self.lock:
            self.cfg = cfg
            self.sessions = {}
            try:
                self._save_remembered({})
            except OSError:
                pass

    def login(self, pw, ip, remember=False):
        if not self.configured:
            raise ValueError("Noch kein Passwort gesetzt")
        bh = self.own_bcrypt()
        if bh:
            verify = lambda: self.bcrypt_ok(pw or "", bh)
        else:
            verify = lambda: hmac.compare_digest(self._hash(pw or "", bytes.fromhex(self.cfg["salt"])), bytes.fromhex(self.cfg["hash"]))
        if not self.check_password(ip, verify):
            raise ValueError("Passwort falsch")
        tok = secrets.token_urlsafe(32)
        with self.lock:
            now = time.time()
            self.sessions = {t: e for t, e in self.sessions.items() if e > now}
            self.sessions[tok] = now + SESSION_SECONDS
            if remember:
                keep = {k: v for k, v in self._remembered().items()
                        if isinstance(v, list) and len(v) == 2 and v[0] > now and v[1] == self._cred()}
                keep[self._tok_id(tok)] = [now + REMEMBER_SECONDS, self._cred()]
                try:
                    self._save_remembered(keep)
                except OSError:
                    pass
        return tok

    def valid(self, tok):
        if not tok:
            return False
        with self.lock:
            if self.sessions.get(tok, 0) > time.time():
                return True
            e = self._remembered().get(self._tok_id(tok))
            return bool(isinstance(e, list) and len(e) == 2 and e[0] > time.time() and e[1] == self._cred())

    def logout(self, tok):
        with self.lock:
            self.sessions.pop(tok or "", None)
            r = self._remembered()
            if r.pop(self._tok_id(tok or ""), None) is not None:
                try:
                    self._save_remembered(r)
                except OSError:
                    pass
