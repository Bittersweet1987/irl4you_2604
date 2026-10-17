#!/bin/bash
# LÃ¤uft AUF der Box: baut den WLAN-USB-Treiber shenmintao/aic8800d80 (AIC8800D80/DC/DW, z. B. UGREEN AX900, Tenda U11) gegen den Kernelbaum aus
# 09-box-kerneltree.sh und packt ihn mit Firmware, Umschalt-Regel (USB-Laufwerk -> WLAN) und Modul-Konfiguration als irl4you-wifi-aic8800_<datum>+<kernel>_arm64.deb.
# Installiert nichts ins System. Zweig AIC_BRANCH: legacy-mcu1 bei chip_mcu_id=1 (Standard, Stick der Box), main bei chip_mcu_id=0 oder unbekannt (siehe README des Treibers).
set -euo pipefail
B=${B:-/var/tmp/irl4you-build}
KVER=$(uname -r)
KSRC=$B/linux
# Dieser Stick (UGREEN AX900, a69c:5723) meldet chip_id=7, chip_mcu_id=1 -> legacy-mcu1; der Zweig main läuft darauf nicht (Firmware-Timeout)
AIC_BRANCH=${AIC_BRANCH:-legacy-mcu1}
test -f "$KSRC/Module.symvers" || { echo "FEHLER: erst 09-box-kerneltree.sh"; exit 1; }
cd "$B"
[ -d aic8800d80/.git ] || git clone -q --depth 1 -b "$AIC_BRANCH" https://github.com/shenmintao/aic8800d80.git aic8800d80
git -C aic8800d80 fetch -q --depth 1 origin "$AIC_BRANCH" && git -C aic8800d80 checkout -q -f -B "$AIC_BRANCH" FETCH_HEAD
REV=$(git -C aic8800d80 log -1 --format='%h %cs'); echo "aic8800d80 $REV ($AIC_BRANCH)"
cd aic8800d80/drivers/aic8800
make clean -C "$KSRC" M="$PWD" >/dev/null 2>&1 || true
make -C "$KSRC" M="$PWD" -j"$(nproc)" modules 2>&1 | tail -5
ST=$B/aic8800-st; rm -rf "$ST"
M=$ST/lib/modules/$KVER/updates/aic8800
mkdir -p "$ST/DEBIAN" "$M" "$ST/etc/usb_modeswitch.d" "$ST/lib/firmware"
for m in aic_load_fw aic8800_fdrv aic_zlp_quirk; do cp "$m"/"$m".ko "$M/"; done
cd ../..
for d in fw/aic8800*; do cp -r "$d" "$ST/lib/firmware/"; done
cp usb_modeswitch/1111_1111 "$ST/etc/usb_modeswitch.d/1111:1111"
# Das Umschalten (USB-Laufwerk -> WLAN) macht pipbox-wlandriver.service der Box; das Paket bringt nur Treiber, Firmware und die Umschaltdatei für Pandora-Klone.
D=${PKG_PREFIX:-$(date +%Y%m%d)}
cat > "$ST/DEBIAN/control" <<CTL
Package: irl4you-wifi-aic8800
Version: $D+$KVER
Architecture: arm64
Maintainer: IRL4YOU <irl4you@localhost>
Depends: kmod, usb-modeswitch
Replaces: irl4you-aic8800
Conflicts: irl4you-aic8800
Provides: irl4you-aic8800
Section: kernel
Priority: optional
Description: WLAN-USB-Treiber AIC8800 (D80/DC/DW) fuer Kernel $KVER
 Module aic_load_fw, aic8800_fdrv, aic_zlp_quirk mit Firmware. Quelle: github.com/shenmintao/aic8800d80 ($REV, Zweig $AIC_BRANCH, GPL-2.0).
CTL
printf '#!/bin/sh\ndepmod -a %s || true\nudevadm control --reload-rules 2>/dev/null || true\nexit 0\n' "$KVER" > "$ST/DEBIAN/postinst"; cp "$ST/DEBIAN/postinst" "$ST/DEBIAN/postrm"
chmod 755 "$ST/DEBIAN/postinst" "$ST/DEBIAN/postrm"
dpkg-deb --root-owner-group --build "$ST" "$B/irl4you-wifi-aic8800_${D}+${KVER}_arm64.deb" >/dev/null
ls -la "$B"/irl4you-wifi-aic8800_*.deb
