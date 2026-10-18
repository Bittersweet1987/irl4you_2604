# IRL4YOU Box

## Inhalt / Contents

- [Deutsch](#deutsch)
  - [Wichtigste Teile](#wichtigste-teile)
  - [Zugriff auf andere Dienste](#zugriff-auf-andere-dienste)
  - [Danksagung](#danksagung)
  - [Hinweis zu KI](#hinweis-zu-ki)
  - [Lizenz](#lizenz)
- [English](#english)
  - [Main parts](#main-parts)
  - [Access to other services](#access-to-other-services)
  - [Acknowledgements](#acknowledgements)
  - [Note on AI](#note-on-ai)
  - [License](#license)

## Deutsch

Software für die IRL4YOU Box: ein kleiner Rechner (Orange Pi 5 Plus, Rock 5B+ ungetestet) für Livestreams aus dem Alltag. Die Box nimmt Kameras, HDMI und Handys auf, mischt sie (Bild-in-Bild), kodiert per Hardware und sendet gebündelt über mehrere Leitungen (Mobilfunk, WLAN, LAN) zu Twitch & Co.

Entwickelt von [Bittersweet1987](https://discord.com/users/232451293040476160) und [Akinos01 (IRL4YOU)](https://discord.com/users/523858990510243861).

Läuft auf Ubuntu 26.04 mit Rockchip-Kernel 6.1.

### Wichtigste Teile

- **Oberfläche** im Browser (`irl4you/`): Senden, Kameras, Netzwerk, Vorschau, Twitch-Chat, Logs, Updates; 13 Sprachen.
- **Eingänge**: RTMP/SRT (SRS 6), HDMI, USB-Kameras, DJI-Kameras per Bluetooth, Handys.
- **Encoder und SRTLA-Sender** (`encoder/`, `srtla/`): eigene Entwicklung, bündelt mehrere Leitungen zu einer Sendung.
- **Updater** (`updater/`): `irl4you-update` holt die Commits von `main`; er wartet, solange gesendet wird.
- **Bauen** (`build/`): Pakete und Images entstehen auf der Box. Releases: [docs/RELEASE.md](docs/RELEASE.md).

### Zugriff auf andere Dienste

Die Box ruft diese Dienste von Dritten auf. Sie gehören ihren Betreibern; Nutzung nach deren Bedingungen.

- **Twitch** (Anmeldung, API, Chat und EventSub): Chat, Ereignisse und Senden. Anmeldedaten bleiben auf der Box.
- **BetterTTV, FrankerFaceZ, 7TV**: Emotes im Chat, zur Laufzeit geladen und nicht mitgeliefert.
- **GitHub**: Updates (`irl4you-update` liest die Commits von `main` und lädt den Stand).
- **Tailscale** (optional): Fernzugriff, den man selbst einrichtet.
- **Ubuntu-Paketquellen und PyPI**: Systempakete und Python-Bibliotheken bei Installation und Updates.
- **Moblin, Streamer.bot** (nur Links/Anbindung): Moblin-App und DJI-Ablauf nach [Moblin](https://github.com/eerimoq/moblin); die Apps selbst sind nicht enthalten.

### Danksagung

Danke an die Entwickler, deren Arbeit die Box nutzt oder auf der sie aufbaut:

- **[Moblin](https://github.com/eerimoq/moblin)** von Erik Moqvist: Vorlage für den Ablauf der DJI-Kopplung. Dazu [dji-remote](https://github.com/dimadesu/dji-remote) von dimadesu.
- **[SRS](https://github.com/ossrs/srs)**: RTMP/SRT-Eingang.
- **Rockchip** ([MPP](https://github.com/rockchip-linux/mpp), RGA, gstreamer-rockchip über [JeffyCN](https://github.com/JeffyCN/mirrors)): Hardware-Kodierung und Bildskalierung.
- **[Armbian](https://github.com/armbian/linux-rockchip)**: Rockchip-Kernel. **[lwfinger](https://github.com/lwfinger/rtw88)** und **[shenmintao](https://github.com/shenmintao/aic8800d80)**: WLAN-Treiber.
- **GStreamer, Ubuntu, NetworkManager, nginx, Python** und alle weiteren Open-Source-Projekte unter der Box.
- **Twitch, BetterTTV, FrankerFaceZ, 7TV, Tailscale**: Dienste, die die Box nutzt.

Alle Lizenzen der Fremdprojekte stehen in [NOTICE.md](NOTICE.md).

### Hinweis zu KI

Dieses Projekt wurde mit KI erstellt und wird von KI unterstützt. Code, Texte und Übersetzungen können davon stammen; sie sind nicht in jedem Fall von Menschen Zeile für Zeile geprüft. Bitte vor dem Einsatz im Livebetrieb selbst testen.

### Lizenz

Der eigene Code steht unter [CC BY-ND 4.0](LICENSE): Nutzung auch kommerziell erlaubt, Änderungen nur nach Rückfrage bei [Bittersweet1987](https://discord.com/users/232451293040476160) oder [Akinos01 (IRL4YOU)](https://discord.com/users/523858990510243861), siehe [ZUSATZERLAUBNIS.md](ZUSATZERLAUBNIS.md). Drittprojekte behalten ihre Lizenzen, siehe [NOTICE.md](NOTICE.md).

Anfragen zu Änderungen per Discord: [Bittersweet1987](https://discord.com/users/232451293040476160) oder [Akinos01 (IRL4YOU)](https://discord.com/users/523858990510243861).

## English

Software for the IRL4YOU Box: a small computer (Orange Pi 5 Plus, Rock 5B+ untested) for live streaming on the go. The box takes in cameras, HDMI and phones, mixes them (picture-in-picture), encodes in hardware and sends the stream bonded over several links (cellular, Wi-Fi, LAN) to Twitch and others.

Developed by [Bittersweet1987](https://discord.com/users/232451293040476160) and [Akinos01 (IRL4YOU)](https://discord.com/users/523858990510243861).

Runs on Ubuntu 26.04 with the Rockchip 6.1 kernel.

### Main parts

- **Web interface** (`irl4you/`): streaming, cameras, network, preview, Twitch chat, logs, updates; 13 languages.
- **Inputs**: RTMP/SRT (SRS 6), HDMI, USB cameras, DJI cameras over Bluetooth, phones.
- **Encoder and SRTLA sender** (`encoder/`, `srtla/`): own development, bonds several links into one stream.
- **Updater** (`updater/`): `irl4you-update` fetches the commits of `main`; it waits while a stream is running.
- **Building** (`build/`): packages and images are built on the box. Releases: [docs/RELEASE.md](docs/RELEASE.md).

### Access to other services

The box calls these third-party services. They belong to their operators; use is subject to their terms.

- **Twitch** (login, API, chat and EventSub): chat, events and streaming. Credentials stay on the box.
- **BetterTTV, FrankerFaceZ, 7TV**: chat emotes, loaded at runtime and not shipped.
- **GitHub**: updates (`irl4you-update` reads the commits of `main` and downloads the release state).
- **Tailscale** (optional): remote access that you set up yourself.
- **Ubuntu package sources and PyPI**: system packages and Python libraries during installation and updates.
- **Moblin, Streamer.bot** (links/integration only): the Moblin app and the DJI procedure after [Moblin](https://github.com/eerimoq/moblin); the apps themselves are not included.

### Acknowledgements

Thanks to the developers whose work the box uses or builds on:

- **[Moblin](https://github.com/eerimoq/moblin)** by Erik Moqvist: template for the DJI pairing procedure. Also [dji-remote](https://github.com/dimadesu/dji-remote) by dimadesu.
- **[SRS](https://github.com/ossrs/srs)**: RTMP/SRT input.
- **Rockchip** ([MPP](https://github.com/rockchip-linux/mpp), RGA, gstreamer-rockchip via [JeffyCN](https://github.com/JeffyCN/mirrors)): hardware encoding and scaling.
- **[Armbian](https://github.com/armbian/linux-rockchip)**: Rockchip kernel. **[lwfinger](https://github.com/lwfinger/rtw88)** and **[shenmintao](https://github.com/shenmintao/aic8800d80)**: Wi-Fi drivers.
- **GStreamer, Ubuntu, NetworkManager, nginx, Python** and all other open-source projects under the box.
- **Twitch, BetterTTV, FrankerFaceZ, 7TV, Tailscale**: services the box uses.

All licenses of third-party projects are listed in [NOTICE.md](NOTICE.md).

### Note on AI

This project was created with AI and is supported by AI. Code, text and translations may come from it; they are not necessarily reviewed line by line by humans. Please test yourself before using it in a live broadcast.

### License

The project's own code is under [CC BY-ND 4.0](LICENSE): use, including commercial use, is allowed; changes only after asking [Bittersweet1987](https://discord.com/users/232451293040476160) or [Akinos01 (IRL4YOU)](https://discord.com/users/523858990510243861), see [ZUSATZERLAUBNIS.md](ZUSATZERLAUBNIS.md) (German). Third-party projects keep their own licenses, see [NOTICE.md](NOTICE.md).

Requests for changes via Discord: [Bittersweet1987](https://discord.com/users/232451293040476160) or [Akinos01 (IRL4YOU)](https://discord.com/users/523858990510243861).
