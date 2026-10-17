# Eigene Pakete (arm64) für die Box

Alle Pakete wurden auf der Box selbst gebaut und dort getestet (Skripte in `build/`). `install/system-install.sh` spielt sie ein.

| Paket | Inhalt | Test |
|---|---|---|
| `irl4you-encoder` | Encoder (eigene Entwicklung) | Regler-Test, Laufzeit-Test mit Testbild über SRT, auch mit dem Hardware-H.265-Encoder |
| `irl4you-srtla` | SRTLA-Bündel-Sender (eigene Entwicklung) | 23 Tests |
| `irl4you-wifi-rtw88` | WLAN-USB-Treiber lwfinger/rtw88 (RTL8811CU u. a.) für Kernel 6.1.172-irl4you | Suchen, Verbinden (5 GHz), Hotspot (AP) auf der Box |

Der WLAN-Treiber gehört zu genau einem Kernel (Version im Namen). Bei einem neuen Kernel wird er neu gebaut.
