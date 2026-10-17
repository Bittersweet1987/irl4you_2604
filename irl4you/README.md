# irl4you/

Hier liegt der Programmstand von IRL4YOU, der als Release-Paket ausgeliefert wird (alles, was heute unter `/opt/pipbox` liegt).
Noch leer: der Stand aus `Belabox-2604\irl4you\` kommt hierher, sobald die Umstellung auf 26.04 so weit ist.

Erwartet werden zusätzlich zu den Programmdateien:
- `install/system-install.sh`: richtet Dienste, nginx, udev-Regeln und eigene Pakete ein. Kopiert **keine** Programmdateien
  (die liegen schon an ihrem Platz, `/opt/pipbox` zeigt auf die aktive Version). Muss mehrfach laufen dürfen.
- optional `install/health.sh`: zusätzliche Prüfung nach dem Umschalten (z. B. Oberfläche antwortet auf Port 80).
