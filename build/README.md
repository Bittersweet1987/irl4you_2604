# Bauen auf der Box

Eigene Pakete werden **auf der Box selbst** gebaut und getestet (Orange Pi 5 Plus, Ubuntu 26.04, Kernel 6.1.172-irl4you), dann als
`.deb` nach `irl4you/debs/` committet und von der Box über `irl4you-update install` geholt. Übersicht der Pakete: [PAKETE.md](PAKETE.md).

| Skript | Zweck |
|---|---|
| `09-box-kerneltree.sh` | Kernel-Quellbaum (`armbian/linux-rockchip`, Zweig `rk-6.1-rkr7.2`) mit der Konfiguration des laufenden Kernels bauen; liefert `Module.symvers` für Modulbau |
| `10-rtw88.sh` | WLAN-USB-Treiber `lwfinger/rtw88` gegen diesen Baum bauen und als `irl4you-wifi-rtw88` verpacken (`PKG_PREFIX=` setzt den Versionsanfang) |
| `box-build.sh encoder\|srtla\|srs\|rtw88\|alle` | Pakete `irl4you-encoder`, `irl4you-srtla`, `irl4you-srs` bauen, Tests laufen lassen, `.deb` in `/var/tmp/irl4you-build/debs` |

Alle Skripte brauchen root (`sudo`), sind mehrfach lauffähig und installieren nichts ins System außer Bauwerkzeugen.
Ablauf bei jeder Änderung: bauen → auf der Box testen → `.deb` committen → `irl4you-update install` auf der Box.
