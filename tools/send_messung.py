#!/usr/bin/env python3
"""Messung der Sendekette (Encoder + SRTLA-Sender) auf der IRL4YOU Box.

Läuft auf der Box (root, wegen /run/pipbox-send), nur Python-Standardbibliothek. Sie liest die Statusdateien der laufenden Sendung
(srtla.json, encoder-stats.json) und rechnet daraus Kennzahlen. Mit --neustart startet sie die Sendung selbst neu und misst dann auch
den Aufbau ab dem Startbefehl.

    sudo python3 send_messung.py --neustart --dauer 150 --name vorher --json vorher.json
    python3 send_messung.py --vergleich vorher.json nachher.json        # Tabelle (Markdown)

Gemessen wird (alles aus den Statusdateien, es werden keine Server-Daten oder Schlüssel gelesen oder ausgegeben):
  Aufbau     Zeit bis erste Leitung angemeldet, alle Leitungen angemeldet, SRT des Encoders verbunden, erste Daten im Netz,
             Bitrate 50 % / 90 % des späteren Dauerwerts
  Durchsatz  je Leitung und gesamt (kbit/s, Mittel der Messphase), Anteil, Verlust (NAK je gesendetem Paket), Umordnung, Laufzeit
  Ruckler    Sekunden mit weniger als 25 Bildern/s für Ausgang und jede Kamera, kleinstes fps, Lücken im Ausgang (Alter des letzten
             Pakets > 100 ms), SRT-Verlust und Wiederholungen des Encoders, größter Sendepuffer
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

RUN = "/run/pipbox-send"
SRTLA = f"{RUN}/srtla.json"
ENC = f"{RUN}/encoder-stats.json"
FPS_LOW = 25.0


def load(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def sample_loop(dur, t0, poll=0.2, rows_file=None):
    """Liefert Zeilen (Zeit seit t0, srtla-Stand, Encoder-Stand); eine Zeile je neuem Stand einer der beiden Dateien."""
    rows, last_s, last_e = [], None, None
    out = open(rows_file, "a") if rows_file else None
    end = t0 + dur
    while time.time() < end:
        s, e = load(SRTLA), load(ENC)
        ns = s.get("t") if s else None
        ne = e.get("t") if e else None
        # Encoder schreibt ganze Sekunden; Änderung an up_s oder frames als Zeichen für neuen Stand
        ke = (e.get("up_s"), (e.get("srt") or {}).get("sent")) if e else None
        if (ns is not None and ns != last_s) or (ke is not None and ke != last_e):
            rows.append((time.time() - t0, s, e))
            if out:
                out.write(json.dumps(rows[-1]) + chr(10))
                out.flush()
                os.fsync(out.fileno())
            last_s, last_e = ns, ke
        time.sleep(poll)
    return rows


def first(rows, pred):
    for t, s, e in rows:
        try:
            if pred(s or {}, e or {}):
                return round(t, 2)
        except (TypeError, KeyError, ValueError):
            pass
    return None


def analyse(rows, name, warm):
    """warm: Sekunden nach Start, ab denen die 'Dauerphase' gerechnet wird (Aufbau und Rampe ausgenommen)."""
    res = {"name": name, "samples": len(rows)}
    links_used = lambda s: [l for l in (s.get("links") or []) if l.get("state") in ("used", "reserve")]
    n_links = max((len(s.get("links") or []) for _, s, _ in rows if s), default=0)
    res["leitungen"] = n_links
    res["aufbau"] = {
        "erste_leitung_s": first(rows, lambda s, e: len(links_used(s)) >= 1),
        "alle_leitungen_s": first(rows, lambda s, e: n_links and len(links_used(s)) >= n_links),
        "encoder_srt_s": first(rows, lambda s, e: (e.get("srt") or {}).get("connected")),
        "erste_daten_s": first(rows, lambda s, e: sum(l.get("kbps", 0) for l in s.get("links") or []) > 0),
        "daten_500kbps_s": first(rows, lambda s, e: sum(l.get("kbps", 0) for l in s.get("links") or []) >= 500),
    }
    targets = [(t, (e.get("rate") or {}).get("kbps")) for t, _, e in rows if e and (e.get("rate") or {}).get("kbps")]
    late = [k for t, k in targets if t >= warm]
    plateau = statistics.median(late) if late else None
    res["rampe"] = {"dauerwert_kbps": plateau}
    for frac in (0.5, 0.9):
        res["rampe"][f"{int(frac * 100)}%_s"] = next((round(t, 1) for t, k in targets if plateau and k >= frac * plateau), None)

    steady = [(t, s, e) for t, s, e in rows if t >= warm]
    res["messphase_s"] = round(steady[-1][0] - steady[0][0], 1) if len(steady) > 1 else 0
    ss = [(t, s) for t, s, _ in steady if s]
    per_link = {}
    if len(ss) > 1:
        a, b = ss[0][1], ss[-1][1]
        span = max(ss[-1][0] - ss[0][0], 1e-6)
        total_pk = sum(l.get("packets", 0) for l in b.get("links") or []) - sum(l.get("packets", 0) for l in a.get("links") or [])
        al = {l["ip"]: l for l in a.get("links") or []}
        for l in b.get("links") or []:
            o = al.get(l["ip"], {})
            pk = l.get("packets", 0) - o.get("packets", 0)
            kb = [x.get("kbps", 0) for _, st in ss for x in st.get("links") or [] if x["ip"] == l["ip"]]
            per_link[l["ip"]] = {
                "dev": l.get("dev", ""),
                "kbps": round(statistics.fmean(kb), 0) if kb else 0,
                "anteil_%": pct(pk, total_pk),
                "verlust_%": pct(l.get("lost", 0) - o.get("lost", 0), pk),
                "umordnung_%": pct(l.get("reordered", 0) - o.get("reordered", 0), pk),
                "rtt_ms": round(l.get("rtt_ms", 0), 1),
                "jitter_ms": round(l.get("jitter_ms", 0), 1),
                "fenster": l.get("window"),
            }
        res["gesamt_kbps"] = round(sum(v["kbps"] for v in per_link.values()), 0)
        res["pakete_je_s"] = round(total_pk / span, 0)
    res["je_leitung"] = per_link

    es = [(t, e) for t, _, e in steady if e]
    if len(es) > 1:
        a, b = es[0][1].get("srt") or {}, es[-1][1].get("srt") or {}
        sent = b.get("sent", 0) - a.get("sent", 0)
        res["encoder_srt"] = {
            "verlust_%": pct(b.get("lost", 0) - a.get("lost", 0), sent),
            "wiederholt_%": pct(b.get("resent", 0) - a.get("resent", 0), sent),
            "send_kbps_mittel": round(statistics.fmean([(x.get("srt") or {}).get("send_kbps", 0) for _, x in es]), 0),
            "rtt_ms_mittel": round(statistics.fmean([(x.get("srt") or {}).get("rtt_ms", 0) for _, x in es]), 1),
            "sendpuffer_ms_max": max((x.get("srt") or {}).get("buf_ms", 0) for _, x in es),
            "abgeworfen": b.get("dropped", 0) - a.get("dropped", 0),
        }
        res["bitrate_kbps_mittel"] = round(statistics.fmean([(x.get("rate") or {}).get("kbps", 0) for _, x in es]), 0)
        ages = [(x.get("out") or {}).get("age_ms", 0) for _, x in es]
        res["ausgang_luecken_ueber_100ms"] = sum(1 for v in ages if v > 100)
        fps = [x.get("fps", 0) for _, x in es]
        res["fps_haupt"] = {"mittel": round(statistics.fmean(fps), 1), "min": min(fps), "sekunden_unter_25": sum(1 for v in fps if v < FPS_LOW)}
        cams = {}
        for _, x in es:
            for k, c in (x.get("cams") or {}).items():
                if c.get("live"):
                    cams.setdefault(k, []).append((c.get("fps", 0), c.get("jit_ms", 0)))
        res["fps_kameras"] = {k: {"mittel": round(statistics.fmean(f for f, _ in v), 1), "min": min(f for f, _ in v),
                                  "sekunden_unter_25": sum(1 for f, _ in v if f < FPS_LOW),
                                  "ankunft_schwankung_ms": round(statistics.fmean(j for _, j in v), 1)}
                              for k, v in sorted(cams.items())}
    return res


def table(rs):
    names = [r["name"] for r in rs]

    def g(r, *path):
        for p in path:
            r = r.get(p) if isinstance(r, dict) else None
        return "-" if r is None else r

    rows = [
        ("Aufbau: erste Leitung angemeldet (s)", ("aufbau", "erste_leitung_s")),
        ("Aufbau: alle Leitungen angemeldet (s)", ("aufbau", "alle_leitungen_s")),
        ("Aufbau: SRT des Encoders verbunden (s)", ("aufbau", "encoder_srt_s")),
        ("Aufbau: erste Daten im Netz (s)", ("aufbau", "erste_daten_s")),
        ("Aufbau: 500 kbit/s erreicht (s)", ("aufbau", "daten_500kbps_s")),
        ("Rampe: Dauerwert Bitrate (kbit/s)", ("rampe", "dauerwert_kbps")),
        ("Rampe: 50 % erreicht (s)", ("rampe", "50%_s")),
        ("Rampe: 90 % erreicht (s)", ("rampe", "90%_s")),
        ("Durchsatz gesamt (kbit/s)", ("gesamt_kbps",)),
        ("Bitrate Mittel (kbit/s)", ("bitrate_kbps_mittel",)),
        ("SRT Verlust Encoder (%)", ("encoder_srt", "verlust_%")),
        ("SRT Wiederholungen (%)", ("encoder_srt", "wiederholt_%")),
        ("Sendepuffer max (ms)", ("encoder_srt", "sendpuffer_ms_max")),
        ("Ausgang Lücken >100 ms (Stände)", ("ausgang_luecken_ueber_100ms",)),
        ("Hauptbild fps Mittel", ("fps_haupt", "mittel")),
        ("Hauptbild fps min", ("fps_haupt", "min")),
        ("Hauptbild Sekunden <25 fps", ("fps_haupt", "sekunden_unter_25")),
    ]
    out = ["| Kennzahl | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for label, path in rows:
        out.append(f"| {label} | " + " | ".join(str(g(r, *path)) for r in rs) + " |")
    cams = sorted({k for r in rs for k in (r.get("fps_kameras") or {})})
    for k in cams:
        for what, key in (("fps Mittel", "mittel"), ("fps min", "min"), ("Sek. <25 fps", "sekunden_unter_25"), ("Ankunft-Schwankung ms", "ankunft_schwankung_ms")):
            out.append(f"| Kamera {k} {what} | " + " | ".join(str(g(r, "fps_kameras", k, key)) for r in rs) + " |")
    ips = sorted({ip for r in rs for ip in (r.get("je_leitung") or {})})
    for ip in ips:
        for what, key in (("kbit/s", "kbps"), ("Anteil %", "anteil_%"), ("Verlust %", "verlust_%"), ("Umordnung %", "umordnung_%"), ("RTT ms", "rtt_ms")):
            out.append(f"| Leitung {ip} {what} | " + " | ".join(str(g(r, "je_leitung", ip, key)) for r in rs) + " |")
    return "\n".join(out)


def run_service(action):
    subprocess.run(["systemctl", action, "pipbox-send.service"], check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--neustart", action="store_true", help="Sendung neu starten und den Aufbau mitmessen")
    ap.add_argument("--start", action="store_true", help="Sendung starten (nur wenn sie nicht läuft)")
    ap.add_argument("--stop", action="store_true", help="Sendung nach der Messung beenden")
    ap.add_argument("--dauer", type=float, default=150.0, help="Messdauer in Sekunden ab Start (Standard 150)")
    ap.add_argument("--warm", type=float, default=None, help="Dauerphase ab Sekunde (Standard: ab 60 %% der Dauer, mindestens 90)")
    ap.add_argument("--name", default="messung")
    ap.add_argument("--json", help="Ergebnis als JSON speichern")
    ap.add_argument("--zeilen", metavar="DATEI", help="Rohdaten der Messung (JSON-Zeilen, werden laufend gesichert) auswerten, keine Messung")
    ap.add_argument("--vergleich", nargs="+", metavar="JSON", help="Tabelle aus gespeicherten Ergebnissen, keine Messung")
    a = ap.parse_args()
    if a.vergleich:
        print(table([json.load(open(p)) for p in a.vergleich]))
        return 0
    if a.zeilen:
        rows = [tuple(json.loads(l)) for l in open(a.zeilen) if l.strip()]
        print(table([analyse(rows, a.name, a.warm if a.warm is not None else 60.0)]))
        return 0
    t0 = time.time()
    if a.neustart:
        run_service("restart")
    elif a.start:
        run_service("start")
    warm = a.warm if a.warm is not None else max(90.0, a.dauer * 0.6)
    rows = sample_loop(a.dauer, t0, rows_file=(a.json + ".zeilen") if a.json else None)
    if a.stop:
        run_service("stop")
    res = analyse(rows, a.name, min(warm, a.dauer - 10))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, ensure_ascii=False)
    print(table([res]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
