#!/bin/sh
# Root-Partition und Dateisystem auf die ganze Karte vergrößern (einmalig; macht nichts, wenn hinter der Partition kein Platz mehr ist).
# Das Image ist klein, damit es auf jede Karte passt; die Box braucht den Platz für Aufnahmen, Protokolle und Updates.
set -eu
mm=$(findmnt -n -o MAJ:MIN / | tr -d ' ') || exit 0
name=$(basename "$(readlink -f "/sys/dev/block/$mm")")
[ -r "/sys/class/block/$name/partition" ] || exit 0          # kein Partitions-Gerät (z. B. Netzwerk-Root): nichts tun
disk=/dev/$(lsblk -no pkname "/dev/$name")
part=$(cat "/sys/class/block/$name/partition")
if ! command -v growpart >/dev/null 2>&1; then
    apt-get update -q >/dev/null 2>&1 || true
    apt-get install -y -q --no-install-recommends cloud-guest-utils >/dev/null 2>&1 || { echo "grow-rootfs: growpart nicht verfügbar, übersprungen"; exit 0; }
fi
if growpart --dry-run "$disk" "$part" >/dev/null 2>&1; then
    growpart "$disk" "$part" >/dev/null
    resize2fs "/dev/$name" >/dev/null 2>&1
    echo "grow-rootfs: /dev/$name vergrößert"
fi
