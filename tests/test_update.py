"""Tests für den Update-Helfer. Ein kleiner Server spielt die GitHub-API (Commits, Prüfungen, Git-Baum, Tarball),
systemctl ist ein Platzhalter-Skript.

Aufruf: python3 -m unittest discover -s tests -v
"""
import datetime
import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "updater"))
import irl4you_update as U  # noqa: E402

FAKE_SYSTEMCTL = r'''#!/usr/bin/env python3
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(d, "systemctl.log"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
try:
    st = json.load(open(os.path.join(d, "systemctl.json")))
except Exception:
    st = {}
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if args and args[0] == "show":
    u = sys.argv[-1]
    print("loaded" if u in st.get("known", ["pipbox.service", "pipbox-send.service"]) else "not-found")
    sys.exit(0)
if args and args[0] == "is-active":
    on = args[1] in st.get("active", ["pipbox.service"])
    print("active" if on else "inactive")
    sys.exit(0 if on else 3)
sys.exit(0)
'''

HOOK_OK = '''#!/bin/sh
echo "$IRL4YOU_ACTION $IRL4YOU_VERSION prev=$IRL4YOU_PREVIOUS" >> "$IRL4YOU_ROOT/../hooks.log"
'''
HOOK_FAIL = '''#!/bin/sh
echo "$IRL4YOU_ACTION $IRL4YOU_VERSION prev=$IRL4YOU_PREVIOUS" >> "$IRL4YOU_ROOT/../hooks.log"
echo kaputt >&2
exit 4
'''


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def repo_files(version="2.0.0", hook=HOOK_OK, manifest=None, irl=None):
    """Dateien eines Commits: Pfad -> Text/Bytes oder ("link", Ziel)."""
    m = {"name": "irl4you", "version": "@VERSION@", "min_updater": 1, "restart": ["pipbox.service"],
         "health_units": ["pipbox.service"], "reboot": False}
    m.update(manifest or {})
    files = {"VERSION": version + "\n", "irl4you/server.py": "print('hallo %s')\n" % version,
             "irl4you/web/static": ("link", "../server.py"),
             "release/hooks/install": hook, "release/hooks/health": "#!/bin/sh\nexit 0\n",
             "release/manifest.json": json.dumps(m), "updater/irl4you_update.py": "# platzhalter\n",
             "updater/update.conf.example": "[update]\n"}
    files.update(irl or {})
    return {k: v for k, v in files.items() if v is not None}


def as_bytes(v):
    return v if isinstance(v, bytes) else v.encode()


