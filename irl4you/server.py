#!/usr/bin/env python3
"""IRL4YOU BOX Oberfläche: Einstieg. Die Teile liegen im Paket webui/ (jede Datei höchstens etwa 500 Zeilen).

Start: python3 server.py --host 0.0.0.0 --port 8780 --state /var/lib/pipbox ...
Andere Programme (pipbox_send.py) holen sich Klassen und Konstanten weiter über `import server`; dafür stellt dieser Einstieg alle Namen der Teile bereit.
"""
import importlib

for _name in ['common', 'sampler', 'usbwatch', 'netstate', 'pipeline_plugins', 'pipeline_build', 'pipeline', 'send', 'cameras', 'auth', 'remote', 'stats', 'layout', 'wifi', 'system', 'updates', 'camservices', 'settings_clean', 'settings_transfer', 'access', 'httpserver', 'actions', 'http_base', 'http_stats', 'routes_get', 'routes_post', 'handler', 'main']:
    _mod = importlib.import_module("webui." + _name)
    globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

from webui.main import main      # noqa: E402  (auch über die Schleife da; hier für Leser und Werkzeuge ausdrücklich)

if __name__ == "__main__":
    main()
