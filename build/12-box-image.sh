#!/bin/bash
# Bootfähiges Image (.img.zip) aus der LAUFENDEN Box erzeugen. Läuft als root auf der Box; die Box wird nur gelesen
# (Ablage und Arbeitsdatei unter $WORK, nichts am System selbst wird geändert, kein Dienst gestoppt).
#
# Aufruf:  sudo build/12-box-image.sh [ausgabe-name]
# Umgebung:
#   SCRUB=1 (Standard)  persönliche Daten entfernen (für Release/Weitergabe); SCRUB=0 = Testkopie mit allem (nur für Marco selbst)
#   SIZE_MB             Größe der Partition/des Images (Standard: belegter Platz + Reserve, mindestens 4096)
#   WORK                Arbeitsordner (Standard /var/tmp/irl4you-image)
#   NAME                Dateiname ohne Endung (Standard irl4you-2604-<board>-<version>)
#   BOARD / BOOTLOADER  anderes Board: Name (z. B. rock-5b-plus) und Bootloader-Datei (u-boot-rockchip.bin, kommt ab Sektor 64 statt der Karten-Kopie)
#   FORCE=1             auch bauen, wenn gerade gesendet wird (nicht empfohlen)
#
# Image-Layout wie auf der Box: GPT, Partition 1 ab Sektor 32768 (16 MiB), ext4 ohne 64bit/metadata_csum (U-Boot 2017 liest nur das
# ältere Format), Bootloader ab Sektor 64 wird 1:1 von der Box-Karte übernommen, neue PARTUUID/UUID je Image.
# Das Image wächst beim ersten Start über grow-rootfs auf die ganze Karte.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Nur als root"; exit 1; }
WORK=${WORK:-/var/tmp/irl4you-image}
SCRUB=${SCRUB:-1}
M=$WORK/mnt
log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { log "FEHLER: $*"; exit 1; }

if [ "${FORCE:-0}" != 1 ] && pgrep -f 'irl4you-encoder|srtla_send' >/dev/null; then
    die "Es wird gesendet. Erst nach der Sendung bauen (oder FORCE=1)."
fi
for t in rsync sfdisk mkfs.ext4 losetup python3 blkid; do command -v $t >/dev/null || die "$t fehlt"; done

