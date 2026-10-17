#!/usr/bin/env python3
"""Update-Helfer von IRL4YOU (Ubuntu 26.04). Die Box folgt den Commits des eigenen GitHub-Repositorys (Zweig main).

Aufruf (nur als root, über systemd):
  irl4you-update check           neuesten Commit ermitteln, nichts installieren
  irl4you-update install [SHA]   neuesten Commit des Zweigs (nur wenn neu) oder genau den Commit SHA installieren
  irl4you-update rollback        zurück auf die vorher aktive Version
  irl4you-update auto            für den Timer: prüfen und, wenn in der Konfig erlaubt, installieren
  irl4you-update request         für die .path-Einheit: Stichwort aus der Anfragedatei der Oberfläche ausführen
  irl4you-update status          Status als JSON ausgeben

Version = Commit. Eine Version heißt auf der Box wie die ersten 12 Zeichen ihres Commit-Hashes; die Datei VERSION im
Repository ist nur der Anzeigename.

Ablauf beim Installieren:
  1. nie während einer Übertragung,
  2. Zweig abfragen (Commit-Hash kommt per HTTPS von der GitHub-API), neuester Stand nur, wenn seine Prüfungen (CI) grün sind,
  3. Tarball genau dieses Commits laden (Größe begrenzt), streng entpacken (nur Dateien, Ordner und Verweise innerhalb),
  4. jede Datei gegen den Git-Baum des Commits prüfen (Blob-Hash, keine fehlenden und keine zusätzlichen Dateien),
  5. daraus das Paket zusammensetzen (irl4you/ + release/hooks + updater/) nach releases/<id>, Manifest prüfen,
  6. Verweis "current" (und optional /opt/pipbox) atomar auf die neue Version umhängen,
  7. hooks/install der neuen Version ausführen, Dienste neu starten, Gesundheit prüfen,
  8. bei einem Fehler: Verweis zurück, hooks/install der alten Version, Dienste neu starten.

Die Oberfläche kann nur Stichwörter aus einer festen Liste anfordern (check, install, rollback, switch <SHA>).
Quelle, Zugangsschlüssel und Pfade stehen ausschließlich in der Konfig-Datei, die nur root ändern kann.
"""
import configparser
import datetime
import fcntl
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

UPDATER_API = 2                     # Stand dieses Helfers; ein Paket kann im Manifest "min_updater" verlangen
CONFIG = os.environ.get("IRL4YOU_UPDATE_CONF", "/etc/irl4you/update.conf")
VERSION_RE = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}(-[a-z0-9.]{1,20})?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_RE = re.compile(r"^[0-9a-f]{7,40}$")
ID_RE = re.compile(r"^[0-9a-f]{12}$")
MODES = ("check", "install", "rollback", "switch")
USER_AGENT = "irl4you-update/%d" % UPDATER_API

DEFAULTS = {
    "repo": "Bittersweet1987/irl4you_2604",
    "api": "https://api.github.com",
    "branch": "main",
    "require_ci": "true",                           # nur Commits installieren, deren Prüfungen (GitHub Actions) grün sind
    "token_file": "/etc/irl4you/update-token",      # optional, nur für ein privates Repository
    "auto_install": "false",                        # der Timer installiert nur, wenn hier true steht
    "root": "/opt/irl4you",                         # enthält releases/<id> und den Verweis current
    "extra_link": "/opt/pipbox",                    # zusätzlicher Verweis auf die aktive Version (leer: keiner)
    "state_dir": "/var/lib/irl4you",
    "status_file": "/run/pipbox-swupdate/status.json",
    "request_file": "/var/lib/pipbox/swupdate-request",
    "log_file": "/var/log/irl4you-update.log",
    "keep": "3",                                    # so viele Versionen bleiben auf der Box (aktive und vorherige immer)
    "max_download_mb": "512",
    "min_free_mb": "1024",
    "busy_processes": "irl4you-encoder belacoder",
    "busy_units": "pipbox-send.service",
    "systemctl": "systemctl",
    "hook_timeout": "900",
    "health_timeout": "120",                        # so lange dürfen die Dienste aus health_units zum Starten brauchen
    "ci_grace_minutes": "10",                       # ohne jede Prüfung gilt ein Commit nach so langer Zeit als "keine CI vorhanden"
    "allow_insecure_api": "false",                  # nur für Tests: http:// statt https:// erlauben
}


class Refuse(Exception):
    """Ein erwarteter Grund, nicht weiterzumachen. Die Meldung geht so an die Oberfläche."""


def short(sha):
    return (sha or "")[:7]


