"""Tests für den Update-Helfer. Ein kleiner Server spielt die GitHub-API, systemctl ist ein Platzhalter-Skript.

Aufruf: python3 -m unittest discover -s tests -v
"""
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
import unittest

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


def make_pkg(version, hook=HOOK_OK, manifest=None, extra=None, file_version=None):
    """Baut ein Paket im Speicher. extra: Liste von TarInfo-Fabriken für Angriffs-Tests."""
    buf = io.BytesIO()
    m = {"name": "irl4you", "version": version, "min_updater": 1, "restart": ["pipbox.service"],
         "health_units": ["pipbox.service"], "reboot": False}
    if manifest:
        m.update(manifest)
    files = {"VERSION": (file_version or version) + "\n", "manifest.json": json.dumps(m),
             "hooks/install": hook, "server.py": "print('hallo %s')\n" % version}
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            ti = tarfile.TarInfo("./" + name)
            ti.size = len(data)
            ti.mode = 0o755 if name.startswith("hooks/") else 0o644
            tar.addfile(ti, io.BytesIO(data))
        ti = tarfile.TarInfo("./web/static")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "../server.py"
        tar.addfile(ti)
        for f in extra or []:
            ti, data = f()
            tar.addfile(ti, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


class FakeGitHub:
    """Liefert /repos/<repo>/releases und /repos/<repo>/releases/assets/<id>."""

    def __init__(self, repo="Bittersweet1987/irl4you_2604"):
        self.repo = repo
        self.releases = []
        self.assets = {}
        self.redirect_assets = False
        self.requests = []
        self._next = 1
        fake = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                fake.requests.append((self.headers.get("Host"), self.path, self.headers.get("Authorization"),
                                      self.headers.get("Accept")))
                base = "/repos/%s/releases" % fake.repo
                if self.path.startswith(base + "?"):
                    return self._send(200, json.dumps(fake.releases).encode(), "application/json")
                if self.path.startswith(base + "/assets/"):
                    aid = int(self.path.rsplit("/", 1)[1])
                    if fake.redirect_assets:
                        self.send_response(302)
                        self.send_header("Location", "http://localhost:%d/blob/%d" % (fake.port, aid))
                        self.end_headers()
                        return
                    return self._send(200, fake.assets[aid], "application/octet-stream")
                if self.path.startswith("/blob/"):
                    return self._send(200, fake.assets[int(self.path.rsplit("/", 1)[1])], "application/octet-stream")
                self._send(404, b"{}", "application/json")

            def _send(self, code, data, ctype):
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

    def _asset(self, name, data):
        aid = self._next
        self._next += 1
        self.assets[aid] = data
        return {"id": aid, "name": name, "size": len(data)}

    def add(self, version, pkg=None, prerelease=False, draft=False, bad_sum=False, missing_sum=False, notes=""):
        pkg = make_pkg(version) if pkg is None else pkg
        name = "irl4you-%s.tar.gz" % version
        digest = hashlib.sha256(pkg).hexdigest()
        if bad_sum:
            digest = "0" * 64
        assets = [self._asset(name, pkg)]
        if not missing_sum:
            assets.append(self._asset(name + ".sha256", ("%s  %s\n" % (digest, name)).encode()))
        self.releases.insert(0, {"tag_name": "v" + version, "draft": draft, "prerelease": prerelease, "body": notes,
                                 "published_at": "2026-10-17T12:00:00Z", "assets": assets})


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
        cfg = U.Config(path=None, overrides=dict(self.overrides, **kw))
        return U.Updater(cfg, sleep=lambda s: None)

    def set_units(self, active):
        with open(os.path.join(os.path.dirname(self.sysctl), "systemctl.json"), "w") as f:
            json.dump({"active": active}, f)

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

    def releases_on_disk(self):
        return sorted(os.listdir(os.path.join(self.tmp, "opt", "irl4you", "releases")))


class TestVersions(unittest.TestCase):
    def test_order(self):
        vs = ["1.0.71", "2.0.0-rc.1", "2.0.0", "2.0.0-beta.2", "2.0.0-beta.10", "10.0.0", "2.0.1"]
        self.assertEqual(sorted(vs, key=U.vkey),
                         ["1.0.71", "2.0.0-beta.2", "2.0.0-beta.10", "2.0.0-rc.1", "2.0.0", "2.0.1", "10.0.0"])

    def test_invalid(self):
        for v in ("2.0", "v2.0.0", "2.0.0;rm", "../1.0.0", "", None):
            with self.assertRaises(U.Refuse):
                U.vkey(v)


class TestConfig(unittest.TestCase):
    def test_https_required(self):
        with self.assertRaises(U.Refuse):
            U.Config(path=None, overrides={"api": "http://example.org"})

    def test_bad_repo(self):
        with self.assertRaises(U.Refuse):
            U.Config(path=None, overrides={"repo": "a/b/../c"})

    def test_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("[update]\nrepo = foo/bar\nchannel = beta\nauto_install = true\n")
        self.addCleanup(os.remove, f.name)
        c = U.Config(path=f.name)
        self.assertEqual((c.repo, c.channel, c.auto_install), ("foo/bar", "beta", True))
        self.assertEqual(c.extra_link, "/opt/pipbox")


class TestCheck(Base):
    def test_latest_stable(self):
        self.gh.add("2.0.0")
        self.gh.add("2.0.1", notes="Neu: Updates")
        self.gh.add("2.1.0-beta.1", prerelease=True)
        self.gh.add("2.2.0", draft=True)
        self.gh.add("2.3.0", missing_sum=True)
        latest, avail = self.u.check()
        self.assertEqual((latest, avail), ("2.0.1", True))
        s = self.status()
        self.assertEqual(s["state"], "idle")
        self.assertEqual(s["notes"], "Neu: Updates")
        self.assertEqual([r["version"] for r in s["releases"]], ["2.0.1", "2.0.0"])

    def test_beta_channel(self):
        self.gh.add("2.0.0")
        self.gh.add("2.1.0-beta.1", prerelease=True)
        self.assertEqual(self.make(channel="beta").check(), ("2.1.0-beta.1", True))

    def test_up_to_date(self):
        self.gh.add("2.0.0")
        self.u.install()
        self.assertEqual(self.u.check(), ("2.0.0", False))
        self.assertEqual(self.status()["message"], "IRL4YOU ist aktuell.")

    def test_empty_repo(self):
        self.assertEqual(self.u.check(), (None, False))


class TestInstall(Base):
    def test_first_install(self):
        self.gh.add("2.0.0")
        self.assertTrue(self.u.install())
        root = self.overrides["root"]
        self.assertEqual(os.readlink(os.path.join(root, "current")), os.path.join(root, "releases", "2.0.0"))
        self.assertEqual(os.readlink(self.overrides["extra_link"]), os.path.join(root, "current"))
        with open(os.path.join(self.overrides["extra_link"], "server.py")) as f:
            self.assertIn("2.0.0", f.read())
        self.assertTrue(os.path.islink(os.path.join(root, "current", "web", "static")))
        self.assertEqual(self.hooks(), ["install 2.0.0 prev="])
        self.assertIn("restart pipbox.service", self.calls())
        s = self.status()
        self.assertEqual((s["state"], s["version"], s["progress"]), ("done", "2.0.0", 100))
        self.assertEqual(self.releases_on_disk(), ["2.0.0"])       # keine Reste vom Laden

    def test_update_and_prune(self):
        for v in ("2.0.0", "2.0.1", "2.0.2", "2.0.3"):
            self.gh.add(v)
            self.assertTrue(self.u.install(), v)
        self.assertEqual(self.u.active_version(), "2.0.3")
        self.assertEqual(self.u.previous_version(), "2.0.2")
        self.assertEqual(self.releases_on_disk(), ["2.0.1", "2.0.2", "2.0.3"])
        self.assertEqual(self.hooks()[-1], "install 2.0.3 prev=2.0.2")

    def test_not_newer(self):
        self.gh.add("2.0.0")
        self.u.install()
        self.assertEqual(self.u.run("install"), 2)
        self.assertEqual(self.status()["state"], "refused")
        self.assertIn("Keine neuere Version", self.status()["message"])

    def test_checksum_mismatch(self):
        self.gh.add("2.0.0")
        self.u.install()
        self.gh.add("2.0.1", bad_sum=True)
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("Prüfsumme", self.status()["message"])
        self.assertEqual(self.u.active_version(), "2.0.0")
        self.assertEqual(self.releases_on_disk(), ["2.0.0"])

    def test_hook_fails_rolls_back(self):
        self.gh.add("2.0.0")
        self.u.install()
        self.gh.add("2.0.1", pkg=make_pkg("2.0.1", hook=HOOK_FAIL))
        self.assertFalse(self.u.install())
        self.assertEqual(self.u.active_version(), "2.0.0")
        self.assertEqual(self.hooks()[-2:], ["install 2.0.1 prev=2.0.0", "rollback 2.0.0 prev=2.0.1"])
        self.assertEqual(self.status()["state"], "failed")
        self.assertEqual(self.releases_on_disk(), ["2.0.0"])
        with open(self.overrides["log_file"]) as f:
            self.assertIn("kaputt", f.read())

    def test_service_down_rolls_back(self):
        self.gh.add("2.0.0")
        self.u.install()
        self.gh.add("2.0.1")
        self.set_units([])                                         # pipbox.service startet nicht
        self.assertFalse(self.u.install())
        self.assertEqual(self.u.active_version(), "2.0.0")
        self.assertEqual(self.hooks()[-1], "rollback 2.0.0 prev=2.0.1")

    def test_not_while_sending(self):
        self.gh.add("2.0.0")
        self.set_units(["pipbox.service", "pipbox-send.service"])
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("gesendet", self.status()["message"])
        self.assertIsNone(self.u.active_version())

    def test_manifest_version_mismatch(self):
        self.gh.add("2.0.1", pkg=make_pkg("2.0.0"))
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("erwartet 2.0.1", self.status()["message"])

    def test_version_file_mismatch(self):
        self.gh.add("2.0.1", pkg=make_pkg("2.0.1", file_version="2.0.9"))
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("VERSION", self.status()["message"])

    def test_newer_updater_required(self):
        self.gh.add("2.0.1", pkg=make_pkg("2.0.1", manifest={"min_updater": 99}))
        self.assertEqual(self.u.run("install"), 2)
        self.assertIn("neueren Update-Helfer", self.status()["message"])

    def test_bad_unit_name(self):
        self.gh.add("2.0.1", pkg=make_pkg("2.0.1", manifest={"restart": ["pipbox.service; reboot"]}))
        self.assertEqual(self.u.run("install"), 2)

    def test_size_limit(self):
        self.gh.add("2.0.0")
        u = self.make(max_download_mb="0")
        self.assertEqual(u.run("install"), 2)
        self.assertIn("größer als erlaubt", u.load_status()["message"])

    def test_extra_link_real_dir(self):
        os.makedirs(self.overrides["extra_link"])
        self.gh.add("2.0.0")
        self.assertFalse(self.u.install())
        self.assertEqual(self.status()["state"], "failed")
        self.assertTrue(os.path.isdir(self.overrides["extra_link"]) and not os.path.islink(self.overrides["extra_link"]))

    def test_reboot_flag(self):
        self.gh.add("2.0.0", pkg=make_pkg("2.0.0", manifest={"reboot": True}))
        self.u.install()
        self.assertTrue(self.status()["reboot_required"])


class TestUnsafePackages(Base):
    def attempt(self, factory):
        self.gh.add("2.0.0", pkg=make_pkg("2.0.0", extra=[factory]))
        self.assertEqual(self.u.run("install"), 2, self.status())
        self.assertIsNone(self.u.active_version())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil")))

    def test_path_traversal(self):
        def f():
            ti = tarfile.TarInfo("../../../../evil")
            ti.size = 1
            return ti, b"x"
        self.attempt(f)

    def test_absolute_path(self):
        def f():
            ti = tarfile.TarInfo(os.path.join(self.tmp, "evil"))
            ti.size = 1
            return ti, b"x"
        self.attempt(f)

    def test_symlink_out(self):
        def f():
            ti = tarfile.TarInfo("./etc")
            ti.type = tarfile.SYMTYPE
            ti.linkname = "/etc"
            return ti, None
        self.attempt(f)

    def test_symlink_relative_out(self):
        def f():
            ti = tarfile.TarInfo("./a/b")
            ti.type = tarfile.SYMTYPE
            ti.linkname = "../../../evil"
            return ti, None
        self.attempt(f)

    def test_device(self):
        def f():
            ti = tarfile.TarInfo("./dev")
            ti.type = tarfile.CHRTYPE
            return ti, None
        self.attempt(f)

    def test_hardlink(self):
        def f():
            ti = tarfile.TarInfo("./hl")
            ti.type = tarfile.LNKTYPE
            ti.linkname = "server.py"
            return ti, None
        self.attempt(f)


class TestRollbackSwitch(Base):
    def setUp(self):
        super().setUp()
        for v in ("2.0.0", "2.0.1"):
            self.gh.add(v)
            self.u.install()

    def test_rollback(self):
        self.assertEqual(self.u.run("rollback"), 0)
        self.assertEqual(self.u.active_version(), "2.0.0")
        self.assertEqual(self.u.previous_version(), "2.0.1")
        self.assertEqual(self.hooks()[-1], "switch 2.0.0 prev=2.0.1")
        self.assertEqual(self.u.run("rollback"), 0)                # und wieder vor
        self.assertEqual(self.u.active_version(), "2.0.1")

    def test_switch_remote_older(self):
        self.gh.add("2.0.2")
        self.u.install()
        self.u.prune()
        subprocess.run(["rm", "-rf", os.path.join(self.overrides["root"], "releases", "2.0.0")])
        self.assertEqual(self.u.run("switch", "2.0.0"), 0, self.status())
        self.assertEqual(self.u.active_version(), "2.0.0")

    def test_switch_unknown(self):
        self.assertEqual(self.u.run("switch", "9.9.9"), 2)
        self.assertIn("gibt es im Repository nicht", self.status()["message"])

    def test_rollback_without_previous(self):
        subprocess.run(["rm", "-f", os.path.join(self.overrides["state_dir"], "previous")])
        self.assertEqual(self.u.run("rollback"), 2)


class TestAuto(Base):
    def test_only_reports_by_default(self):
        self.gh.add("2.0.0")
        self.u.auto()
        self.assertIsNone(self.u.active_version())
        self.assertTrue(self.status()["available"])

    def test_installs_when_allowed(self):
        self.gh.add("2.0.0")
        self.make(auto_install="true").auto()
        self.assertEqual(self.u.active_version(), "2.0.0")

    def test_waits_while_sending(self):
        self.gh.add("2.0.0")
        self.set_units(["pipbox.service", "pipbox-send.service"])
        self.make(auto_install="true").auto()
        self.assertIsNone(self.u.active_version())


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
        self.assertEqual(self.req("switch\n2.0.1\n"), ("switch", "2.0.1"))
        self.assertEqual(self.req("rollback\n"), ("rollback", ""))

    def test_invalid(self):
        for t in ("reboot", "install\n2.0.1", "switch", "switch\n2.0", "switch\n2.0.1\nextra", "check; rm -rf /", ""):
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
        self.gh.add("2.0.0")
        self.gh.redirect_assets = True
        u = self.make(token_file=self.token_file())
        self.assertTrue(u.install())
        api = [r for r in self.gh.requests if not r[1].startswith("/blob/")]
        blob = [r for r in self.gh.requests if r[1].startswith("/blob/")]
        self.assertTrue(api and blob)
        self.assertTrue(all(r[2] == "Bearer geheim123" for r in api))
        self.assertTrue(all(r[2] is None for r in blob))
        self.assertTrue(all(r[0].startswith("localhost") for r in blob))
        with open(self.overrides["log_file"]) as f:
            self.assertNotIn("geheim123", f.read())

    def test_token_file_must_be_private(self):
        self.gh.add("2.0.0")
        u = self.make(token_file=self.token_file(0o644))
        self.assertEqual(u.run("check"), 2)
        self.assertIn("chmod 600", u.load_status()["message"])

    def test_missing_token_file_is_public_mode(self):
        self.gh.add("2.0.0")
        u = self.make(token_file=os.path.join(self.tmp, "fehlt"))
        self.assertEqual(u.check(), ("2.0.0", True))
        self.assertTrue(all(r[2] is None for r in self.gh.requests))


class TestBuildScript(Base):
    def test_build_release_is_installable(self):
        src = os.path.join(self.tmp, "src")
        os.makedirs(os.path.join(src, "install"))
        with open(os.path.join(src, "server.py"), "w") as f:
            f.write("print('x')\n")
        out = os.path.join(self.tmp, "dist")
        subprocess.run([os.path.join(REPO, "tools", "build-release.sh"), src, out], check=True, capture_output=True,
                       env=dict(os.environ, SOURCE_DATE_EPOCH="1700000000"))
        with open(os.path.join(REPO, "VERSION")) as f:
            v = f.read().strip()
        pkg = os.path.join(out, "irl4you-%s.tar.gz" % v)
        with open(pkg, "rb") as f:
            data = f.read()
        with open(pkg + ".sha256") as f:
            self.assertEqual(f.read().split()[0], hashlib.sha256(data).hexdigest())
        tree = os.path.join(self.tmp, "tree")
        U.Updater.safe_extract(pkg, tree)
        m = U.Updater.read_manifest(tree, v)
        self.assertEqual(m["restart"], ["pipbox.service"])
        for p in ("hooks/install", "hooks/health", "updater/irl4you_update.py", "updater/systemd/irl4you-update.path",
                  "server.py"):
            self.assertTrue(os.path.isfile(os.path.join(tree, p)), p)
        self.assertTrue(os.access(os.path.join(tree, "hooks/install"), os.X_OK))
        for h in ("install", "health"):
            subprocess.run(["sh", "-n", os.path.join(tree, "hooks", h)], check=True)
        # reproduzierbar
        out2 = os.path.join(self.tmp, "dist2")
        subprocess.run([os.path.join(REPO, "tools", "build-release.sh"), src, out2], check=True, capture_output=True,
                       env=dict(os.environ, SOURCE_DATE_EPOCH="1700000000"))
        with open(os.path.join(out2, "irl4you-%s.tar.gz" % v), "rb") as f:
            self.assertEqual(f.read(), data)


if __name__ == "__main__":
    unittest.main()
