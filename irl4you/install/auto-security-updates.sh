#!/bin/sh
# Ubuntu-Sicherheitsupdates laufen NUR mit einem IRL4YOU-Update (Commit auf main): kein eigener Zeitplan auf der Box,
# denn der Updater startet nie waehrend einer Uebertragung. Nur Sicherheitsquellen, nie Neustart, niedrige Prioritaet.
# Mehrfach lauffaehig; bei jedem Update wird einmal geprueft und eingespielt.
set -u
if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends unattended-upgrades >/dev/null 2>&1 || { echo "auto-security-updates: Installation fehlgeschlagen"; exit 0; }
fi
cat > /etc/apt/apt.conf.d/52irl4you-unattended <<'CONF'
// IRL4YOU Box: nur Sicherheitsupdates, kein automatischer Neustart
Unattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESMApps:${distro_codename}-apps-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESM:${distro_codename}-infra-security";
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "false";
Unattended-Upgrade::Remove-Unused-Dependencies "false";
Unattended-Upgrade::MinimalSteps "true";
CONF
# kein Zeitplan: weder Listen-Aktualisierung noch Upgrade von selbst
printf 'APT::Periodic::Update-Package-Lists "0";\nAPT::Periodic::Unattended-Upgrade "0";\n' > /etc/apt/apt.conf.d/20auto-upgrades
rm -rf /etc/systemd/system/apt-daily.service.d/irl4you-low-priority.conf /etc/systemd/system/apt-daily-upgrade.service.d/irl4you-low-priority.conf
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
systemctl daemon-reload
# einmal jetzt: Listen holen und Sicherheitsupdates einspielen (niedrige Prioritaet)
DEBIAN_FRONTEND=noninteractive nice -n 19 ionice -c3 apt-get update -q >/dev/null 2>&1 || true
nice -n 19 ionice -c3 unattended-upgrade >/var/log/irl4you-security-updates.log 2>&1 || true
echo "auto-security-updates: geprueft und eingespielt (Log: /var/log/irl4you-security-updates.log)"