class FakeGitHub:
    def __init__(self, repo="Bittersweet1987/irl4you_2604"):
        self.repo = repo
        self.commits = []                       # neuester zuerst
        self.redirect = False
        self.requests = []
        self._n = 0
        fake = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = urllib.parse.parse_qs(u.query)
                fake.requests.append((self.headers.get("Host"), u.path, self.headers.get("Authorization")))
                base = "/repos/%s/" % fake.repo
                p = u.path
                if p == base + "commits":
                    return self.js([fake.api(c) for c in fake.commits][:int(q.get("per_page", ["30"])[0])])
                if p.startswith(base + "commits/") and p.endswith("/check-runs"):
                    c = fake.find(p.split("/")[-2])
                    return self.js({"check_runs": fake.runs(c)}) if c else self.js({}, 404)
                if p.startswith(base + "commits/"):
                    c = fake.find(p.rsplit("/", 1)[1])
                    return self.js(fake.api(c)) if c else self.js({}, 404)
                if p.startswith(base + "git/trees/"):
                    c = fake.find(p.rsplit("/", 1)[1])
                    return self.js(fake.tree(c)) if c else self.js({}, 404)
                if p.startswith(base + "tarball/"):
                    c = fake.find(p.rsplit("/", 1)[1])
                    if not c:
                        return self.js({}, 404)
                    if fake.redirect:
                        self.send_response(302)
                        self.send_header("Location", "http://localhost:%d/blob/%s" % (fake.port, c["sha"]))
                        self.end_headers()
                        return
                    return self.send(200, fake.tarball(c), "application/gzip")
                if p.startswith("/blob/"):
                    return self.send(200, fake.tarball(fake.find(p.rsplit("/", 1)[1])), "application/gzip")
                self.js({}, 404)

            def js(self, obj, code=200):
                self.send(code, json.dumps(obj).encode(), "application/json")

            def send(self, code, data, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def add(self, version="2.0.0", message=None, ci="success", age=3600, files=None, tamper=None, extra=None, **kw):
        """Neuer Commit an der Spitze. tamper: Pfad -> Bytes (nur im Tarball) oder None (fehlt im Tarball)."""
        self._n += 1
        files = files if files is not None else repo_files(version, **kw)
        sha = hashlib.sha1(("%d%s" % (self._n, sorted(files))).encode()).hexdigest()
        date = datetime.datetime.fromtimestamp(time.time() - age, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        c = {"sha": sha, "message": message or "Commit %d" % self._n, "date": date, "files": files, "ci": ci,
             "tamper": tamper or {}, "extra": extra or []}
        self.commits.insert(0, c)
        return c

    def find(self, ref):
        for c in self.commits:
            if c["sha"].startswith(ref):
                return c
        return None

    @staticmethod
    def api(c):
        return {"sha": c["sha"], "commit": {"message": c["message"], "committer": {"date": c["date"]}}}

    @staticmethod
    def runs(c):
        return {"success": [{"status": "completed", "conclusion": "success"}],
                "failure": [{"status": "completed", "conclusion": "failure"}],
                "pending": [{"status": "in_progress", "conclusion": None}], "none": []}[c["ci"]]

    @staticmethod
    def tree(c):
        out = []
        for path, v in sorted(c["files"].items()):
            if isinstance(v, tuple):
                out.append({"path": path, "mode": "120000", "type": "blob", "sha": blob_sha(v[1].encode())})
            else:
                out.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha(as_bytes(v))})
        return {"sha": c["sha"], "tree": out, "truncated": False}

    @staticmethod
    def tarball(c):
        buf = io.BytesIO()
        top = "o-r-%s/" % c["sha"][:7]
        with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": c["sha"]}) as tar:
            for path, v in c["files"].items():
                if path in c["tamper"] and c["tamper"][path] is None:
                    continue
                ti = tarfile.TarInfo(top + path)
                if isinstance(v, tuple):
                    ti.type, ti.linkname = tarfile.SYMTYPE, v[1]
                    tar.addfile(ti)
                    continue
                data = c["tamper"].get(path, as_bytes(v))
                ti.size = len(data)
                ti.mode = 0o755 if path.startswith("release/hooks/") else 0o644
                tar.addfile(ti, io.BytesIO(data))
            for f in c["extra"]:
                ti, data = f(top)
                tar.addfile(ti, io.BytesIO(data) if data is not None else None)
        return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gh = FakeGitHub()
        self.addCleanup(self.gh.close)
        self.addCleanup(subprocess.run, ["rm", "-rf", self.tmp])
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        self.sysctl = os.path.join(bindir, "systemctl")
        with open(self.sysctl, "w") as f:
            f.write(FAKE_SYSTEMCTL)
        os.chmod(self.sysctl, 0o755)
        self.set_units(["pipbox.service"])
        self.overrides = {
            "api": "http://127.0.0.1:%d" % self.gh.port, "allow_insecure_api": "true",
            "root": os.path.join(self.tmp, "opt", "irl4you"), "extra_link": os.path.join(self.tmp, "opt", "pipbox"),
            "state_dir": os.path.join(self.tmp, "state"), "status_file": os.path.join(self.tmp, "run", "status.json"),
            "request_file": os.path.join(self.tmp, "state", "swupdate-request"),
            "log_file": os.path.join(self.tmp, "update.log"), "token_file": "", "busy_processes": "",
            "busy_units": "pipbox-send.service", "systemctl": self.sysctl, "health_timeout": "0", "min_free_mb": "1",
        }
        self.u = self.make()

    def make(self, **kw):
        return U.Updater(U.Config(path=None, overrides=dict(self.overrides, **kw)), sleep=lambda s: None)

    def set_units(self, active, known=None):
        st = {"active": active}
        if known is not None:
            st["known"] = known
        with open(os.path.join(os.path.dirname(self.sysctl), "systemctl.json"), "w") as f:
            json.dump(st, f)

    def calls(self):
        try:
            with open(os.path.join(os.path.dirname(self.sysctl), "systemctl.log")) as f:
                return f.read().splitlines()
        except OSError:
            return []

    def hooks(self):
        try:
            with open(os.path.join(self.tmp, "opt", "hooks.log")) as f:
                return f.read().splitlines()
        except OSError:
            return []

    def status(self):
        return self.u.load_status()

    def on_disk(self):
        return sorted(os.listdir(os.path.join(self.tmp, "opt", "irl4you", "releases")))

    def rid(self, c):
        return c["sha"][:12]


