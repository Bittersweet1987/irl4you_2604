# IRL4YOU 2604

IRL4YOU für Ubuntu 26.04 (Orange Pi 5 Plus, Radxa ROCK 5B Plus), ohne BELABOX. Dieses Repository ist zugleich die
**Update-Quelle der Box**: Die Box folgt den **Commits** des Zweigs `main`. Ein Commit dort ist das nächste Update, es gibt
keine Releases und keine Marken.

## Aufbau

| Ordner / Datei | Inhalt |
|---|---|
| `VERSION` | Anzeigename der Version (`x.y.z` oder `x.y.z-rc.N`); die Box unterscheidet Stände am Commit |
| `CHANGELOG.md` | Änderungen für Menschen |
| `irl4you/` | Programmstand von IRL4YOU (heute `/opt/pipbox`); `irl4you/install/` Systemteile, `irl4you/debs/` eigene .deb-Pakete |
| `updater/irl4you_update.py` | Update-Helfer der Box (nur Python-Standardbibliothek) |
| `updater/systemd/` | Dienste: Anfrage der Oberfläche (`.path`) und regelmäßige Prüfung (`.timer`) |
| `updater/update.conf.example` | Konfig der Box (`/etc/irl4you/update.conf`) |
| `release/` | Manifest-Vorlage und Hooks, die zum Paket der Box gehören |
| `.github/workflows/tests.yml` | Tests bei jedem Push; ihr Ergebnis entscheidet, ob die Box einen Commit nimmt |
| `tests/` | Tests des Update-Helfers (`python3 -m unittest discover -s tests`) |

## Neue Version bringen

Änderung committen und auf `main` bringen. Das war's. Soll die Versionsanzeige steigen: `VERSION` anheben und in
`CHANGELOG.md` eintragen. Sobald die Prüfungen (Tests) grün sind, nimmt die Box den Commit.

## Was die Box macht

Ablage: `/opt/irl4you/releases/<erste 12 Zeichen des Commits>/`, aktive Version über den Verweis `/opt/irl4you/current`,
und `/opt/pipbox` zeigt auf `current` (die Pfade von IRL4YOU bleiben gleich).

1. **Prüfen:** Timer alle 6 Stunden (erstmals 10 Minuten nach dem Start) und auf Knopfdruck in der Oberfläche. Der Status
   (neuester Stand, Liste der letzten Commits mit Text, Änderungen seit der installierten Version) steht in
   `/run/pipbox-swupdate/status.json`.
2. **Welcher Commit:** der neueste auf `main`, dessen GitHub-Prüfungen (CI) erfolgreich sind. Läuft die CI noch, wartet die Box;
   schlägt sie fehl, wird der Commit nicht installiert (`require_ci = false` schaltet das ab).
3. **Installieren** (Knopf in der Oberfläche oder, mit `auto_install = true`, durch den Timer): nie während einer Sendung.
   Tarball genau dieses Commits laden, streng entpacken (keine Pfade oder Verweise nach außen, keine Geräte), **jede Datei gegen den
   Git-Baum des Commits prüfen** (Blob-Hash; nichts fehlt, nichts ist zusätzlich), Paket zusammensetzen (`irl4you/` +
   `release/hooks` + `updater/` + `VERSION` + Manifest), Verweis atomar umhängen, `hooks/install`, Dienste neu starten,
   Gesundheit prüfen (nur Dienste, die auf der Box eingerichtet sind; fehlende werden übersprungen und in Protokoll und
   Status vermerkt, ein eingerichteter, aber nicht laufender Dienst führt weiter zum Zurückrollen).
4. **Fehler:** startet die neue Version nicht, hängt der Helfer den Verweis sofort zurück, führt `hooks/install` der alten
   Version aus und startet deren Dienste. Die Oberfläche bekommt eine Meldung.
