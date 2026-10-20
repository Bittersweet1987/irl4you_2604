"""DJI-Kamera: Ändert man die Stabilisierung bei bestehender Verbindung, verbindet die Kamera selbst neu."""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


class FakeCam:
    def __init__(self, state):
        self.state, self.publishing, self.until, self.restarted = state, False, 0, 0
        self.cfg = {"stabilization": "off", "autoconnect": False}
        self.switch_until = 0

    def locked(self):
        return self.state not in ("idle", "error", "searching", "connecting") or self.publishing

    def mode_locked(self):
        return self.state not in ("idle", "error") or self.publishing

    def switch_wait(self):
        return 0

    async def restart(self):
        self.restarted += 1

    def running(self):
        return True


def run(state, req):
    mod = irl("dji_daemon")
    d = object.__new__(mod.Daemon)
    cam = FakeCam(state)
    d.cameras = {"AA:BB:CC:DD:EE:FF": cam}
    d.sanitize = lambda c: None
    d.save = lambda: None
    d.pin_connection = d.offer_connection_network = lambda c: None

    async def go():
        r = await d.handle(dict(req, cmd="update", addr="AA:BB:CC:DD:EE:FF"))
        await asyncio.sleep(0)
        return r
    return cam, asyncio.run(go())


class TestStabilisierung(unittest.TestCase):
    def test_laufende_verbindung_verbindet_neu(self):
        cam, r = run("streaming", {"stabilization": "rocksteady"})
        self.assertEqual((cam.cfg["stabilization"], r.get("reconnect"), cam.restarted), ("rocksteady", True, 1))

    def test_ohne_verbindung_nur_speichern(self):
        cam, r = run("idle", {"stabilization": "rocksteady"})
        self.assertEqual((cam.cfg["stabilization"], r.get("reconnect"), cam.restarted), ("rocksteady", None, 0))

    def test_gleiche_stabilisierung_oder_andere_einstellung_ohne_neustart(self):
        cam, r = run("streaming", {"stabilization": "off"})
        self.assertEqual(cam.restarted, 0)
        cam, r = run("streaming", {"fps": 25})
        self.assertEqual((cam.cfg["fps"], cam.restarted), (25, 0))


if __name__ == "__main__":
    unittest.main()
