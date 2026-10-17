# IRL4YOU 2604

IRL4YOU für Ubuntu 26.04 (Orange Pi 5 Plus, Radxa ROCK 5B Plus), ohne BELABOX. Dieses Repository ist zugleich die
**Update-Quelle der Box**: Jede Version wird als GitHub-Release veröffentlicht, die Box holt sie von hier.

## Aufbau

| Ordner / Datei | Inhalt |
|---|---|
| `VERSION` | aktuelle Versionsnummer (`x.y.z` oder `x.y.z-beta.N`) |
| `CHANGELOG.md` | Änderungen je Version; der Abschnitt `## <Version>` wird Text des Release und auf der Box angezeigt |
| `irl4you/` | Programmstand von IRL4YOU (heute `/opt/pipbox`), kommt aus `Belabox-2604\irl4you\` |
| `updater/irl4you_update.py` | Update-Helfer der Box (nur Python-Standardbibliothek) |
| `updater/systemd/` | Dienste: Anfrage der Oberfläche (`.path`) und regelmäßige Prüfung (`.timer`) |
| `updater/update.conf.example` | Konfig der Box (`/etc/irl4you/update.conf`) |
| `release/` | Manifest-Vorlage und Hooks, die in jedes Paket kommen |
| `tools/build-release.sh` | baut `dist/irl4you-<Version>.tar.gz` und `.sha256` |
| `.github/workflows/` | Tests bei jedem Push, Release bei jeder Marke `v*` |
| `tests/` | Tests des Update-Helfers (`python3 -m unittest discover -s tests`) |

## Neue Version veröffentlichen

1. `VERSION` anheben und einen Abschnitt `## <Version>` in `CHANGELOG.md` schreiben, committen.
2. Marke setzen und pushen: `git tag v2.0.1 && git push origin v2.0.1`.
3. Der Workflow „Release“ prüft, ob Marke und `VERSION` übereinstimmen, lässt die Tests laufen, baut das Paket und legt
   das Release mit `irl4you-2.0.1.tar.gz` und `irl4you-2.0.1.tar.gz.sha256` an.

Eine Marke mit Bindestrich (`v2.1.0-beta.1`) wird Vorabversion und nur von Boxen mit `channel = beta` geholt.

## Paket

`irl4you-<Version>.tar.gz` enthält den Programmstand direkt (ohne oberen Ordner) und dazu:

- `VERSION`, `manifest.json`: Name `irl4you`, Version, `min_updater`, `restart` (Dienste, die neu starten),
  `health_units` (müssen danach laufen), `reboot` (Neustart empfohlen).
- `hooks/install`: richtet Systemteile ein (Update-Helfer, Dienste, dann `install/system-install.sh` von IRL4YOU). Läuft
  nach dem Umschalten mit `IRL4YOU_ACTION=install|switch|rollback` und muss mehrfach laufen dürfen.
- `hooks/health`: zusätzliche Prüfung nach dem Umschalten (ruft `install/health.sh` auf, wenn vorhanden).
- `debs/` (optional): eigene .deb-Pakete (Encoder, SRTLA, MPP …), die `install/system-install.sh` einspielt (z. B. `apt-get install ./debs/*.deb`).
  Erlaubt sind dort nur Dateien `*.deb`.
- `updater/`: der Update-Helfer selbst, damit er mit jeder Version aktualisiert wird.

## Was die Box macht

Ablage: `/opt/irl4you/releases/<Version>/`, aktive Version über den Verweis `/opt/irl4you/current`, und `/opt/pipbox`
zeigt auf `current` (die Pfade von IRL4YOU bleiben gleich).

1. **Prüfen:** Timer alle 6 Stunden (erstmals 10 Minuten nach dem Start) und auf Knopfdruck in der Oberfläche. Der Status
   (neueste Version, Änderungstext, Liste der Versionen) steht in `/run/pipbox-swupdate/status.json`.
2. **Installieren** (Knopf in der Oberfläche oder, mit `auto_install = true`, durch den Timer): nie während einer
   Sendung. Paket laden, SHA256 prüfen, streng entpacken (keine Pfade oder Verweise nach außen, keine Geräte), Manifest
   prüfen, Verweis atomar umhängen, `hooks/install`, Dienste neu starten, Gesundheit prüfen.
3. **Fehler:** startet die neue Version nicht, hängt der Helfer den Verweis sofort zurück, führt `hooks/install` der alten
   Version aus und startet deren Dienste. Die Oberfläche bekommt eine Meldung.
4. **Zurück / Wechseln:** `rollback` springt auf die vorher aktive Version, `switch <Version>` auf eine beliebige (lokal
   vorhandene oder aus GitHub). Die letzten 3 Versionen bleiben auf der Box.

Die Oberfläche schreibt nur ein Stichwort in `/var/lib/pipbox/swupdate-request` (`check`, `install`, `rollback` oder
`switch` plus Version in Zeile 2), wie beim bisherigen Software-Update. Woher die Updates kommen, steht ausschließlich in
`/etc/irl4you/update.conf`.

### Privates Repository

Ist das Repository privat, braucht die Box einen Schlüssel: auf GitHub einen „fine-grained personal access token“ nur für
dieses Repository mit dem Recht *Contents: read-only* anlegen und auf der Box ablegen:

```sh
sudo install -m 600 /dev/stdin /etc/irl4you/update-token   # Schlüssel einfügen, dann Strg+D
```

Der Schlüssel geht nur an `api.github.com`, nie an die Download-Adresse, auf die GitHub weiterleitet, und erscheint in
keinem Protokoll.

### Befehle auf der Box

```sh
sudo irl4you-update status        # aktive, vorherige und vorhandene Versionen
sudo irl4you-update check
sudo irl4you-update install       # oder: install 2.0.1
sudo irl4you-update rollback
journalctl -u irl4you-update -u irl4you-update-auto; less /var/log/irl4you-update.log
```

## Erstes Einrichten auf einer Box

Das Image bringt die erste Version mit. Danach einmal (als root):

```sh
v=$(cat VERSION)                                   # im entpackten Paket
mkdir -p /opt/irl4you/releases && cp -a . /opt/irl4you/releases/$v
ln -sfn /opt/irl4you/releases/$v /opt/irl4you/current
[ -L /opt/pipbox ] || { [ -e /opt/pipbox ] && mv /opt/pipbox /opt/pipbox.alt; ln -s /opt/irl4you/current /opt/pipbox; }
IRL4YOU_ACTION=install IRL4YOU_VERSION=$v IRL4YOU_ROOT=/opt/irl4you IRL4YOU_RELEASE_DIR=/opt/irl4you/releases/$v \
  sh /opt/irl4you/releases/$v/hooks/install
```

`/opt/irl4you/venv` (Python-Umgebung für bleak) liegt neben `releases/` und wird vom Update-Helfer nicht angefasst. Das Ubuntu-Systemupdate
(apt, `pipbox-update.py`) bleibt getrennt bestehen.

Wichtig: Einstellungen und Laufzeitdaten dürfen nicht unter `/opt/pipbox` liegen, sondern unter `/var/lib/pipbox` o. ä.,
weil jede Version ihren eigenen Ordner hat.
