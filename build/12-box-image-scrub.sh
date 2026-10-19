#!/bin/bash
# Persönliche Daten aus einem Image-Stand (Einhängepunkt $1) entfernen. Wird von 12-box-image.sh eingelesen.
# Ergebnis: kein Kennwort im Image. Das Konto "user" ist gesperrt, SSH ist aus. Schaltet man SSH in der Oberfläche ein, erzeugt
# pipbox-ssh.py wie bisher ein Zufallskennwort für den SSH-Benutzer (/var/lib/pipbox/system.json) und startet den Dienst.
# Die Oberfläche fragt beim ersten Aufruf nach einem eigenen Kennwort, weil auth.json fehlt.
# SSH-Hostschlüssel und machine-id entstehen beim ersten Start neu (irl4you-firstboot.service, systemd).
scrub_image() {
    local R=$1
    # Zustand der Oberfläche: Anmeldung, Sitzungen, Tokens, Kameras, Sendeeinstellungen (Dienste legen es neu an)
    find "$R/var/lib/pipbox" -mindepth 1 -delete 2>/dev/null || true
    find "$R/etc/pipbox" -type f -delete 2>/dev/null || true
    rm -rf "$R/var/lib/irl4you/previous" "$R/var/lib/irl4you/update.lock"
    # Zugänge
    rm -f "$R"/etc/ssh/ssh_host_* "$R/home/user/.bash_history" "$R/root/.bash_history"
    rm -rf "$R/home/user/.ssh" "$R/root/.ssh" "$R/home/user/.cache" "$R/home/user/.gnupg" "$R/home/user/.config" \
           "$R/home/user/.sudo_as_admin_successful" "$R/root/.gitconfig" "$R/root/.wget-hsts" "$R/root/.local" "$R/root/.cache" \
           "$R/root/enc" "$R/root/irl4you-update.bak"
    rm -f "$R"/etc/sudoers.d/92-claude-build "$R"/etc/sudoers.d/90-claude-readonly
    # Netz: WLAN-Zugänge, Tailscale-Identität, Adressen
    rm -f "$R"/etc/NetworkManager/system-connections/*
    # Ubuntu 26.04 legt NetworkManager-Verbindungen zusätzlich als netplan-Dateien ab: dort stehen WLAN-Name, WLAN-Kennwort und MAC-Adressen
    rm -f "$R"/etc/netplan/90-NM-*.yaml
    rm -f "$R/var/lib/NetworkManager"/seen-bssids "$R/var/lib/NetworkManager"/timestamps "$R/var/lib/NetworkManager"/NetworkManager.state           "$R/var/lib/NetworkManager"/*.leases
    # Reste der Entwicklung im Home des Root-Kontos (Sicherungen, Listen)
    rm -rf "$R/root/bl-backup" "$R/root"/*.txt "$R/root"/*.bak
    rm -rf "$R/var/lib/tailscale" "$R/var/lib/NetworkManager"/*.lease "$R/var/lib/NetworkManager"/secret_key
    # Kennungen und Spuren
    : > "$R/etc/machine-id"; rm -f "$R/var/lib/dbus/machine-id"; ln -sf /etc/machine-id "$R/var/lib/dbus/machine-id"
    rm -rf "$R/var/lib/systemd/random-seed" "$R/var/lib/systemd/timers"/* "$R/var/lib/dhcp"/* "$R/var/lib/bluetooth"/*
    find "$R/var/log" -type f \( -name '*.log' -o -name '*.log.*' -o -name '*.gz' -o -name '*.1' \) -delete
    : > "$R/var/log/wtmp"; : > "$R/var/log/btmp"; : > "$R/var/log/lastlog"
    rm -rf "$R/var/log/journal"/* "$R/var/log/private"/* "$R/var/cache/apt"/*.bin 2>/dev/null || true
    # Kein Kennwort, SSH aus
    sed -i 's#^user:[^:]*:#user:!:#' "$R/etc/shadow"
    systemctl --root="$R" disable ssh.service ssh.socket >/dev/null 2>&1 || true
    find "$R/etc/systemd/system" -type l \( -name ssh.service -o -name ssh.socket \) -delete
    local pu pg
    pu=$(grep '^pipbox:' "$R/etc/passwd" | cut -d: -f3); pg=$(grep '^pipbox:' "$R/etc/group" | cut -d: -f3)
    install -d -m 700 -o "$pu" -g "$pg" "$R/var/lib/pipbox"
    printf '{"ssh_user": "user"}\n' > "$R/var/lib/pipbox/system.json"
    chown "$pu:$pg" "$R/var/lib/pipbox/system.json"
    # Erststart: Hostschlüssel neu (sshd braucht sie, sobald SSH eingeschaltet wird)
    cat > "$R/etc/systemd/system/irl4you-firstboot.service" <<'EOF'
[Unit]
Description=IRL4YOU BOX Erststart: SSH-Hostschlüssel neu erzeugen
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key
[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
[Install]
WantedBy=multi-user.target
EOF
    ln -sf /etc/systemd/system/irl4you-firstboot.service "$R/etc/systemd/system/multi-user.target.wants/irl4you-firstboot.service"
}
