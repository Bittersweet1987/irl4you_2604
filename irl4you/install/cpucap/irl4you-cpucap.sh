#!/bin/sh
# Deckelt den Takt der großen Kerne (RK3588), solange die Firmware (BL31) die pvtpll-Spannungsstufe des Kernels
# ablehnt: Ab 1608 MHz gibt es sonst einen harten Reset (Orange Pi 5 Plus, BL31 v1.45, Kernel 6.1.172).
# Anderer Wert in /etc/irl4you/cpucap.conf: BIG_MAX_KHZ=<kHz>; 0 = kein Deckel.
BIG_MAX_KHZ=1416000
[ -f /etc/irl4you/cpucap.conf ] && . /etc/irl4you/cpucap.conf
[ "$BIG_MAX_KHZ" = 0 ] && exit 0
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -w "$p/scaling_max_freq" ] || continue
    # Nur Cluster mit Takten über dem Deckel anfassen (die großen Kerne), die kleinen laufen bis 1800 MHz stabil.
    [ "$(cat "$p/cpuinfo_max_freq")" -gt 1800000 ] || continue
    echo "$BIG_MAX_KHZ" > "$p/scaling_max_freq"
done
