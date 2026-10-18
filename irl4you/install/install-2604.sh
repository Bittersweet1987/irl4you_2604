#!/bin/sh
# IRL4YOU BOX auf Ubuntu 26.04 einrichten.
# Läuft als root auf der neuen Box (oder im chroot des neuen Systems mit --chroot: dann werden keine Dienste gestartet).
#
#   install-2604.sh [--chroot] [--migrate-from DIR]
#
# --migrate-from DIR   Daten der alten 22.04-Box übernehmen. DIR ist entweder
#                      a) das Root-Dateisystem der alten Box (z. B. nur lesend unter /mnt/alt eingehängt), erkannt an DIR/var/lib/pipbox:
#                         übernommen werden /var/lib/pipbox, aus /opt/belaUI/config.json nur password_hash, aus /opt/belaUI/setup.json
#                         nur ssh_user, /etc/pipbox (Zusatzadresse, Protokoll-Modus), die WLAN-/Hotspot-Profile aus
#                         /etc/NetworkManager/system-connections und das RTMPS-Zertifikat aus /etc/nginx/certs/rtmps
#                      b) ein Sammelordner mit var-lib-pipbox/, belaUI/config.json, belaUI/setup.json, nginx-certs-rtmps/
#                      In DIR wird nie geschrieben. Das Passwort selbst wird nie gelesen oder geschrieben, nur der vorhandene Hash übernommen.
#
# Ablauf: Benutzer anlegen, Daten der alten Box übernehmen, dann den Stand dieses Checkouts als erste Version einrichten
# (siehe unten "step version"; ruft hooks/install, das den Update-Helfer und alle Systemteile einrichtet). Weitere Stände kommen danach
# über den Update-Helfer (Commits von main, Repo irl4you_2604).
#
# Die eigenen Programme (irl4you-encoder, irl4you-srtla, irl4you-mpp, irl4you-rga, irl4you-gst-rockchip, Kernel) kommen als .deb-Pakete
# aus dem Ordner build/ des Repos und werden hier nicht gebaut.
set -eu
SRC="$(cd "$(dirname "$0")/.." && pwd)"
CHROOT=0
MIGRATE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --chroot) CHROOT=1 ;;
    --migrate-from) MIGRATE="$2"; shift ;;
    *) echo "Aufruf: install-2604.sh [--chroot] [--migrate-from DIR]"; exit 1 ;;
  esac
  shift
done
ROOTDIR=/opt/irl4you
STATE=/var/lib/pipbox
step() { echo "PIPBOX-STEP $1"; }
now() { [ "$CHROOT" = 0 ]; }
export IRL4YOU_CHROOT="$CHROOT"

step benutzer
getent group bluetooth >/dev/null || groupadd --system bluetooth
getent group input >/dev/null || groupadd --system input
if ! grep -q '^pipbox:' /etc/passwd; then
  useradd --system --no-create-home --home-dir "$STATE" --shell /usr/sbin/nologin --groups bluetooth pipbox
fi
mkdir -p "$STATE"

