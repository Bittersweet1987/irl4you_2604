// WLAN-Verbindungen: Adapter-Liste, je Stick Netze suchen / manuell eintragen / verbinden / trennen / vergessen.
// Der Hotspot-Modus steht darunter (07-hs.js). Zustand je Stick (gewähltes Netz, Eingaben) bleibt in wlUi.
const wlUi = {};
const wlOf = (iface) => wlUi[iface] || (wlUi[iface] = { mode: "list", sel: "", pw: "", ssid: "", mpw: "", hidden: false });
const wifiIfaces = () => ((wifiData && wifiData.cards) || []).filter((c) => !c.camera_net && !hsOn0(c));
const wifiDefaultIface = () => (wifiIfaces()[0] || {}).iface || "";
const wlBars = (p) =>
  "▂▄▆█"
    .split("")
    .map((c, i) => `<span style="color:${p >= (i + 1) * 25 - 12 ? "var(--ok)" : "var(--line)"}">${c}</span>`)
    .join("");

function devRow(c, ups) {
  const head = `<b>${esc(c.iface)}</b>${devInfo(c)}`;
  if (c.camera_net)
    return `<div class="wstat${hsOn0(c) ? " ok" : ""}"><span class="wdot"></span><span class="wgrow">${head} · Kameranetz${hsOn0(c) ? " · Hotspot <b>" + esc(c.hotspot.ssid) + "</b> läuft · " + esc(c.ip) : ""} (hier nicht änderbar)</span></div>`;
  if (hsOn0(c))
    return `<div class="wstat ok"><span class="wdot"></span><span class="wgrow">${head} · Hotspot <b>${esc(c.hotspot.ssid)}</b> läuft · ${esc(c.ip)}</span></div>`;
  return (
    `<div class="wstat${c.ip ? " ok" : ""}"><span class="wdot"></span><span class="wgrow">${head} · ${c.ip ? `verbunden${c.ssid ? " mit <b>" + esc(c.ssid) + "</b>" : ""}· ${esc(c.ip)}${c.signal != null ? " · Signal " + c.signal + " %" : ""}` : "nicht verbunden"}</span>` +
    (c.ip
      ? `<label title="Sendet die Box auch über dieses Netz. Danach Sendekette neu starten."><input type="checkbox" data-wup="${esc(c.iface)}"${ups.includes(c.iface) ? " checked" : ""}> Zum Senden verwenden</label>`
      : "") +
    `</div>`
  );
}
function wifiDebug(d) {
  const dbg = (d.scan && d.scan.debug) || [];
  if (!dbg.length || d.state === "working") return "";
  return `<details class="sens" open><summary class="muted">Technische Angaben zur Karte ${esc(d.scan.iface || "")} (die Suche hat nichts gefunden)</summary><pre>${esc(dbg.join("\n"))}</pre></details>`;
}
const wlTrash = (ssid) =>
  `<button type="button" class="sec small wl-del" data-ssid="${esc(ssid)}" title="Netz vergessen" aria-label="Netz vergessen">🗑</button>`;
