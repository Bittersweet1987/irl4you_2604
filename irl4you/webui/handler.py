"""IRL4YOU BOX Oberfläche: HTTP-Handler der Oberfläche (setzt die Teile zusammen)."""

from .http_base import HttpBase
from .http_stats import HttpStats
from .routes_get import GetRoutes
from .routes_post import PostRoutes


class Handler(HttpBase, HttpStats, GetRoutes, PostRoutes):
    # Teile der Oberfläche; main() setzt sie vor dem Start
    sampler = None
    cams = None
    auth = None
    djisvc = None
    netchoice = None
    names = None
    ckeys = None
    srtla = None
    pipeline = None
    send = None
    preview = None
    twitch = None
    hdmi = None
    uiaccess = None
    statsshare = None
    statsserver = None
    fpsprobe = None