class TestConfig(unittest.TestCase):
    def test_https_required(self):
        with self.assertRaises(U.Refuse):
            U.Config(path=None, overrides={"api": "http://example.org"})

    def test_bad_repo_and_branch(self):
        for k, v in (("repo", "a/b/../c"), ("branch", "../x"), ("branch", "a b")):
            with self.assertRaises(U.Refuse):
                U.Config(path=None, overrides={k: v})

    def test_defaults_leave_room_for_slow_health_checks(self):
        c = U.Config(path=None)
        self.assertGreaterEqual(c.health_timeout, 120)      # health.sh der Oberfläche braucht im schlechtesten Fall ~54 s
        self.assertGreaterEqual(c.hook_timeout, 300)

    def test_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("[update]\nrepo = foo/bar\nbranch = dev\nauto_install = true\nrequire_ci = false\n")
        self.addCleanup(os.remove, f.name)
        c = U.Config(path=f.name)
        self.assertEqual((c.repo, c.branch, c.auto_install, c.require_ci), ("foo/bar", "dev", True, False))
        self.assertEqual(c.extra_link, "/opt/pipbox")


class TestCheck(Base):
    def test_notes_between_installed_and_tip(self):
        c1 = self.gh.add(message="Erster Stand")
        self.u.install()
        c2 = self.gh.add("2.0.1", message="Zweiter Stand\n\nMit Einzelheiten")
        c3 = self.gh.add("2.0.2", message="Dritter Stand")
        latest, avail = self.u.check()
        self.assertEqual((latest, avail), (c3["sha"], True))
        s = self.status()
        self.assertEqual(s["state"], "idle")
        self.assertEqual(s["notes"], "- Dritter Stand\n- Zweiter Stand")
        self.assertEqual(s["latest"], c3["sha"][:7])
        self.assertEqual([r["version"] for r in s["releases"]], [c["sha"][:7] for c in (c3, c2, c1)])
        self.assertIn("Mit Einzelheiten", s["releases"][1]["notes"])

    def test_up_to_date(self):
        self.gh.add()
        self.u.install()
        self.assertEqual(self.u.check()[1], False)
        self.assertEqual(self.status()["message"], "IRL4YOU ist aktuell.")

    def test_ci_gate(self):
        self.gh.add(ci="pending")
        self.assertEqual(self.u.check()[1], False)
        self.assertIn("geprüft", self.status()["message"])
        self.gh.commits[0]["ci"] = "failure"
        self.assertEqual(self.u.check()[1], False)
        self.assertIn("fehlgeschlagen", self.status()["message"])
        self.assertEqual(self.make(require_ci="false").check()[1], True)

    def test_no_ci_configured(self):
        self.gh.add(ci="none", age=3600)
        self.assertEqual(self.u.check()[1], True)
        self.gh.add(ci="none", age=5)
        self.assertEqual(self.u.check()[1], False)

    def test_empty_branch(self):
        self.assertEqual(self.u.run("check"), 2)


