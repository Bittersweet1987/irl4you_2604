#!/bin/sh
# Systemteile einrichten. Wird von hooks/install (als root) aufgerufen, IRL4YOU_RELEASE_DIR = Ordner dieser Version.
# Mehrfach lauffähig. Programmdateien kopiert dieses Skript nicht (liegen schon an ihrem Platz).
#   1. Basis-Anpassungen des Grundsystems (system-base-fixes.sh: NetworkManager, Kernel-Hook, HDMI-Eingang, Tastatur/Sprache)
#   2. eigene .deb-Pakete aus debs/ (Encoder, SRTLA, MPP, RGA, GStreamer-Plugin, WLAN-Treiber)
#   3. IRL4YOU selbst (irl4you-setup.sh: Pakete, Benutzer, venv, PiP-Baustein, Netz, udev, RTMP, Dienste)
set -eu
cd "$IRL4YOU_RELEASE_DIR"
export DEBIAN_FRONTEND=noninteractive

# 0. Netz vor dem Update merken: install/health.sh verlangt danach wieder eine Standardroute, wenn es vorher eine gab (sonst Rollback).
#    Dieses Skript verändert im laufenden Betrieb nie Netzwerkkarten, Adressen oder Routen.
if ip -4 route show default 2>/dev/null | grep -q .; then echo 1 > /run/irl4you-net-before; else echo 0 > /run/irl4you-net-before; fi

# 1. Werkzeug für den Boot-Hook (fdtput/fdtget), falls es im Grundsystem fehlt
command -v fdtput >/dev/null 2>&1 || apt-get install -y --no-install-recommends device-tree-compiler || true

# 2. Basis-Anpassungen. Das Skript sucht zz-irl4you-boot und udev/ neben sich, darum zeigt IRL4YOU_RELEASE_DIR für diesen Aufruf auf install/.
IRL4YOU_RELEASE_DIR="$PWD/install" sh install/system-base-fixes.sh

# 3. Eigene Pakete aus debs/
if ls debs/*.deb >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends --allow-downgrades ./debs/*.deb
fi

# 4. IRL4YOU: Dienste, Netz, udev, RTMP, venv, PiP-Baustein
sh install/irl4you-setup.sh
