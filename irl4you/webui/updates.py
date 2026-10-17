"""IRL4YOU BOX Oberfläche: Software-Update von IRL4YOU (Update-Helfer) und System-Updates (apt)."""

import json
import os
import re
import threading
import time

from .common import APP_DIR, belacoder_running, installed_versions, read


class SwUpdate:
    """Software-Update von IRL4YOU über den Update-Helfer (irl4you-update, Repo irl4you_2604). COMMIT_MODEL: Die Box folgt den Commits von main;
    eine Version heißt auf der Box wie die ersten 12 Zeichen ihres Commits, angezeigt wird "VERSION (Commit)". Der Helfer läuft als root,
    Repo und Zugang stehen in /etc/irl4you/update.conf (die Oberfläche kann sie nicht ändern). Anfrage: Stichwort in swupdate-request
    (check, install, rollback, switch + Commit in Zeile 2), Antwort: /run/pipbox-swupdate/status.json."""
    STATUS = "/run/pipbox-swupdate/status.json"
    RELEASES = "/opt/irl4you/releases"
    CURRENT = "/opt/irl4you/current"
    PREVIOUS = "/var/lib/irl4you/previous"
    HELPER = "/usr/local/sbin/irl4you-update"
    ISSUES = "https://github.com/Bittersweet1987/irl4you_2604/issues"
    STAGE = ""
    UPDATER_STATUS_MAX_AGE = 6 * 3600
    CHECK_WAIT = 20            # so lange nach einer Anfrage nicht gleich noch eine stellen
    HEX_RE = re.compile(r"^[0-9a-f]{7,40}$")
    ID_RE = re.compile(r"^[0-9a-f]{12}$")

    def __init__(self, state_dir, demo, send):
        self.req = os.path.join(state_dir, "swupdate-request")
        self.demo, self.send = demo, send
        self.lock = threading.Lock()
        self.asked = 0.0
        here = APP_DIR
        self.version = (read(os.path.join(here, "VERSION"), "") or "0.0.0").strip()
        self.fake = {}
        self.fake_t0 = 0.0

    # ---- Stand dieser Box
    def current_id(self):
        """Kennung der aktiven Version (12 Zeichen des Commits) oder ''."""
        if self.demo:
            return "a84e4b3c9d01"
        try:
            n = os.path.basename(os.readlink(self.CURRENT).rstrip("/"))
        except OSError:
            n = ""
        if not self.ID_RE.match(n):
            try:
                with open(os.path.join(APP_DIR, "manifest.json")) as f:
                    n = str(json.load(f).get("commit") or "")[:12]
            except (OSError, ValueError, AttributeError):
                n = ""
        return n if self.ID_RE.match(n) else ""

    def label(self):
        cid = self.current_id()
        return "%s (%s)" % (self.version, cid[:7]) if cid else self.version

    def _status_file(self):
        try:
            with open(self.STATUS) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_request(self, text):
        fd = os.open(self.req, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(text)

    def check(self, force=False, fresh=False):
        """Der Helfer prüft selbst (Timer alle 6 Stunden). Hier nur auf Wunsch (force) eine Prüfung anstoßen; sie läuft nie während einer Sendung."""
        if self.demo:
            return {"checked": int(time.time()), "latest": "b7c3d21", "available": True, "notes": "- Beispiel für einen neuen Stand."}
        st = self._status_file()
        if force and st.get("state") not in ("installing", "checking") and time.time() - self.asked > self.CHECK_WAIT and not self.send._active() \
                and os.path.exists(self.HELPER):
            self.asked = time.time()
            try:
                self._write_request("check\n")
            except OSError:
                pass
        return st

    def auto_loop(self):
        """Nichts zu tun: den Takt gibt irl4you-update-auto.timer vor."""
        return

    def installed(self):
        """[(Kennung, Anzeigename)] der Versionen auf der Box."""
        if self.demo:
            return [("a84e4b3c9d01", "2.0.0-rc.1 (a84e4b3)"), ("1bde25141847", "2.0.0-rc.1 (1bde251)")]
        out = []
        try:
            names = os.listdir(self.RELEASES)
        except OSError:
            return out
        for n in names:
            m = os.path.join(self.RELEASES, n, "manifest.json")
            if self.ID_RE.match(n) and os.path.isfile(m):
                try:
                    with open(m) as f:
                        v = str(json.load(f).get("version") or "")
                except (OSError, ValueError):
                    v = ""
                out.append((os.stat(m).st_mtime, n, "%s (%s)" % (v, n[:7]) if v else n[:7]))
        return [(n, lab) for _, n, lab in sorted(out, reverse=True)]

    def previous_id(self):
        if self.demo:
            return "1bde25141847"
        p = (read(self.PREVIOUS, "") or "").strip()
        ids = [n for n, _ in self.installed()]
        return p if self.ID_RE.match(p) and p in ids and p != self.current_id() else ""

    def backups(self):
        return [n for n, _ in self.installed()]

    def history(self):
        if self.demo:
            return {"text": "## b7c3d21\n- Beispiel für einen neuen Stand.\n\n## a84e4b3\n- Erster Stand.", "error": ""}
        st = self._status_file()
        parts = []
        for r in st.get("releases") or []:
            if isinstance(r, dict) and self.HEX_RE.match(str(r.get("version", ""))):
                parts.append("## %s\n%s" % (r["version"], str(r.get("notes") or "").strip()))
        if not parts:
            return {"text": "", "error": "Noch keine Liste: bitte zuerst nach Updates suchen." if os.path.exists(self.HELPER) else "Der Update-Helfer ist nicht installiert."}
        return {"text": "\n\n".join(parts), "error": ""}

    def versions(self, st=None):
        """Stände auf der Box und die letzten Commits von GitHub, neueste zuerst."""
        st = self._status_file() if st is None else st
        cur = self.current_id()
        inst = dict(self.installed())
        rels = [r for r in (st.get("releases") or []) if isinstance(r, dict) and self.HEX_RE.match(str(r.get("version", "")))]
        res, seen = [], set()
        pos = {str(r.get("commit") or r["version"])[:12]: i for i, r in enumerate(rels)}
        cur_pos = pos.get(cur)
        for r in rels:
            full = str(r.get("commit") or r["version"])
            rid = full[:12]
            seen.add(rid)
            relation = "aktuell" if rid == cur else ("neuer" if cur_pos is None or pos[rid] < cur_pos else "älter")
            res.append({"version": rid[:7], "id": rid, "label": inst.get(rid) or rid[:7], "local": rid in inst, "github": True,
                        "current": rid == cur, "date": str(r.get("published", ""))[:10], "notes": str(r.get("notes", ""))[:300], "relation": relation})
        for rid, lab in inst.items():
            if rid not in seen:
                res.append({"version": rid[:7], "id": rid, "label": lab, "local": True, "github": False, "current": rid == cur,
                            "date": "", "notes": "", "relation": "aktuell" if rid == cur else "älter"})
        if cur and cur not in seen and cur not in inst:
            res.append({"version": cur[:7], "id": cur, "label": self.label(), "local": False, "github": False, "current": True, "date": "", "notes": "", "relation": "aktuell"})
        return res

    @staticmethod
    def _pct(st):
        p = st.get("progress")
        return p if isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 100 else 0

    def demo_fake(self):
        t0 = self.fake_t0
        steps = ((0, 2, "Lade den neuen Stand von GitHub"), (2, 22, "Prüfe das Archiv"), (4, 36, "Entpacke den Stand"),
                 (6, 58, "Schalte auf die neue Version um"), (10, 95, "Starte die Dienste neu"))
        age = time.time() - t0
        if age >= 12:
            return {"state": "done", "message": "Demo: Update vorgetäuscht.", "time": int(time.time()), "progress": 100}
        cur = [x for x in steps if x[0] <= age][-1]
        return {"state": "installing", "step": cur[2], "progress": cur[1], "time": int(time.time())}

    def progress_public(self):
        st = (self.demo_fake() if self.fake_t0 else {}) if self.demo else self._status_file()
        state = st.get("state") if st.get("state") in ("installing", "done", "rolledback", "failed", "refused") else "idle"
        if state != "installing" and (not st.get("time") or time.time() - st["time"] > 6 * 3600):
            state = "idle"
        step = st.get("step", "")
        return {"state": state, "step": step if state == "installing" and isinstance(step, str) else "", "progress": self._pct(st)}

    def status(self, force=False, fresh=False):
        chk = self.check(force, fresh)
        st = ((self.demo_fake() if self.fake_t0 else dict(self.fake)) or {}) if self.demo else chk
        latest = chk.get("latest") if self.HEX_RE.match(str(chk.get("latest") or "")) else None
        state = st.get("state", "idle")
        out = {"current": self.label(), "stage": self.STAGE, "latest": latest, "notes": str(chk.get("notes") or "")[:4000] if chk.get("available") else "",
               "error": "", "checked_at": chk.get("checked") or chk.get("checked_at"),
               "newer": bool(latest and chk.get("available")),
               "state": state if state in ("installing", "done", "rolledback", "failed", "refused") else "idle",
               "step": st.get("step", "") if isinstance(st.get("step"), str) else "", "message": str(st.get("message", ""))[:300],
               "frm": st.get("frm", ""), "to": st.get("to", ""), "progress": self._pct(st),
               "reboot_required": bool(st.get("reboot_required"))}
        if state == "checking":
            out["checking"] = True
        if out["state"] not in ("idle", "installing") and st.get("time") and time.time() - st["time"] > self.UPDATER_STATUS_MAX_AGE:
            out["state"], out["message"] = "idle", ""
        if out["state"] == "idle" and chk.get("message") and chk.get("available") is False:
            out["message"] = str(chk.get("message"))[:300]
        if not self.demo and not os.path.exists(self.HELPER):
            out["error"] = "Der Update-Helfer ist auf dieser Box nicht installiert."
        prev = self.previous_id()
        lab = dict(self.installed())
        out["backup_version"] = lab.get(prev, prev[:7]) if prev else ""
        out["versions"] = self.versions({} if self.demo else st)
        out["sending"] = False if self.demo else bool(belacoder_running() or self.send._active())
        out["helper_installed"] = self.demo or os.path.exists(self.HELPER)
        return out

    def request(self, action, confirm, version=None, older=False):
        if action not in ("install", "rollback", "switch"):
            raise ValueError("Unbekannte Aktion")
        if confirm is not True:
            raise ValueError("Bestätigung fehlt")
        st = self.status()
        if not st["helper_installed"]:
            raise ValueError("Der Update-Helfer ist nicht installiert")
        if st["sending"]:
            raise ValueError("Es wird gerade gesendet. Bitte zuerst die Übertragung beenden.")
        if st["state"] == "installing":
            raise ValueError("Ein Update läuft bereits")
        if action == "install" and not st["newer"]:
            raise ValueError("Es gibt keinen neueren Stand")
        if action == "rollback" and not st["backup_version"]:
            raise ValueError("Es gibt keine vorherige Version")
        if action == "switch":
            v = str(version or "").strip().lower()
            if not self.HEX_RE.match(v):
                raise ValueError("Bitte einen Stand aus der Liste wählen (Commit, mindestens 7 Zeichen)")
            known = [x for x in st["versions"] if x["id"].startswith(v[:12]) or v.startswith(x["id"])]
            if not known or not (known[0]["local"] or known[0]["github"]):
                raise ValueError("Dieser Stand ist weder auf der Box noch auf GitHub bekannt")
            if known[0]["current"]:
                raise ValueError("Dieser Stand ist schon installiert")
            if known[0]["relation"] == "älter" and older is not True:
                raise ValueError("Das ist ein älterer Stand. Bitte ausdrücklich bestätigen.")
            version = known[0]["id"]
        if self.demo:
            self.fake_t0 = time.time()
            return
        self._write_request(action + "\n" + (version + "\n" if action == "switch" else ""))


class Updates:
    MODES = ("check", "dry", "run", "reboot")

    def __init__(self, state_dir, demo):
        self.demo = demo
        self.req = os.path.join(state_dir, "update-request")
        self.status_path = os.path.join(state_dir, "update-status.json")
        self.log_path = os.path.join(state_dir, "update.log")
        self.fake = {}
        self.lock = threading.Lock()
        self.last_try = 0.0

    def boot_id(self):
        return (read("/proc/sys/kernel/random/boot_id", "demo") or "demo").strip()

    def reboot_done(self, st):
        rb = st.get("reboot_boot_id")
        if rb and rb != self.boot_id():
            return True
        try:
            up = float((read("/proc/uptime", "") or "0").split()[0])
            return bool(st.get("finished")) and st["finished"] < time.time() - up
        except (ValueError, IndexError, TypeError):
            return False

    def status(self):
        if self.demo:
            st = dict(self.fake) or {"state": "never"}
            versions = {"belabox-linux-rk3588": "20241120-2", "belaui": "20250518-5",
                        "belacoder": "20250518-1"}
            log = st.pop("log", "")
            kernel = "5.10.160-belabox (Demo)"
        else:
            try:
                with open(self.status_path) as f:
                    st = json.load(f)
            except (OSError, ValueError):
                st = {"state": "never"}
            versions = installed_versions()
            log = ""
            try:
                with open(self.log_path) as f:
                    log = "".join(f.readlines()[-60:])
            except OSError:
                pass
            kernel = os.uname().release
        st["reboot_pending"] = bool(st.get("reboot_required")) and st.get("reboot_boot_id") == self.boot_id()
        if st.get("state") == "rebooting" and self.reboot_done(st):
            st["state"] = "done"
            st["message"] = "Die Box ist nach dem Neustart wieder oben."
        st["versions"] = versions
        st["kernel_running"] = kernel
        st["streaming"] = belacoder_running() if not self.demo else False
        st["helper_installed"] = self.demo or os.path.exists("/etc/systemd/system/pipbox-update.path")
        st["log"] = log
        return st

    def request(self, mode, confirm):
        if mode not in self.MODES:
            raise ValueError("Unbekannte Aktion")
        if mode in ("run", "reboot") and not confirm:
            raise ValueError("Bestätigung fehlt")
        cur = self.status()
        if cur.get("state") == "running":
            raise ValueError("Es läuft bereits eine Aktion")
        if mode in ("run", "reboot") and cur["streaming"]:
            raise ValueError("Übertragung läuft. Bitte zuerst den Stream beenden.")
        if not cur["helper_installed"]:
            raise ValueError("Update-Helfer ist nicht installiert")
        if self.demo:
            threading.Thread(target=self._fake, args=(mode,), daemon=True).start()
            return
        fd = os.open(self.req, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(mode + "\n")

    AUTO_EVERY = 6 * 3600
    AUTO_RETRY = 3600
    AUTO_AFTER_BOOT = 2 * 60
    EARLY_UPTIME = 30 * 60
    AUTO_RETRY_EARLY = 5 * 60

    @classmethod
    def auto_check_due(cls, st, now, uptime, streaming, request_pending, last_try, helper=True):
        if not helper or streaming or request_pending or uptime < cls.AUTO_AFTER_BOOT:
            return False
        if st.get("state") in ("running", "rebooting"):
            return False
        retry = cls.AUTO_RETRY_EARLY if uptime < cls.EARLY_UPTIME else cls.AUTO_RETRY
        if last_try and now - last_try < retry:
            return False
        last = st.get("last_check") or 0
        if last < now - uptime:
            return True
        return now - last >= cls.AUTO_EVERY

    def auto_check(self, now=None, last_try=None, present=False):
        if self.demo:
            return False
        try:
            uptime = float((read("/proc/uptime", "") or "0").split()[0])
        except (ValueError, IndexError):
            uptime = 0.0
        if present:
            uptime = max(uptime, float(self.AUTO_AFTER_BOOT))
        st = self.status()
        if last_try is None:
            last_try = self.last_try
        if not self.auto_check_due(st, now or time.time(), uptime, st.get("streaming", False), os.path.exists(self.req), last_try,
                                   helper=st.get("helper_installed", False)):
            return False
        fd = os.open(self.req, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("autocheck\n")
        self.last_try = time.time()
        return True

    def auto_loop(self):
        time.sleep(30)
        while True:
            try:
                self.auto_check()
            except Exception as e:
                print("auto_check:", e)
            try:
                early = float((read("/proc/uptime", "") or "0").split()[0]) < self.EARLY_UPTIME
            except (ValueError, IndexError):
                early = False
            time.sleep(60 if early else 15 * 60)

    def _fake(self, mode):
        f = self.fake
        f.update(state="running", mode=mode, message="")
        time.sleep(1.5)
        if mode == "run":
            total = 12
            for i in range(total + 1):
                f["progress"] = {"downloading": min(i * 2, total), "unpacking": max(0, i - 4),
                                 "setting_up": max(0, i - 8), "total": total}
                f["log"] = f"Get:{i} http://repo.example ...\nUnpacking paket-{i} ...\n"
                time.sleep(0.6)
            f.update(state="done", message="Update abgeschlossen.", reboot_required=True,
                     reboot_boot_id=self.boot_id(), available=0, belabox=[], packages=[])
        elif mode == "reboot":
            f.update(state="rebooting", message="Neustart wird eingeleitet. (Demo)")
        else:
            f.update(state="done", mode=mode, available=224, download="412 MB",
                     packages=["belaui", "belacoder", "belabox-linux-rk3588", "libc6"],
                     belabox=["belaui", "belacoder", "belabox-linux-rk3588"],
                     would_reboot=True, last_check=int(time.time()), held=[])