class TestInstall(Base):
    def test_first_install(self):
        c = self.gh.add()
        self.assertTrue(self.u.install())
        root, rid = self.overrides["root"], self.rid(c)
        self.assertEqual(os.readlink(os.path.join(root, "current")), os.path.join(root, "releases", rid))
        self.assertEqual(os.readlink(self.overrides["extra_link"]), os.path.join(root, "current"))
        with open(os.path.join(self.overrides["extra_link"], "server.py")) as f:
            self.assertIn("2.0.0", f.read())
        cur = os.path.join(root, "current")
        self.assertTrue(os.path.islink(os.path.join(cur, "web", "static")))
        self.assertTrue(os.access(os.path.join(cur, "hooks", "install"), os.X_OK))
        self.assertTrue(os.path.isfile(os.path.join(cur, "updater", "irl4you_update.py")))
        with open(os.path.join(cur, "manifest.json")) as f:
            m = json.load(f)
        self.assertEqual((m["version"], m["commit"]), ("2.0.0", c["sha"]))
        self.assertEqual(self.hooks(), ["install 2.0.0 prev="])
        self.assertIn("restart pipbox.service", self.calls())
        s = self.status()
        self.assertEqual((s["state"], s["progress"], s["version"]), ("done", 100, "2.0.0 (%s)" % c["sha"][:7]))
        self.assertEqual(self.on_disk(), [rid])

    def test_update_and_prune(self):
        cs = []
        for v in ("2.0.0", "2.0.1", "2.0.2", "2.0.3"):
            cs.append(self.gh.add(v))
            self.assertTrue(self.u.install(), v)
        self.assertEqual(self.u.active_id(), self.rid(cs[3]))
        self.assertEqual(self.u.previous_id(), self.rid(cs[2]))
        self.assertEqual(self.on_disk(), sorted(self.rid(c) for c in cs[1:]))
        self.assertEqual(self.hooks()[-1], "install 2.0.3 prev=%s" % self.rid(cs[2]))

    def test_not_newer(self):
        self.gh.add()
        self.u.install()
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("Keine neuere Version", self.status()["message"])

    def test_ci_pending_blocks_but_explicit_sha_does_not(self):
        c = self.gh.add(ci="pending")
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("geprüft", self.status()["message"])
        self.assertTrue(self.u.install(c["sha"]))

    def test_tampered_file(self):
        c0 = self.gh.add()
        self.u.install()
        self.gh.add("2.0.1", tamper={"irl4you/server.py": b"print('boese')\n"})
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("stimmt nicht mit dem Commit überein", self.status()["message"])
        self.assertEqual(self.u.active_id(), self.rid(c0))
        self.assertEqual(self.on_disk(), [self.rid(c0)])

    def test_extra_file(self):
        def f(top):
            ti = tarfile.TarInfo(top + "irl4you/zusatz.py")
            ti.size = 1
            return ti, b"x"
        self.gh.add(extra=[f])
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("gehört nicht zum Commit", self.status()["message"])

    def test_missing_file(self):
        self.gh.add(tamper={"irl4you/server.py": None})
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("fehlen", self.status()["message"])

    def test_hook_fails_rolls_back(self):
        c0 = self.gh.add()
        self.u.install()
        c1 = self.gh.add("2.0.1", hook=HOOK_FAIL)
        self.assertFalse(self.u.install())
        self.assertEqual(self.u.active_id(), self.rid(c0))
        self.assertEqual(self.hooks()[-2:], ["install 2.0.1 prev=%s" % self.rid(c0), "rollback 2.0.0 prev=%s" % self.rid(c1)])
        self.assertEqual(self.status()["state"], "failed")
        self.assertEqual(self.on_disk(), [self.rid(c0)])
        with open(self.overrides["log_file"]) as f:
            self.assertIn("kaputt", f.read())

    def test_service_down_rolls_back(self):
        c0 = self.gh.add()
        self.u.install()
        self.gh.add("2.0.1")
        self.set_units([])
        self.assertFalse(self.u.install())
        self.assertEqual(self.u.active_id(), self.rid(c0))
        self.assertTrue(self.hooks()[-1].startswith("rollback 2.0.0"))

    def test_missing_units_are_skipped(self):
        """Basis-System ohne pipbox.service: Gesundheitsprüfung und Neustart überspringen den Dienst, das Update gelingt."""
        self.set_units([], known=[])
        c = self.gh.add()
        self.assertTrue(self.u.install())
        self.assertEqual(self.u.active_id(), self.rid(c))
        self.assertNotIn("restart pipbox.service", self.calls())
        s = self.status()
        self.assertEqual((s["state"], s["skipped_units"]), ("done", ["pipbox.service"]))
        self.assertIn("pipbox.service", s["message"])
        with open(self.overrides["log_file"]) as f:
            self.assertIn("Dienst pipbox.service ist auf dieser Box nicht eingerichtet", f.read())

    def test_missing_unit_does_not_hide_a_broken_one(self):
        self.set_units([], known=["pipbox.service"])           # eingerichtet, läuft aber nicht
        self.gh.add(manifest={"health_units": ["pipbox.service", "gibt-es-nicht.service"]})
        self.assertFalse(self.u.install())
        self.assertEqual(self.status()["state"], "failed")

    def test_slow_health_hook_is_not_cut_off_by_health_timeout(self):
        c = self.gh.add(files=repo_files(irl={"irl4you/hooks_dummy": "x"}))
        files = repo_files()
        files["release/hooks/health"] = "#!/bin/sh\nsleep 3\nexit 0\n"
        self.gh.commits[0]["files"] = files
        self.assertTrue(self.make(health_timeout="1").install())
        self.assertEqual(self.u.active_id(), self.rid(c))

    def test_hook_failure_still_rolls_back_without_units(self):
        self.set_units([], known=[])
        c0 = self.gh.add()
        self.u.install()
        self.gh.add("2.0.1", hook=HOOK_FAIL)
        self.assertFalse(self.u.install())
        self.assertEqual(self.u.active_id(), self.rid(c0))

    def test_not_while_sending(self):
        self.gh.add()
        self.set_units(["pipbox.service", "pipbox-send.service"])
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("gesendet", self.status()["message"])
        self.assertIsNone(self.u.active_id())

    def test_manifest_problems(self):
        for man, text in (({"min_updater": 99}, "neueren Update-Helfer"),
                          ({"restart": ["pipbox.service; reboot"]}, "restart"),
                          ({"name": "anders"}, "kein IRL4YOU-Paket")):
            self.gh.add(manifest=man)
            self.assertEqual(self.u.run("install"), 2, man)
            self.assertIn(text, self.status()["message"])

    def test_missing_irl4you_dir(self):
        files = repo_files()
        files.pop("irl4you/server.py")
        files.pop("irl4you/web/static")
        self.gh.add(files=files)
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("irl4you/", self.status()["message"])

    def test_size_limit(self):
        self.gh.add()
        u = self.make(max_download_mb="0")
        self.assertEqual(u.run("install"), 2)
        self.assertIn("größer als erlaubt", u.load_status()["message"])

    def test_extra_link_real_dir(self):
        os.makedirs(self.overrides["extra_link"])
        self.gh.add()
        self.assertFalse(self.u.install())
        self.assertEqual(self.status()["state"], "failed")
        self.assertTrue(os.path.isdir(self.overrides["extra_link"]) and not os.path.islink(self.overrides["extra_link"]))

    def test_reboot_flag(self):
        self.gh.add(manifest={"reboot": True})
        self.u.install()
        self.assertTrue(self.status()["reboot_required"])

    def test_debs(self):
        self.gh.add(irl={"irl4you/debs/irl4you-wifi-8821cu_1.0_arm64.deb": b"deb"})
        self.assertTrue(self.u.install())
        self.assertTrue(os.path.isfile(os.path.join(self.overrides["root"], "current", "debs", "irl4you-wifi-8821cu_1.0_arm64.deb")))

    def test_only_debs_in_debs(self):
        self.gh.add(irl={"irl4you/debs/evil.sh": b"#!/bin/sh"})
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("nur .deb", self.status()["message"])


