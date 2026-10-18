# IRL4YOU Box

Software für die IRL4YOU Box: ein kleiner Rechner (Orange Pi 5 Plus, Rock 5B+ ungetestet) für Livestreams aus dem Alltag. Die Box nimmt Kameras, HDMI und Handys auf, mischt sie (Bild-in-Bild), kodiert per Hardware und sendet gebündelt über mehrere Leitungen (Mobilfunk, WLAN, LAN) zu Twitch & Co.

Läuft auf Ubuntu 26.04 mit Rockchip-Kernel 6.1.

## Wichtigste Teile

- **Oberfläche** im Browser (`irl4you/`): Senden, Kameras, Netzwerk, Vorschau, Twitch-Chat, Logs, Updates; 13 Sprachen.
- **Eingänge**: RTMP/SRT (SRS 6), HDMI, USB-Kameras, DJI-Kameras per Bluetooth, Handys.
- **Encoder und SRTLA-Sender** (`encoder/`, `srtla/`): eigene Entwicklung, bündelt mehrere Leitungen zu einer Sendung.
- **Updater** (`updater/`): `irl4you-update` holt die Commits von `main`; er wartet, solange gesendet wird.
- **Bauen** (`build/`): Pakete und Images entstehen auf der Box. Releases: [docs/RELEASE.md](docs/RELEASE.md).

## Versionen

Schema `vX.Y.Z`: X gibt Marco vor (0 = Alpha), Y steigt mit einem Release, Z zählt die Commits. Änderungen stehen in [CHANGELOG.md](CHANGELOG.md).

## Lizenz

Der eigene Code steht unter [CC BY-ND 4.0](LICENSE): Nutzung auch kommerziell erlaubt, Änderungen nur nach Rückfrage bei Bittersweet1987, Ausnahme IRL4YOU ([ZUSATZERLAUBNIS.md](ZUSATZERLAUBNIS.md)). Drittprojekte behalten ihre Lizenzen, siehe [NOTICE.md](NOTICE.md).
