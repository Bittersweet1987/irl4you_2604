#!/bin/sh
# Takt und Wärme der Box (RK3588). Alles ohne Qualitätsverlust: Gemessen am 19.10.2026 (Orange Pi 5 Plus, 4 Kameras, 1080p30, 12 Mbit/s):
# vorher 49-52 °C beim Senden, mit diesen Einstellungen 44-46 °C, Bildrate der Kameras unverändert (Einbrüche unter 28 fps in 4 % der Messungen wie vorher).
#
# 1. Große Kerne: Takt deckeln. Die Firmware (BL31 v1.45) lehnt die pvtpll-Spannungsstufe des Kernels ab, ab 1608 MHz gab es sonst einen
#    harten Reset (Orange Pi 5 Plus, Kernel 6.1.172). Mit BL31 v1.47 (irl4you-bootloader apply) lief 2208 MHz stabil, 2304/2256 MHz nicht.
#    Normalbetrieb (Hardware-Kodierung): 1416 MHz reichen, die großen Kerne laufen dabei bei 35-55 % und 3-4 °C kälter als mit 2016 MHz.
#    Software-Kodierung (Menü Entwickler, x264) braucht mehr: BIG_SW_MAX_KHZ (2016 MHz mit v1.47, sonst 1416 MHz), die Sendekette hebt den Deckel dafür an.
# 2. Regler "ondemand" der CPU: Standard schaltet erst ab 95 % Last hoch (dann ruckelt es); hier ab 35 %, der hohe Takt wird länger gehalten,
#    der Mindesttakt der großen Kerne ist 1008 MHz.
# 3. Speichertakt (DMC) auf höchstens 1068 MHz: der Regler hing sonst dauerhaft bei 2112 MHz.
# 4. NPU (wird nicht benutzt) auf höchstens 300 MHz.
# Alle Werte lassen sich in /etc/irl4you/cpucap.conf ändern (0 = Wert nicht anfassen), z. B. BIG_MAX_KHZ=2016000.
BIG_MAX_KHZ=1416000
BIG_SW_MAX_KHZ=1416000
BIG_MIN_KHZ=1008000
UP_THRESHOLD=35
DOWN_FACTOR=8
DMC_MAX_HZ=1068000000
NPU_MAX_HZ=300000000
if [ -x /usr/local/sbin/irl4you-bootloader ] && /usr/local/sbin/irl4you-bootloader status 2>/dev/null | grep -q 'bl31-v1.47'; then
    BIG_SW_MAX_KHZ=2016000
fi
[ -f /etc/irl4you/cpucap.conf ] && . /etc/irl4you/cpucap.conf

put() { [ -w "$2" ] && echo "$1" > "$2"; return 0; }

# Wert für die Sendekette (Software-Kodierung): hebt den Deckel an, wenn x264 läuft
echo "$BIG_SW_MAX_KHZ" > /run/irl4you-cpucap-sw 2>/dev/null; chmod 644 /run/irl4you-cpucap-sw 2>/dev/null

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    # Nur Cluster mit Takten über 1800 MHz sind die großen Kerne (die kleinen laufen bis 1800 MHz stabil).
    if [ "$(cat "$p/cpuinfo_max_freq")" -gt 1800000 ]; then
        [ "$BIG_MAX_KHZ" != 0 ] && put "$BIG_MAX_KHZ" "$p/scaling_max_freq"
        [ "$BIG_MIN_KHZ" != 0 ] && put "$BIG_MIN_KHZ" "$p/scaling_min_freq"
    fi
    [ "$UP_THRESHOLD" != 0 ] && put "$UP_THRESHOLD" "$p/ondemand/up_threshold"
    [ "$DOWN_FACTOR" != 0 ] && put "$DOWN_FACTOR" "$p/ondemand/sampling_down_factor"
done
[ "$DMC_MAX_HZ" != 0 ] && put "$DMC_MAX_HZ" /sys/class/devfreq/dmc/max_freq
if [ "$NPU_MAX_HZ" != 0 ]; then
    for d in /sys/class/devfreq/*npu*; do put "$NPU_MAX_HZ" "$d/max_freq"; done
fi
exit 0
