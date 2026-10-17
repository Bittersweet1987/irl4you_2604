#!/bin/sh
# Ist das Netz nach dem Update noch da? system-install.sh merkt vor dem Update in /run/irl4you-net-before (1/0), ob es eine Standardroute gab.
# War es 1, müssen jetzt wieder eine Standardroute und eine globale IPv4-Adresse da sein (bis zu 30 s Geduld). Rückgabe 0 = gut, 1 = Netz weg.
# Umgebung nur für Tests: IRL4YOU_NET_STATE (Datei), IRL4YOU_NET_WAIT (Sekunden je Versuch).
STATE="${IRL4YOU_NET_STATE:-/run/irl4you-net-before}"
WAIT="${IRL4YOU_NET_WAIT:-5}"
[ "$(cat "$STATE" 2>/dev/null || echo 0)" = 1 ] || exit 0
for i in 1 2 3 4 5 6; do
  if ip -4 route show default | grep -q . && ip -4 -o addr show scope global | grep -q .; then exit 0; fi
  sleep "$WAIT"
done
echo "Nach dem Update hat die Box keine Standardroute oder keine Adresse mehr" >&2
exit 1