class Config:
    def __init__(self, path=CONFIG, overrides=None):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read_dict({"update": DEFAULTS})
        if path and os.path.exists(path):
            cp.read(path, encoding="utf-8")
        if overrides:
            cp.read_dict({"update": {k: str(v) for k, v in overrides.items()}})
        s = cp["update"]
        self.repo = s["repo"].strip()
        if not re.match(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$", self.repo):
            raise Refuse("Ungültige Angabe repo in der Konfig")
        self.api = s["api"].strip().rstrip("/")
        self.insecure = s.getboolean("allow_insecure_api")
        if not self.api.startswith("https://") and not self.insecure:
            raise Refuse("Die Update-Quelle muss HTTPS sein")
        self.branch = s["branch"].strip()
        if not re.match(r"^[A-Za-z0-9_./-]{1,100}$", self.branch) or ".." in self.branch:
            raise Refuse("Ungültige Angabe branch in der Konfig")
        self.require_ci = s.getboolean("require_ci")
        self.token_file = s["token_file"].strip()
        self.auto_install = s.getboolean("auto_install")
        self.root = s["root"].strip()
        self.extra_link = s["extra_link"].strip()
        self.state_dir = s["state_dir"].strip()
        self.status_file = s["status_file"].strip()
        self.request_file = s["request_file"].strip()
        self.log_file = s["log_file"].strip()
        self.keep = max(2, s.getint("keep"))
        self.max_download = s.getint("max_download_mb") * 1024 * 1024
        self.min_free = s.getint("min_free_mb") * 1024 * 1024
        self.busy_processes = s["busy_processes"].split()
        self.busy_units = s["busy_units"].split()
        self.systemctl = s["systemctl"].split()
        self.hook_timeout = s.getint("hook_timeout")
        self.health_timeout = s.getint("health_timeout")
        self.ci_grace = s.getint("ci_grace_minutes") * 60

    @property
    def releases(self):
        return os.path.join(self.root, "releases")

    @property
    def current(self):
        return os.path.join(self.root, "current")

    def token(self):
        """Zugangsschlüssel nur aus einer Datei, die niemand außer root lesen kann."""
        if not self.token_file:
            return ""
        try:
            st = os.stat(self.token_file)
        except OSError:
            return ""
        if st.st_mode & 0o077:
            raise Refuse("Die Schlüsseldatei darf nur für root lesbar sein (chmod 600)")
        with open(self.token_file, encoding="utf-8") as f:
            return f.read().strip()


class _NoAuthOnForeignRedirect(urllib.request.HTTPRedirectHandler):
    """Downloads leiten auf einen anderen Rechner um (codeload.github.com). Dorthin darf der Schlüssel nicht mit."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old_host = urllib.parse.urlsplit(req.full_url).netloc
        if urllib.parse.urlsplit(newurl).netloc != old_host:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        if not newurl.startswith("https://") and not getattr(req, "_irl4you_insecure", False):
            raise Refuse("Umleitung auf eine Adresse ohne HTTPS abgelehnt")
        new._irl4you_insecure = getattr(req, "_irl4you_insecure", False)
        return new


class Updater:
    def __init__(self, cfg, now=time.time, sleep=time.sleep):
        self.cfg = cfg
        self.now = now
        self.sleep = sleep
        self.opener = urllib.request.build_opener(_NoAuthOnForeignRedirect())
        self.skipped = set()                    # Dienste aus dem Manifest, die auf der Box (noch) fehlen

    # ---------- Protokoll und Status ----------

    def log(self, msg):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
        print(line, flush=True)
        try:
            p = self.cfg.log_file
            if os.path.exists(p) and os.path.getsize(p) > 400_000:
                with open(p, "rb") as f:
                    f.seek(-200_000, 2)
                    f.readline()
                    keep = f.read()
                with open(p, "wb") as f:
                    f.write(keep)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def load_status(self):
        try:
            with open(self.cfg.status_file, encoding="utf-8") as f:
                s = json.load(f)
            return s if isinstance(s, dict) else {}
        except (OSError, ValueError):
            return {}

    def status(self, **kw):
        d = os.path.dirname(self.cfg.status_file)
        os.makedirs(d, mode=0o755, exist_ok=True)
        s = self.load_status()
        s.update(kw)
        s["time"] = int(self.now())
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".status-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(s, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.cfg.status_file)
        return s

    # ---------- Zustand auf der Box ----------

    def active_id(self):
        try:
            target = os.readlink(self.cfg.current)
        except OSError:
            return None
        v = os.path.basename(target.rstrip("/"))
        return v if ID_RE.match(v) else None

    def manifest_of(self, rid):
        try:
            with open(os.path.join(self.cfg.releases, rid, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
            return m if isinstance(m, dict) else {}
        except (OSError, ValueError):
            return {}

    def active_commit(self):
        rid = self.active_id()
        return self.manifest_of(rid).get("commit") if rid else None

    def label(self, rid):
        """Anzeigename: 'VERSION (Commit)'."""
        if not rid:
            return "-"
        v = self.manifest_of(rid).get("version")
        return "%s (%s)" % (v, rid[:7]) if v else rid[:7]

    def installed_versions(self):
        """Ids der vorhandenen Versionen, zuletzt eingerichtete zuerst."""
        try:
            names = os.listdir(self.cfg.releases)
        except OSError:
            return []
        out = []
        for n in names:
            p = os.path.join(self.cfg.releases, n, "manifest.json")
            if ID_RE.match(n) and os.path.isfile(p):
                out.append((os.stat(p).st_mtime, n))
        return [n for _, n in sorted(out, reverse=True)]

    def previous_id(self):
        try:
            with open(os.path.join(self.cfg.state_dir, "previous"), encoding="utf-8") as f:
                v = f.read().strip()
        except OSError:
            return None
        return v if ID_RE.match(v) and v in self.installed_versions() else None

    def _write_state(self, name, value):
        os.makedirs(self.cfg.state_dir, mode=0o755, exist_ok=True)
        p = os.path.join(self.cfg.state_dir, name)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            f.write(value + "\n")
        os.replace(p + ".tmp", p)

    def sending(self):
        names = set(self.cfg.busy_processes)
        if names:
            for d in os.listdir("/proc"):
                if d.isdigit():
                    try:
                        with open("/proc/%s/comm" % d, encoding="utf-8") as f:
                            if f.read().strip() in names:
                                return True
                    except OSError:
                        pass
        for unit in self.cfg.busy_units:
            r = self.systemctl("is-active", unit)
            if r.stdout.strip() in ("active", "activating"):
                return True
        return False

    def systemctl(self, *args):
        return subprocess.run(self.cfg.systemctl + list(args), capture_output=True, text=True, timeout=120)

    # ---------- GitHub ----------

    def _request(self, url, accept):
        if not url.startswith(self.cfg.api + "/"):
            raise Refuse("Adresse außerhalb der Update-Quelle abgelehnt")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept,
                                                   "X-GitHub-Api-Version": "2022-11-28"})
        tok = self.cfg.token()
        if tok:
            req.add_header("Authorization", "Bearer " + tok)
        req._irl4you_insecure = self.cfg.insecure
        try:
            return self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise Refuse("GitHub lehnt die Anfrage ab (%d). Schlüssel oder Anfragegrenze prüfen." % e.code)
            if e.code in (404, 422):
                raise Refuse("Repository, Zweig oder Commit nicht gefunden (%d)" % e.code)
            raise Refuse("GitHub antwortet mit %d" % e.code)
        except urllib.error.URLError as e:
            raise Refuse("GitHub nicht erreichbar: %s" % (str(e.reason)[:80],))

    def _json(self, path):
        with self._request(self.cfg.api + path, "application/vnd.github+json") as r:
            data = r.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise Refuse("Antwort von GitHub ist zu groß")
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def _commit(c):
        sha = str(c.get("sha") or "")
        if not SHA_RE.match(sha):
            raise Refuse("Ungültige Antwort von GitHub (Commit)")
        info = c.get("commit") or {}
        date = ((info.get("committer") or {}).get("date")) or ""
        return {"sha": sha, "id": sha[:12], "message": str(info.get("message") or "")[:20000], "date": date}

    def commits(self, n=15):
        """Neueste Commits des Zweigs, neuester zuerst."""
        raw = self._json("/repos/%s/commits?sha=%s&per_page=%d" % (self.cfg.repo, urllib.parse.quote(self.cfg.branch), n))
        out = [self._commit(c) for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []
        if not out:
            raise Refuse("Der Zweig %s hat keine Commits" % self.cfg.branch)
        return out

    def build_number(self, sha):
        """Dritte Stelle der Version: Commits seit dem letzten Release. Ein Release ist der letzte Commit, der VERSION ändert."""
        try:
            rel = self._json("/repos/%s/commits?sha=%s&path=VERSION&per_page=1" % (self.cfg.repo, sha))
            base = rel[0]["sha"]
            if not SHA_RE.match(base):
                raise ValueError(base)
            if base == sha:
                return 0
            return int(self._json("/repos/%s/compare/%s...%s" % (self.cfg.repo, base, sha))["ahead_by"])
        except (Refuse, ValueError, KeyError, IndexError, TypeError) as e:
            self.log("Dritte Stelle der Version nicht ermittelbar (%s), 0 angenommen" % e)
            return 0

    def resolve(self, ref):
        return self._commit(self._json("/repos/%s/commits/%s" % (self.cfg.repo, urllib.parse.quote(ref))))

    def ci_state(self, commit):
        """ok | pending | failed. Ohne jede Prüfung: pending in den ersten Minuten nach dem Commit, danach ok (keine CI eingerichtet)."""
        raw = self._json("/repos/%s/commits/%s/check-runs?per_page=100" % (self.cfg.repo, commit["sha"]))
        runs = raw.get("check_runs") or []
        if not runs:
            try:
                age = self.now() - datetime.datetime.fromisoformat(commit["date"].replace("Z", "+00:00")).timestamp()
            except ValueError:
                age = 0
            return "pending" if age < self.cfg.ci_grace else "ok"
        if any(r.get("status") != "completed" for r in runs):
            return "pending"
        if all(r.get("conclusion") in ("success", "skipped", "neutral") for r in runs):
            return "ok"
        return "failed"

    def download(self, url, dest, limit, progress=None):
        with self._request(url, "application/vnd.github+json") as r, open(dest, "xb") as out:
            try:
                total = int(r.headers.get("Content-Length") or 0)
            except ValueError:
                total = 0
            if total > limit:
                raise Refuse("Das Paket ist größer als erlaubt")
            got, last = 0, 0.0
            while True:
                part = r.read(256 * 1024)
                if not part:
                    break
                got += len(part)
                if got > limit:
                    raise Refuse("Das Paket ist größer als erlaubt")
                out.write(part)
                if progress and total and self.now() - last >= 0.5:
                    last = self.now()
                    progress(min(100, got * 100 // total))

    # ---------- Paket ----------

    @staticmethod
    def safe_extract(archive, dest):
        """Entpackt nur Dateien, Ordner und Verweise, die im Archiv bleiben. Geräte, harte Verweise und Pfade nach außen: Abbruch."""
        os.makedirs(dest, mode=0o755)
        n = 0
        with tarfile.open(archive, mode="r:gz") as tar:
            members = []
            for m in tar.getmembers():
                rel = posixpath.normpath(m.name)
                if rel in (".", ""):
                    continue
                if m.name.startswith("/") or rel == ".." or rel.startswith("../") or "\x00" in m.name:
                    raise Refuse("Unzulässiger Pfad im Archiv: %r" % (m.name[:60],))
                if m.issym():
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), m.linkname))
                    if m.linkname.startswith("/") or target == ".." or target.startswith("../"):
                        raise Refuse("Verweis zeigt aus dem Archiv heraus: %r" % (m.name[:60],))
                elif not (m.isfile() or m.isdir()):
                    raise Refuse("Unzulässiger Eintrag im Archiv: %r" % (m.name[:60],))
                n += 1
                if n > 20000:
                    raise Refuse("Das Archiv enthält zu viele Dateien")
                members.append(m)
            tar.extractall(dest, members=members, filter="data")
        tops = os.listdir(dest)
        if len(tops) != 1 or not os.path.isdir(os.path.join(dest, tops[0])) or os.path.islink(os.path.join(dest, tops[0])):
            raise Refuse("Das Archiv hat nicht die erwartete Form (ein oberster Ordner)")
        return os.path.join(dest, tops[0])

    @staticmethod
    def verify_tree(root, entries):
        """Jede Datei muss zum Git-Baum des Commits passen: Blob-Hash gleich, nichts fehlt, nichts ist zusätzlich."""
        expected = {e["path"]: e for e in entries if isinstance(e, dict) and e.get("type") == "blob"}
        seen = set()

        def walk(d, rel):
            for e in sorted(os.scandir(d), key=lambda x: x.name):
                r = rel + e.name
                if e.is_symlink():
                    data, link = os.readlink(e.path).encode(), True
                    h = hashlib.sha1(b"blob %d\0" % len(data))
                    h.update(data)
                elif e.is_dir(follow_symlinks=False):
                    walk(e.path, r + "/")
                    continue
                elif e.is_file(follow_symlinks=False):
                    link = False
                    h = hashlib.sha1(b"blob %d\0" % os.path.getsize(e.path))
                    with open(e.path, "rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            h.update(chunk)
                else:
                    raise Refuse("Unzulässiger Eintrag im Archiv: %r" % (r[:60],))
                exp = expected.get(r)
                if exp is None:
                    raise Refuse("Datei gehört nicht zum Commit: %r" % (r[:60],))
                if (exp.get("mode") == "120000") != link or exp.get("sha") != h.hexdigest():
                    raise Refuse("Datei stimmt nicht mit dem Commit überein: %r" % (r[:60],))
                seen.add(r)

        walk(root, "")
        if set(expected) - seen:
            raise Refuse("Dem Archiv fehlen Dateien des Commits")

    @staticmethod
    def assemble(repo, dest, commit, build=0):
        """Paket aus dem Repository zusammensetzen: irl4you/ (Programmstand) + release/hooks + updater/ + VERSION + manifest.json.
        Steht in VERSION nur 'x.y' (Release), wird 'build' (Commits seit dem Release) als dritte Stelle angehängt."""
        src = os.path.join(repo, "irl4you")
        if not os.path.isdir(src) or os.path.islink(src):
            raise Refuse("Im Commit fehlt der Ordner irl4you/")
        try:
            with open(os.path.join(repo, "VERSION"), encoding="utf-8") as f:
                version = f.read().strip()
            if re.match(r"^\d{1,4}\.\d{1,4}$", version):
                version = "%s.%d" % (version, build)
            with open(os.path.join(repo, "release", "manifest.json"), encoding="utf-8") as f:
                manifest = json.loads(f.read().replace("@VERSION@", version))
        except (OSError, ValueError):
            raise Refuse("VERSION oder release/manifest.json fehlt im Commit oder ist fehlerhaft")
        if not isinstance(manifest, dict):
            raise Refuse("release/manifest.json ist fehlerhaft")
        shutil.copytree(src, dest, symlinks=True)
        for d in ("hooks",):
            s = os.path.join(repo, "release", d)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(dest, d), symlinks=True, dirs_exist_ok=True)
        s = os.path.join(repo, "updater")
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dest, "updater"), symlinks=True, dirs_exist_ok=True)
        with open(os.path.join(dest, "VERSION"), "w", encoding="utf-8") as f:
            f.write(version + "\n")
        manifest["commit"] = commit
        with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        for n in os.listdir(os.path.join(dest, "hooks")) if os.path.isdir(os.path.join(dest, "hooks")) else []:
            p = os.path.join(dest, "hooks", n)
            if os.path.isfile(p) and not os.path.islink(p):
                os.chmod(p, 0o755)
        return version

    @staticmethod
    def read_manifest(tree, want_commit=None):
        try:
            with open(os.path.join(tree, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            raise Refuse("manifest.json fehlt oder ist fehlerhaft")
        if not isinstance(m, dict) or m.get("name") != "irl4you":
            raise Refuse("Das Paket ist kein IRL4YOU-Paket")
        if not isinstance(m.get("version"), str) or not VERSION_RE.match(m["version"]):
            raise Refuse("Ungültige Versionsnummer im Manifest")
        if want_commit and m.get("commit") != want_commit:
            raise Refuse("Der Commit im Manifest passt nicht")
        try:
            if int(m.get("min_updater", 1)) > UPDATER_API:
                raise Refuse("Das Paket braucht einen neueren Update-Helfer")
        except (TypeError, ValueError):
            raise Refuse("Ungültige Angabe min_updater im Manifest")
        for key in ("restart", "health_units"):
            v = m.get(key, [])
            if not isinstance(v, list) or not all(isinstance(u, str) and re.match(r"^[A-Za-z0-9@_.:-]{1,80}$", u) for u in v):
                raise Refuse("Ungültige Angabe %s im Manifest" % key)
        debs = os.path.join(tree, "debs")
        if os.path.lexists(debs):
            if os.path.islink(debs) or not os.path.isdir(debs):
                raise Refuse("debs im Paket ist kein Ordner")
            for n in os.listdir(debs):
                p = os.path.join(debs, n)
                if not n.endswith(".deb") or os.path.islink(p) or not os.path.isfile(p):
                    raise Refuse("In debs/ sind nur .deb-Dateien erlaubt: %r" % (n[:40],))
        try:
            with open(os.path.join(tree, "VERSION"), encoding="utf-8") as f:
                if f.read().strip() != m["version"]:
                    raise Refuse("VERSION im Paket passt nicht zum Manifest")
        except OSError:
            raise Refuse("VERSION fehlt im Paket")
        return m

    def free_bytes(self):
        os.makedirs(self.cfg.root, mode=0o755, exist_ok=True)
        st = os.statvfs(self.cfg.root)
        return st.f_bavail * st.f_frsize

    # ---------- Umschalten ----------

    def _point(self, link, target):
        """Verweis atomar umhängen (neuer Verweis daneben, dann rename)."""
        if os.path.exists(link) and not os.path.islink(link):
            raise Refuse("%s ist ein echter Ordner, kein Verweis. Bitte einmalig umstellen (siehe README)." % link)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        tmp = "%s.new-%d" % (link, os.getpid())
        try:
            os.remove(tmp)
        except OSError:
            pass
        os.symlink(target, tmp)
        os.replace(tmp, link)

    def activate(self, rid):
        self._point(self.cfg.current, os.path.join(self.cfg.releases, rid))
        if self.cfg.extra_link:
            self._point(self.cfg.extra_link, self.cfg.current)

    def run_hook(self, rid, name, action, previous):
        hook = os.path.join(self.cfg.releases, rid, "hooks", name)
        if not os.path.isfile(hook):
            return 0, []
        env = dict(os.environ, LC_ALL="C.UTF-8", IRL4YOU_ACTION=action, IRL4YOU_COMMIT=rid,
                   IRL4YOU_VERSION=str(self.manifest_of(rid).get("version", "")),
                   IRL4YOU_PREVIOUS=previous or "", IRL4YOU_ROOT=self.cfg.root,
                   IRL4YOU_RELEASE_DIR=os.path.join(self.cfg.releases, rid))
        try:
            p = subprocess.run(["/bin/sh", hook], cwd=os.path.dirname(os.path.dirname(hook)), env=env,
                               capture_output=True, text=True, errors="replace", timeout=self.cfg.hook_timeout,
                               start_new_session=True)
        except subprocess.TimeoutExpired:
            return -9, ["Zeitüberschreitung"]
        return p.returncode, (p.stdout + p.stderr).splitlines()[-30:]

    def known_units(self, units, what):
        """Nur Dienste, die auf dieser Box eingerichtet sind; die übrigen werden übersprungen (mit Meldung im Protokoll)."""
        known = []
        for u in units:
            r = self.systemctl("show", "-p", "LoadState", "--value", u)
            if r.returncode != 0 or r.stdout.strip() in ("", "not-found", "masked"):
                self.log("%s: Dienst %s ist auf dieser Box nicht eingerichtet, übersprungen" % (what, u))
                self.skipped.add(u)
            else:
                known.append(u)
        return known

    def restart(self, manifest):
        self.systemctl("daemon-reload")
        for unit in self.known_units(manifest.get("restart", []), "Neustart"):
            self.systemctl("restart", unit)

    def healthy(self, rid, manifest, previous):
        units = self.known_units(manifest.get("health_units", []), "Gesundheitsprüfung")
        end = self.now() + self.cfg.health_timeout
        while True:
            bad = [u for u in units if self.systemctl("is-active", "--quiet", u).returncode != 0]
            if not bad:
                break
            if self.now() >= end:
                self.log("Dienste laufen nicht: " + ", ".join(bad))
                return False
            self.sleep(2)
        rc, tail = self.run_hook(rid, "health", "health", previous)
        if rc != 0:
            self.log("Gesundheitsprüfung fehlgeschlagen (%d):\n%s" % (rc, "\n".join(tail)))
            return False
        return True

    def switch_to(self, new, old, action):
        """Aktiviert new; bei Fehler zurück auf old. Liefert True bei Erfolg."""
        manifest = self.read_manifest(os.path.join(self.cfg.releases, new))
        self.status(step="Schalte auf %s um" % self.label(new), progress=70)
        try:
            self.activate(new)
            rc, tail = self.run_hook(new, "install", action, old)
            if tail:
                self.log("hooks/install (%s):\n%s" % (new, "\n".join(tail)))
            ok = rc == 0
            if ok:
                self.status(step="Starte die Dienste neu", progress=85)
                self.restart(manifest)
                ok = self.healthy(new, manifest, old)
        except Exception as e:                              # jeder Fehler nach dem Umschalten führt zurück
            self.log("Fehler beim Umschalten: %r" % (e,))
            ok = False
        if ok:
            if old and old != new:
                self._write_state("previous", old)
            return True
        self.log("%s läuft nicht, zurück auf %s" % (self.label(new), self.label(old)))
        if old:
            self.status(step="Fehler, stelle %s wieder her" % self.label(old), progress=90)
            self.activate(old)
            rc2, tail2 = self.run_hook(old, "install", "rollback", new)
            if tail2:
                self.log("hooks/install (%s, zurück):\n%s" % (old, "\n".join(tail2)))
            try:
                self.restart(self.read_manifest(os.path.join(self.cfg.releases, old)))
            except Refuse as e:
                self.log("Alte Version ohne gültiges Manifest: %s" % e)
        return False

    def prune(self):
        keep = {self.active_id(), self.previous_id()}
        for v in self.installed_versions()[self.cfg.keep:]:
            if v not in keep:
                shutil.rmtree(os.path.join(self.cfg.releases, v), ignore_errors=True)
        try:
            for n in os.listdir(self.cfg.releases):
                if n.startswith("."):
                    shutil.rmtree(os.path.join(self.cfg.releases, n), ignore_errors=True)
        except OSError:
            pass

    # ---------- Aktionen ----------

    def _newer_than_active(self, commits):
        """(Commit, Hinweistext) des Zweigspitzenstands, wenn er neu und freigegeben ist, sonst (None, Grund)."""
        tip, cur = commits[0], self.active_commit()
        if cur == tip["sha"]:
            return None, "IRL4YOU ist aktuell."
        if self.cfg.require_ci:
            st = self.ci_state(tip)
            if st == "pending":
                return None, "Neuer Stand %s wird noch von GitHub geprüft." % short(tip["sha"])
            if st == "failed":
                return None, "Neuer Stand %s hat fehlgeschlagene Prüfungen und wird nicht installiert." % short(tip["sha"])
        return tip, "Neuer Stand %s ist verfügbar." % short(tip["sha"])

    def check(self):
        cur = self.active_commit()
        self.status(state="checking", step="Frage GitHub nach neuen Versionen", message="")
        commits = self.commits()
        tip, msg = self._newer_than_active(commits)
        notes = []
        for c in commits:
            if c["sha"] == cur:
                break
            notes.append("- " + c["message"].strip().splitlines()[0] if c["message"].strip() else "- (ohne Text)")
        self.status(state="idle", step="", version=self.label(self.active_id()), commit=(cur or "")[:12],
                    latest=short(commits[0]["sha"]), available=bool(tip), checked=int(self.now()),
                    notes="\n".join(notes)[:4000] if tip else "",
                    releases=[{"version": short(c["sha"]), "commit": c["sha"], "published": c["date"], "prerelease": False,
                               "notes": c["message"][:4000]} for c in commits],
                    message=msg)
        return (tip["sha"] if tip else None), bool(tip)

    def _fetch(self, commit, progress):
        """Commit herunterladen, prüfen und als releases/<id> einrichten."""
        rid, sha = commit["id"], commit["sha"]
        os.makedirs(self.cfg.releases, mode=0o755, exist_ok=True)
        os.makedirs(self.cfg.state_dir, mode=0o755, exist_ok=True)
        if self.free_bytes() < self.cfg.min_free:
            raise Refuse("Zu wenig freier Speicher für das Update")
        work = tempfile.mkdtemp(dir=self.cfg.releases, prefix=".dl-")
        try:
            self.status(step="Lade Commit %s" % short(sha), progress=5)
            tree_info = self._json("/repos/%s/git/trees/%s?recursive=1" % (self.cfg.repo, sha))
            if tree_info.get("truncated"):
                raise Refuse("Der Dateibaum des Commits ist zu groß für die Prüfung")
            archive = os.path.join(work, "src.tar.gz")
            self.download("%s/repos/%s/tarball/%s" % (self.cfg.api, self.cfg.repo, sha), archive, self.cfg.max_download,
                          lambda pct: self.status(progress=5 + pct * 45 // 100))
            self.status(step="Prüfe und entpacke das Archiv", progress=52)
            repo_dir = self.safe_extract(archive, os.path.join(work, "src"))
            self.verify_tree(repo_dir, tree_info.get("tree") or [])
            self.log("Commit %s geladen, Dateien stimmen mit dem Git-Baum überein" % short(sha))
            pkg = os.path.join(work, "pkg")
            self.assemble(repo_dir, pkg, sha, self.build_number(sha))
            self.read_manifest(pkg, sha)
            dest = os.path.join(self.cfg.releases, rid)
            if os.path.lexists(dest):
                shutil.rmtree(dest)                 # nicht aktiv (sonst wäre es oben abgelehnt): alter Rest
            os.rename(pkg, dest)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def install(self, target=None):
        if self.sending():
            raise Refuse("Es wird gerade gesendet. Bitte zuerst die Übertragung beenden.")
        cur = self.active_id()
        self.status(state="installing", step="Frage GitHub nach dem Stand", message="", frm=self.label(cur),
                    to=target or "", progress=2)
        if target is None:
            tip, msg = self._newer_than_active(self.commits(1))
            if tip is None:
                raise Refuse(msg if "aktuell" not in msg else "Keine neuere Version (installiert %s)" % self.label(cur))
            commit = tip
        else:
            if not HEX_RE.match(target):
                raise Refuse("Ungültiger Commit")
            local = [v for v in self.installed_versions() if (v.startswith(target) if len(target) <= 12 else v == target[:12])]
            if local:
                if local[0] == cur:
                    raise Refuse("Version %s ist schon installiert" % self.label(cur))
                return self._switch_local(local[0], cur)
            commit = self.resolve(target)
            if commit["id"] == cur:
                raise Refuse("Version %s ist schon installiert" % self.label(cur))
        self.status(to=short(commit["sha"]))
        self._fetch(commit, None)
        new = commit["id"]
        ok = self.switch_to(new, cur, "install")
        self.prune()
        if not ok:
            if cur:
                shutil.rmtree(os.path.join(self.cfg.releases, new), ignore_errors=True)
            self.status(state="failed", step="", progress=0, version=self.label(self.active_id()),
                        message="%s startete nicht, %s ist wieder aktiv." % (short(commit["sha"]), self.label(cur)))
            return False
        self.log("Update auf %s abgeschlossen" % self.label(new))
        m = self.manifest_of(new)
        self.status(state="done", step="", version=self.label(new), commit=new, available=False, progress=100,
                    reboot_required=bool(m.get("reboot")), skipped_units=sorted(self.skipped),
                    message="%s ist installiert." % self.label(new) + (" Bitte neu starten." if m.get("reboot") else "")
                    + (" Nicht eingerichtet, daher nicht geprüft: %s." % ", ".join(sorted(self.skipped)) if self.skipped else ""))
        return True

    def _switch_local(self, rid, cur):
        ok = self.switch_to(rid, cur, "switch")
        self.prune()
        if ok:
            self.status(state="done", step="", version=self.label(rid), commit=rid, progress=100,
                        message="Gewechselt auf %s." % self.label(rid))
        else:
            self.status(state="failed", step="", progress=0, version=self.label(self.active_id()),
                        message="%s startete nicht, %s ist wieder aktiv." % (self.label(rid), self.label(cur)))
        return ok

    def rollback(self):
        if self.sending():
            raise Refuse("Es wird gerade gesendet. Bitte zuerst die Übertragung beenden.")
        cur, prev = self.active_id(), self.previous_id()
        if not prev or prev == cur:
            raise Refuse("Es gibt keine vorherige Version zum Zurückrollen")
        self.status(state="installing", step="Zurück auf %s" % self.label(prev), message="", frm=self.label(cur),
                    to=self.label(prev), progress=10)
        return self._switch_local(prev, cur)

    def auto(self):
        latest, avail = self.check()
        if avail and self.cfg.auto_install:
            if self.sending():
                self.log("Update %s wartet: es wird gesendet" % short(latest))
                return
            self.install()

    def read_request(self):
        """Anfragedatei der Oberfläche lesen und löschen. Liefert (Stichwort, Argument) oder (None, None)."""
        p = self.cfg.request_file
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except OSError:
            return None, None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None, None
            text = os.read(fd, 256).decode("utf-8", "replace")
        finally:
            os.close(fd)
            try:
                os.remove(p)
            except OSError:
                pass
        lines = text.strip().splitlines()
        mode = lines[0].strip() if lines else ""
        arg = lines[1].strip() if len(lines) > 1 else ""
        if mode not in MODES or len(lines) > 2 or (mode == "switch") != bool(arg) or (arg and not HEX_RE.match(arg)):
            self.log("Unbekannte Anforderung verworfen")
            return None, None
        return mode, arg

    def run(self, mode, arg=None):
        try:
            if mode == "check":
                self.check()
            elif mode == "install":
                self.install(arg or None)
            elif mode == "switch":
                self.install(arg)
            elif mode == "rollback":
                self.rollback()
            elif mode == "auto":
                self.auto()
            return 0
        except Refuse as e:
            self.log("abgelehnt: %s" % e)
            self.status(state="refused", step="", message=str(e), progress=0)
            return 2
        except Exception as e:                                  # nie ohne Meldung enden
            self.log("Fehler: %r" % (e,))
            self.status(state="failed", step="", message="Fehler beim Update: %s" % str(e)[:160], progress=0)
            return 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        cfg = Config()
    except Refuse as e:
        print("Konfig: %s" % e, file=sys.stderr)
        return 2
    u = Updater(cfg)
    cmd = argv[0]
    if cmd == "status":
        print(json.dumps(dict(u.load_status(), active=u.active_id(), installed=u.installed_versions(),
                              previous=u.previous_id()), indent=2))
        return 0
    os.makedirs(cfg.state_dir, mode=0o755, exist_ok=True)
    lock = open(os.path.join(cfg.state_dir, "update.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Es läuft schon ein Update.", file=sys.stderr)
        return 3
    if cmd == "request":
        mode, arg = u.read_request()
        return u.run(mode, arg) if mode else 0
    if cmd in ("check", "rollback", "auto") and len(argv) == 1:
        return u.run(cmd)
    if cmd == "install" and len(argv) <= 2:
        return u.run("install", argv[1] if len(argv) == 2 else None)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