class TestUnsafeArchives(Base):
    def attempt(self, factory):
        self.gh.add(extra=[factory])
        self.assertEqual(self.u.run("install"), 2, self.status())
        self.assertIsNone(self.u.active_id())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil")))

    def test_path_traversal(self):
        def f(top):
            ti = tarfile.TarInfo("../../../../evil")
            ti.size = 1
            return ti, b"x"
        self.attempt(f)

    def test_absolute_path(self):
        def f(top):
            ti = tarfile.TarInfo(os.path.join(self.tmp, "evil"))
            ti.size = 1
            return ti, b"x"
        self.attempt(f)

    def test_symlink_out(self):
        def f(top):
            ti = tarfile.TarInfo(top + "etc")
            ti.type, ti.linkname = tarfile.SYMTYPE, "/etc"
            return ti, None
        self.attempt(f)

    def test_symlink_relative_out(self):
        def f(top):
            ti = tarfile.TarInfo(top + "a/b")
            ti.type, ti.linkname = tarfile.SYMTYPE, "../../../evil"
            return ti, None
        self.attempt(f)

    def test_device(self):
        def f(top):
            ti = tarfile.TarInfo(top + "dev")
            ti.type = tarfile.CHRTYPE
            return ti, None
        self.attempt(f)

    def test_hardlink(self):
        def f(top):
            ti = tarfile.TarInfo(top + "hl")
            ti.type, ti.linkname = tarfile.LNKTYPE, "VERSION"
            return ti, None
        self.attempt(f)

    def test_two_top_dirs(self):
        def f(top):
            ti = tarfile.TarInfo("zweiter-ordner/x")
            ti.size = 1
            return ti, b"x"
        self.attempt(f)


