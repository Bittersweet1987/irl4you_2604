#!/usr/bin/env python3
"""Gibt den Abschnitt "## <Version>" aus CHANGELOG.md aus (für den Text des Release, den die Box anzeigt)."""
import re
import sys

version, path = sys.argv[1], sys.argv[2]
try:
    text = open(path, encoding="utf-8").read()
except OSError:
    text = ""
m = re.search(r"^## \[?%s\]?[^\n]*\n(.*?)(?=^## |\Z)" % re.escape(version), text, re.M | re.S)
print(m.group(1).strip() if m else "IRL4YOU %s" % version)
