"""Design-System der Oberfläche (irl4you/web/css): Dateigröße, Token-Vollständigkeit, keine Farbwerte in Komponenten."""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "irl4you", "web", "css")
DESIGNS = ["klar", "kompakt", "kompakt-std", "kontrast", "cockpit", "mischpult"]
COLOR_TOKENS = ["bg", "card", "text", "muted", "line", "ctl", "accent", "bar", "blue", "ok", "warn", "crit",
                "on-bar", "on-warn", "on-ok", "on-crit", "shade", "focus"]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class DesignSystem(unittest.TestCase):
    def test_dateien_max_500_zeilen(self):
        for p in glob.glob(os.path.join(CSS, "**", "*.css"), recursive=True):
            self.assertLessEqual(len(_read(p).splitlines()), 500, p)

    def test_tokens_enthalten_alle_farben(self):
        t = _read(os.path.join(CSS, "tokens.css"))
        for n in ["--c-" + c for c in COLOR_TOKENS] + ["--r-card", "--r-ctl", "--s-2", "--f-body", "--bw", "--ctl-h"]:
            self.assertIn(n + ":", t, n)

    def test_themes_vollstaendig(self):
        for d in DESIGNS:
            s = _read(os.path.join(CSS, "themes", d + ".css"))
            for mode in ("dark", "light"):
                m = re.search(r'\[data-design="%s"\]\[data-theme="%s"\][^{]*\{([^}]*)\}' % (d, mode), s)
                self.assertTrue(m, (d, mode))
                for n in COLOR_TOKENS + ["r-card", "r-ctl"]:
                    k = "--c-" + n if n not in ("r-card", "r-ctl") else "--" + n
                    self.assertIn(k + ":", m.group(1), (d, mode, n))

    def test_komponenten_ohne_farbwerte_nur_tokens(self):
        for p in glob.glob(os.path.join(CSS, "komponenten", "*.css")):
            s = re.sub(r"/\*.*?\*/", "", _read(p), flags=re.S)
            self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", s), p)
            self.assertFalse(re.search(r"style=", s), p)
            for var in re.findall(r"var\((--[\w-]+)\)", s):
                self.assertTrue(re.match(r"--(c|f|s|r|bw|shadow|ctl-h)", var), (p, var))

    def test_klassen_mit_praefix(self):
        for p in glob.glob(os.path.join(CSS, "komponenten", "*.css")):
            s = re.sub(r"/\*.*?\*/", "", _read(p), flags=re.S)
            for sel in re.findall(r"([^{}]+)\{", s):
                for c in re.findall(r"\.([\w-]+)", sel):
                    if c in ("secondary", "danger", "small", "ok", "warn", "crit", "off", "wait", "unk"):
                        continue
                    self.assertTrue(c.startswith("ui-"), (p, c))


if __name__ == "__main__":
    unittest.main()