class TestRollbackSwitch(Base):
    def setUp(self):
        super().setUp()
        self.cs = []
        for v in ("2.0.0", "2.0.1"):
            self.cs.append(self.gh.add(v))
            self.u.install()

    def test_rollback_and_forward(self):
        self.assertEqual(self.u.run("rollback"), 0)
        self.assertEqual(self.u.active_id(), self.rid(self.cs[0]))
        self.assertEqual(self.u.previous_id(), self.rid(self.cs[1]))
        self.assertEqual(self.hooks()[-1], "switch 2.0.0 prev=%s" % self.rid(self.cs[1]))
        self.assertEqual(self.u.run("rollback"), 0)
        self.assertEqual(self.u.active_id(), self.rid(self.cs[1]))

    def test_switch_local_by_short_and_full_sha(self):
        self.assertEqual(self.u.run("switch", self.cs[0]["sha"][:7]), 0)
        self.assertEqual(self.u.active_id(), self.rid(self.cs[0]))
        self.assertEqual(self.u.run("switch", self.cs[1]["sha"]), 0)
        self.assertEqual(self.u.active_id(), self.rid(self.cs[1]))

    def test_switch_remote_older(self):
        for v in ("2.0.2", "2.0.3"):
            self.cs.append(self.gh.add(v))
            self.u.install()
        self.assertNotIn(self.rid(self.cs[0]), self.on_disk())
        self.assertEqual(self.u.run("switch", self.cs[0]["sha"]), 0, self.status())
        self.assertEqual(self.u.active_id(), self.rid(self.cs[0]))

    def test_switch_unknown(self):
        self.assertEqual(self.u.run("switch", "9" * 40), 2)
        self.assertIn("nicht gefunden", self.status()["message"])

    def test_switch_current_refused(self):
        self.assertEqual(self.u.run("switch", self.cs[1]["sha"][:10]), 2)

    def test_rollback_without_previous(self):
        os.remove(os.path.join(self.overrides["state_dir"], "previous"))
        self.assertEqual(self.u.run("rollback"), 2)


class TestAuto(Base):
    def test_only_reports_by_default(self):
        self.gh.add()
        self.u.auto()
        self.assertIsNone(self.u.active_id())
        self.assertTrue(self.status()["available"])

    def test_installs_when_allowed(self):
        c = self.gh.add()
        self.make(auto_install="true").auto()
        self.assertEqual(self.u.active_id(), self.rid(c))

    def test_waits_for_ci(self):
        self.gh.add(ci="pending")
        self.make(auto_install="true").auto()
        self.assertIsNone(self.u.active_id())

    def test_waits_while_sending(self):
        self.gh.add()
        self.set_units(["pipbox.service", "pipbox-send.service"])
        self.make(auto_install="true").auto()
        self.assertIsNone(self.u.active_id())


