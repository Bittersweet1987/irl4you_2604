#!/bin/sh
# IRL4YOU BOX: Dienste, Netz, udev, RTMP, venv und PiP-Baustein einrichten (Ubuntu 26.04, ohne BELABOX). Wird von install/system-install.sh
# aufgerufen (nach Basis-Anpassungen und eigenen .deb-Paketen). Kopiert keine Programmdateien: die liegen unter
# /opt/irl4you/releases/<Version>, /opt/pipbox zeigt auf die aktive Version. Darf mehrfach laufen.
#
# Umgebung (setzt der Update-Helfer; von Hand: IRL4YOU_RELEASE_DIR=<Ordner dieser Version> sh install/irl4you-setup.sh):
#   IRL4YOU_RELEASE_DIR   Ordner der Version (Standard: Ordner über diesem Skript)
#   IRL4YOU_CHROOT=1      im chroot des neuen Systems: nichts starten, kein nmcli/udevadm/nginx-Reload
set -eu
HERE="${IRL4YOU_RELEASE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CHROOT="${IRL4YOU_CHROOT:-0}"
OPT=/opt/pipbox
VENV=/opt/irl4you/venv
STATE=/var/lib/pipbox
step() { echo "PIPBOX-STEP $1"; }
now() { [ "$CHROOT" = 0 ]; }

step pakete
need=""
for p in python3 python3-venv python3-gi python3-dbus python3-bcrypt bluez gstreamer1.0-tools network-manager modemmanager \
         usb-modeswitch usb-modeswitch-data mobile-broadband-provider-info nginx libnginx-mod-stream libssl3t64 openssl iproute2 util-linux; do
  dpkg -s "$p" >/dev/null 2>&1 || need="$need $p"
done
if [ -n "$need" ]; then
  echo "Installiere fehlende Pakete:$need"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $need
fi

step benutzer
getent group bluetooth >/dev/null || groupadd --system bluetooth
getent group input >/dev/null || groupadd --system input
if ! grep -q '^pipbox:' /etc/passwd; then
  useradd --system --no-create-home --home-dir "$STATE" --shell /usr/sbin/nologin --groups bluetooth pipbox
fi
mkdir -p "$STATE"

chown pipbox:pipbox "$STATE"
chmod 700 "$STATE"

step bleak
# bleak/dbus-fast für den DJI-Dienst: unter 26.04 kein pip als root (PEP 668), darum eine eigene Umgebung (ein gemeinsamer Ordner für alle Versionen,
# nicht in der Version selbst). --system-site-packages: python3-gi und python3-dbus aus Ubuntu bleiben sichtbar.
# Feste Versionen aus install/requirements.txt, installiert nur wenn etwas fehlt oder die Datei sich geändert hat. Ohne Internet bleibt eine
# vorhandene Umgebung unverändert (kein Abbruch des Updates); fehlt sie ganz, ist das ein Fehler.
mkdir -p /opt/irl4you
[ -x "$VENV/bin/python3" ] || python3 -m venv --system-site-packages "$VENV"
REQ_SUM=$(sha256sum "$HERE/install/requirements.txt" | cut -d' ' -f1)
if [ "$(cat "$VENV/.requirements.sha256" 2>/dev/null)" != "$REQ_SUM" ] || ! "$VENV/bin/python3" -c "import bleak, dbus_fast" 2>/dev/null; then
  if "$VENV/bin/pip" install --disable-pip-version-check --quiet -r "$HERE/install/requirements.txt"; then
    echo "$REQ_SUM" > "$VENV/.requirements.sha256"
  else
    echo "WARNUNG: bleak/dbus-fast konnten nicht installiert werden (Internet?)" >&2
  fi
fi
"$VENV/bin/python3" -c "import bleak, dbus_fast" || { echo "FEHLER: bleak fehlt in $VENV (Internet?)" >&2; exit 1; }

step baustein
# Bild-in-Bild-Baustein: wird in den Ordner dieser Version gebaut (jede Version hat ihren eigenen), nur wenn er fehlt oder der Quelltext neuer ist
if [ -f "$HERE/gst-src/gstpbpip.c" ]; then
  mkdir -p "$HERE/gst"
  if [ ! -f "$HERE/gst/libgstpbpip.so" ] || ! cmp -s "$HERE/gst-src/gstpbpip.c" "$HERE/gst/.gstpbpip.c" 2>/dev/null; then
    if PBOUT="$HERE/gst" sh "$HERE/gst-src/build.sh"; then cp "$HERE/gst-src/gstpbpip.c" "$HERE/gst/.gstpbpip.c"; else
      echo "WARNUNG: Der PiP-Baustein konnte nicht gebaut werden; Bild-in-Bild bleibt gesperrt."; fi
  fi