5. **Zurück / Wechseln:** `rollback` springt auf die vorher aktive Version, `switch <Commit>` auf einen beliebigen Stand
   (lokal vorhanden oder aus GitHub). Die letzten 3 Versionen bleiben auf der Box.

Die Oberfläche schreibt nur ein Stichwort in `/var/lib/pipbox/swupdate-request` (`check`, `install`, `rollback` oder
`switch` plus Commit-Hash (7 bis 40 Zeichen) in Zeile 2). Woher die Updates kommen, steht ausschließlich in
`/etc/irl4you/update.conf`.

### Paket

Das Paket auf der Box entsteht aus dem Commit: `irl4you/` direkt, dazu `VERSION`, `manifest.json` (aus `release/manifest.json`,
plus der Commit), `hooks/` (aus `release/hooks/`) und `updater/`.

- `manifest.json`: Name `irl4you`, Version, `min_updater`, `restart` (Dienste, die neu starten), `health_units` (müssen danach
  laufen), `reboot` (Neustart empfohlen).
- `hooks/install`: richtet Systemteile ein (Update-Helfer, Dienste, dann `install/system-install.sh` von IRL4YOU). Läuft nach dem
  Umschalten mit `IRL4YOU_ACTION=install|switch|rollback` und muss mehrfach laufen dürfen.
- `hooks/health`: zusätzliche Prüfung nach dem Umschalten (ruft `install/health.sh` auf, wenn vorhanden).
- `debs/` (optional): eigene .deb-Pakete, die `install/system-install.sh` einspielt. Erlaubt sind dort nur Dateien `*.deb`.
- `/opt/irl4you/venv` (Python-Umgebung für bleak) liegt neben `releases/` und wird vom Update-Helfer nicht angefasst. Das
  Ubuntu-Systemupdate (apt, `pipbox-update.py`) bleibt getrennt bestehen.

### Privates Repository

Ist das Repository privat, braucht die Box einen Schlüssel: auf GitHub einen „fine-grained personal access token“ nur für dieses
Repository mit den Rechten *Contents: read-only* und *Checks: read-only* anlegen und auf der Box ablegen:

```sh
sudo install -m 600 /dev/stdin /etc/irl4you/update-token   # Schlüssel einfügen, dann Strg+D
```

Der Schlüssel geht nur an `api.github.com`, nie an die Download-Adresse, auf die GitHub weiterleitet, und erscheint in keinem
Protokoll.

### Befehle auf der Box

```sh
sudo irl4you-update status        # aktive, vorherige und vorhandene Versionen
sudo irl4you-update check
sudo irl4you-update install       # oder: install <Commit>
sudo irl4you-update rollback
less /var/log/irl4you-update.log
```

## Erstes Einrichten auf einer Box

Einmal (als root) im entpackten Stand des Repositorys:

```sh
sha=$(git rev-parse HEAD)   # oder die 40 Zeichen des Commits
id=$(echo $sha | cut -c1-12)
python3 - "$PWD" /opt/irl4you/releases/$id $sha <<'PY'
import sys; sys.path.insert(0, sys.argv[1] + "/updater")
import irl4you_update as U
U.Updater.assemble(sys.argv[1], sys.argv[2], sys.argv[3])
PY
ln -sfn /opt/irl4you/releases/$id /opt/irl4you/current
[ -L /opt/pipbox ] || { [ -e /opt/pipbox ] && mv /opt/pipbox /opt/pipbox.alt; ln -s /opt/irl4you/current /opt/pipbox; }
IRL4YOU_ACTION=install IRL4YOU_ROOT=/opt/irl4you IRL4YOU_RELEASE_DIR=/opt/irl4you/releases/$id \
  sh /opt/irl4you/releases/$id/hooks/install
```

Wichtig: Einstellungen und Laufzeitdaten dürfen nicht unter `/opt/pipbox` liegen, sondern unter `/var/lib/pipbox` o. ä., weil
jede Version ihren eigenen Ordner hat.