class TestRequest(Base):
    def req(self, text):
        os.makedirs(self.overrides["state_dir"], exist_ok=True)
        with open(self.overrides["request_file"], "w") as f:
            f.write(text)
        r = self.u.read_request()
        self.assertFalse(os.path.exists(self.overrides["request_file"]))
        return r

    def test_valid(self):
        self.assertEqual(self.req("install\n"), ("install", ""))
        self.assertEqual(self.req("check"), ("check", ""))
        self.assertEqual(self.req("switch\nabcdef1\n"), ("switch", "abcdef1"))
        self.assertEqual(self.req("rollback\n"), ("rollback", ""))

    def test_invalid(self):
        for t in ("reboot", "install\nabcdef1", "switch", "switch\n2.0.1", "switch\nabc", "switch\nabcdef1\nextra",
                  "switch\n../../x", "check; rm -rf /", ""):
            self.assertEqual(self.req(t), (None, None), t)

    def test_symlink_ignored(self):
        os.makedirs(self.overrides["state_dir"], exist_ok=True)
        target = os.path.join(self.tmp, "secret")
        with open(target, "w") as f:
            f.write("install")
        os.symlink(target, self.overrides["request_file"])
        self.assertEqual(self.u.read_request(), (None, None))
        self.assertTrue(os.path.exists(target))


class TestToken(Base):
    def token_file(self, mode=0o600):
        p = os.path.join(self.tmp, "token")
        with open(p, "w") as f:
            f.write("geheim123\n")
        os.chmod(p, mode)
        return p

    def test_token_sent_to_api_not_to_redirect(self):
        self.gh.add()
        self.gh.redirect = True
        self.assertTrue(self.make(token_file=self.token_file()).install())
        api = [r for r in self.gh.requests if not r[1].startswith("/blob/")]
        blob = [r for r in self.gh.requests if r[1].startswith("/blob/")]
        self.assertTrue(api and blob)
        self.assertTrue(all(r[2] == "Bearer geheim123" for r in api))
        self.assertTrue(all(r[2] is None and r[0].startswith("localhost") for r in blob))
        with open(self.overrides["log_file"]) as f:
            self.assertNotIn("geheim123", f.read())

    def test_token_file_must_be_private(self):
        self.gh.add()
        u = self.make(token_file=self.token_file(0o644))
        self.assertEqual(u.run("check"), 2)
        self.assertIn("chmod 600", u.load_status()["message"])

    def test_missing_token_file_is_public_mode(self):
        self.gh.add()
        self.assertEqual(self.make(token_file=os.path.join(self.tmp, "fehlt")).check()[1], True)
        self.assertTrue(all(r[2] is None for r in self.gh.requests))


class TestShippedFiles(unittest.TestCase):
    def test_scripts_parse(self):
        for p in ("irl4you/install/system-install.sh", "irl4you/install/system-base-fixes.sh", "irl4you/install/zz-irl4you-boot",
                  "release/hooks/install", "release/hooks/health"):
            subprocess.run(["sh", "-n", os.path.join(REPO, p)], check=True)

    def test_system_install_calls_base_fixes_and_debs(self):
        with open(os.path.join(REPO, "irl4you/install/system-install.sh")) as f:
            text = f.read()
        self.assertIn("system-base-fixes.sh", text)
        self.assertIn("debs/*.deb", text)

    def test_repo_assembles_to_valid_package(self):
        d = tempfile.mkdtemp()
        self.addCleanup(subprocess.run, ["rm", "-rf", d])
        dest = os.path.join(d, "pkg")
        sha = "a" * 40
        version = U.Updater.assemble(REPO, dest, sha)
        m = U.Updater.read_manifest(dest, sha)
        self.assertEqual(m["version"], version)
        self.assertEqual(m["restart"], ["pipbox.service"])
        for p in ("hooks/install", "hooks/health", "updater/irl4you_update.py", "updater/systemd/irl4you-update.path",
                  "install/system-install.sh", "install/zz-irl4you-boot", "VERSION"):
            self.assertTrue(os.path.isfile(os.path.join(dest, p)), p)
        self.assertTrue(os.access(os.path.join(dest, "hooks/install"), os.X_OK))

    def test_default_config_example_loads(self):
        c = U.Config(path=os.path.join(REPO, "updater", "update.conf.example"))
        self.assertEqual((c.repo, c.branch, c.require_ci, c.auto_install), ("Bittersweet1987/irl4you_2604", "main", True, False))


if __name__ == "__main__":
    unittest.main()
