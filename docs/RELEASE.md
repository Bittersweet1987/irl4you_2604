# Releases und Versionsnummer

Die Version hat die Form x.y.z und wird als vx.y.z angezeigt.

- **x** gibt Marco vor (0 = Alpha).
- **y** steigt nur bei einem Release. Ein Release entsteht, wenn Marco es ansagt.
- **z** ist die Zahl der Commits seit dem letzten Release. Sie wird nicht gepflegt: Der Updater zählt sie beim Installieren selbst.

## Release erstellen

1. Die Datei `VERSION` auf `x.y` ändern (zum Beispiel `0.2`, ohne dritte Stelle) und nach `main` committen.
2. Die CI läuft, danach legt der Workflow `.github/workflows/release.yml` Tag und GitHub-Release `vx.y.0` auf diesem Commit an (Notizen automatisch aus den Commits).
3. Die Box installiert wie bisher jeden grünen Commit von `main` über `irl4you-update`. Der Release ist für sie nur der Punkt, ab dem die dritte Stelle wieder bei 0 beginnt.

Jede Release-Beschreibung beginnt mit dem Lizenzhinweis (CC BY-ND 4.0); ein bestehender Release ohne den Hinweis bekommt ihn beim erneuten Lauf nachgetragen. LICENSE, ZUSATZERLAUBNIS.md und NOTICE.md liegen im Repo und damit auch im Updater-Stand und im Image.

Fehlt ein Release, lässt er sich über Actions → Release → "Run workflow" nachholen. Gibt es den Tag schon, passiert nichts.

## Commit-Nachrichten

Keine Zeilen `Co-Authored-By:` (und keine `Claude-Session:`-Zeilen) in Commit-Nachrichten dieses Projekts. Die Änderungsliste in der Oberfläche blendet solche Zeilen zusätzlich aus und zeigt pro Commit die Versionsnummer vX.Y.Z.
