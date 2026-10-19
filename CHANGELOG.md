# Änderungen

Versionsschema: x.y.z, angezeigt als vx.y.z. x gibt Marco vor (0 = Alpha). y steigt nur, wenn Marco ein Release ausruft (dann wird VERSION auf "x.y" geändert). z ist die Zahl der Commits seit dem letzten Release und wird vom Updater beim Installieren aus GitHub gezählt (VERSION enthält nur "x.y"). Die Box folgt weiterhin den Commits von main; die Nummer ist nur der Anzeigename.

## 0.3
- Kameras laufen flüssig: Der Kamerapuffer im Encoder war zu klein (8 Bilder, `max-bytes` 200 kB bei 1350 ms Vorlauf), dadurch wurden die ältesten Bilder weggeworfen und der Mischer wiederholte ein bis zwei Sekunden dasselbe Bild. Der Puffer fasst jetzt Vorlauf plus 1,5 s (Encoder 0.2.2). Standbild-Folgen am Empfänger: vorher bis 70 Bilder, jetzt höchstens so viele wie in den Kameraeingängen selbst.
- Keine falsche Meldung "Bild 2,5 s zu früh" mehr (Kamera wurde alle paar Minuten 15 s abgeschaltet): `lag_ms` wurde je Bild auf ganze Millisekunden gekürzt, die Summe sank dadurch ständig; jetzt in Nanosekunden, die ersten 5 s nach dem Kamerastart zählen nicht mit.
- Ausblenden, Tonquelle und Stumm lösten in der neuen Sendekette einen Neustart der ganzen Sendung aus; sie werden jetzt live umgestellt (wie Bildwechsel und Kamera deaktivieren).
- Die SRT-Sendegeschwindigkeit ist auf die eingestellte Höchstbitrate plus 25 % begrenzt (Encoder 0.2.3): kein Stoß mit Leitungsgeschwindigkeit mehr nach dem Verbinden oder einem Stau (vorher kurzzeitig bis über 60 Mbit/s bei 12 Mbit/s Höchstbitrate).
- WLAN: "Trennen" schaltet die automatische Verbindung ab (bleibt nach einem Neustart getrennt), "Vergessen" meldet Fehler statt Erfolg.
- SSH-Passwort: ohne `system.json` gilt der erste normale Benutzer als Standard (Anzeige und Zurücksetzen gingen sonst nicht); Bluetooth-Firmware (.zst) für Realtek-Sticks wie UB500 wird entpackt.
- Netzwerk: feste Zusatzadresse jederzeit entfernbar, Warnung bei zwei Anschlüssen im selben Adressbereich, Routing je Anschluss nach DHCP-Adresse.
- Takt-Deckel der großen Kerne 2016 MHz mit Firmware BL31 v1.47 (`irl4you-bootloader`, nur manuell), sonst 1416 MHz.
- Software-Update: "Neueste auf GitHub" zeigt die Versionsnummer; Änderungsliste mit einem Eintrag je Commit; Sicherheitsupdates nur noch zusammen mit IRL4YOU-Updates.
- Lizenz CC BY-ND 4.0 mit Zusatzerlaubnis für IRL4YOU, README zweisprachig; SRS prüft H.264 zuerst im Längenformat (Redmi); Bildraten-Messung der Eingänge korrigiert; Encoder- und SRTLA-Quelltext liegen im Repo.
- Bekannt offen: In seltenen Fällen setzt sich die Box hart zurück (LED rot, Netzteil ziehen); die Ursache ist noch nicht gefunden.

