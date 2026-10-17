#!/usr/bin/env python3
"""Update-Helfer von IRL4YOU (Ubuntu 26.04). Holt neue Versionen als GitHub-Releases aus dem eigenen Repository.

Aufruf (nur als root, über systemd):
  irl4you-update check           neueste passende Version ermitteln, nichts installieren
  irl4you-update install [X]     neueste Version (nur wenn neuer) oder genau Version X installieren
  irl4you-update rollback        zurück auf die vorher aktive Version
  irl4you-update auto            für den Timer: prüfen und, wenn in der Konfig erlaubt, installieren
  irl4you-update request         für die .path-Einheit: Stichwort aus der Anfragedatei der Oberfläche ausführen
  irl4you-update status          Status als JSON ausgeben

Ein Release besteht aus der Marke v<Version> und zwei Dateien:
  irl4you-<Version>.tar.gz          das Paket (Inhalt siehe README)
  irl4you-<Version>.tar.gz.sha256   "<sha256>  irl4you-<Version>.tar.gz"

Ablauf beim Installieren:
  1. nie während einer Übertragung,
  2. Paket laden (Größe begrenzt), SHA256 gegen die Prüfdatei prüfen,
  3. streng entpacken (nur Dateien, Ordner und Verweise innerhalb des Pakets) nach releases/<Version>,
  4. manifest.json prüfen (Name, Version passt zur Marke, Mindeststand des Helfers),
  5. Verweis "current" (und optional /opt/pipbox) atomar auf die neue Version umhängen,
  6. hooks/install der neuen Version ausführen, Dienste neu starten, Gesundheit prüfen,
  7. bei einem Fehler: Verweis zurück, hooks/install der alten Version, Dienste neu starten.

Die Oberfläche kann nur Stichwörter aus einer festen Liste anfordern (check, install, rollback, switch <Version>).
Quelle, Zugangsschlüssel und Pfade stehen ausschließlich in der Konfig-Datei, die nur root ändern kann.
"""
import configparser
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

UPDATER_API = 1                     # Stand dieses Helfers; ein Paket kann im Manifest "min_updater" verlangen
CONFIG = os.environ.get("IRL4YOU_UPDATE_CONF", "/etc/irl4you/update.conf")
VERSION_RE = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}(-[a-z0-9.]{1,20})?$")
MODES = ("check", "install", "rollback", "switch")
USER_AGENT = "irl4you-update/%d" % UPDATER_API

DEFAULTS = {
    "repo": "Bittersweet1987/irl4you_2604",
    "api": "https://api.github.com",
    "channel": "stable",                            # stable: nur Releases; beta: auch Vorabversionen
    "token_file": "/etc/irl4you/update-token",      # optional, nur für ein privates Repository
    "auto_install": "false",                        # der Timer installiert nur, wenn hier true steht
    "root": "/opt/irl4you",                         # enthält releases/<Version> und den Verweis current
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
    "health_timeout": "60",
    "allow_insecure_api": "false",                  # nur für Tests: http:// statt https:// erlauben
}


class Refuse(Exception):
    """Ein erwarteter Grund, nicht weiterzumachen. Die Meldung geht so an die Oberfläche."""


