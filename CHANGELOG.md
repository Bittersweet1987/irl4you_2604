# Änderungen

## 2.0.0-rc.1
- Basis für das Testsystem: NetworkManager verwaltet eth0/eth1, Kernel-Hook (`/boot/Image`, `/boot/dtb`, HDMI-Eingang der Orange Pi 5 Plus), WLAN-Treiber als .deb, deutsche Tastatur/Sprache als Standard.
- Vorabversion: wird nur von Boxen mit `channel = beta` in `/etc/irl4you/update.conf` geholt.

## 2.0.0
- Erste Version für Ubuntu 26.04 (nur IRL4YOU, ohne BELABOX).
- Updates kommen als GitHub-Releases aus diesem Repository (Prüfsumme, atomares Umschalten, automatisches Zurückrollen).
