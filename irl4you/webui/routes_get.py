"""IRL4YOU BOX Oberfläche: HTTP-Handler: lesende Anfragen (GET)."""

import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .actions import rotation_state
from .auth import Auth
from .cameras import label_bluetooth
from .common import WEB_DIR, iface_ips, read
from .webfiles import static_file


PHONE_FRAME = """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>IRL4YOU BOX</title>
<script>try{if(window.top!==window||matchMedia("(max-width:620px)").matches)location.replace("/?app=1")}catch(e){location.replace("/?app=1")}</script></head>
<body style="margin:0;background:#0f172a"><iframe title="IRL4YOU BOX" src="/?app=1" style="display:block;margin:0 auto;border:0;width:480px;max-width:100%;height:100vh;height:100dvh"></iframe>
<script>try{var t=localStorage.getItem("pb_theme"),v=JSON.parse(localStorage.getItem("pb_views")||"null"),d=v&&v.mobile&&v.mobile.design;if(t==="light"||(t!=="dark"&&d==="klar"))document.body.style.background="#f1f5f9"}catch(e){}</script></body></html>"""


class GetRoutes:
    def do_GET(self):
        self.request_read()
        path = self.path.split("?")[0]
        if (path == "/i18n.js" or path.startswith("/i18n/")) and self.i18n_file(path):
            return
        if path in ("/", "/index.html"):
            if self.authed() and "app=1" not in self.path and self.phone_view_wanted():
                return self.send_bytes(200, PHONE_FRAME.encode("utf-8"), "text/html; charset=utf-8")
            return self.page("index.html" if self.authed() else "login.html")
        if path == "/api/auth":
            out = {"configured": self.auth.configured, "mode": self.auth.mode, "authed": self.authed(), "setup": self.auth.setup_needed}
            if self.auth.mode == "demo":
                out["demo_password"] = Auth.DEMO_PASSWORD
            return self.reply(200, out)
        if path == "/api/swprogress":
            return self.reply(200, self.swupdate.progress_public())
        if not self.authed():
            return self.reply(401, {"error": "nicht angemeldet"})
        sf = static_file(path)
        if sf:
            return self.send_bytes(200, sf[0], sf[1])
        if path == "/modem.js":
            body = read(os.path.join(WEB_DIR, "modem.js"), "")
            return self.send_bytes(200, body.encode(), "application/javascript; charset=utf-8")
        if path == "/api/modems":
            return self.reply(200, self.modems.status())
        if path in ("/chat.js", "/chat.css"):
            body = read(os.path.join(WEB_DIR, path[1:]), "")
            return self.send_bytes(200, body.encode(), "application/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
        if path == "/api/statsshare":
            return self.reply(200, self.stats_status())
        if path == "/api/statsshare/widget":
            return self.stats_widget()
        if path == "/api/metrics":
            return self.reply(200, self.metrics_data())
        if path == "/api/previewaccess":
            return self.reply(200, dict(self.previewaccess.status(), origin=self.origin()))
        if path == "/api/preview":
            org = self.origin()
            if not self.preview:
                return self.reply(200, {"available": False, "why": "missing", "origin": org})
            if not self.previewaccess.allowed(org):
                return self.reply(200, {"available": False, "why": "extern", "origin": org})
            if not self.send._active():
                return self.reply(200, {"available": False, "why": "off", "origin": org})
            st = self.preview.status()
            st["origin"] = org
            if org == "extern":
                st.update(ext_width=self.previewaccess.EXT_WIDTH, ext_fps=self.previewaccess.EXT_FPS)
                if self.previewaccess.status()["ext_viewers"] >= self.previewaccess.EXT_MAX:
                    st.update(available=False, why="busy")
            return self.reply(200, st)
        if path == "/api/preview/stream":
            return self.preview_stream()
        if path == "/api/controller-keys":
            return self.reply(200, self.ckeys.snapshot())
        if path == "/api/logmode":
            return self.reply(200, self.logmode.status())
        if path == "/api/layout":
            return self.reply(200, self.layout.get())
        if path == "/api/deck":
            return self.reply(200, self.deck.get())
        if path == "/api/pipeline/rotation":
            return self.reply(200, rotation_state(self.pipeline, self.cams))
        if path == "/api/hub":
            return self.reply(200, dict(self.hub.get(), port=self.hub_port))
        if path == "/api/btdriver":
            return self.reply(200, self.btdriver.status())
        if path == "/api/logs":
            return self.reply(200, self.logbundle.status())
        if path == "/api/settings/progress":
            return self.reply(200, dict(self.transfer.progress))
        if path == "/api/settings":
            return self.reply(200, {"has_backup": os.path.isfile(self.transfer.backup_path), "sending": bool(self.send._active())})
        if path == "/api/developer":
            return self.reply(200, self.developer.status())
        if path == "/api/encoder":
            return self.reply(200, self.encmode.status())
        if path == "/api/developer/password":
            try:
                return self.reply(200, self.developer.password())
            except ValueError as e:
                return self.reply(404, {"error": str(e)})
        if path == "/api/logs/file":
            body = self.logbundle.content()
            if body is None:
                return self.reply(404, {"error": "Es liegt noch keine fertige Protokolldatei vor"})
            return self.send_bytes(200, body, "text/plain; charset=utf-8",
                                   headers={"Content-Disposition": 'attachment; filename="irl4you-protokolle.txt"'})
        if path == "/api/power":
            return self.reply(200, self.power.status())
        if path == "/api/wifi":
            return self.reply(200, self.wifi.status())
        if path == "/api/wifi/hotspot":
            q = urllib.parse.parse_qs((self.path.split("?", 1) + [""])[1])
            try:
                return self.reply(200, self.wifi.hotspot_secret((q.get("iface") or [""])[0]))
            except ValueError as e:
                return self.reply(404, {"error": str(e)})
        if path == "/api/remote":
            return self.reply(200, self.remote.status())
        if path == "/api/swupdate":
            q = (self.path.split("?", 1) + [""])[1]
            return self.reply(200, self.swupdate.status(force="check=1" in q, fresh="fresh=1" in q))
        if path == "/api/swupdate/history":
            return self.reply(200, self.swupdate.history())
        if path == "/api/support":
            return self.reply(200, {"cases": self.support.list(), "version": self.swupdate.version, "issues": "https://github.com/Bittersweet1987/irl4you_2604/issues",
                                    "now": int(time.time()), "delete_window": int(self.support.DELETE_WINDOW)})
        if path == "/api/dji":
            st = label_bluetooth(self.djisvc.status(), self.names)
            return self.reply(200, st)
        if path == "/api/uiaccess":
            return self.reply(200, self.uiaccess.status(self.local_ip()))
        if path == "/api/netaddr":
            return self.reply(200, self.netaddr.status())
        if path == "/api/twitch":
            return self.reply(200, self.twitch.status())
        if path == "/api/sysalerts":
            return self.reply(200, self.sysalerts.status())
        if path == "/api/twitch/login":
            return self.reply(200, self.twitchaccounts.status(self.headers.get("x-pb-owner", "")))
        if path == "/api/twitch/bot":
            return self.reply(200, self.twitchbot.status())
        if path == "/api/chat":
            qs = urllib.parse.parse_qs((self.path.split("?", 1) + [""])[1])
            try:
                since = max(0, int((qs.get("since") or ["0"])[0]))
            except ValueError:
                since = 0
            out = self.chatreader.poll(since)
            out["account"] = self.twitchaccounts.status(self.headers.get("x-pb-owner", ""))
            out["youtube"] = self.youtubepublic.status() if self.youtubepublic.ready() else {"state": "aus"}
            out["events"] = self.chatevents.status() if getattr(self, "chatevents", None) else {"state": "aus", "types": [], "error": ""}
            return self.reply(200, out)
        if path == "/api/youtube":
            return self.reply(200, {"chat": self.youtubepublic.status(), "handle": self.youtubepublic.channel})
        if path == "/api/hdmi":
            return self.reply(200, self.hdmi.status())
        if path == "/api/network":
            return self.reply(200, self.netchoice.status())
        if path == "/api/srtla":
            return self.reply(200, {**self.srtla.public(), "interfaces": iface_ips(), "conn_names": self.conn_labels()})
        if path == "/api/pipeline":
            st = self.pipeline.status(self.cams.listing(""))
            st["live"] = {"main": self.send.delay_live(), "pips": self.send.delay_live_pips()}
            return self.reply(200, st)
        if path == "/api/send":
            out = self.send.status()
            out["autostart"] = self.autostart.status()
            return self.reply(200, out)
        self.reply(404, {"error": "not found"})
