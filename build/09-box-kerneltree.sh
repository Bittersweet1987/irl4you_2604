#!/bin/bash
# Läuft AUF der Box (26.04, Kernel 6.1.172-irl4you): baut den Kernel-Quellbaum mit der Konfiguration des laufenden Kernels, damit
# Out-of-tree-Module (WLAN-Treiber, btusb) dagegen gebaut werden können. Erzeugt Module.symvers (nötig wegen MODVERSIONS).
# Nur im Bauordner, installiert nichts ins System außer den Bauwerkzeugen.
set -euo pipefail
B=${B:-/var/tmp/irl4you-build}
KVER=$(uname -r)
BRANCH=${KERNEL_BRANCH:-rk-6.1-rkr7.2}
mkdir -p "$B"; cd "$B"
export DEBIAN_FRONTEND=noninteractive
echo "[$(date +%H:%M:%S)] Bauwerkzeuge"
apt-get update -q >/dev/null
apt-get install -y -q --no-install-recommends build-essential git flex bison bc libssl-dev libelf-dev dwarves cpio rsync kmod \
    python3-dev pkg-config dkms libncurses-dev xz-utils >/dev/null
echo "[$(date +%H:%M:%S)] Kernelquellen $BRANCH"
if [ ! -d linux/.git ]; then git clone -q --depth 1 --branch "$BRANCH" https://github.com/armbian/linux-rockchip.git linux
else git -C linux fetch -q --depth 1 origin "$BRANCH" && git -C linux reset -q --hard FETCH_HEAD; fi
cd linux
for p in 001-hid-sony.patch bluetooth-hci-quirk-v6.1-v6.15.patch; do
    curl -fsSL -o "$B/$p" "https://raw.githubusercontent.com/armbian/build/main/patch/kernel/rk35xx-vendor-6.1/$p"
    if git apply --check "$B/$p" 2>/dev/null; then git apply "$B/$p"; echo "Patch $p angewendet"; else echo "Patch $p schon drin oder passt nicht"; fi
done
cp "/boot/config-$KVER" .config
make olddefconfig >/dev/null
test "$(make -s kernelrelease)" = "$KVER" || { echo "FEHLER: kernelrelease $(make -s kernelrelease) != $KVER"; exit 1; }
echo "[$(date +%H:%M:%S)] Bauen ($(nproc) Kerne, niedrige Priorität)"
nice -n 10 make -j"$(nproc)" modules >"$B/kernel-build.log" 2>&1
test -f Module.symvers && echo "[$(date +%H:%M:%S)] FERTIG: $B/linux (Module.symvers vorhanden)"
