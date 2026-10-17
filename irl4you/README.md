# irl4you/

Hier liegt der Programmstand von IRL4YOU, der als Release-Paket ausgeliefert wird (alles, was heute unter `/opt/pipbox` liegt).
Der volle Stand aus `Belabox-2604\irl4you\` kommt hierher, sobald die Umstellung auf 26.04 so weit ist.

Heute enthalten (Basis für das Testsystem):
- `install/system-install.sh`: richtet Systemteile ein (ruft `system-base-fixes.sh` auf, installiert `debs/*.deb`).
  Kopiert **keine** Programmdateien (die liegen schon an ihrem Platz, `/opt/pipbox` zeigt auf die aktive Version). Mehrfach lauffähig.
- `install/system-base-fixes.sh`: NetworkManager verwaltet alle Karten, Kernel-Hook, HDMI-Eingang im DTB, Tastatur/Sprache.
- `install/zz-irl4you-boot`: Kernel-Hook (landet in `/etc/kernel/postinst.d/`): `/boot/Image`, `/boot/dtb`, `hdmirx` auf `okay`.
- `debs/`: eigene .deb-Pakete (z. B. `irl4you-wifi-8821cu_*.deb`), werden von `system-install.sh` eingespielt. Nur `*.deb` erlaubt.

Optional: `install/health.sh`: zusätzliche Prüfung nach dem Umschalten (z. B. Oberfläche antwortet auf Port 80).
