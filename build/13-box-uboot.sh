#!/bin/bash
# U-Boot (u-boot.org, mainline) für ROCK 5B/5B+ direkt auf der Box bauen. Ergebnis: $OUTBIN (u-boot-rockchip.bin, kommt ab Sektor 64 auf die Karte).
# DDR-Init und BL31 stammen aus rockchip-linux/rkbin (Binärdateien von Rockchip). Nichts von BELABOX.
# swig fehlt auf der Box: wird nur als .deb heruntergeladen und in $W/swig entpackt (nichts installiert).
# Aufruf als root: build/13-box-uboot.sh [defconfig-name]   (Standard rock5b-rk3588_defconfig, erkennt 5B, 5B+ und 5T selbst)
set -euo pipefail
W=${W:-/var/tmp/irl4you-build/uboot}
TAG=${UBOOT_TAG:-v2026.10}
DEFCONFIG=${1:-rock5b-rk3588_defconfig}
OUTBIN=${OUTBIN:-$W/u-boot-rock-5b-plus.bin}
log() { echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p "$W/swig"; cd "$W"
if [ ! -x swig/root/usr/bin/swig ]; then
    (cd swig && apt-get download swig >/dev/null 2>&1 && dpkg -x swig_*.deb root)
fi
export SWIG_LIB=$(ls -d "$W"/swig/root/usr/share/swig/* | head -1) PATH="$W/swig/root/usr/bin:$PATH"
[ -d u-boot/.git ] || git clone -q --depth 1 --branch "$TAG" https://github.com/u-boot/u-boot.git u-boot
[ -d rkbin/.git ] || git clone -q --depth 1 https://github.com/rockchip-linux/rkbin.git rkbin
git -C rkbin pull -q --ff-only || true
git -C u-boot log -1 --format='U-Boot %h %cs'; git -C rkbin log -1 --format='rkbin %h %cs'
DDR=$(ls "$W"/rkbin/bin/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v*.bin | sort -V | tail -1)
BL31=$(ls "$W"/rkbin/bin/rk35/rk3588_bl31_v*.elf | sort -V | tail -1)
echo "DDR $DDR"; echo "BL31 $BL31"
cd u-boot
make -s O="$W/out" "$DEFCONFIG"
nice -n 19 make -s O="$W/out" -j4 ROCKCHIP_TPL="$DDR" BL31="$BL31"
cp "$W/out/u-boot-rockchip.bin" "$OUTBIN"
ls -l "$OUTBIN"; sha256sum "$OUTBIN"
log "fertig"