## 0.1
- Lizenz: der eigene Code steht jetzt unter CC BY-ND 4.0 statt MIT (Nutzung auch kommerziell, Änderungen nur nach Rückfrage bei [Bittersweet1987](https://discord.com/users/232451293040476160) oder [Akinos01](https://discord.com/users/523858990510243861), Ausnahme IRL4YOU; `LICENSE`, `ZUSATZERLAUBNIS.md`, `NOTICE.md`). Seitenfuß in allen Sprachen angepasst; gilt auch für frühere Versionen (bereits unter MIT erhaltene Kopien behalten ihre damaligen Rechte).
- Die IRL4YOU Box ist ohne Portangabe erreichbar (http://irl4you.local oder http://<IP>, Port 80); der alte Port 8780 bleibt. Der Dienst versucht Port 80 weiter, wenn er beim Start noch belegt ist, statt dauerhaft nur auf 8780 zu laufen. Anmeldung und Ersteinrichtung nur aus dem lokalen Netz unverändert.
- Senden schneller und flüssiger (Encoder 0.2.1, SRTLA 0.1.3): Der Encoder startet sofort mit der Obergrenze der Bitrate und senkt nur noch bei echtem Stau (vorher Anlauf von 300 kbit/s mit +50 kbit/s je Sekunde, dazu Senken schon bei 40 ms mehr Laufzeit). Die Bildzeitstempel der Kameras werden geglättet statt nach der Ankunft gesetzt (gleichmäßige Bildabstände im Mischer, flüssigeres Haupt- und Nebenbild). Der Encoder darf Qualität bis QP 1 nutzen (qp-min 1): vorher blieb er bei etwa 3 bis 5 Mbit/s hängen, obwohl die Leitungen mehr hergaben. SRTLA gibt verlustreichen Leitungen weniger Pakete (Verlustgewichtung je Leitung, Anteil und Fensterwahl). Neu: tools/send_messung.py misst Aufbauzeit, Durchsatz je Leitung, Verlust und Bildraten der Sendung auf der Box.
- Karte "System-Updates" (apt-Updates mit eigenen Paketen, pipbox-update, /api/update, Symbol im Kopf, Texte in allen Sprachen). Das Software-Update von IRL4YOU (irl4you-update) bleibt.
- WLAN-Sticks mit AIC8800 (z. B. UGREEN AX900): Treiber, Firmware und Umschaltdatei kommen als Paket irl4you-wifi-aic8800 (Zweig legacy-mcu1 für Kernel 6.1.172); pipbox-wlandriver schaltet den Stick vom USB-Laufwerk-Modus um und prüft die Schnittstelle, es wird nichts mehr geladen oder gebaut.
- Bluetooth: der Kernel 6.1 kennt UGREEN BT6.0 (Barrot) und TP-Link UB500 selbst; der alte btusb-Patch entfällt. pipbox-btdriver trägt nur noch fehlende Kennungen zur Laufzeit nach und hebt eine Funksperre (rfkill) auf; pipbox-btchip prüft nur noch den eingebauten Chip der ROCK 5B Plus.
- Redmi und andere Handys: SRS prüft H.264 im RTMP-Strom jetzt zuerst im Längenformat (try_annexb_first off); vorher Abbruch "not annexb" beim ersten Bild und endloses Wiederverbinden. Ein SRS-Neustart durch das Update trennt die Kameras kurz.
- Bildrate der Eingänge: SRS setzt den Bildzähler nur alle ~15 s weiter (Bytezähler alle ~3 s). Die Messung (pipbox-rtmpstat) rechnet jetzt je Zähler zwischen dessen Sprüngen, liest alle 0,2 s im Hintergrund und rastet auf übliche Bildraten ein: nie mehr als gesendet, keine Lücken (auch nicht beim Wiederverbinden).
- Neues Versionsschema (vorher 2.0.0-rc.x), erstes Release 0.1. Der Updater zählt die dritte Stelle selbst, sobald VERSION nur "x.y" enthält. Sonst unverändert gegenüber 2.0.0-rc.4.
- Oberfläche aufgeteilt: server.py (7300 Zeilen) ist nur noch der Einstieg, die Teile liegen im Paket webui/ (jede Datei höchstens 500 Zeilen). Keine Funktionsänderung.
- Weboberfläche aufgeteilt: index.html (365 KB) ist nur noch das Gerüst; je Karte eine Datei in web/partials/, Stile in web/css/, Skripte in web/js/ (formatiert, je höchstens etwa 500 Zeilen). Der Server setzt die Teile beim Ausliefern zusammen und liefert /ui/css und /ui/js aus. Keine Funktionsänderung.
- Twitch-Teil aufgeteilt: twitch.py (2750 Zeilen) ist jetzt das Paket twitch/ mit 12 Dateien (je höchstens 400 Zeilen). Keine Funktionsänderung.

## 2.0.0-rc.4
- Feste Kartennamen (eth0, eth1) nach MAC nur noch als systemd-.link-Dateien, die beim nächsten Start gelten. Im laufenden Betrieb (Update) wird keine Karte mehr umbenannt, keine Netzwerkverbindung verändert. Behebt den Netzausfall beim Einspielen von rc.2.
- Prüfung nach dem Update: War vorher eine Standardroute da, muss sie nachher wieder da sein, sonst wird zurückgerollt.

## 2.0.0-rc.3
- RTMP-Eingang ist jetzt SRS 6 (H.264 und H.265 über RTMP) statt nginx-rtmp; RTMPS bleibt über nginx (nur TLS). Die Statistik auf Port 1936 hat das alte Format.
- bleak/dbus-fast mit festen Versionen, nur installiert wenn etwas fehlt (Update bricht ohne Internet nicht mehr ab).
- Tailscale-Einrichtung erkennt Ubuntu 26.04 (resolute).

## 2.0.0-rc.2
- Programmstand von IRL4YOU für 26.04: eigene Sendekette (`irl4you-encoder`, `irl4you-srtla`), Mobilfunk-Modems mit APN, Roaming und Netzwahl, eigenes Passwort der Oberfläche (der bisherige Hash wird übernommen), Oberfläche auch auf Port 80, Ton von USB-Karte oder Analogeingang.
- Netzwerk über NetworkManager: Quell-Routing je Karte, Ausweichroute, feste Kartennamen nach MAC; udev-Regeln und nginx-RTMP von IRL4YOU.
- Software-Update über den Update-Helfer.

## 2.0.0-rc.1
- Basis für das Testsystem: NetworkManager verwaltet eth0/eth1, Kernel-Hook (`/boot/Image`, `/boot/dtb`, HDMI-Eingang der Orange Pi 5 Plus), WLAN-Treiber als .deb, deutsche Tastatur/Sprache als Standard.

## 2.0.0
- Erste Version für Ubuntu 26.04 (nur IRL4YOU).
- Updates kommen aus den Commits dieses Repositorys (Zweig main): Git-Baum-Prüfung jeder Datei, CI muss grün sein, atomares Umschalten, automatisches Zurückrollen.
