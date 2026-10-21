"""IRL4YOU BOX Oberfläche: Aktionen aus Tastenbelegungen und Szenenwechsel."""

from .common import KEY_RE
from .pipeline import PipelineStore


def scene_swap(pipeline, cams, send, with_key=None):
    if with_key is not None and (not isinstance(with_key, str) or not KEY_RE.match(with_key)):
        raise ValueError("Kamera unbekannt")
    target = with_key or pipeline.cfg.get("pip")
    if target and any(x["key"] == target and x.get("state") == "offline" for x in cams.listing("")):
        raise ValueError("Diese Kamera ist nicht verbunden und lässt sich nicht zum Hauptbild machen.")
    old_audio = PipelineStore.view_values(pipeline.cfg)[1]
    shown = pipeline.swap_main_pip(with_key)
    if send.always_live() or send.swap_live():
        note = "Getauscht, ohne Unterbrechung."
        moved = PipelineStore.view_values(pipeline.cfg)[1] != old_audio
        if shown or moved:
            hide, aud = PipelineStore.view_values(pipeline.cfg)
            cur = send.view_state()
            if not (send.view_live() and send.apply_view(hide, aud, bool(cur and cur["mute"]))):
                note += " Das kleine Bild erscheint beim nächsten Start der Sendung." if shown else " Der Ton wechselt beim nächsten Start der Sendung."
        return {"ok": True, "restarted": False, "note": note}
    restarted, note = send.restart_if_live()
    return {"ok": True, "restarted": restarted, "note": note or "Getauscht."}


def scene_assign(pipeline, cams, send, slot, key):
    """Kamera auf einen Platz legen. Tauschen zwei Kameras, die schon im Bild sind, geht das wie ein Tausch ohne Unterbrechung; eine Kamera, die noch
    nicht im Bild war, braucht einen Neustart der Sendung."""
    if slot not in PipelineStore.SLOTS:
        raise ValueError("Platz unbekannt")
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise ValueError("Kamera unbekannt")
    if any(x["key"] == key and x.get("state") == "offline" for x in cams.listing("")):
        raise ValueError("Diese Kamera ist nicht verbunden.")
    old_audio = PipelineStore.view_values(pipeline.cfg)[1]
    kind, shown = pipeline.assign_slot(slot, key, [c["key"] for c in cams.cams])
    if kind == "same":
        return {"ok": True, "restarted": False, "note": ""}
    if kind == "swap" and (send.always_live() or send.swap_live()):
        note = "Getauscht, ohne Unterbrechung."
        moved = PipelineStore.view_values(pipeline.cfg)[1] != old_audio
        if shown or moved:
            hide, aud = PipelineStore.view_values(pipeline.cfg)
            cur = send.view_state()
            if not (send.view_live() and send.apply_view(hide, aud, bool(cur and cur["mute"]))):
                note += " Das kleine Bild erscheint beim nächsten Start der Sendung." if shown else " Der Ton wechselt beim nächsten Start der Sendung."
        return {"ok": True, "restarted": False, "note": note}
    restarted, note = send.restart_if_live()
    return {"ok": True, "restarted": restarted, "note": note or "Gespeichert."}


def controller_action(fn, pipeline, cams, send):
    cfg = pipeline.cfg
    if fn in ("pip1", "pip2", "pip3"):
        key = cfg.get({"pip1": "pip", "pip2": "pip2", "pip3": "pip3"}[fn])
        if not key or cfg.get("type") != "pip":
            return
        scene_swap(pipeline, cams, send, key)
    elif fn == "main":
        want = next((c["key"] for c in cams.cams if c.get("role") == "main"), None)
        if want and want != cfg.get("main") and cfg.get("type") == "pip":
            scene_swap(pipeline, cams, send, want)
    elif fn == "mute":
        f = send.footer()
        send.change_view(mute=not bool(f and f["audio"]["mute"]))
    elif fn == "audio_next":
        f = send.footer()
        if f:
            send.change_view(audio=f["audio"]["next"])
