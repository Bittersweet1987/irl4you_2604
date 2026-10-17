#!/bin/sh
# Prüfung nach dem Umschalten auf eine Version (Rückgabe 0 = gut, sonst rollt der Update-Helfer zurück).
# Die Dienste aus "health_units" im Manifest prüft der Helfer selbst; hier: antwortet die Oberfläche auf Port 80 und 8780, und ist das Netz noch da?
set -eu
ok=0
for i in 1 2 3 4 5 6 7 8; do
  if python3 - <<'PY'
import json, sys, urllib.request
for port in (8780, 80):
    with urllib.request.urlopen("http://127.0.0.1:%d/api/auth" % port, timeout=4) as r:
        d = json.load(r)
        if "configured" not in d:
            sys.exit(1)
PY
  then ok=1; break; fi
  sleep 3
done
[ "$ok" = 1 ] || { echo "Die Oberfläche antwortet nicht auf Port 80 und 8780" >&2; exit 1; }

# Netz: Gab es vor dem Update eine Standardroute, muss sie jetzt wieder da sein (sonst Rollback, damit die Box nicht abgeschnitten bleibt)
sh "$(dirname "$0")/net-check.sh" || exit 1
exit 0
