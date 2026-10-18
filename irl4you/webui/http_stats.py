"""IRL4YOU BOX Oberfläche: HTTP-Handler: Messwerte und Statistik für die Oberfläche."""

import os

from .camservices import HDMI_KEY
from .common import WEB_DIR, read
from .netstate import uplink_states
from .stats import build_stats_snapshot


class HttpStats:
    def conn_labels(self):
        base = dict(self.wifi.labels()) if self.wifi else {}
        base.update(self.names.conn_names() if self.names else {})
        return base

    def metrics_data(self, light=False):
        m = self.sampler.sample()
        try:
            m["alerts"] = list(m.get("alerts") or []) + self.usbwatch.alerts()
        except Exception:
            pass
        try:
            m["alerts"] = list(m.get("alerts") or []) + self.netaddr.warning()
        except Exception:
            pass
        m["cameras"] = self.cams.listing(self.host(), self.djisvc.host_for_key)
        parked = set()
        try:
            pc = self.pipeline.cfg
            inactive = set(pc.get("inactive") or []) if pc.get("type") == "pip" else set()
            parked = inactive | self.djisvc.parked_keys()
            pips = {pc.get(k) for k in ("pip", "pip2", "pip3") if pc.get(k)} if pc.get("type") == "pip" else set()
            for c in m["cameras"]:
                c["parked"] = c.get("key") in parked
                c["is_main"] = pc.get("type") == "pip" and c.get("key") == pc.get("main")
                c["in_pips"] = c.get("key") in pips
        except Exception:
            pass
        try:
            hs = self.hdmi.status() if self.hdmi else None
            m["alerts"] = list(m.get("alerts") or []) + self.outages.alerts(m["cameras"], hs, parked)
        except Exception:
            pass
        extras = self.djisvc.camera_extras()
        for c in m["cameras"]:
            c.update(extras.get(c["key"], {}))
        m["uplinks"] = uplink_states(((self.srtla.data or {}).get("settings") or {}).get("uplinks") or [])
        m["conn_names"] = self.conn_labels()
        pic = None if light else self.send.picture()
        for c in m["cameras"]:
            p = pic.get(c["key"]) if pic else None
            c["pic"], c["pic_wait"] = (p[0], p[1]) if p else (None, 0)
        measured = self.send.measured_fps()
        if self.fpsprobe:
            self.fpsprobe.keep({c["key"] for c in m["cameras"] if c.get("state") == "live"})
        for c in m["cameras"]:
            if c.get("state") == "live" and not c.get("fps"):
                if c["key"] in measured:
                    c["fps"], c["fps_measured"] = measured[c["key"]], True
                    continue
                f = self.djisvc.fps_for_key(c["key"])
                if f:
                    c["fps"], c["fps_set"] = float(f), True
                elif self.fpsprobe and c["key"] != HDMI_KEY:
                    p = self.fpsprobe.get(c["key"])
                    if p:
                        c["fps"], c["fps_measured"] = p, True
        return m

    @classmethod
    def stats_snapshot_now(cls):
        h = object.__new__(cls)
        h.headers = {}
        return cls.statsshare.snapshot(lambda: build_stats_snapshot(h.metrics_data(light=True), {"active": h.send.live_fast()}, h.conn_labels(), h.statsshare.groups()))

    def stats_status(self):
        st = self.statsshare.status()
        rs = self.remote.status()
        st.update(installed=rs["installed"], connected=rs["connected"], busy=rs["state"] == "working", state=rs["state"], message=rs["message"], hint_url=rs["hint_url"],
                  public=bool(rs.get("stats")), clients=self.statsserver.clients() if self.statsserver else 0, page_url="", ws_url="")
        base = rs.get("stats_base") or ""
        if st["enabled"] and st["token"] and base.startswith("https://"):
            st["page_url"] = base + "/?t=" + st["token"]
            st["ws_url"] = "wss://" + base[len("https://"):] + "/ws?t=" + st["token"]
        return st

    def stats_widget(self):
        st = self.stats_status()
        if not st["ws_url"]:
            return self.reply(409, {"error": "Die öffentliche Statistik ist nicht freigegeben"})
        page = read(os.path.join(WEB_DIR, "statistik.html"), None)
        if page is None:
            return self.reply(404, {"error": "statistik.html fehlt"})
        body = page.replace("__STATS_URL__", st["ws_url"]).encode("utf-8")
        return self.send_bytes(200, body, "text/html; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="statistik.html"'})

    def phone_view_wanted(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, val = part.strip().partition("=")
            if k == "pb_view_mode" and val == "mobile":
                return True
        return False
