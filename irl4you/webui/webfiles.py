"""IRL4YOU BOX Oberfläche: Dateien der Weboberfläche (Teile der Seite, Stile, Skripte) aus web/ ausliefern."""
import os
import re

from .common import WEB_DIR, read

INCLUDE_RE = re.compile(r"^[ \t]*<!--#include ([a-z0-9_-]+\.html)-->[ \t]*$", re.M)
STATIC_RE = re.compile(r"^/ui/(css|js)/((?:[A-Za-z0-9_-]+/)?[A-Za-z0-9_-]+)\.(css|js)$")
CTYPES = {"css": "text/css; charset=utf-8", "js": "application/javascript; charset=utf-8"}


def expand_includes(text, web_dir=None):
    """Ersetzt Zeilen <!--#include name.html--> durch den Inhalt von web/partials/name.html (eine Karte oder ein Teil der Seite)."""
    base = os.path.join(web_dir or WEB_DIR, "partials")

    def one(m):
        return (read(os.path.join(base, m.group(1)), "") or "").rstrip("\n")
    return INCLUDE_RE.sub(one, text)


def static_file(path, web_dir=None):
    """/ui/css/NN-name.css, /ui/css/themes/klar.css und /ui/js/NN-name.js -> (Inhalt, Inhaltstyp) oder None. Nur diese zwei Ordner, höchstens ein Unterordner, nur einfache Namen."""
    m = STATIC_RE.match(path)
    if not m or m.group(1) != m.group(3):
        return None
    body = read(os.path.join(web_dir or WEB_DIR, m.group(1), "%s.%s" % (m.group(2), m.group(3))), None)
    return None if body is None else (body.encode("utf-8"), CTYPES[m.group(1)])
