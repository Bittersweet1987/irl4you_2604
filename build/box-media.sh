#!/bin/bash
# Läuft AUF der Box (26.04): baut die Rockchip-Medienbibliotheken aus den Quellen und legt .deb nach $B/debs.
#   irl4you-mpp          rockchip-linux/mpp, Standard: Tag 1.1.0 (Release); MPP_REF=develop oder ein Commit geht auch
#   irl4you-rga          JeffyCN/mirrors, Zweig linux-rga-multi (Quelltext; airockchip/librga liefert nur fertige Binärdateien)
#   irl4you-gst-rockchip JeffyCN/mirrors, Zweig gstreamer-rockchip (mpph264enc, mpph265enc, mppvideodec, mppjpegdec, ...)
# Aufruf: box-media.sh [mpp|rga|gst|alle]. Installiert wird nichts: .deb testen, committen, per irl4you-update einspielen.
set -euo pipefail
B=${B:-/var/tmp/irl4you-build}
MPP_REF=${MPP_REF:-1.1.0}
mkdir -p "$B/debs"; cd "$B"
export DEBIAN_FRONTEND=noninteractive
log() { echo "[$(date +%H:%M:%S)] $*"; }

# mkdeb NAME VERSION STAGING "Depends" "Beschreibung" ["Lizenz[|Quelle]"]; die Lizenz kommt nach /usr/share/doc/NAME/copyright (Texte: NOTICE.md im Repo)
mkdeb() {
    local name=$1 ver=$2 st=$3 deps=$4 desc=$5 lic=${6:-CC-BY-ND-4.0|IRL4YOU}
    mkdir -p "$st/DEBIAN" "$st/usr/share/doc/$name"
    printf 'Paket: %s
Lizenz: %s
Quelle/Urheber: %s
Vollstaendige Lizenztexte: /usr/share/common-licenses und NOTICE.md im Repo Bittersweet1987/irl4you_2604
'         "$name" "${lic%%|*}" "${lic#*|}" > "$st/usr/share/doc/$name/copyright"
    printf 'Package: %s\nVersion: %s\nArchitecture: arm64\nMaintainer: IRL4YOU <irl4you@localhost>\nDepends: %s\nSection: video\nPriority: optional\nDescription: %s\n' \
        "$name" "$ver" "$deps" "$desc" > "$st/DEBIAN/control"
    dpkg-deb --root-owner-group --build "$st" "$B/debs/${name}_${ver}_arm64.deb" >/dev/null
    ls -la "$B/debs/${name}_${ver}_arm64.deb"
}

# fetch URL REF DIR: Quelltext holen und auf REF (Zweig, Tag oder Commit) stellen. Immer flach (depth 1): JeffyCN/mirrors enthaelt die
# Kernelzweige und waere als Vollklon 15 GB gross (hat beim ersten Versuch die Platte gefuellt).
fetch() {
    if [ ! -d "$B/$3/.git" ]; then git init -q "$B/$3"; git -C "$B/$3" remote add origin "$1"; fi
    git -C "$B/$3" fetch -q --depth 1 origin "$2"
    git -C "$B/$3" checkout -q -f FETCH_HEAD
    git -C "$B/$3" log -1 --format='%h %cs %s'
}

build_mpp() {
    log "irl4you-mpp ($MPP_REF)"
    apt-get install -y -q --no-install-recommends build-essential git cmake pkgconf >/dev/null
    fetch https://github.com/rockchip-linux/mpp.git "$MPP_REF" mpp
    cd "$B/mpp"; rm -rf b st
    cmake -S . -B b -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_BUILD_TYPE=Release -DBUILD_TEST=OFF -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu >/dev/null
    cmake --build b -j"$(nproc)" >"$B/mpp-build.log" 2>&1 || { tail -20 "$B/mpp-build.log"; exit 1; }
    DESTDIR="$PWD/st" cmake --install b >/dev/null
    local v; v="$(echo "$MPP_REF" | sed 's/[^0-9A-Za-z.]/./g').$(git log -1 --format=%cd --date=format:%Y%m%d)"
    mkdeb irl4you-mpp "$v" "$PWD/st" "libc6" "Rockchip MPP (Hardware-Video) fuer IRL4YOU, aus rockchip-linux/mpp gebaut" "Apache-2.0|Rockchip, rockchip-linux/mpp"
    cd "$B"
}

build_rga() {
    log "irl4you-rga"
    apt-get install -y -q --no-install-recommends build-essential git meson ninja-build libdrm-dev >/dev/null
    fetch https://github.com/JeffyCN/mirrors.git linux-rga-multi librga-src
    cd "$B/librga-src"; rm -rf b st
    meson setup b --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release -Dlibrga_demo=false >/dev/null
    meson compile -C b >"$B/rga-build.log" 2>&1 || { tail -20 "$B/rga-build.log"; exit 1; }
    DESTDIR="$PWD/st" meson install -C b >/dev/null
    mkdeb irl4you-rga "2.$(git log -1 --format=%cd --date=format:%Y%m%d)" "$PWD/st" "libc6, libstdc++6" "Rockchip RGA fuer IRL4YOU, aus dem Quelltext (JeffyCN/mirrors linux-rga-multi) gebaut" "Apache-2.0|Rockchip, JeffyCN/mirrors linux-rga-multi"
    cd "$B"
}

build_gst() {
    log "irl4you-gst-rockchip"
    apt-get install -y -q --no-install-recommends build-essential git meson ninja-build pkgconf libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
        libgstreamer-plugins-bad1.0-dev libdrm-dev libx11-dev >/dev/null
    # gebaut wird gegen die frisch gebauten Bibliotheken: erst in ein Zwischenverzeichnis installieren, damit pkg-config sie findet
    local P="$B/sysroot"; rm -rf "$P"; mkdir -p "$P"
    for d in "$B/mpp/st" "$B/librga-src/st"; do cp -a "$d/usr" "$P/" 2>/dev/null || true; done
    export PKG_CONFIG_PATH="$P/usr/lib/aarch64-linux-gnu/pkgconfig" CPATH="$P/usr/include:$P/usr/include/rockchip" LIBRARY_PATH="$P/usr/lib/aarch64-linux-gnu"
    fetch https://github.com/JeffyCN/mirrors.git gstreamer-rockchip gstreamer-rockchip
    cd "$B/gstreamer-rockchip"; rm -rf b st
    meson setup b --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release -Drockchipmpp=enabled -Drga=enabled >/dev/null 2>&1 \
        || meson setup b --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release >/dev/null
    meson compile -C b >"$B/gst-build.log" 2>&1 || { tail -20 "$B/gst-build.log"; exit 1; }
    DESTDIR="$PWD/st" meson install -C b >/dev/null
    mkdeb irl4you-gst-rockchip "1.$(git log -1 --format=%cd --date=format:%Y%m%d).${PKG_REV:-1}" "$PWD/st" \
        "irl4you-mpp, irl4you-rga, libgstreamer1.0-0, libgstreamer-plugins-base1.0-0" "GStreamer-Elemente fuer Rockchip MPP/RGA fuer IRL4YOU (gstreamer-rockchip)" "LGPL-2.1|Rockchip/JeffyCN, gstreamer-rockchip"
    cd "$B"
}

case "${1:-alle}" in
    mpp) build_mpp ;;
    rga) build_rga ;;
    gst) build_gst ;;
    alle) build_mpp; build_rga; build_gst ;;
    *) echo "Aufruf: $0 mpp|rga|gst|alle"; exit 2 ;;
esac
log "fertig"