function wlRow(n, saved, sel) {
  const isSaved = saved.includes(n.ssid);
  return `<div class="wrow${n.in_use ? " cur" : ""}${sel === n.ssid ? " sel" : ""}${isSaved ? " wsv" : ""}" role="button" tabindex="0" data-ssid="${esc(n.ssid)}"><span class="wname">${esc(n.ssid)}</span>
    <span class="wsig">${n.signal != null ? wlBars(n.signal) + " " + n.signal + " %" : ""}</span>
    <span class="wsec">${n.security ? (n.security !== "offen" ? "🔒 " + esc(n.security) : "offen") : ""}${isSaved ? (n.security ? " · " : "") + "gespeichert" : ""}</span>${n.in_use ? '<span class="wuse">verbunden</span>' : ""}${isSaved ? wlTrash(n.ssid) : ""}</div>`;
}
const WL_LIST_S = 180;
// Ergebnisliste einer Suche: nur während und bis 3 Minuten nach der Suche offen, danach nur das verbundene Netz
function wlScanShown(c, d) {
  if (!d.scan || d.scan.iface !== c.iface) return false;
  return d.state === "working" && d.action === "scan" ? true : (d.now || 0) - (d.scan.scanned || 0) < WL_LIST_S;
}
function wlList(c, d, u, off) {
  const saved = d.saved || [],
    shown = wlScanShown(c, d),
    nets = shown ? d.scan.nets || [] : c.ssid ? [{ ssid: c.ssid, signal: c.signal, security: "", in_use: true }] : [];
  let h = `<div class="actions"><button type="button" class="sec wl-scan"${off}>Netze suchen</button>${c.ip ? `<button type="button" class="sec wl-disc"${off}>Trennen</button>` : ""}</div>`;
  if (nets.length)
    h += `<div class="muted">${shown ? "Gefundene Netze – Zeile anklicken zum Auswählen:" : "Verbunden mit"}</div><div class="wlist">${nets.map((n) => wlRow(n, saved, u.sel)).join("")}</div>`;
  else if (shown) h += wifiDebug(d);
  if (u.sel) {
    const sv = saved.includes(u.sel);
    h += `<div class="wlsel"><div class="muted">Gewähltes Netz: <b>${esc(u.sel)}</b></div>
      <label class="muted">Passwort<input class="wl-pw" type="password" maxlength="64" autocomplete="new-password" value="${esc(u.pw)}" placeholder="${sv ? "leer = gespeichertes Passwort verwenden" : "leer bei offenem Netz"}"></label>
      <div class="actions"><button type="button" class="wl-go"${off}>Verbinden</button><button type="button" class="sec wl-cancel">Abbrechen</button></div></div>`;
  }
  return h;
}
function wlManual(c, u, off) {
  return `<div class="wform"><label class="muted">Netzname (SSID)<input class="wl-ssid" maxlength="32" autocomplete="off" value="${esc(u.ssid)}"></label>
    <label class="muted">Passwort<input class="wl-mpw" type="password" maxlength="64" autocomplete="new-password" value="${esc(u.mpw)}" placeholder="leer bei offenem Netz"></label></div>
    <label class="muted" style="display:block;margin:8px 0"><input type="checkbox" class="wl-hidden"${u.hidden ? " checked" : ""}> verstecktes Netz (Name wird nicht ausgesendet)</label>
    <div class="actions"><button type="button" class="wl-go"${off}>Verbinden</button>${c.ip ? `<button type="button" class="sec wl-disc"${off}>Trennen</button>` : ""}</div>`;
}
function wlPanel(c, d, busy) {
  if (c.camera_net) return "";
  if (hsOn0(c)) return '<div class="ph" style="margin:4px 0 0 18px">Auf diesem Stick läuft der Hotspot. Zum Verbinden mit einem WLAN zuerst den Hotspot beenden (unten bei Hotspot-Modus).</div>';
  const u = wlOf(c.iface),
    off = busy ? " disabled" : "",
    on = (m) => (u.mode === m ? " on" : "");
  return `<div class="wlpanel"><div class="seg" role="group"><button type="button" class="wl-mode${on("list")}" data-m="list" aria-pressed="${u.mode === "list"}">Aus Liste wählen</button><button type="button" class="wl-mode${on("manual")}" data-m="manual" aria-pressed="${u.mode === "manual"}">Manuell eingeben</button></div>${u.mode === "manual" ? wlManual(c, u, off) : wlList(c, d, u, off)}</div>`;
}
let wlExpire = null;
function renderWifiDev(d, force) {
  const ups = ((srtlaData && srtlaData.settings) || {}).uplinks || [],
    busy = !d.helper_installed || d.state === "working",
    none = '<div class="ph">Keine WLAN-Karte gefunden.</div>';
  const cl = d.cards.length ? d.cards.map((c) => `<div class="wcard" data-iface="${esc(c.iface)}">${devRow(c, ups)}${wlPanel(c, d, busy)}</div>`).join("") : none;
  const hs =
    d.cards
      .map((c) => {
        const ctl = hsControls(c, busy);
        return ctl ? `<div class="wcard" data-iface="${esc(c.iface)}">${hsHead(c)}${ctl}</div>` : "";
      })
      .join("") || (d.cards.length ? '<div class="ph">Kein WLAN-Stick kann einen Hotspot aufbauen.</div>' : none);
  const a = document.activeElement;
  clearTimeout(wlExpire);
  const left = d.cards.filter((c) => !c.camera_net && wlScanShown(c, d) && d.state !== "working").map((c) => WL_LIST_S - ((d.now || 0) - d.scan.scanned));
  if (left.length) wlExpire = setTimeout(() => renderWifiDev(wifiData, true), Math.max(1, Math.min(...left)) * 1000 + 300);
  for (const [id, html] of [["wifidev", cl], ["hsdev", hs]]) {
    const el = $(id);
    if (!force && a && el.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName)) continue;
    if (el._html !== html) {
      el.innerHTML = html;
      el._html = html;
    }
  }
}
function wifiRerender(focus) {
  renderWifiDev(wifiData, true);
  if (focus) {
    const f = $("wifidev").querySelector(focus);
    if (f) f.focus();
  }
}
async function wifiDo(body, busy) {
  $("wifimsg").textContent = busy;
  try {
    await srtlaCall("POST", "/api/wifi", body);
  } catch (x) {
    $("wifimsg").textContent = x.message;
    return x.message || "Fehler";
  }
  clearTimeout(wifiTimer);
  wifiTimer = setTimeout(wifiLoad, 1200);
  [6000, 14000].forEach((ms) => setTimeout(wifiLoad, ms));
  return "";
}
async function wifiLoad() {
  let d;
  try {
    d = await srtlaCall("GET", "/api/wifi");
  } catch (e) {
    return;
  }
  wifiData = d;
  renderWifiDev(d);
  const sig = d.cards.map((c) => c.iface + ":" + c.ip).join("|");
  if (wifiSig !== null && sig !== wifiSig) srtlaLoad();
  wifiSig = sig;
  const dr = d.driver || {},
    el = $("wifidriver");
  el.textContent = ["working", "waiting", "failed", "unsupported"].includes(dr.state) ? dr.message || "" : "";
  el.style.color = dr.state === "failed" || dr.state === "unsupported" ? "var(--crit)" : "";
  const hsAct = String(d.action || "").startsWith("hotspot_");
  $("wifimsg").textContent = d.helper_installed
    ? hsAct
      ? ""
      : d.message || ""
    : "Der WLAN-Helfer ist auf dieser Box noch nicht installiert (install.sh erneut ausführen).";
  $("hsmsg").textContent = !d.helper_installed ? "" : hsAct ? (d.state === "working" ? "Läuft …" : d.message || "") : hsMsg;
  for (const k of Object.keys(hsSaving)) {
    if (d.state === "done" && d.action === "hotspot_save") {
      hsOpen[k] = false;
      delete hsDraft[k];
      delete hsSaving[k];
      renderWifiDev(d, true);
    } else if (d.state === "error") {
      delete hsSaving[k];
    }
  }
  if (d.state === "working") {
    (hsAct ? $("hsmsg") : $("wifimsg")).textContent = "Läuft …";
    clearTimeout(wifiTimer);
    wifiTimer = setTimeout(wifiLoad, 1500);
  }
}
function wlConnect(iface) {
  const u = wlOf(iface),
    manual = u.mode === "manual",
    ssid = (manual ? u.ssid : u.sel).trim();
  if (!ssid) {
    $("wifimsg").textContent = "Bitte einen Netznamen angeben.";
    return;
  }
  const pw = manual ? u.mpw : u.pw;
  u.mpw = u.pw = u.sel = "";
  wifiRerender();
  wifiDo({ action: "connect", iface, ssid, password: pw, hidden: manual && u.hidden }, "Verbinde …");
}
$("wifidev").addEventListener("click", (e) => {
  const t = e.target.closest && e.target.closest("button, .wrow");
  const card = t && t.closest(".wcard");
  if (!card) return;
  const iface = card.dataset.iface,
    u = wlOf(iface),
    c = t.classList;
  if (c.contains("wl-mode")) {
    u.mode = t.dataset.m;
    wifiRerender();
  } else if (c.contains("wl-scan")) wifiDo({ action: "scan", iface }, "Suche läuft …");
  else if (c.contains("wl-disc")) wifiDo({ action: "disconnect", iface }, "Trenne …");
  else if (c.contains("wl-del")) {
    const ssid = t.dataset.ssid;
    if (confirm(`Netz „${ssid}“ vergessen?\n\nDas gespeicherte Netz und sein Passwort werden von der Box gelöscht. Danach verbindet sich die Box nicht mehr von selbst damit.`)) {
      if (u.sel === ssid) u.sel = "";
      wifiDo({ action: "forget", ssid }, "Wird vergessen …");
    }
  } else if (c.contains("wl-go")) wlConnect(iface);
  else if (c.contains("wl-cancel")) {
    u.sel = u.pw = "";
    wifiRerender();
  } else if (c.contains("wrow")) {
    const same = u.sel === t.dataset.ssid;
    u.sel = same ? "" : t.dataset.ssid;
    u.pw = "";
    wifiRerender(same ? "" : ".wl-pw");
  }
});
$("wifidev").addEventListener("keydown", (e) => {
  const row = e.target.classList && e.target.classList.contains("wrow") ? e.target : null;
  if (row && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    row.click();
  } else if (e.key === "Enter" && e.target.matches && e.target.matches(".wl-pw, .wl-mpw, .wl-ssid")) {
    const card = e.target.closest(".wcard");
    if (card) wlConnect(card.dataset.iface);
  }
});
$("wifidev").addEventListener("input", (e) => {
  const card = e.target.closest && e.target.closest(".wcard");
  if (!card) return;
  const u = wlOf(card.dataset.iface),
    c = e.target.classList;
  if (c.contains("wl-pw")) u.pw = e.target.value;
  else if (c.contains("wl-ssid")) u.ssid = e.target.value;
  else if (c.contains("wl-mpw")) u.mpw = e.target.value;
  else if (c.contains("wl-hidden")) u.hidden = e.target.checked;
});
$("wificard").addEventListener("change", async (e) => {
  const iface = e.target.dataset && e.target.dataset.wup;
  if (e.target.classList.contains("wl-hidden")) {
    const card = e.target.closest(".wcard");
    if (card) wlOf(card.dataset.iface).hidden = e.target.checked;
  }
  if (!iface || !srtlaData) return;
  const st = srtlaData.settings,
    ups = new Set(st.uplinks);
  e.target.checked ? ups.add(iface) : ups.delete(iface);
  try {
    await srtlaCall("POST", "/api/srtla/settings", { uplinks: [...ups] });
    $("wifimsg").textContent =
      (e.target.checked ? "Zum Senden gespeichert" : "Nicht mehr zum Senden") +
      ". Die Änderung wirkt innerhalb weniger Sekunden, ohne Neustart.";
  } catch (x) {
    $("wifimsg").textContent = x.message;
    e.target.checked = !e.target.checked;
  }
  srtlaLoad();
});
wifiLoad();
setInterval(() => {
  if (due("wifi", "netcard", 60000) && !$("wificard").contains(document.activeElement)) wifiLoad();
}, 10000);
