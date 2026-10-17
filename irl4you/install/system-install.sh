#!/bin/sh
# Systemteile einrichten. Wird von hooks/install (als root) aufgerufen, IRL4YOU_RELEASE_DIR = Ordner dieser Version.
# Mehrfach lauffähig. Programmdateien kopiert dieses Skript nicht (liegen schon an ihrem Platz).
set -eu
cd "$IRL4YOU_RELEASE_DIR"
export DEBIAN_FRONTEND=noninteractive

# 1. Werkzeug für den Boot-Hook (fdtput/fdtget), falls es im Grundsystem fehlt
command -v fdtput >/dev/null 2>&1 || apt-get install -y --no-install-recommends device-tree-compiler || true

# 2. Basis-Anpassungen (NetworkManager, Kernel-Hook, HDMI-Eingang im DTB, Tastatur/Sprache). Das Skript sucht
#    zz-irl4you-boot neben sich, darum zeigt IRL4YOU_RELEASE_DIR für diesen Aufruf auf install/.
IRL4YOU_RELEASE_DIR="$PWD/install" sh install/system-base-fixes.sh

# 3. Eigene Pakete aus debs/ (z. B. WLAN-Treiber irl4you-wifi-8821cu; später Encoder, SRTLA, MPP)
if ls debs/*.deb >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends --allow-downgrades ./debs/*.deb
fi