fi

step netz
# NetworkManager verwaltet alle Karten; Quell-Routing, Ausweichweg und Zusatzadresse als Dispatcher-Skripte
install -m 644 "$HERE/install/net/90-irl4you.conf" /etc/NetworkManager/conf.d/90-irl4you.conf
for f in pipbox-source-routing pipbox-fallback-route; do
  install -m 755 "$HERE/install/net/$f" "/etc/NetworkManager/dispatcher.d/$f"
done
install -d /etc/iproute2/rt_tables.d
python3 "$OPT/pipbox-netaddr.py" --refresh || true
# Feste Kartennamen nach MAC: nur Dateien schreiben (/etc/pipbox/netnames.json, /etc/systemd/network/10-irl4you-*.link). Sie gelten beim nächsten Start.
# NIE im laufenden Betrieb umbenennen: das trennt die Karte, DHCP bricht ab und die Box ist nicht mehr erreichbar.
if now; then python3 "$OPT/pipbox-netnames.py" || true; fi      # im chroot nicht: dort sind es die Karten des Bau-Rechners
# Reste der ersten Fassung (Dienst, der im Betrieb umbenannte) entfernen
if [ -e /etc/systemd/system/pipbox-netnames.service ]; then
  systemctl disable pipbox-netnames.service 2>/dev/null || true
  rm -f /etc/systemd/system/pipbox-netnames.service /etc/systemd/system/sysinit.target.wants/pipbox-netnames.service
fi
# ifupdown und ifplugd übernehmen die LAN-Karten nicht mehr (nur ausschalten, nicht jetzt anhalten: sonst könnte die Verbindung abreißen)
for u in ifplugd.service networking.service; do
  systemctl disable "$u" 2>/dev/null || true
done

step udev
install -m 644 "$HERE/install/udev/80-irl4you-capture.rules" /etc/udev/rules.d/80-irl4you-capture.rules
install -m 644 "$HERE/install/udev/85-irl4you-audio.rules" /etc/udev/rules.d/85-irl4you-audio.rules
install -m 644 "$HERE/install/udev/41-irl4you-modeswitch.rules" /etc/udev/rules.d/41-irl4you-modeswitch.rules
for r in 80-pipbox-btdriver.rules 81-pipbox-btchip.rules 81-pipbox-wlandriver.rules; do
  [ -f "$HERE/install/udev/$r" ] && install -m 644 "$HERE/install/udev/$r" "/etc/udev/rules.d/$r"
done
if now; then udevadm control --reload-rules 2>/dev/null || true; udevadm trigger --subsystem-match=video4linux --subsystem-match=sound 2>/dev/null || true; fi

step rtmp
# Port 80 gehört der Oberfläche: die Beispielseite von nginx darf ihn nicht belegen
rm -f /etc/nginx/sites-enabled/default
# RTMP-Eingang ist SRS (irl4you-srs, Pakete aus debs/); nginx macht nur noch RTMPS (TLS auf 1934 -> 127.0.0.1:1935).
# Reste der früheren nginx-rtmp-Einrichtung entfernen; dann muss nginx neu starten (ein Neuladen gibt Port 1935/1936 nicht frei).
# Nur umstellen, wenn SRS da ist (Paket irl4you-srs aus debs/); sonst bleibt der bisherige Eingang unberührt, damit die Kameras nicht ohne Server dastehen.
old_rtmp=0
srs_changed=0
SRS_OK=0
[ -x /usr/bin/irl4you-srs ] && SRS_OK=1
if [ "$SRS_OK" = 1 ]; then
  for f in /etc/nginx/modules-enabled/99-irl4you-rtmp.conf /etc/nginx/sites-enabled/irl4you-rtmp-stats /etc/nginx/sites-available/irl4you-rtmp-stats; do
    [ -e "$f" ] && { rm -f "$f"; old_rtmp=1; }
  done
  install -d /etc/irl4you
  cmp -s "$HERE/install/srs/srs.conf" /etc/irl4you/srs.conf 2>/dev/null || srs_changed=1
  install -m 644 "$HERE/install/srs/srs.conf" /etc/irl4you/srs.conf
  install -m 644 "$HERE/install/nginx/99-irl4you-rtmps.conf" /etc/nginx/modules-enabled/99-irl4you-rtmps.conf
