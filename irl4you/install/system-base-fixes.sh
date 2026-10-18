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

# 4. Hostname irl4you: macht die Box unter http://irl4you.local erreichbar (mDNS über avahi). Nur wenn noch der Standardname gesetzt ist.
cur=$(hostname 2>/dev/null || true)
if [ -z "$cur" ] || [ "$cur" = belabox ] || [ "$cur" = localhost ]; then
    hostnamectl set-hostname irl4you 2>/dev/null || echo irl4you > /etc/hostname
    if grep -q '^127.0.1.1' /etc/hosts; then sed -i 's/^127.0.1.1.*/127.0.1.1 irl4you/' /etc/hosts; else echo '127.0.1.1 irl4you' >> /etc/hosts; fi
    systemctl try-restart avahi-daemon 2>/dev/null || true
    changed=1
fi

# 5. Systempartition auf die ganze Karte vergrößern (einmalig)
sh "$HERE/grow-rootfs.sh" || true

# 6. Boot-Parameter fuer USB-Platten mit Problemen im UAS-Modus (Marcos Platte 2537:1066/1068): usb-storage statt uas verwenden.
#    Nur ergaenzen, wenn der Parameter fehlt; die Zeile in extlinux.conf wird sonst nicht angefasst.
conf=/boot/extlinux/extlinux.conf
if [ -f "$conf" ] && ! grep -q 'usb-storage.quirks=' "$conf"; then
    sed -i '/^[[:space:]]*APPEND /s/$/ usb-storage.quirks=0x2537:0x1066:u,0x2537:0x1068:u/' "$conf"; changed=1
fi

# 7. Status-LEDs: gruen = Box laeuft, blau = Herzschlag (Dienst irl4you-leds, setzt die LEDs bei jedem Start)
install -D -m 755 "$HERE/leds/irl4you-leds.sh" /usr/libexec/irl4you/irl4you-leds.sh
if ! cmp -s "$HERE/leds/irl4you-leds.service" /etc/systemd/system/irl4you-leds.service; then
    install -m 644 "$HERE/leds/irl4you-leds.service" /etc/systemd/system/irl4you-leds.service
    systemctl daemon-reload; systemctl enable irl4you-leds.service >/dev/null 2>&1 || true
fi
/usr/libexec/irl4you/irl4you-leds.sh || true

# 8. Automatische Sicherheitsupdates von Ubuntu (ohne Neustart, niedrige Prioritaet)
sh "$HERE/auto-security-updates.sh" || true

# 9. Takt der grossen Kerne deckeln (Firmware lehnt die pvtpll-Spannungsstufe ab; ab 1608 MHz harter Reset)
install -D -m 755 "$HERE/cpucap/irl4you-cpucap.sh" /usr/libexec/irl4you/irl4you-cpucap.sh
if ! cmp -s "$HERE/cpucap/irl4you-cpucap.service" /etc/systemd/system/irl4you-cpucap.service; then
    install -m 644 "$HERE/cpucap/irl4you-cpucap.service" /etc/systemd/system/irl4you-cpucap.service
    systemctl daemon-reload; systemctl enable irl4you-cpucap.service >/dev/null 2>&1 || true
fi
/usr/libexec/irl4you/irl4you-cpucap.sh || true

# 10. Werkzeug zum Tauschen des Bootloader-FIT (nur bereitgestellt, nichts wird automatisch geschrieben): irl4you-bootloader status|apply|restore
install -d /usr/share/irl4you/bootloader
install -m 644 "$HERE"/bootloader/*.bin /usr/share/irl4you/bootloader/
install -m 755 "$HERE/bootloader/irl4you-bootloader.sh" /usr/share/irl4you/bootloader/irl4you-bootloader.sh
ln -sf /usr/share/irl4you/bootloader/irl4you-bootloader.sh /usr/local/sbin/irl4you-bootloader

[ "$changed" = 1 ] && echo "system-base-fixes: Änderungen angewendet (Neustart empfohlen)" || echo "system-base-fixes: nichts zu tun"
exit 0
