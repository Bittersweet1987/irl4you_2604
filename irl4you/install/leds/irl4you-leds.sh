#!/bin/sh
# Status-LEDs der Box setzen (eigene Umsetzung): nur gruen als Dauerlicht (Box laeuft), alle anderen LEDs aus, Speicher-LED zeigt Zugriffe.
# Orange Pi 5 Plus (green_led/blue_led) und ROCK 5B Plus benennen ihre LEDs unterschiedlich; genommen wird, was es gibt.
set -u
for led in /sys/class/leds/*; do
    [ -w "$led/trigger" ] || continue
    case "$(basename "$led")" in
        *mmc*|*disk*) echo mmc0 > "$led/trigger" 2>/dev/null || true ;;
        *green*) echo none > "$led/trigger" 2>/dev/null || true; cat "$led/max_brightness" > "$led/brightness" 2>/dev/null || true ;;
        *rtw88*|*phy*|*wlan*) ;;
        *) echo none > "$led/trigger" 2>/dev/null || true; echo 0 > "$led/brightness" 2>/dev/null || true ;;
    esac
done