else
  echo "WARNUNG: /usr/bin/irl4you-srs fehlt (Paket irl4you-srs in debs/): der RTMP-Eingang bleibt, wie er ist." >&2
fi
if [ ! -f /etc/nginx/certs/rtmps/cert.pem ]; then
  install -d -m 755 /etc/nginx/certs/rtmps
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=irl4you-box" \
    -keyout /etc/nginx/certs/rtmps/privkey.pem -out /etc/nginx/certs/rtmps/cert.pem 2>/dev/null
  chmod 600 /etc/nginx/certs/rtmps/privkey.pem
fi
nginx -t
# im chroot nicht: /run gehört dort dem laufenden System, ein "nginx -s reload" träfe dessen nginx
if now; then python3 "$HERE/pipbox-logmode.py" --apply-nginx 2>/dev/null || true; fi

step dienste
for f in "$HERE"/install/*.service "$HERE"/install/*.path "$HERE"/install/*.timer "$HERE"/install/*.socket; do
  install -m 644 "$f" "/etc/systemd/system/$(basename "$f")"
done
# Reste der alten Fassung (Software-Update lief früher über pipbox-swupdate, jetzt über irl4you-update)
rm -f /etc/systemd/system/pipbox-swupdate.service /etc/systemd/system/pipbox-swupdate.path
mkdir -p /etc/systemd/system/tailscaled.service.d
[ -f "$HERE/install/tailscaled-pipbox-order.conf" ] && install -m 644 "$HERE/install/tailscaled-pipbox-order.conf" /etc/systemd/system/tailscaled.service.d/pipbox-order.conf
UNITS="pipbox.service pipbox-dji.service pipbox-hdmi.service pipbox-health.service pipbox-arp.service
  pipbox-update.path pipbox-send-ctl.path pipbox-remote.path pipbox-remote-heal.timer pipbox-wifi.path
  pipbox-power.path pipbox-logmode.path pipbox-netaddr.path pipbox-logs.path pipbox-ssh.path pipbox-btdriver.timer pipbox-btdriver.path
  pipbox-wlandriver.timer pipbox-btchip.path pipbox-btchip.service pipbox-logrotate.timer pipbox-preview.socket
  pipbox-modem.path pipbox-modem-apply.timer irl4you-srs.service pipbox-rtmpstat.service NetworkManager.service ModemManager.service nginx.service ssh.service"
if now; then
  systemctl daemon-reload
  systemctl disable pipbox-swupdate.path 2>/dev/null || true
  systemctl enable $UNITS
  # nginx nur neu laden (trennt die Kameras nicht), starten, wenn es nicht läuft
  if [ "$old_rtmp" = 1 ] && systemctl is-active --quiet nginx.service; then systemctl restart nginx.service
  elif systemctl is-active --quiet nginx.service; then systemctl reload nginx.service; else systemctl start nginx.service; fi
  # RTMP-Eingang und Statistik: starten, wenn sie noch nicht laufen (nach einem Wechsel von nginx-rtmp auf SRS neu)
  # geänderte SRS-Konfiguration: Neustart trennt die Kameras kurz, darum nie während einer Sendung (dann gilt sie ab dem nächsten Start)
  if [ "$srs_changed" = 1 ] && systemctl is-active --quiet irl4you-srs.service && ! pgrep -x irl4you-encoder >/dev/null 2>&1; then
    systemctl restart irl4you-srs.service
  fi
  if [ "$SRS_OK" = 1 ]; then systemctl start irl4you-srs.service pipbox-rtmpstat.service || echo "WARNUNG: irl4you-srs lief nicht an" >&2; fi
  # Dienste, die schon laufen, startet der Update-Helfer laut Manifest ("restart") neu; hier nur, was noch nicht läuft
  systemctl start pipbox-dji.service pipbox-hdmi.service pipbox-health.service pipbox.service
  systemctl start pipbox-modem-apply.timer --no-block || true
else
  # im chroot nur einschalten (Verknüpfungen anlegen), nichts starten
  for u in $UNITS; do systemctl enable "$u" 2>/dev/null || echo "Hinweis: $u nicht eingeschaltet"; done
fi
echo "IRL4YOU BOX: Systemteile eingerichtet (Oberfläche auf Port 80 und 8780)."
