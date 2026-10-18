#!/bin/sh
# Automatische Sicherheitsupdates (unattended-upgrades): nur Ubuntu-Sicherheitsquellen, nie automatischer Neustart,
# niedrige Prioritaet (Nice/IO idle), damit ein laufender Stream nicht gestoert wird. Mehrfach lauffaehig.
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
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
for u in apt-daily apt-daily-upgrade; do
    mkdir -p "/etc/systemd/system/$u.service.d"
    printf '[Service]\nNice=19\nIOSchedulingClass=idle\nCPUSchedulingPolicy=idle\n' > "/etc/systemd/system/$u.service.d/irl4you-low-priority.conf"
done
systemctl daemon-reload
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
echo "auto-security-updates: eingerichtet"
