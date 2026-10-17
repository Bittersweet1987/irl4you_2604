#!/bin/sh
# Baut das Release-Paket irl4you-<Version>.tar.gz und die Prüfdatei dazu.
#   tools/build-release.sh [Quellordner] [Ausgabeordner]
# Quellordner: Programmstand von IRL4YOU (Standard: irl4you/), Ausgabe: Standard dist/.
# Die Version kommt aus der Datei VERSION im Wurzelordner des Repositorys.
# Das Paket ist reproduzierbar (feste Reihenfolge, Zeitstempel und Besitzer).
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
src=${1:-$here/irl4you}
out=${2:-$here/dist}
version=$(tr -d ' \n\r' < "$here/VERSION")
echo "$version" | grep -Eq '^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}(-[a-z0-9.]{1,20})?$' || { echo "VERSION ungültig: $version" >&2; exit 1; }
[ -d "$src" ] || { echo "Quellordner fehlt: $src" >&2; exit 1; }

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
tree="$stage/tree"
mkdir -p "$tree"
# Programmstand (ohne Git-Daten und Zwischenstände)
( cd "$src" && tar --exclude=.git --exclude=__pycache__ --exclude='*.pyc' -cf - . ) | ( cd "$tree" && tar -xf - )
# Bestandteile, die jedes Paket hat
printf '%s\n' "$version" > "$tree/VERSION"
sed "s/@VERSION@/$version/" "$here/release/manifest.json" > "$tree/manifest.json"
mkdir -p "$tree/hooks" "$tree/updater/systemd"
cp "$here"/release/hooks/* "$tree/hooks/"
cp "$here/updater/irl4you_update.py" "$here/updater/update.conf.example" "$tree/updater/"
cp "$here"/updater/systemd/* "$tree/updater/systemd/"
chmod 755 "$tree"/hooks/* "$tree/updater/irl4you_update.py"
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$tree/manifest.json"

mkdir -p "$out"
name="irl4you-$version.tar.gz"
epoch=${SOURCE_DATE_EPOCH:-$(git -C "$here" log -1 --format=%ct 2>/dev/null || echo 0)}
( cd "$tree" && tar --sort=name --mtime="@$epoch" --owner=0 --group=0 --numeric-owner \
      --pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime -cf - . ) | gzip -n -9 > "$out/$name"
( cd "$out" && sha256sum "$name" > "$name.sha256" )
echo "$out/$name"
cat "$out/$name.sha256"
