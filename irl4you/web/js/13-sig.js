$("sw_rollback").addEventListener("click", async () => {
  if (!confirm("Zur vorherigen Version zurückgehen?\n\nDie Oberfläche startet dabei kurz neu. Es darf nicht gesendet werden.")) return;
  swBegin("Wird zurückgestellt …");
  try {
    await srtlaCall("POST", "/api/swupdate", { action: "rollback", confirm: true });
  } catch (x) {
    swPending = pbUpdating = 0;
    progSet("swprog", false);
    $("sw_msg").textContent = x.message;
    $("sw_msg").style.color = "var(--crit)";
  }
  setTimeout(() => swLoad(false), 1500);
});
swLoad(false, true);
$("swcard").addEventListener("toggle", () => {
  if ($("swcard").open) swLoad(false, true);
});
(function swLoop() {
  (swPending || pbUpdating || due("sw", "swcard", 60000) ? swLoad(false) : Promise.resolve()).finally(() =>
    setTimeout(swLoop, swPending || pbUpdating ? 2000 : 8000),
  );
})();
try {
  const v = sessionStorage.getItem("pb_updated");
  if (v) {
    sessionStorage.removeItem("pb_updated");
    const t = $("updtoast");
    t.textContent = `✔ Update installiert: Die Box läuft jetzt mit Version ${v}.`;
    t.hidden = false;
    setTimeout(() => (t.hidden = true), 9000);
  }
} catch (e) {}
function renderDetails(m) {
  if (!$("statdet").open) return;
  const d = m.details || {},
    drow = (l, v, t) =>
      `<div class="row" style="padding:2px 0"><span class="muted"${t ? `title="${esc(t)}"` : ""}>${l}</span><span>${v}</span></div>`;
  const f1 = (x) => (x == null || x < 0 ? "–" : (+x).toFixed(1)),
    n0 = (x) => (x == null || x < 0 ? "–" : String(Math.round(x)));
  const s = d.send;
  $("det_send").innerHTML = !s
    ? '<span class="muted">Keine Daten (die Sendung läuft nicht).</span>'
    : drow("Bitrate", `<b>${f1(upShown(m))}</b> Mbit/s <span class="muted">(eingestellt ${f1(s.bitrate_kbps / 1000)})</span>`) +
      drow("Laufzeit (Ping, RTT)", `<b>${f1(s.rtt_ms)}</b> ms`) +
      Object.entries(m.uplinks || {})
        .filter(([n, u]) => u && u.srtt != null)
        .map(([n, u]) => drow('<span class="muted">· ' + esc(ifd(n)) + "</span>", `${n0(u.srtt)} ms`))
        .join("") +
      drow("Sendepuffer", `<b>${n0(s.snd_buf_ms)}</b> ms <span class="muted">(${n0(s.snd_buf_pkts)} Pakete)</span>`) +
      drow(
        "Paketverlust",
        `<b>${n0(s.loss_total)}</b> <span class="muted">(${s.loss_pct == null ? "–" : s.loss_pct.toFixed(2)} %)</span>`,
      ) +
      drow("Encoder-Bilder pro Sekunde", `<b>${f1(s.fps)}</b>`);
  const cores = (m.cpu && m.cpu.cores) || [],
    fr = (m.cpu && m.cpu.freq_mhz) || [],
    ac = d.accel || {};
  const bar = (p) => `<div class="bar" style="margin:1px 0 3px"><i style="width:${Math.max(0, Math.min(100, p || 0))}%"></i></div>`;
  $("det_cpu").innerHTML =
    cores
      .map(
        (c, i) =>
          drow(
            `Kern ${i}`,
            `<b>${fmt(c, 0)}</b> % <span class="muted">${fr[i] ? (fr[i] >= 1000 ? (fr[i] / 1000).toFixed(1) + " GHz" : fr[i] + " MHz") : ""}</span>`,
          ) + bar(c),
      )
      .join("") +
    (ac.gpu ? drow("GPU", `<b>${ac.gpu.load_pct}</b> % <span class="muted">${ac.gpu.mhz} MHz</span>`) + bar(ac.gpu.load_pct) : "");
  $("det_temp").innerHTML =
    (d.temps || []).map((t) => drow(esc(t.name), `<b>${f1(t.c)}</b> °C`)).join("") || '<span class="muted">keine Daten</span>';
  const k = d.disk;
  $("det_disk").innerHTML = !k
    ? '<span class="muted">keine Daten</span>'
    : drow("Belegt", `<b>${f1(k.used_gb)}</b> GB <span class="muted">(${f1(k.used_pct)} %)</span>`) +
      bar(k.used_pct) +
      drow("Frei", `<b>${f1(k.free_gb)}</b> GB`) +
      drow("Gesamt", `${f1(k.total_gb)} GB`);
}
$("statdet").addEventListener("toggle", () => {
  if ($("statdet").open) tick();
});
function upTotal(m) {
  const upl = ((srtlaData && srtlaData.settings) || {}).uplinks || [];
  let nets = Object.entries(m.net || {});
  const sel = nets.filter(([n]) => upl.includes(n));
  if (sel.length) nets = sel;
  return nets.reduce((a, [n, r]) => a + (+r.tx_mbit || 0), 0);
}
function upShown(m) {
  const wire = upTotal(m),
    pay = m.payload_mbit == null ? null : +m.payload_mbit;
  return pay == null || isNaN(pay) ? wire : Math.min(pay, wire);
}
function sigLevel(m) {
  const s = m.details && m.details.send;
  if (!s) return null;
  const ups = Object.values(m.uplinks || {}).filter(Boolean),
    on = ups.filter((u) => u.state === "an").length;
  if (ups.length && !on) return 0;
  let q = 4;
  if (ups.length && on < ups.length) q -= 1;
  const want = (s.bitrate_kbps || 0) / 1000;
  if (want > 0) {
    const r = upTotal(m) / want,
      backlog = s.snd_buf_ms != null && s.snd_buf_ms > 300;
    if (r < 0.1) q -= 2;
    else if (backlog && r < 0.5) q -= 2;
    else if (backlog && r < 0.8) q -= 1;
  }
  if (s.rtt_ms != null) {
    if (s.rtt_ms > 1000) q -= 2;
    else if (s.rtt_ms > 400) q -= 1;
  }
  if (s.snd_buf_ms != null) {
    if (s.snd_buf_ms > 3000) q -= 2;
    else if (s.snd_buf_ms > 1500) q -= 1;
  }
  return Math.max(0, Math.min(4, q));
}
let tickOk = 0;
const sigPts = [],
  SIG_WIN = 30000;
