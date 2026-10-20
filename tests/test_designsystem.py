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


PARTIALS = os.path.join(ROOT, "irl4you", "web", "partials")


class Umschalter(unittest.TestCase):
    """docs/DESIGN.md: Wahl zwischen 2 bis 4 kurzen festen Optionen ist ein Umschalter (.seg), kein Auswahlfeld und keine eigene Knopfgruppe."""
    # Auswahlfelder mit festen Optionen, die bewusst Auswahlfelder bleiben (lange Beschreibungen)
    AUSNAHMEN = {"hdmi_audio", "hdmi_fmt", "p_audio", "b_spread"}

    def test_feste_kurze_auswahl_ist_umschalter(self):
        for p in glob.glob(os.path.join(PARTIALS, "*.html")):
            for m in re.finditer(r"<select([^>]*)>(.*?)</select>", _read(p), re.S):
                opts = re.findall(r"<option[^>]*>([^<]*)</option>", m.group(2))
                sid = re.search(r'id="([^"]+)"', m.group(1))
                name = sid.group(1) if sid else ""
                if 2 <= len(opts) <= 4 and name not in self.AUSNAHMEN:
                    self.assertIn("data-seg", m.group(1), (os.path.basename(p), name, "Umschalter nötig (docs/DESIGN.md)"))
                    self.assertTrue(all(len(o) <= 20 for o in opts), (os.path.basename(p), name, "Optionstext zu lang für einen Umschalter"))

    def test_keine_eigenen_gruppenstile(self):
        for p in glob.glob(os.path.join(CSS, "*.css")):
            self.assertNotIn(".vseg", _read(p), p)
        for p in glob.glob(os.path.join(PARTIALS, "*.html")):
            self.assertNotIn("vseg", _read(p), p)


class DesignSystem(unittest.TestCase):
    def test_dateien_max_500_zeilen(self):
        for p in glob.glob(os.path.join(CSS, "*.css")):
            self.assertLessEqual(len(_read(p).splitlines()), 500, p)

    def test_tokens_enthalten_alle_farben(self):
        t = _read(os.path.join(CSS, "00-ds-tokens.css"))
        for n in ["--c-" + c for c in COLOR_TOKENS] + ["--r-card", "--r-ctl", "--s-2", "--f-body", "--bw", "--ctl-h"]:
            self.assertIn(n + ":", t, n)

    def test_themes_vollstaendig(self):
        for d in DESIGNS:
            s = _read(os.path.join(CSS, "00-ds-theme-%s.css" % d))
            for mode in ("dark", "light"):
                m = re.search(r'\[data-design="%s"\]\[data-theme="%s"\][^{]*\{([^}]*)\}' % (d, mode), s)
                self.assertTrue(m, (d, mode))
                for n in COLOR_TOKENS + ["r-card", "r-ctl"]:
                    k = "--c-" + n if n not in ("r-card", "r-ctl") else "--" + n
                    self.assertIn(k + ":", m.group(1), (d, mode, n))

    def test_alle_ds_dateien_eingebunden(self):
        index = _read(os.path.join(ROOT, "irl4you", "web", "index.html"))
        for p in glob.glob(os.path.join(CSS, "00-ds-*.css")):
            self.assertIn('/ui/css/%s"' % os.path.basename(p), index, p)

    def test_komponenten_ohne_farbwerte_nur_tokens(self):
        for p in [os.path.join(CSS, "00-ds-%s.css" % c) for c in ("text", "card", "button", "form", "status")]:
            s = re.sub(r"/\*.*?\*/", "", _read(p), flags=re.S)
            self.assertFalse(re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", s), p)
            self.assertFalse(re.search(r"style=", s), p)
            for var in re.findall(r"var\((--[\w-]+)\)", s):
                self.assertTrue(re.match(r"--(c|f|s|r|bw|shadow|ctl-h)", var), (p, var))

    def test_klassen_mit_praefix(self):
        for p in [os.path.join(CSS, "00-ds-%s.css" % c) for c in ("text", "card", "button", "form", "status")]:
            s = re.sub(r"/\*.*?\*/", "", _read(p), flags=re.S)
            for sel in re.findall(r"([^{}]+)\{", s):
                for c in re.findall(r"\.([\w-]+)", sel):
                    if c in ("secondary", "danger", "small", "ok", "warn", "crit", "off", "wait", "unk"):
                        continue
                    self.assertTrue(c.startswith("ui-"), (p, c))


if __name__ == "__main__":
    unittest.main()
