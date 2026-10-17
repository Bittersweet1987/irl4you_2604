# Änderungen

## 2.0.0-rc.5
- Oberfläche aufgeteilt: server.py (7300 Zeilen) ist nur noch der Einstieg, die Teile liegen im Paket webui/ (jede Datei höchstens 500 Zeilen). Keine Funktionsänderung.

Versionsschema: 0.x.y, angezeigt als v0.x.y. Erste Stelle gibt Marco vor (0 = Alpha), zweite Stelle steigt bei großen/neuen Funktionen, dritte bei Fehlerbehebungen. Die Box folgt weiterhin den Commits von main; die Nummer ist nur der Anzeigename.

## 0.1.0
- Neues Versionsschema (vorher 2.0.0-rc.x). Sonst unverändert gegenüber 2.0.0-rc.4.

## 2.0.0-rc.4
- Feste Kartennamen (eth0, eth1) nach MAC nur noch als systemd-.link-Dateien, die beim nächsten Start gelten. Im laufenden Betrieb (Update) wird keine Karte mehr umbenannt, keine Netzwerkverbindung verändert. Behebt den Netzausfall beim Einspielen von rc.2.
- Prüfung nach dem Update: War vorher eine Standardroute da, muss sie nachher wieder da sein, sonst wird zurückgerollt.

## 2.0.0-rc.3
- RTMP-Eingang ist jetzt SRS 6 (H.264 und H.265 über RTMP) statt nginx-rtmp; RTMPS bleibt über nginx (nur TLS). Die Statistik auf Port 1936 hat das alte Format.
- bleak/dbus-fast mit festen Versionen, nur installiert wenn etwas fehlt (Update bricht ohne Internet nicht mehr ab).
- Tailscale-Einrichtung erkennt Ubuntu 26.04 (resolute).

## 2.0.0-rc.2
- Programmstand von IRL4YOU für 26.04 (ohne BELABOX): eigene Sendekette (`irl4you-encoder`, `irl4you-srtla`), Mobilfunk-Modems mit APN, Roaming und Netzwahl, eigenes Passwort der Oberfläche (der bisherige Hash wird übernommen), Oberfläche auch auf Port 80, Ton von USB-Karte oder Analogeingang.
- Netzwerk über NetworkManager: Quell-Routing je Karte, Ausweichroute, feste Kartennamen nach MAC; udev-Regeln und nginx-RTMP von IRL4YOU.
- Software-Update über den Update-Helfer.

## 2.0.0-rc.1
- Basis für das Testsystem: NetworkManager verwaltet eth0/eth1, Kernel-Hook (`/boot/Image`, `/boot/dtb`, HDMI-Eingang der Orange Pi 5 Plus), WLAN-Treiber als .deb, deutsche Tastatur/Sprache als Standard.

## 2.0.0
- Erste Version für Ubuntu 26.04 (nur IRL4YOU, ohne BELABOX).
- Updates kommen aus den Commits dieses Repositorys (Zweig main): Git-Baum-Prüfung jeder Datei, CI muss grün sein, atomares Umschalten, automatisches Zurückrollen.