function sigNice(v) {
  for (const c of [5000, 10000, 15000, 20000, 30000, 50000, 100000]) if (v * 1.05 <= c) return c;
  return Math.ceil(v / 10000) * 10000;
}
function sigDraw() {
  const line = $("net_line");
  if (!line || !sigPts.length) return;
  const now = Date.now(),
    cut = now - SIG_WIN;
  while (sigPts.length > 1 && sigPts[1].t <= cut) sigPts.shift();
  const pts = sigPts.map((p) => ({ t: Math.max(cut, p.t), v: p.v })),
    FLOOR = 0,
    ceil = sigNice(Math.max(...pts.map((p) => p.v)));
  const plot = pts.length === 1 ? [{ t: Math.max(cut, now - 2000), v: pts[0].v }, pts[0]] : pts,
    mb = (v) => (v / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 });
  $("sg_val").textContent = mb(pts[pts.length - 1].v);
  $("sg_max").textContent = mb(ceil);
  $("sg_mid").textContent = mb((FLOOR + ceil) / 2);
  $("sg_min").textContent = mb(FLOOR);
  line.setAttribute(
    "points",
    plot
      .map(
        (p) =>
          Math.min(80, ((p.t - cut) / SIG_WIN) * 80).toFixed(1) +
          "," +
          (19 - ((Math.max(FLOOR, Math.min(ceil, p.v)) - FLOOR) / (ceil - FLOOR)) * 18).toFixed(1),
      )
      .join(" "),
  );
}
setInterval(() => {
  if (document.hidden) return;
  const el = $("net_sig");
  if (!el) return;
  const stale = tickOk > 0 && Date.now() - tickOk > 8000;
  el.classList.toggle("stale", stale);
  if (stale) {
    $("sg_val").textContent = "–";
    el.setAttribute("title", "Verbindung: keine Messwerte von der Box");
  } else sigDraw();
}, 500);
function paintSig(m) {
  const el = $("net_sig");
  if (!el) return;
  const q = sigLevel(m),
    sd = m.details && m.details.send;
  sigPts.push({ t: Date.now(), v: q == null ? 0 : Math.max(0, upShown(m) * 1000) });
  sigDraw();
  el.classList.remove("ok", "warn", "crit");
  if (q != null) el.classList.add(q >= 3 ? "ok" : q === 2 ? "warn" : "crit");
  const tip =
    q == null
      ? "Verbindung: keine Messung (es wird nicht gesendet)"
      : q >= 3
        ? "Verbindung: gut"
        : q === 2
          ? "Verbindung: mäßig"
          : "Verbindung: schlecht";
  el.setAttribute("title", tip);
  el.setAttribute("aria-label", tip);
}
