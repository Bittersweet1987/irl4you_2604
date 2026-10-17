#!/bin/bash
# Läuft AUF der Box: baut den WLAN-Treiber lwfinger/rtw88 (Realtek RTL8811CU/8821CU/8822BU/8812CU ... per USB, mac80211) gegen den Kernelbaum
# aus 09-box-kerneltree.sh und packt ihn als irl4you-wifi-rtw88_<datum>+<kernel>_arm64.deb. Installiert nichts ins System.
set -euo pipefail
B=${B:-/var/tmp/irl4you-build}
KVER=$(uname -r)
KSRC=$B/linux
test -f "$KSRC/Module.symvers" || { echo "FEHLER: erst 09-box-kerneltree.sh"; exit 1; }
cd "$B"
[ -d rtw88/.git ] || git clone -q --depth 1 https://github.com/lwfinger/rtw88.git rtw88
git -C rtw88 pull -q --ff-only || true
REV=$(git -C rtw88 log -1 --format='%h %cs'); echo "rtw88 $REV"
cd rtw88
make clean >/dev/null 2>&1 || true
make -j"$(nproc)" KSRC="$KSRC" KVER="$KVER" 2>&1 | tail -15
ls -la *.ko
# Paket
ST=$B/rtw88-st; rm -rf "$ST"; mkdir -p "$ST/DEBIAN" "$ST/lib/modules/$KVER/updates/rtw88" "$ST/etc/modprobe.d" "$ST/etc/NetworkManager/conf.d"
# nur USB-Teil: Kern, USB-Anbindung, Chip-Module und die *u.ko-Stick-Treiber (kein PCIe, kein SDIO: die Boards haben dafür eigene Treiber im Kernel)
for m in rtw_core rtw_usb rtw_88xxa rtw_8723x rtw_8812a rtw_8814a rtw_8821a rtw_8821c rtw_8822b rtw_8822c; do
    cp "$m.ko" "$ST/lib/modules/$KVER/updates/rtw88/"
done
cp rtw_*u.ko "$ST/lib/modules/$KVER/updates/rtw88/"
ls "$ST/lib/modules/$KVER/updates/rtw88/" | wc -l
cat > "$ST/etc/modprobe.d/irl4you-rtw88.conf" <<'CONF'
# Der Treiber aus irl4you-wifi-rtw88 (Module rtw_*) ersetzt die rtw88_*-Module des Kernels für USB-Sticks.
# Die Kernel-Module haben keinen USB-Teil; sie sollen nicht gleichzeitig geladen werden.
blacklist rtw88_core
blacklist rtw88_8821c
blacklist rtw88_8822b
blacklist rtw88_8723d
blacklist rtw88_8822c
CONF
# Der Treiber legt neben wlan0 eine zweite Schnittstelle p2p0 (gleiche MAC) an. NetworkManager soll nur wlan0 verwenden.
# Dateiname 95: muss nach 90-irl4you.conf gelesen werden (dort steht unmanaged-devices=none), sonst gewinnt "none".
printf '[keyfile]
unmanaged-devices=interface-name:p2p0
' > "$ST/etc/NetworkManager/conf.d/95-irl4you-rtw88.conf"
D=${PKG_PREFIX:-$(date +%Y%m%d)}
cat > "$ST/DEBIAN/control" <<CTL
Package: irl4you-wifi-rtw88
Version: $D+$KVER
Architecture: arm64
Maintainer: IRL4YOU <irl4you@localhost>
Depends: kmod
Section: kernel
Priority: optional
Description: WLAN-USB-Treiber rtw88 (lwfinger, mac80211) fuer Kernel $KVER
 Realtek RTL8811CU/8821CU/8822BU/8812CU/8822CU als Modul rtw_8821cu usw. Quelle: github.com/lwfinger/rtw88 ($REV).
CTL
printf '#!/bin/sh\ndepmod -a %s || true\nexit 0\n' "$KVER" > "$ST/DEBIAN/postinst"; cp "$ST/DEBIAN/postinst" "$ST/DEBIAN/postrm"
chmod 755 "$ST/DEBIAN/postinst" "$ST/DEBIAN/postrm"
dpkg-deb --root-owner-group --build "$ST" "$B/irl4you-wifi-rtw88_${D}+${KVER}_arm64.deb" >/dev/null
ls -la "$B"/irl4you-wifi-rtw88_*.deb