def vkey(v):
    """Sortierschlüssel: Zahlen, dann Release vor Vorabversion."""
    if not isinstance(v, str) or not VERSION_RE.match(v):
        raise Refuse("Ungültige Versionsnummer: %r" % (str(v)[:24],))
    core, _, pre = v.partition("-")
    nums = tuple(int(x) for x in core.split("."))
    if not pre:
        return nums, (1, ())
    return nums, (0, tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")))


def is_newer(a, b):
    return vkey(a) > vkey(b)


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
        self.channel = s["channel"].strip()
        if self.channel not in ("stable", "beta"):
            raise Refuse("Ungültiger Kanal in der Konfig (stable oder beta)")
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
    """Die API leitet Downloads auf einen anderen Rechner um (signierte Adresse). Dorthin darf der Schlüssel nicht mit."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old_host = urllib.parse.urlsplit(req.full_url).netloc
        if urllib.parse.urlsplit(newurl).netloc != old_host:
            for h in ("Authorization",):
                new.headers.pop(h, None)
                new.unredirected_hdrs.pop(h, None)
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

    def active_version(self):
        try:
            target = os.readlink(self.cfg.current)
        except OSError:
            return None
        v = os.path.basename(target.rstrip("/"))
        return v if VERSION_RE.match(v) else None

    def installed_versions(self):
        try:
            names = os.listdir(self.cfg.releases)
        except OSError:
            return []
        out = [n for n in names if VERSION_RE.match(n) and os.path.isfile(os.path.join(self.cfg.releases, n, "manifest.json"))]
        return sorted(out, key=vkey, reverse=True)

    def previous_version(self):
        try:
            with open(os.path.join(self.cfg.state_dir, "previous"), encoding="utf-8") as f:
                v = f.read().strip()
        except OSError:
            return None
        return v if VERSION_RE.match(v) and v in self.installed_versions() else None

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
            if e.code == 404:
                raise Refuse("Repository oder Release nicht gefunden (404)")
            raise Refuse("GitHub antwortet mit %d" % e.code)
        except urllib.error.URLError as e:
            raise Refuse("GitHub nicht erreichbar: %s" % (str(e.reason)[:80],))

    def _json(self, path):
        with self._request(self.cfg.api + path, "application/vnd.github+json") as r:
            data = r.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise Refuse("Antwort von GitHub ist zu groß")
        return json.loads(data.decode("utf-8"))

    def releases(self):
        """Gültige Releases des Kanals, neueste zuerst: [{version, tag, notes, published, prerelease, pkg, sum}]."""
        raw = self._json("/repos/%s/releases?per_page=50" % self.cfg.repo)
        out = []
        for r in raw if isinstance(raw, list) else []:
            if r.get("draft"):
                continue
            if r.get("prerelease") and self.cfg.channel != "beta":
                continue
            tag = str(r.get("tag_name") or "")
            if not tag.startswith("v") or not VERSION_RE.match(tag[1:]):
                continue
            v = tag[1:]
            assets = {a.get("name"): a for a in r.get("assets") or [] if isinstance(a, dict)}
            pkg, summ = assets.get("irl4you-%s.tar.gz" % v), assets.get("irl4you-%s.tar.gz.sha256" % v)
            if not pkg or not summ:
                continue
            out.append({"version": v, "tag": tag, "notes": str(r.get("body") or "")[:20000],
                        "published": r.get("published_at") or "", "prerelease": bool(r.get("prerelease")),
                        "pkg": pkg, "sum": summ})
        out.sort(key=lambda x: vkey(x["version"]), reverse=True)
        return out

    def _asset_url(self, asset):
        aid = asset.get("id")
        if not isinstance(aid, int):
            raise Refuse("Ungültige Angabe im Release")
        return "%s/repos/%s/releases/assets/%d" % (self.cfg.api, self.cfg.repo, aid)

    def download(self, asset, dest, limit, progress=None):
        """Lädt eine Release-Datei nach dest, liefert die SHA256-Summe (hex)."""
        h = hashlib.sha256()
        got, last = 0, 0.0
        with self._request(self._asset_url(asset), "application/octet-stream") as r, open(dest, "xb") as out:
            try:
                total = int(r.headers.get("Content-Length") or 0)
            except ValueError:
                total = 0
            if total > limit:
                raise Refuse("Das Paket ist größer als erlaubt")
            while True:
                part = r.read(256 * 1024)
                if not part:
                    break
                got += len(part)
                if got > limit:
                    raise Refuse("Das Paket ist größer als erlaubt")
                h.update(part)
                out.write(part)
                if progress and total and self.now() - last >= 0.5:
                    last = self.now()
                    progress(min(100, got * 100 // total))
        return h.hexdigest()

    def fetch_checksum(self, asset, pkg_name, work):
        tmp = os.path.join(work, pkg_name + ".sha256")
        self.download(asset, tmp, 4096)
        with open(tmp, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == pkg_name and re.match(r"^[0-9a-f]{64}$", parts[0].lower()):
                return parts[0].lower()
        raise Refuse("Die Prüfsummen-Datei des Release ist ungültig")

    # ---------- Paket ----------

    @staticmethod
    def safe_extract(archive, dest):
        """Entpackt nur Dateien, Ordner und Verweise, die im Paket bleiben. Geräte, harte Verweise und Pfade nach außen: Abbruch."""
        os.makedirs(dest, mode=0o755)
        n = 0
        with tarfile.open(archive, mode="r:gz") as tar:
            members = []
            for m in tar.getmembers():
                rel = posixpath.normpath(m.name)
                if rel in (".", ""):
                    continue
                if m.name.startswith("/") or rel == ".." or rel.startswith("../") or "\x00" in m.name:
                    raise Refuse("Unzulässiger Pfad im Paket: %r" % (m.name[:60],))
                if m.issym():
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), m.linkname))
                    if m.linkname.startswith("/") or target == ".." or target.startswith("../"):
                        raise Refuse("Verweis zeigt aus dem Paket heraus: %r" % (m.name[:60],))
                elif not (m.isfile() or m.isdir()):
                    raise Refuse("Unzulässiger Eintrag im Paket: %r" % (m.name[:60],))
                n += 1
                if n > 20000:
                    raise Refuse("Das Paket enthält zu viele Dateien")
                members.append(m)
            tar.extractall(dest, members=members, filter="data")
        return n

    @staticmethod
    def read_manifest(tree, want_version):
        try:
            with open(os.path.join(tree, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            raise Refuse("manifest.json fehlt oder ist fehlerhaft")
        if not isinstance(m, dict) or m.get("name") != "irl4you":
            raise Refuse("Das Paket ist kein IRL4YOU-Paket")
        if m.get("version") != want_version:
            raise Refuse("Das Paket enthält Version %s, erwartet %s" % (str(m.get("version"))[:24], want_version))
        if int(m.get("min_updater", 1)) > UPDATER_API:
            raise Refuse("Das Paket braucht einen neueren Update-Helfer")
        for key in ("restart", "health_units"):
            v = m.get(key, [])
            if not isinstance(v, list) or not all(isinstance(u, str) and re.match(r"^[A-Za-z0-9@_.:-]{1,80}$", u) for u in v):
                raise Refuse("Ungültige Angabe %s im Manifest" % key)
        try:
            with open(os.path.join(tree, "VERSION"), encoding="utf-8") as f:
                if f.read().strip() != want_version:
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

    def activate(self, version):
        target = os.path.join(self.cfg.releases, version)
        self._point(self.cfg.current, target)
        if self.cfg.extra_link:
            self._point(self.cfg.extra_link, self.cfg.current)

    def run_hook(self, version, name, action, previous):
        hook = os.path.join(self.cfg.releases, version, "hooks", name)
        if not os.path.isfile(hook):
            return 0, []
        env = dict(os.environ, LC_ALL="C.UTF-8", IRL4YOU_ACTION=action, IRL4YOU_VERSION=version,
                   IRL4YOU_PREVIOUS=previous or "", IRL4YOU_ROOT=self.cfg.root,
                   IRL4YOU_RELEASE_DIR=os.path.join(self.cfg.releases, version))
        try:
            p = subprocess.run(["/bin/sh", hook], cwd=os.path.dirname(os.path.dirname(hook)), env=env,
                               capture_output=True, text=True, errors="replace", timeout=self.cfg.hook_timeout,
                               start_new_session=True)
        except subprocess.TimeoutExpired:
            return -9, ["Zeitüberschreitung"]
        tail = (p.stdout + p.stderr).splitlines()[-30:]
        return p.returncode, tail

    def restart(self, manifest):
        self.systemctl("daemon-reload")
        for unit in manifest.get("restart", []):
            self.systemctl("restart", unit)

    def healthy(self, version, manifest, previous):
        units = manifest.get("health_units", [])
        end = self.now() + self.cfg.health_timeout
        while True:
            bad = [u for u in units if self.systemctl("is-active", "--quiet", u).returncode != 0]
            if not bad:
                break
            if self.now() >= end:
                self.log("Dienste laufen nicht: " + ", ".join(bad))
                return False
            self.sleep(2)
        rc, tail = self.run_hook(version, "health", "health", previous)
        if rc != 0:
            self.log("Gesundheitsprüfung fehlgeschlagen (%d):\n%s" % (rc, "\n".join(tail)))
            return False
        return True

    def switch_to(self, new, old, action):
        """Aktiviert new; bei Fehler zurück auf old. Liefert True bei Erfolg."""
        manifest = self.read_manifest(os.path.join(self.cfg.releases, new), new)
        self.status(step="Schalte auf Version %s um" % new, progress=70)
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
            return True, manifest
        self.log("Version %s läuft nicht, zurück auf %s" % (new, old or "-"))
        if old:
            self.status(step="Fehler, stelle Version %s wieder her" % old, progress=90)
            self.activate(old)
            rc2, tail2 = self.run_hook(old, "install", "rollback", new)
            if tail2:
                self.log("hooks/install (%s, zurück):\n%s" % (old, "\n".join(tail2)))
            try:
                self.restart(self.read_manifest(os.path.join(self.cfg.releases, old), old))
            except Refuse as e:
                self.log("Alte Version ohne gültiges Manifest: %s" % e)
        return False, manifest

    def prune(self):
        keep = {self.active_version(), self.previous_version()}
        versions = self.installed_versions()
        for v in versions[self.cfg.keep:]:
            if v not in keep:
                shutil.rmtree(os.path.join(self.cfg.releases, v), ignore_errors=True)
        try:
            for n in os.listdir(self.cfg.releases):
                if n.startswith("."):
                    shutil.rmtree(os.path.join(self.cfg.releases, n), ignore_errors=True)
        except OSError:
            pass

    # ---------- Aktionen ----------

    def check(self):
        cur = self.active_version()
        self.status(state="checking", step="Frage GitHub nach neuen Versionen", message="")
        rels = self.releases()
        latest = rels[0]["version"] if rels else None
        avail = bool(latest and (cur is None or is_newer(latest, cur)))
        self.status(state="idle", step="", version=cur, latest=latest, available=avail, checked=int(self.now()),
                    notes=rels[0]["notes"][:4000] if avail else "",
                    releases=[{"version": r["version"], "published": r["published"], "prerelease": r["prerelease"]}
                              for r in rels[:15]],
                    message=("Version %s ist verfügbar." % latest) if avail else "IRL4YOU ist aktuell.")
        return latest, avail

    def install(self, version=None):
        if self.sending():
            raise Refuse("Es wird gerade gesendet. Bitte zuerst die Übertragung beenden.")
        cur = self.active_version()
        self.status(state="installing", step="Frage GitHub nach der Version", message="", frm=cur, to=version or "", progress=2)
        rels = self.releases()
        if version is None:
            if not rels:
                raise Refuse("Im Repository gibt es noch kein passendes Release")
            rel = rels[0]
            if cur and not is_newer(rel["version"], cur):
                raise Refuse("Keine neuere Version (installiert %s, neueste %s)" % (cur, rel["version"]))
        else:
            vkey(version)
            if version == cur:
                raise Refuse("Version %s ist schon installiert" % version)
            if version in self.installed_versions():
                return self._switch_local(version, cur)
            rel = next((r for r in rels if r["version"] == version), None)
            if rel is None:
                raise Refuse("Version %s gibt es im Repository nicht" % version)
        new = rel["version"]
        if self.free_bytes() < self.cfg.min_free + int(rel["pkg"].get("size") or 0) * 3:
            raise Refuse("Zu wenig freier Speicher für das Update")
        os.makedirs(self.cfg.releases, mode=0o755, exist_ok=True)
        os.makedirs(self.cfg.state_dir, mode=0o755, exist_ok=True)
        work = tempfile.mkdtemp(dir=self.cfg.releases, prefix=".dl-")
        try:
            name = "irl4you-%s.tar.gz" % new
            self.status(to=new, step="Lade Version %s" % new, progress=5)
            want = self.fetch_checksum(rel["sum"], name, work)
            archive = os.path.join(work, name)
            got = self.download(rel["pkg"], archive, self.cfg.max_download,
                                lambda pct: self.status(progress=5 + pct * 45 // 100))
            if got != want:
                raise Refuse("Prüfsumme stimmt nicht, das Paket wird nicht installiert")
            self.log("Paket %s geladen, Prüfsumme ok" % name)
            self.status(step="Prüfe und entpacke das Paket", progress=55)
            tree = os.path.join(work, "tree")
            self.safe_extract(archive, tree)
            self.read_manifest(tree, new)
            dest = os.path.join(self.cfg.releases, new)
            if os.path.lexists(dest):
                shutil.rmtree(dest)                 # nicht aktiv (sonst wäre es oben abgelehnt): unvollständiger alter Stand
            os.rename(tree, dest)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        ok, _ = self.switch_to(new, cur, "install")
        self.prune()
        if not ok:
            if cur:
                shutil.rmtree(os.path.join(self.cfg.releases, new), ignore_errors=True)
            self.status(state="failed", step="", progress=0, version=self.active_version(),
                        message="Version %s startete nicht, Version %s ist wieder aktiv." % (new, cur or "-"))
            return False
        self.log("Update auf %s abgeschlossen" % new)
        m = self.read_manifest(os.path.join(self.cfg.releases, new), new)
        self.status(state="done", step="", version=new, available=False, progress=100, reboot_required=bool(m.get("reboot")),
                    message="Version %s ist installiert." % new + (" Bitte neu starten." if m.get("reboot") else ""))
        return True

    def _switch_local(self, version, cur):
        ok, _ = self.switch_to(version, cur, "switch")
        self.prune()
        if ok:
            self.status(state="done", step="", version=version, progress=100, message="Gewechselt auf Version %s." % version)
        else:
            self.status(state="failed", step="", progress=0, version=self.active_version(),
                        message="Version %s startete nicht, Version %s ist wieder aktiv." % (version, cur or "-"))
        return ok

    def rollback(self):
        if self.sending():
            raise Refuse("Es wird gerade gesendet. Bitte zuerst die Übertragung beenden.")
        cur, prev = self.active_version(), self.previous_version()
        if not prev or prev == cur:
            raise Refuse("Es gibt keine vorherige Version zum Zurückrollen")
        self.status(state="installing", step="Zurück auf Version %s" % prev, message="", frm=cur, to=prev, progress=10)
        return self._switch_local(prev, cur)

    def auto(self):
        latest, avail = self.check()
        if avail and self.cfg.auto_install:
            if self.sending():
                self.log("Update %s wartet: es wird gesendet" % latest)
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
        if mode not in MODES or len(lines) > 2 or (mode == "switch") != bool(arg) or (arg and not VERSION_RE.match(arg)):
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
        print(json.dumps(dict(u.load_status(), active=u.active_version(), installed=u.installed_versions(),
                              previous=u.previous_version()), indent=2))
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