step daten
if [ -n "$MIGRATE" ]; then
  [ -d "$MIGRATE" ] || { echo "FEHLER: $MIGRATE fehlt"; exit 1; }
  if [ -d "$MIGRATE/var/lib/pipbox" ]; then
    M_STATE="$MIGRATE/var/lib/pipbox"; M_BELA="$MIGRATE/opt/belaUI"; M_CERTS="$MIGRATE/etc/nginx/certs/rtmps"
    # Einstellungen außerhalb von /var/lib/pipbox (nur übernehmen, was es hier noch nicht gibt)
    if [ -d "$MIGRATE/etc/pipbox" ]; then install -d /etc/pipbox; cp -an "$MIGRATE/etc/pipbox/." /etc/pipbox/; fi
    if [ -d "$MIGRATE/etc/NetworkManager/system-connections" ]; then
      install -d -m 700 /etc/NetworkManager/system-connections
      cp -an "$MIGRATE/etc/NetworkManager/system-connections/." /etc/NetworkManager/system-connections/
      chmod 600 /etc/NetworkManager/system-connections/* 2>/dev/null || true
      echo "WLAN- und Hotspot-Profile übernommen."
    fi
  else
    M_STATE="$MIGRATE/var-lib-pipbox"; M_BELA="$MIGRATE/belaUI"; M_CERTS="$MIGRATE/nginx-certs-rtmps"
  fi
  if [ -d "$M_STATE" ]; then
    # Vorhandene Einstellungen der neuen Box haben Vorrang (nichts überschreiben, was hier schon eingerichtet wurde)
    cp -an "$M_STATE/." "$STATE/"
    echo "Daten aus der alten Box übernommen."
  fi
  # Passwort der Oberfläche: der bcrypt-Hash aus belaUI wird zum eigenen Passwort von IRL4YOU (gleiches Passwort, kein Neusetzen)
  if [ ! -s "$STATE/auth.json" ] && [ -f "$M_BELA/config.json" ]; then
    python3 - "$M_BELA/config.json" "$STATE/auth.json" <<'PY'
import json, os, sys
src, dst = sys.argv[1], sys.argv[2]
h = json.load(open(src)).get("password_hash")
if isinstance(h, str) and h.startswith("$2") and len(h) == 60:
    fd = os.open(dst + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"bcrypt": h}, f)
    os.replace(dst + ".tmp", dst)
    print("Passwort-Hash der Oberfläche übernommen (das Passwort bleibt gleich).")
else:
    print("Kein Passwort-Hash in der belaUI-Konfiguration: Beim ersten Aufruf wird ein neues Passwort festgelegt.")
PY
  fi
  if [ ! -f "$STATE/system.json" ] && [ -f "$M_BELA/setup.json" ]; then
    python3 - "$M_BELA/setup.json" "$STATE/system.json" <<'PY'
import json, re, sys
u = json.load(open(sys.argv[1])).get("ssh_user")
if isinstance(u, str) and re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", u):
    json.dump({"ssh_user": u}, open(sys.argv[2], "w"))
    print("SSH-Benutzer übernommen:", u)
PY
  fi
  if [ -f "$M_CERTS/cert.pem" ] && [ ! -f /etc/nginx/certs/rtmps/cert.pem ]; then
    install -d -m 755 /etc/nginx/certs/rtmps
    install -m 644 "$M_CERTS/cert.pem" /etc/nginx/certs/rtmps/cert.pem
    install -m 600 "$M_CERTS/privkey.pem" /etc/nginx/certs/rtmps/privkey.pem
  fi
fi
# Ohne übernommenen SSH-Benutzer: der erste normale Benutzer (UID 1000)
if [ ! -f "$STATE/system.json" ]; then
  u=$(getent passwd 1000 | cut -d: -f1 || true)
  [ -n "$u" ] && printf '{"ssh_user": "%s"}\n' "$u" > "$STATE/system.json"
fi
chown -R pipbox:pipbox "$STATE"
chmod 700 "$STATE"

step version
# Erstes Einrichten wie im README von irl4you_2604: Der Stand dieses Repositorys wird mit dem Update-Helfer zu einer Version zusammengesetzt
# (irl4you/ + release/hooks + updater/ + VERSION + manifest.json), nach /opt/irl4you/releases/<12 Zeichen des Commits> gelegt, /opt/irl4you/current
# und /opt/pipbox zeigen darauf, dann läuft hooks/install. Danach folgt die Box den Commits von main (irl4you-update).
# Läuft nur im Checkout des Repositorys (neben irl4you/ liegen updater/ und release/); sonst bleibt es bei den übernommenen Daten.
REPO="$(cd "$SRC/.." && pwd)"
if [ ! -f "$REPO/updater/irl4you_update.py" ]; then
  echo "Daten übernommen. Zum Einrichten dieses Skript aus dem Checkout von irl4you_2604 starten (irl4you/install/install-2604.sh)."
  exit 0
fi
SHA="${IRL4YOU_COMMIT:-$(git -C "$REPO" rev-parse HEAD 2>/dev/null || true)}"
case "$SHA" in [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;; *) echo "FEHLER: Commit unbekannt (git oder IRL4YOU_COMMIT=<40 Zeichen>)" >&2; exit 1 ;; esac
[ "${#SHA}" = 40 ] || { echo "FEHLER: IRL4YOU_COMMIT braucht die 40 Zeichen des Commits" >&2; exit 1; }
ID=$(echo "$SHA" | cut -c1-12)
mkdir -p "$ROOTDIR/releases"
if [ ! -d "$ROOTDIR/releases/$ID" ]; then
  python3 - "$REPO" "$ROOTDIR/releases/$ID" "$SHA" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/updater")
import irl4you_update as U
U.Updater.assemble(sys.argv[1], sys.argv[2], sys.argv[3])
PY
fi
ln -sfn "$ROOTDIR/releases/$ID" "$ROOTDIR/current"
if [ ! -L /opt/pipbox ]; then
  [ -e /opt/pipbox ] && mv /opt/pipbox /opt/pipbox.alt
  ln -s "$ROOTDIR/current" /opt/pipbox
fi
export IRL4YOU_ACTION=install IRL4YOU_ROOT="$ROOTDIR" IRL4YOU_RELEASE_DIR="$ROOTDIR/releases/$ID"
sh "$IRL4YOU_RELEASE_DIR/hooks/install"
echo "IRL4YOU BOX eingerichtet: Oberfläche auf Port 80 und 8780, Stand $ID."
