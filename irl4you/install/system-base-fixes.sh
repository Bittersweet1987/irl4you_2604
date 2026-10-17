#!/bin/sh
# Basis-Anpassungen für das IRL4YOU-Grundsystem (Ubuntu 26.04, Kernel 6.1). Mehrfach lauffähig, ändert nur, was fehlt.
# Gedacht für install/system-install.sh eines Release-Pakets: IRL4YOU_RELEASE_DIR zeigt auf den Ordner der Version,
# dort liegt (neben diesem Skript) die Datei zz-irl4you-boot.
set -eu
HERE=${IRL4YOU_RELEASE_DIR:-$(cd "$(dirname "$0")" && pwd)}
changed=0

# 1. NetworkManager verwaltet alle Netzwerkkarten. Ubuntu lässt ihn sonst Kabel-Karten ignorieren
#    (/usr/lib/NetworkManager/conf.d/10-globally-managed-devices.conf, gedacht für netplan); eine leere Datei gleichen Namens in /etc hebt das auf.
f=/etc/NetworkManager/conf.d/10-globally-managed-devices.conf
if [ ! -e "$f" ]; then
    install -d /etc/NetworkManager/conf.d
    : > "$f"; changed=1
fi

# 2. Boot-Hook: unkomprimiertes Kernel-Image nach /boot/Image, DTBs nach /boot/dtb, HDMI-Eingang im DTB einschalten.
#    Läuft sofort für den laufenden Kernel und danach bei jeder Kernel-Installation.
hook=/etc/kernel/postinst.d/zz-irl4you-boot
if ! cmp -s "$HERE/zz-irl4you-boot" "$hook" 2>/dev/null; then
    install -D -m755 "$HERE/zz-irl4you-boot" "$hook"; changed=1
fi
if [ "$(fdtget /boot/dtb/rockchip/rk3588-orangepi-5-plus.dtb /hdmirx-controller@fdee0000 status 2>/dev/null || echo ?)" = "disabled" ]; then
    "$hook" "$(uname -r)"; changed=1   # DTB wird beim nächsten Start gelesen (Neustart nötig)
fi

# 2b. udev-Regel: /dev/hdmirx zeigt auf den HDMI-Eingang (Treiber-Name stream_hdmirx)
rules=/etc/udev/rules.d/81-irl4you-hdmirx.rules
if ! cmp -s "$HERE/udev/81-irl4you-hdmirx.rules" "$rules" 2>/dev/null; then
    install -D -m644 "$HERE/udev/81-irl4you-hdmirx.rules" "$rules"; changed=1
    udevadm control --reload 2>/dev/null || true
    udevadm trigger --subsystem-match=video4linux --action=add 2>/dev/null || true
fi

# 3. Deutsche Tastatur, Sprache und Zeitzone als Standard (nur wenn noch nichts gesetzt ist)
[ -f /etc/default/keyboard ] || { printf 'XKBMODEL="pc105"\nXKBLAYOUT="de"\nXKBVARIANT=""\nXKBOPTIONS=""\nBACKSPACE="guess"\n' > /etc/default/keyboard; changed=1; }
[ -f /etc/default/locale ] || { printf 'LANG=de_DE.UTF-8\nLANGUAGE=de_DE:de\n' > /etc/default/locale; changed=1; }

[ "$changed" = 1 ] && echo "system-base-fixes: Änderungen angewendet (Neustart empfohlen)" || echo "system-base-fixes: nichts zu tun"
exit 0
