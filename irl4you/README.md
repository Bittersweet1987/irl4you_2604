# irl4you/

Programmstand von IRL4YOU für Ubuntu 26.04 (alles, was auf der Box unter `/opt/pipbox` liegt; jeder Commit auf `main` ist ein Stand).
Gepflegt wird er lokal in `Belabox-2604\irl4you\`, getestet (`tests/test_irl4you.py`, auf der Box die Suite in `Belabox-2604\tests`) und dann hierher committet.

- `server.py` (Oberfläche, Port 8780 und 80), `pipbox_send.py`/`pipbox_live.py` (Sendekette mit `irl4you-encoder` und `irl4you-srtla`),
  `pipbox_modem.py` + `pipbox-modem.py` (Mobilfunk), `dji*.py`, `hdmi_daemon.py`, Helfer `pipbox-*.py`, `web/`.
- `install/system-install.sh`: wird von `hooks/install` aufgerufen. Reihenfolge: `system-base-fixes.sh` (NetworkManager, Kernel-Hook, HDMI-Eingang, Tastatur/Sprache),
  eigene Pakete aus `debs/`, dann `irl4you-setup.sh` (Pakete aus Ubuntu, Benutzer, venv `/opt/irl4you/venv` für bleak, PiP-Baustein, NetworkManager-Hooks,
  udev, nginx-RTMP, Dienste). Kopiert **keine** Programmdateien, mehrfach lauffähig.
- `install/*.service|path|timer|socket`, `install/net/`, `install/udev/`, `install/nginx/`: Dienste und Systemdateien.
- `install/health.sh`: nach dem Umschalten antwortet die Oberfläche auf Port 8780 und 80.
- `install/install-2604.sh [--chroot] [--migrate-from DIR]`: Erstinstallation im Checkout (Daten der alten 22.04-Box übernehmen, Stand als erste Version einrichten).
- `debs/`: eigene .deb-Pakete (nur `*.deb`), werden von `system-install.sh` eingespielt.
- Einstellungen und Laufzeitdaten liegen nie hier, sondern unter `/var/lib/pipbox` und `/etc/pipbox`.
