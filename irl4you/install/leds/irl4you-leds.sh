#!/bin/sh
# Status-LEDs der Box setzen (eigene Umsetzung): gruen = Box laeuft (Dauerlicht), blau = Herzschlag, Speicher-LED zeigt Zugriffe.
# Orange Pi 5 Plus (green_led/blue_led) und ROCK 5B Plus benennen ihre LEDs unterschiedlich; genommen wird, was es gibt.
set -u
hb=1
for led in /sys/class/leds/*; do
    [ -w "$led/trigger" ] || continue
    n=$(basename "$led")
    case "$n" in
        *mmc*|*disk*) echo mmc0 > "$led/trigger" 2>/dev/null || true ;;
        *green*) echo none > "$led/trigger" 2>/dev/null || true; cat "$led/max_brightness" > "$led/brightness" 2>/dev/null || true ;;
        *rtw88*|*phy*|*wlan*) ;;
        *) if [ $hb = 1 ]; then echo heartbeat > "$led/trigger" 2>/dev/null || true; hb=0
           else echo none > "$led/trigger" 2>/dev/null || true; fi ;;
    esac
done
