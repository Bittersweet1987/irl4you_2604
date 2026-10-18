# irl4you/

Programmstand von IRL4YOU für Ubuntu 26.04 (alles, was auf der Box unter `/opt/pipbox` liegt; jeder Commit auf `main` ist ein Stand).
Gepflegt wird er lokal gepflegt, getestet (`tests/test_irl4you.py`, auf der Box die Box-Suite) und dann hierher committet.

- `server.py` (Einstieg) und `webui/` (Oberfläche, Port 8780 und 80, aufgeteilt in Teile mit höchstens 500 Zeilen: common, auth, pipeline*, send, cameras, wifi, updates, routes_get/post …), `pipbox_send.py`/`pipbox_live.py` (Sendekette mit `irl4you-encoder` und `irl4you-srtla`),
  `pipbox_modem.py` + `pipbox-modem.py` (Mobilfunk), `dji*.py`, `hdmi_daemon.py`, Helfer `pipbox-*.py`, `web/`.
- `install/system-install.sh`: wird von `hooks/install` aufgerufen. Reihenfolge: `system-base-fixes.sh` (NetworkManager, Kernel-Hook, HDMI-Eingang, Tastatur/Sprache),
  eigene Pakete aus `debs/`, dann `irl4you-setup.sh` (Pakete aus Ubuntu, Benutzer, venv `/opt/irl4you/venv` für bleak, PiP-Baustein, NetworkManager-Hooks,
  udev, nginx-RTMP, Dienste). Kopiert **keine** Programmdateien, mehrfach lauffähig.
- RTMP-Eingang: `irl4you-srs` (SRS 6, H.264 und H.265; Paket aus `debs/`, gebaut mit `build/08-srs.sh`), Konfiguration `install/srs/srs.conf`, RTMPS über nginx (nur TLS, `install/nginx/`), Statistik auf Port 1936 im alten Format von `pipbox-rtmpstat.py` (aus der API von SRS).
- `install/requirements.txt`: feste Versionen von bleak und dbus-fast für die Umgebung `/opt/irl4you/venv`.
- `install/*.service|path|timer|socket`, `install/net/`, `install/udev/`, `install/nginx/`: Dienste und Systemdateien.
- `install/health.sh`: nach dem Umschalten antwortet die Oberfläche auf Port 8780 und 80.
- `install/install-2604.sh [--chroot] [--migrate-from DIR]`: Erstinstallation im Checkout (Daten der alten 22.04-Box übernehmen, Stand als erste Version einrichten).
- `debs/`: eigene .deb-Pakete (nur `*.deb`), werden von `system-install.sh` eingespielt.
- Einstellungen und Laufzeitdaten liegen nie hier, sondern unter `/var/lib/pipbox` und `/etc/pipbox`.
