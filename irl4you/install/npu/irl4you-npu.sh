#!/bin/sh
# Stellt die NPU-Last (RK3588, nur als root im Debug-Dateisystem lesbar) für die Oberfläche bereit: /run/irl4you-npu enthält z. B. "0 0 0" (Prozent je NPU-Kern).
SRC=/sys/kernel/debug/rknpu/load
OUT=/run/irl4you-npu
[ -r "$SRC" ] || exit 0
while true; do
    sed -n 's/.*Core0: *\([0-9]*\)%.*Core1: *\([0-9]*\)%.*Core2: *\([0-9]*\)%.*/\1 \2 \3/p' "$SRC" > "$OUT.tmp" 2>/dev/null && chmod 644 "$OUT.tmp" && mv -f "$OUT.tmp" "$OUT"
    sleep 2
done
