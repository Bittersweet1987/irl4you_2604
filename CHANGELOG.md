# Änderungen

## 2.0.0-rc.2
- Programmstand von IRL4YOU für 26.04 (ohne BELABOX): eigene Sendekette (`irl4you-encoder`, `irl4you-srtla`), Mobilfunk-Modems mit APN, Roaming und Netzwahl, eigenes Passwort der Oberfläche (der bisherige Hash wird übernommen), Oberfläche auch auf Port 80, Ton von USB-Karte oder Analogeingang.
- Netzwerk über NetworkManager: Quell-Routing je Karte, Ausweichroute, feste Kartennamen nach MAC; udev-Regeln und nginx-RTMP von IRL4YOU.
- Software-Update über den Update-Helfer.

## 2.0.0-rc.1
- Basis für das Testsystem: NetworkManager verwaltet eth0/eth1, Kernel-Hook (`/boot/Image`, `/boot/dtb`, HDMI-Eingang der Orange Pi 5 Plus), WLAN-Treiber als .deb, deutsche Tastatur/Sprache als Standard.

## 2.0.0
- Erste Version für Ubuntu 26.04 (nur IRL4YOU, ohne BELABOX).
- Updates kommen aus den Commits dieses Repositorys (Zweig main): Git-Baum-Prüfung jeder Datei, CI muss grün sein, atomares Umschalten, automatisches Zurückrollen.