# Quelle: Karte, auf der / liegt
ROOTDEV=$(findmnt -n -o SOURCE /)
if [ "$ROOTDEV" = /dev/root ]; then
    PU=$(tr ' ' '
' < /proc/cmdline | sed -n 's/^root=PARTUUID=//p')
    ROOTDEV=$(blkid -t "PARTUUID=$PU" -o device)
fi
DISK=/dev/$(lsblk -no pkname "$ROOTDEV")
[ -b "$DISK" ] || die "Karte nicht gefunden"
VERSION=$(readlink /opt/irl4you/current | xargs basename 2>/dev/null || echo unbekannt)
BOARD=${BOARD:-$(tr -d '\0' < /proc/device-tree/model 2>/dev/null | tr 'A-Z ' 'a-z-' | sed 's/rockchip.*//;s/-$//;s/[^a-z0-9-]//g')}
NAME=${NAME:-irl4you-2604-${BOARD:-board}-$VERSION}

USED_MB=$(du -xsm --exclude=/var/tmp --exclude=/var/cache/apt/archives / 2>/dev/null | cut -f1)
SIZE_MB=${SIZE_MB:-$(( (USED_MB > 4096 ? USED_MB : 4096) + 1200 ))}
FREE_MB=$(df --output=avail -BM "$(dirname "$WORK")" | tail -1 | tr -dc 0-9)
# beschrieben wird nur der belegte Teil (Image ist sparse), dazu das Zip (ca. die H�lfte)
NEED_MB=$(( USED_MB * 3 / 2 + 1500 ))
[ "$FREE_MB" -gt "$NEED_MB" ] || die "Zu wenig Platz in $(dirname "$WORK"): $FREE_MB MB frei, gebraucht ca. $NEED_MB"

IMG=$WORK/$NAME.img
mkdir -p "$WORK" "$M"
cleanup() { mountpoint -q "$M" && umount "$M" || true; [ -n "${LOOP:-}" ] && losetup -d "$LOOP" 2>/dev/null || true; }
trap cleanup EXIT
nice_() { nice -n 19 ionice -c3 "$@"; }

log "Image $NAME.img (${SIZE_MB} MB), Quelle $ROOTDEV auf $DISK, SCRUB=$SCRUB"
rm -f "$IMG" "$IMG.zip"
truncate -s $(( SIZE_MB + 16 + 1 ))M "$IMG"
PARTUUID=$(cat /proc/sys/kernel/random/uuid)
FSUUID=$(cat /proc/sys/kernel/random/uuid)
sfdisk -q "$IMG" <<EOF
label: gpt
first-lba: 34
start=32768, size=$(( SIZE_MB * 2048 )), type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$PARTUUID, name=rootfs, attrs="LegacyBIOSBootable"
EOF
log "Bootloader ab Sektor 64 ${BOOTLOADER:+aus $BOOTLOADER}${BOOTLOADER:-von der Box-Karte} übernehmen"
if [ -n "${BOOTLOADER:-}" ]; then nice_ dd if="$BOOTLOADER" of="$IMG" bs=512 seek=64 conv=notrunc status=none
else nice_ dd if="$DISK" of="$IMG" bs=512 skip=64 seek=64 count=32704 conv=notrunc status=none; fi
LOOP=$(losetup -fP --show "$IMG")
mkfs.ext4 -q -L rootfs -U "$FSUUID" -O ^64bit,^metadata_csum "${LOOP}p1"
mount "${LOOP}p1" "$M"

log "Dateien kopieren (rsync, nur lesend an der Box)"
nice_ rsync -aHAXx --numeric-ids \
    --exclude=/proc/* --exclude=/sys/* --exclude=/dev/* --exclude=/run/* --exclude=/tmp/* --exclude=/mnt/* --exclude=/media/* \
    --exclude=/var/tmp/* --exclude=/var/cache/apt/archives/*.deb --exclude=/var/cache/apt/*.bin --exclude=/lost+found \
    --exclude=/swapfile / "$M/"
mkdir -p "$M"/{proc,sys,dev,run,tmp,mnt,media}; chmod 1777 "$M/tmp"; mkdir -p "$M/var/tmp"; chmod 1777 "$M/var/tmp"

log "Boot-Einträge auf neue PARTUUID"
OLD=$(sed -n 's/^PARTUUID=\([^ ]*\).*/\1/p' "$M/etc/fstab" | head -1)
[ -n "$OLD" ] || die "PARTUUID in fstab nicht gefunden"
sed -i "s/$OLD/$PARTUUID/g" "$M/etc/fstab" "$M/boot/extlinux/extlinux.conf"
grep -q "$PARTUUID" "$M/boot/extlinux/extlinux.conf" || die "extlinux.conf nicht angepasst"

if [ "$SCRUB" = 1 ]; then
    log "Persönliche Daten entfernen"
    source "$(dirname "$(readlink -f "$0")")/12-box-image-scrub.sh"
    scrub_image "$M"
fi

log "Prüfen"
[ -f "$M/boot/Image" ] && [ -d "$M/boot/dtb" ] || die "Kernel oder dtb fehlt im Image"
e2fsck -fn "${LOOP}p1" >/dev/null 2>&1 || true
sync; umount "$M"; e2fsck -fn "${LOOP}p1" | tail -1
losetup -d "$LOOP"; LOOP=

log "Packen (.img.zip)"
nice_ python3 - "$IMG" <<'PY'
import sys, zipfile
img = sys.argv[1]
with zipfile.ZipFile(img + ".zip", "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
    z.write(img, img.rsplit("/", 1)[-1])
PY
rm -f "$IMG"
( cd "$WORK" && sha256sum "$NAME.img.zip" > "$NAME.img.zip.sha256" )
ls -l "$WORK"
log "fertig: $WORK/$NAME.img.zip"
