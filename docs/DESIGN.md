# Designvorgabe der Oberfläche

Damit die Oberfläche einheitlich bleibt, gelten diese Regeln für jede neue und geänderte Stelle (Dateien in `irl4you/web`). Aussehen und Farben
kommen aus dem Design-System (`css/00-ds-*.css`, Tokens, sechs Themes). Kein Baustein bekommt eigene Farben oder eigene Knopfstile.

## Bausteine

| Zweck | Baustein | Regel |
|---|---|---|
| Menükarte | `<details class="card wide" id="c_…">` mit `<summary><span class="sumh">Titel</span></summary>` | eine Karte je Thema |
| Unterbereich in einer Karte | `<details class="subsec">` (einklappbar) oder `<div class="sech">Zwischenüberschrift</div>` | Zwischenüberschrift immer mit `.sech`, nie fett formatierter Text |
| **Wahl zwischen 2 bis 4 festen, kurzen Möglichkeiten** | **Umschalter `.seg`**: Knopfgruppe, der gewählte Knopf trägt `.on` (und `aria-pressed`) | Für ein `<select>` mit festen Optionen: `data-seg` ans Select schreiben (`js/21-seg.js` baut die Knopfgruppe, das Select bleibt Datenquelle). Optionstext höchstens etwa 16 Zeichen |
| Wahl aus vielen oder langen oder dynamischen Möglichkeiten | `<select>` (Kameras, Netze, Ecken, lange Beschreibungen) | nicht als Umschalter |
| Hauptaktion einer Karte (Speichern, Hinzufügen) | `<button>` ohne Klasse | höchstens eine je Bereich |
| Nebenaktion | `<button class="sec">` (klein: `sec small`) | |
| Aktion mit Folgen (Neustart, Zugang öffnen) | `warnbtn`, Zerstörendes `dangerbtn` | |
| Suchen, Neu anlegen (Netze suchen, Neuer Server) | `warnbtn` (gelb wie „Live gehen“) | |
| Trennen, Vergessen, Löschen, Zustand „Aus“ des Hotspots | `dangerbtn` (rot wie „SSH ausschalten“) | Vergessen und Löschen als kleines Symbol: `dangerbtn small` |
| Hinweis, Erklärung, Rückmeldung | `<div class="ph">`, Rückmeldung mit `role="status"` | kurze Sätze, nichts in Farbe hervorheben |
| Status | `wstat` mit `wdot` | |
| Ein/Aus und Mehrfachauswahl | Häkchen (`checkbox`) in `optlist` | |

Ein Umschalter ist immer eine Knopfgruppe im Stil von `.seg` (zum Beispiel Encoder Hardware/Software, Desktop/Mobil, Eine Kamera/Bild-in-Bild).
Eigene Gruppen-Stile wie das frühere `.vseg` gibt es nicht mehr.

## Verboten

- Farbwerte (`#…`, `rgb()`) in Komponenten, Partials oder Inline-Styles: nur Tokens (`var(--c-…)`), das prüft `tests/test_designsystem.py`.
- Neue Knopfklassen für einzelne Karten; Ausnahmen sind im Prüfbericht gelistet und werden nach und nach auf die Bausteine oben zurückgeführt.
- Inline-`style` für Aussehen (Farben, Rahmen, Schrift). Erlaubt bleiben einzelne Abstände (`margin`) und Breiten, wenn es keine Klasse dafür gibt.
- Ein `<select>` mit 2 bis 4 kurzen festen Optionen ohne `data-seg` (prüft ein Test).
- Text im Code ohne Übersetzung: jeder sichtbare deutsche Text braucht einen Eintrag in `web/i18n/*.json` (alle 13 Sprachen).

## Ablauf bei Änderungen

1. Passenden Baustein aus der Tabelle wählen. Gibt es keinen, zuerst den Baustein im Design-System anlegen (alle sechs Themes, hell und dunkel), nicht in der Karte.
2. Texte in alle Sprachdateien eintragen.
3. Dateien höchstens etwa 500 Zeilen (CSS und JS), `python -m unittest discover -s tests` muss grün sein.
4. Ansicht in einem Theme dunkel und hell sowie als Handy-Breite (unter 620 Pixel) prüfen.
