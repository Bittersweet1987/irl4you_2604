"""IRL4YOU BOX Oberfläche: Wahl der Videokodierung (Hardware oder Software), Menü Entwickler."""

import glob
import os

import pipbox_live

MODES = ("hardware", "software")


class EncoderMode:
    FILE = "encoder-mode"

    def __init__(self, state_dir, demo, send):
        self.path = os.path.join(state_dir, self.FILE)
        self.demo, self.send = demo, send
        self._fake = "hardware"

    @staticmethod
    def software_available():
        """x264 (Software-Kodierung) ist als GStreamer-Baustein installiert."""
        return bool(glob.glob("/usr/lib/*/gstreamer-1.0/libgstx264.so"))

    def mode(self):
        return self._fake if self.demo else pipbox_live.encoder_mode(self.path)

    def status(self):
        sw = True if self.demo else self.software_available()
        return {"mode": self.mode(), "software_available": bool(sw), "sending": bool(self.demo is False and self.send._active())}

    def set(self, mode):
        if mode not in MODES:
            raise ValueError("Kodierung: Hardware oder Software")
        if mode == "software" and not self.status()["software_available"]:
            raise ValueError("Software-Kodierung ist auf dieser Box nicht verfügbar")
        before = self.mode()
        if self.demo:
            self._fake = mode
            return {"ok": True, "restarted": False, "note": ""}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            f.write(mode + "\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.path)
        if mode == before or not self.send._active():
            return {"ok": True, "restarted": False, "note": "" if mode == before else "Gilt ab dem nächsten Start der Sendung."}
        restarted, note = self.send.restart_if_live()
        return {"ok": True, "restarted": restarted, "note": note}
