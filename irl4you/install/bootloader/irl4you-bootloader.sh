#!/bin/sh
# Tauscht den FIT-Teil (U-Boot + BL31) auf der SD-Karte der Orange Pi 5 Plus. Nur Sektor 16384 ff., sonst nichts.
# Aufruf als root:  irl4you-bootloader status | apply | restore
# apply   schreibt BL31 v1.47 (Sicherung des Ist-Stands nach /var/lib/irl4you/bootloader-backup)
# restore schreibt den ursprünglichen Stand (BL31 v1.45) zurück
# Wird NICHT automatisch beim Update ausgeführt. Startet die Box nach apply nicht mehr, hilft nur die Karte am PC (restore-fit.ps1).
set -eu
HERE=$(dirname "$(readlink -f "$0")")
DEV=${DEV:-/dev/mmcblk1}; SEEK=16384
NEW="$HERE/fit-opi5plus-bl31-v1.47.bin"; ORIG="$HERE/fit-opi5plus-orig-bl31-v1.45.bin"
BK=/var/lib/irl4you/bootloader-backup
hash_of() { sha256sum | cut -d' ' -f1; }
cur() { dd if="$DEV" bs=512 skip=$SEEK count=$(( $(stat -c %s "$1") / 512 )) status=none | hash_of; }
want() { hash_of < "$1"; }
write() { dd if="$1" of="$DEV" bs=512 seek=$SEEK conv=fsync status=none; sync; [ "$(cur "$1")" = "$(want "$1")" ] || { echo "FEHLER: Rücklesen stimmt nicht"; exit 1; }; }
case "${1:-status}" in
status)
    for f in "$ORIG" "$NEW"; do [ "$(cur "$f")" = "$(want "$f")" ] && echo "aktiv: $(basename "$f")"; done; exit 0 ;;
apply|restore)
    [ "$(id -u)" = 0 ] || { echo "nur als root"; exit 1; }
    grep -q "Orange Pi 5 Plus" /proc/device-tree/model || { echo "nur Orange Pi 5 Plus"; exit 1; }
    if [ "$1" = apply ]; then SRC=$NEW; OTHER=$ORIG; else SRC=$ORIG; OTHER=$NEW; fi
    # nur schreiben, wenn der Ist-Stand der bekannte andere ist (nichts Unbekanntes überschreiben)
    if [ "$(cur "$SRC")" = "$(want "$SRC")" ]; then echo "schon aktiv"; exit 0; fi
    if [ "$(cur "$OTHER")" != "$(want "$OTHER")" ]; then echo "FEHLER: unbekannter Stand im FIT-Bereich, nichts geschrieben"; exit 1; fi
    mkdir -p "$BK"; dd if="$DEV" bs=512 skip=$SEEK count=$(( $(stat -c %s "$OTHER") / 512 )) of="$BK/fit-$(date +%Y%m%d%H%M%S).bin" status=none
    write "$SRC"; echo "geschrieben: $(basename "$SRC"). Neustart nötig." ;;
*) echo "Aufruf: $0 status|apply|restore"; exit 1 ;;
esac
