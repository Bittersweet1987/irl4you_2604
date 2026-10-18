# Drittprojekte und Lizenzen

IRL4YOU Box besteht aus eigenem Code (MIT-Lizenz, siehe `LICENSE`) und aus Programmen und Treibern anderer Projekte, die mit der Box ausgeliefert oder bei der Installation geladen werden. Diese Seite nennt, was wirklich verwendet wird. Keine Rechtsberatung.

## Quelltext in diesem Repository

| Teil | Herkunft | Lizenz |
|---|---|---|
| Oberfläche, Dienste, Updater, Tests (`irl4you/`, `updater/`, `tests/`) | eigene Entwicklung | MIT |
| Encoder `irl4you-encoder`, SRTLA-Sender `irl4you-srtla` | eigene Entwicklung (Clean-Room: SRTLA nur nach eigener Protokollbeschreibung) | MIT |
| Bild-in-Bild-Baustein `irl4you/gst-src/` | eigene Entwicklung, lädt zur Laufzeit GStreamer (LGPL) | MIT |
| DJI-Kopplung `irl4you/dji_daemon.py`, `dji.py` | Ablauf und Nachrichtenformat nach Moblin (siehe unten), DJI-Dienst von Bittersweet1987 | MIT |

Aus BELABOX (belaUI, belacoder, srtla) wird **kein Quelltext, keine Datei und kein Programm** mehr verwendet. IRL4YOU Box ist kein Produkt von BELABOX, Radxa, Orange Pi, Rockchip oder DJI. Die Prozessnamen `belacoder` und `belaUI` kommen im Code nur noch vor, um die Reste einer alten Installation zu erkennen und beim Umzug das Anmeldepasswort (Hash) und den Benutzernamen zu übernehmen.

## Moblin (MIT)

Die DJI-Kopplung per Bluetooth folgt dem Ablauf, den das Projekt [Moblin](https://github.com/eerimoq/moblin) von Erik Moqvist umsetzt (Ordner `Moblin/Integrations/Dji/`): Nachrichtenformat, Konstanten und Ablauf wurden nach Python übertragen. Gegenprobe mit [dimadesu/dji-remote](https://github.com/dimadesu/dji-remote) (MIT). Das DJI-Protokoll ist von DJI nicht dokumentiert. Die App Moblin selbst ist nicht enthalten; die Oberfläche bietet nur einen Link, der Streams in der App Moblin öffnet.

> Copyright (c) 2023 Erik Moqvist
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Pakete und Bibliotheken

Die Pakete in `irl4you/debs/` baut die Box selbst (Skripte in `build/`). Der Quelltext der Fremdprojekte wird beim Bauen von GitHub geholt; Stand und Quelle stehen in den Bauskripten.

| Komponente | Quelle | Lizenz | Hinweis |
|---|---|---|---|
| SRS 6.0.193 (`irl4you-srs`) | [ossrs/srs](https://github.com/ossrs/srs) | MIT | RTMP/SRT-Eingang, Bau mit einer Zeile Korrektur (`build/box-build.sh`) |
| Rockchip MPP 1.1.0 (`irl4you-mpp`) | [rockchip-linux/mpp](https://github.com/rockchip-linux/mpp) | Apache-2.0 | Hardware-Video |
| Rockchip RGA (`librga`) | [JeffyCN/mirrors](https://github.com/JeffyCN/mirrors), Zweig `linux-rga-multi` | Apache-2.0 | Bildskalierung |
| GStreamer-Elemente für MPP (`irl4you-gst-rockchip`) | [JeffyCN/mirrors](https://github.com/JeffyCN/mirrors), Zweig `gstreamer-rockchip` | LGPL/MIT laut Quellprojekt | gebaut gegen MPP |
| WLAN-Treiber rtw88 (`irl4you-wifi-rtw88`) | [lwfinger/rtw88](https://github.com/lwfinger/rtw88) | GPL-2.0 | Kernelmodul für Kernel 6.1.172 |
| WLAN-Treiber AIC8800 (`irl4you-wifi-aic8800`) | [shenmintao/aic8800d80](https://github.com/shenmintao/aic8800d80), Zweig `legacy-mcu1` | GPL-2.0, Firmware des Herstellers | Kernelmodul für Kernel 6.1.172 |
| Linux-Kernel (Rockchip BSP 6.1) | [armbian/linux-rockchip](https://github.com/armbian/linux-rockchip) | GPL-2.0 | Quelle für Kernelbaum und Module |
| bleak 3.0.2, dbus-fast 5.2.0 | PyPI | MIT / MIT | per `pip` bei der Installation geladen, nicht mitgeliefert |
| GStreamer, libsrt, OpenSSL, nginx, NetworkManager, Python, Tailscale u. a. | Ubuntu 26.04 bzw. Tailscale-Paketquelle | jeweils eigene Lizenz (u. a. LGPL, MPL-2.0, Apache-2.0, BSD) | Systempakete, nicht verändert |

## Emotes im Twitch-Chat

Der Chat lädt Emotes zur Laufzeit von Twitch, BetterTTV, FrankerFaceZ und 7TV. Die Bilder gehören ihren Urhebern und werden nicht mitgeliefert.

## Welche Lizenz gilt wo

- **MIT**: der eigene Code dieses Repositorys.
- **GPL-2.0**: Kernel und die beiden WLAN-Treiber. Die Pakete enthalten die gebauten Module; der Quelltext ist über die oben genannten Quellen und die Bauskripte in `build/` erreichbar.
- **MIT, Apache-2.0, LGPL**: SRS, MPP, librga, gstreamer-rockchip (siehe Tabelle).
