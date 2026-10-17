#!/bin/bash
# Läuft AUF der Box (26.04): baut eigene Pakete direkt im Bauordner /var/tmp/irl4you-build und legt die .deb in $B/debs.
# Nichts davon wird ins System installiert. Aufruf: box-build.sh <encoder|srtla|srs|pbpip|rtw88|aic8800|alle>
# Reihenfolge der Auslieferung: bauen -> testen -> .deb nach irl4you/debs/ committen -> per irl4you-update installieren.
set -euo pipefail
B=${B:-/var/tmp/irl4you-build}
KVER=$(uname -r)
PIP_REPO=${PIP_REPO:-https://github.com/Bittersweet1987/irl4you-pip.git}
mkdir -p "$B/debs"; cd "$B"
export DEBIAN_FRONTEND=noninteractive
log() { echo "[$(date +%H:%M:%S)] $*"; }

# mkdeb NAME VERSION STAGING "Depends" "Beschreibung"
mkdeb() {
    local name=$1 ver=$2 st=$3 deps=$4 desc=$5
    mkdir -p "$st/DEBIAN"
    printf 'Package: %s\nVersion: %s\nArchitecture: arm64\nMaintainer: IRL4YOU <irl4you@localhost>\nDepends: %s\nSection: video\nPriority: optional\nDescription: %s\n' \
        "$name" "$ver" "$deps" "$desc" > "$st/DEBIAN/control"
    dpkg-deb --root-owner-group --build "$st" "$B/debs/${name}_${ver}_arm64.deb" >/dev/null
    ls -la "$B/debs/${name}_${ver}_arm64.deb"
}

# PR-Stand aus irl4you-pip holen (Entwürfe, solange nicht gemergt): pip_src <Verzeichnis> <PR-Nummer>
pip_src() {
    if [ ! -d "$B/$1/.git" ]; then git clone -q "$PIP_REPO" "$B/$1"; fi
    git -C "$B/$1" fetch -q origin "pull/$2/head:pr$2" 2>/dev/null || git -C "$B/$1" fetch -q origin main
    git -C "$B/$1" checkout -q -f "pr$2" 2>/dev/null || git -C "$B/$1" checkout -q -f origin/main
    git -C "$B/$1" log -1 --format='%h %cs %s'
}

build_encoder() {
    log "irl4you-encoder"
    apt-get install -y -q --no-install-recommends meson ninja-build gcc pkgconf libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
        libjson-glib-dev libsrt-gnutls-dev srt-tools gstreamer1.0-plugins-ugly gstreamer1.0-plugins-bad gstreamer1.0-libav >/dev/null
    pip_src pip-encoder 2
    cd "$B/pip-encoder/encoder"; rm -rf b st
    meson setup b --prefix=/usr >/dev/null; meson compile -C b 2>&1 | tail -3
    meson test -C b --print-errorlogs 2>&1 | tail -6
    DESTDIR="$PWD/st" meson install -C b >/dev/null
    local v; v=$(sed -n "s/.*version : '\([^']*\)'.*/\1/p" meson.build | head -1)
    mkdeb irl4you-encoder "$v" "$PWD/st" "libgstreamer1.0-0, libgstreamer-plugins-base1.0-0, libjson-glib-1.0-0, libsrt1.5-gnutls" "Encoder fuer IRL4YOU (eigene Entwicklung)"
    cd "$B"
}

build_srtla() {
    log "irl4you-srtla"
    apt-get install -y -q --no-install-recommends gcc make >/dev/null
    pip_src pip-srtla 1
    cd "$B/pip-srtla/srtla"; rm -rf build st
    make 2>&1 | tail -3
    make test 2>&1 | tail -8
    make install PREFIX=/usr DESTDIR="$PWD/st" >/dev/null
    mkdeb irl4you-srtla "$(cat VERSION)" "$PWD/st" "libc6, python3" "SRTLA-Buendel-Sender fuer IRL4YOU (eigene Entwicklung)"
    cd "$B"
}

build_srs() {
    log "irl4you-srs (SRS 6)"
    apt-get install -y -q --no-install-recommends build-essential git cmake tcl patch unzip pkgconf libssl-dev ca-certificates >/dev/null
    if [ -d srs/.git ]; then git -C srs fetch -q --depth 1 origin 6.0release && git -C srs reset -q --hard FETCH_HEAD
    else git clone -q --depth 1 --branch 6.0release https://github.com/ossrs/srs.git srs; fi
    git -C srs log -1 --format='%h %cs %s'
    cd srs/trunk
    # Fehler in SRS 6.0release: "edge" wird in srs_app_srt_conn.cpp nur im #ifdef SRS_RTC deklariert, aber auch ohne RTC benutzt (Bau mit --rtc=off bricht ab).
    # Minimale Korrektur: die Abfrage dort direkt stellen (Verhalten gleich).
    sed -i 's/if (srt_to_rtmp \&\& edge) {/if (srt_to_rtmp \&\& _srs_config->get_vhost_is_edge(req_->vhost)) {/' src/app/srs_app_srt_conn.cpp
    ./configure --jobs="$(nproc)" --h265=on --srt=on --rtc=off --gb28181=off --utest=off --https=on --static=off --sanitizer=off --prefix=/usr/lib/irl4you-srs > "$B/srs-configure.log" 2>&1 || { tail -30 "$B/srs-configure.log"; exit 1; }
    make -j"$(nproc)" > "$B/srs-make.log" 2>&1 || { tail -30 "$B/srs-make.log"; exit 1; }; test -x objs/srs; ./objs/srs -v
    rm -rf ../st; install -D -m 755 objs/srs ../st/usr/bin/irl4you-srs
    local v; v=$(awk '/VERSION_MAJOR/{a=$3} /VERSION_MINOR/{b=$3} /VERSION_REVISION/{c=$3} END{print a"."b"."c}' src/core/srs_core_version6.hpp)
    mkdeb irl4you-srs "$v" "$B/srs/st" "libc6, libstdc++6, libssl3t64" "RTMP/HEVC-Eingang fuer IRL4YOU (SRS 6, ossrs/srs)"
    cd "$B"
}

build_pbpip() {
    log "irl4you-pbpip (Bild-in-Bild-Baustein)"
    apt-get install -y -q --no-install-recommends gcc pkgconf libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev >/dev/null
    local src; src="$(cd "$(dirname "$0")/.." && pwd)/irl4you/gst-src/gstpbpip.c"
    test -f "$src" || { echo "FEHLER: $src fehlt"; exit 1; }
    rm -rf "$B/pbpip-st"; mkdir -p "$B/pbpip-st/opt/irl4you/gst"
    gcc -O2 -Wall -fPIC -shared -DPACKAGE=\"irl4you\" "$src" -o "$B/pbpip-st/opt/irl4you/gst/libgstpbpip.so"         $(pkg-config --cflags --libs gstreamer-video-1.0 gstreamer-base-1.0 gstreamer-1.0)
    GST_PLUGIN_PATH="$B/pbpip-st/opt/irl4you/gst" gst-inspect-1.0 pbpip | head -4
    mkdeb irl4you-pbpip "1.0.$(date +%Y%m%d)" "$B/pbpip-st" "libgstreamer1.0-0, libgstreamer-plugins-base1.0-0, libc6" "Bild-in-Bild-Baustein fuer IRL4YOU (eigene Entwicklung), nach /opt/irl4you/gst"
}

case "${1:-alle}" in
    encoder) build_encoder ;;
    srtla)   build_srtla ;;
    srs)     build_srs ;;
    pbpip)   build_pbpip ;;
    rtw88)   bash "$(dirname "$0")/10-rtw88.sh" ;;
    aic8800) bash "$(dirname "$0")/11-aic8800.sh" ;;
    alle)    build_srtla; build_encoder; build_srs; build_pbpip ;;
    *) echo "Aufruf: $0 encoder|srtla|srs|pbpip|rtw88|aic8800|alle"; exit 2 ;;
esac
log "fertig"
