"""IRL4YOU BOX Oberfläche: Start der Oberfläche: Teile anlegen und den Server starten."""

import argparse
import os
import threading
import time

import controller_keys
import pipbox_modem
from twitch import (ChatPaths, HelixChat, ModSessions, SysAlerts, TwitchAccounts, TwitchBotLogin, TwitchChat, TwitchEvents,
                    TwitchLogin, TwitchMod, TwitchNotifier, TwitchReader, TwitchSender, TwitchStore)

try:
    import pipbox_preview
except ImportError:
    pipbox_preview = None

from .access import ExtraAddress, PreviewAccess, SupportCases, UiAccess
from .actions import controller_action
from .auth import Auth
from .cameras import CameraStore, DeviceNames, FpsProbe
from .camservices import DjiService, HdmiService
from .common import APP_DIR, iface_ips
from .handler import Handler
from .httpserver import LimitedHTTPServer
from .layout import DeckStore, LayoutStore
from .netstate import IfaceMemory, NetChoice, SrtlaStore
from .pipeline import PipelineStore
from .remote import Remote
from .sampler import Sampler
from .send import SendControl
from .settings_transfer import SettingsTransfer
from .stats import StatsServer, StatsShare
from .system import AutoStart, BtDriver, Developer, LogBundle, LogMode, Power
from .updates import SwUpdate
from .usbwatch import OutageWatch, UsbWatch
from .wifi import Wifi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--demo", action="store_true", help="Beispielwerte statt /proc")
    ap.add_argument("--allow-public", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--state", default=os.path.join(APP_DIR, "state"),
                    help="Ordner für Passwort-Hash und Kameraliste")
    ap.add_argument("--bela-config", default="", help=argparse.SUPPRESS)      # veraltet, ohne Wirkung (alte Dienstdateien nennen es noch)
    ap.add_argument("--extra-port", type=int, default=0, help="zusätzlicher Port (z. B. 80), gleiche Oberfläche")
    ap.add_argument("--rtmp-port", type=int, default=1935, help="RTMP-Port, den Kameras nutzen")
    ap.add_argument("--rtmp-app", default="publish", help="nginx-rtmp-Applikation")
    ap.add_argument("--rtmp-stat-url", default="", help="nginx-rtmp-Statistik (XML), z. B. http://127.0.0.1/stat")
    args = ap.parse_args()
    Handler.djisvc = None
    Handler.auth = Auth(args.state, demo=args.demo and args.host in ("127.0.0.1", "::1", "localhost"))
    Handler.cams = CameraStore(os.path.join(args.state, "cameras.json"), args.rtmp_app, args.rtmp_stat_url, args.demo)
    Handler.outages = OutageWatch()
    Handler.usbwatch = UsbWatch(os.path.join(args.state, "usb-events.json"), demo=args.demo)
    Handler.support = SupportCases(os.path.join(args.state, "support-cases.json"))
    Handler.sampler = Sampler(args.demo)
    Handler.sampler.sample()
    Handler.srtla = SrtlaStore(os.path.join(args.state, "srtla.json"))
    Handler.pipeline = PipelineStore(os.path.join(args.state, "pipeline.json"))
    Handler.send = SendControl(args.state, Handler.srtla, Handler.pipeline, Handler.cams, args.demo)
    Handler.preview = pipbox_preview.Client() if pipbox_preview and not args.demo else None
    Handler.swupdate = SwUpdate(args.state, args.demo, Handler.send)
    if not args.demo:
        threading.Thread(target=Handler.swupdate.auto_loop, daemon=True).start()
    Handler.remote = Remote(args.state, args.demo)
    Handler.netchoice = NetChoice(os.path.join(args.state, "camera-net.json"))
    Handler.names = DeviceNames(args.state)
    Handler.layout = LayoutStore(args.state)
    Handler.deck = DeckStore(args.state)
    Handler.statsshare = StatsShare(args.state, demo=args.demo)
    Handler.fpsprobe = FpsProbe("rtmp://127.0.0.1:%d/%s" % (args.rtmp_port, args.rtmp_app), os.path.join(args.state, "gst-registry.bin"), demo=args.demo)
    Handler.statsserver = StatsServer(Handler.statsshare, Handler.stats_snapshot_now)
    if not args.demo:
        Handler.statsserver.start()
    Handler.wifi = Wifi(args.state, args.demo, Handler.netchoice, Handler.names, Handler.srtla)
    Handler.power = Power(args.state, args.demo, Handler.send)
    Handler.logmode = LogMode(args.state, args.demo)
    Handler.btdriver = BtDriver(args.state, args.demo)
    Handler.logbundle = LogBundle(args.state, args.demo)
    Handler.developer = Developer(args.state, args.demo)
    Handler.autostart = AutoStart(args.state, Handler.send, args.demo)
    if not args.demo:
        threading.Thread(target=Handler.autostart.run, daemon=True).start()
    Handler.cams.ipfn = Handler.netchoice.ip
    Handler.djisvc = DjiService(args.state, Handler.cams, args.rtmp_app, args.rtmp_port, args.demo)
    Handler.djisvc.pipeline = Handler.pipeline
    Handler.ckeys = controller_keys.ControllerKeys(args.state, lambda fn: controller_action(fn, Handler.pipeline, Handler.cams, Handler.send), demo=args.demo)
    Handler.ckeys.start()
    Handler.transfer = SettingsTransfer(args.state, Handler.cams, Handler.pipeline, Handler.srtla, Handler.autostart, Handler.names, Handler.djisvc,
                                        Handler.wifi, Handler.send, args.demo)
    def chat_sources():
        ups = list(((Handler.srtla.data or {}).get("settings") or {}).get("uplinks") or [])
        ips = {x["iface"]: x["ip"] for x in iface_ips() if x.get("ip")}
        return [ips[u] for u in ups if u in ips]
    Handler.chatpaths = ChatPaths(chat_sources)
    Handler.transfer.netchoice = Handler.netchoice
    if not args.demo:
        mem = IfaceMemory(os.path.join(args.state, "iface-macs.json"))
        try:
            mem.reconcile(Handler.srtla, Handler.netchoice, Handler.cams, Handler.wifi, Handler.names)
        except Exception as e:
            print("iface_macs:", type(e).__name__, flush=True)
        threading.Thread(target=mem.run, args=(Handler.srtla, Handler.netchoice, Handler.cams, Handler.wifi, Handler.names), daemon=True).start()
    Handler.twitch = TwitchNotifier(TwitchStore(os.path.join(args.state, "twitch.json")), Handler.djisvc, Handler.cams, Handler.send, chat=TwitchChat(paths=Handler.chatpaths), demo=args.demo)
    Handler.sysalerts = SysAlerts(os.path.join(args.state, "sysalerts.json"), Handler.twitch, Handler.sampler, demo=args.demo)
    Handler.twitchlogin = TwitchLogin(os.path.join(args.state, "twitch-login.json"), demo=args.demo, paths=Handler.chatpaths)
    Handler.twitch.store.account = Handler.twitchlogin
    Handler.twitchbot = TwitchBotLogin(os.path.join(args.state, "twitch-bot-login.json"), demo=args.demo, paths=Handler.chatpaths)
    Handler.twitchsessions = ModSessions(args.state, demo=args.demo, paths=Handler.chatpaths)
    Handler.twitchaccounts = TwitchAccounts(Handler.twitchlogin, Handler.twitchsessions, store=Handler.twitch.store)
    Handler.twitch.store.bot = Handler.twitchbot
    if not args.demo:
        threading.Thread(target=Handler.twitchlogin.keep, daemon=True).start()
        threading.Thread(target=Handler.twitchbot.keep, daemon=True).start()
    Handler.chatreader = TwitchReader(Handler.twitch.store, demo=args.demo, paths=Handler.chatpaths)
    Handler.chatmod = TwitchMod(Handler.twitch.store, Handler.twitchlogin, paths=Handler.chatpaths, demo=args.demo, demo_reader=Handler.chatreader if args.demo else None)
    Handler.chathelix = HelixChat(Handler.twitchlogin, Handler.chatmod)
    Handler.chatsender = TwitchSender(Handler.twitch.store, chat=TwitchChat(paths=Handler.chatpaths), demo_reader=Handler.chatreader if args.demo else None, mod=Handler.chatmod, helix=Handler.chathelix)
    Handler.twitchaccounts.check = Handler.chatmod.is_moderator
    Handler.chatevents = TwitchEvents(Handler.twitch.store, Handler.twitchlogin, Handler.chatmod, Handler.chatreader, paths=Handler.chatpaths)
    if not args.demo:
        Handler.chatreader.events = Handler.chatevents
    Handler.hdmi = HdmiService(args.state, Handler.cams, args.demo)
    Handler.transfer.hdmi, Handler.transfer.twitch = Handler.hdmi, Handler.twitch.store
    if not args.demo:
        threading.Thread(target=Handler.twitch.run, daemon=True).start()
        threading.Thread(target=Handler.sysalerts.run, daemon=True).start()

    def watcher():
        while True:
            try:
                Handler.cams.auto_add()
            except Exception as e:
                print("auto_add:", e)
            time.sleep(3)
    threading.Thread(target=watcher, daemon=True).start()
    Handler.uiaccess = UiAccess(os.path.join(args.state, "ui-access.json"), demo=args.demo)
    Handler.previewaccess = PreviewAccess(os.path.join(args.state, "preview-access.json"), demo=args.demo)
    Handler.netaddr = ExtraAddress(args.state, demo=args.demo)
    Handler.modems = pipbox_modem.Modems(args.state, demo=args.demo)
    LimitedHTTPServer.ui_access = Handler.uiaccess
    LimitedHTTPServer.allow_public = args.allow_public
    srv = LimitedHTTPServer((args.host, args.port), Handler)
    if args.extra_port and args.extra_port != args.port:
        def serve_extra():
            # Port 80 kann beim Start noch belegt sein (z. B. nginx-Beispielseite): weiter versuchen, bis die Oberfläche auch ohne Port erreichbar ist
            warned = False
            while True:
                try:
                    extra = LimitedHTTPServer((args.host, args.extra_port), Handler)
                except OSError as e:
                    if not warned:
                        print(f"Port {args.extra_port} nicht verfügbar, versuche es weiter: {e}", flush=True)
                        warned = True
                    time.sleep(5)
                    continue
                print(f"PIPBOX auch auf http://{args.host}:{args.extra_port}", flush=True)
                extra.serve_forever()
        threading.Thread(target=serve_extra, daemon=True).start()
    print(f"PIPBOX auf http://{args.host}:{args.port} (demo={args.demo})")
    srv.serve_forever()
