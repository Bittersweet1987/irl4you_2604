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
function hsDefaults(c) {
  const h = c.hotspot;
  return { ssid: h ? h.ssid : "IRL4YOU-BOX", pw: "", band: h && h.band === "a" ? "a" : "bg", ch: h ? h.channel || 0 : 0 };
}
function hsPanel(c, busy) {
  const dr = hsDraft[c.iface] || (hsDraft[c.iface] = hsDefaults(c)),
    chs = HS_CH[dr.band] || HS_CH.bg,
    off = busy ? " disabled" : "";
  return `<div class="hspanel" data-iface="${esc(c.iface)}"><div class="wform">
    <label class="muted">Name des Hotspots<input class="hs-ssid" maxlength="32" autocomplete="off" value="${esc(dr.ssid)}"></label>
    <label class="muted">Passwort (8 bis 63 Zeichen)<input class="hs-pw-in" maxlength="63" autocomplete="off" value="${esc(dr.pw)}" placeholder="${c.hotspot ? "leer = gespeichertes Passwort" : ""}"></label>
    <label class="muted">Band<select class="hs-band"><option value="bg"${dr.band === "bg" ? " selected" : ""}>2,4 GHz (reicht weiter)</option><option value="a"${dr.band === "a" ? " selected" : ""}${c.band5 === false ? " disabled" : ""}>5 GHz (schneller, weniger Störungen)</option></select></label>
    <label class="muted">Kanal<select class="hs-ch">${chs.map((n) => `<option value="${n}"${+dr.ch === n ? " selected" : ""}>${n ? `Kanal ${n}` : "automatisch"}</option>`).join("")}</select></label>
  </div><div class="actions"><button type="button" class="hs-save"${off}>Speichern</button> <button type="button" class="sec hs-gen">Passwort erzeugen</button> <button type="button" class="sec hs-close">Schließen</button></div></div>`;
}
function hsControls(c, busy) {
  if (c.ap === false) return "";
  const on = hsOn0(c),
    pw = hsPwText[c.iface],
    off = busy ? " disabled" : "";
  const label = `<span class="muted" title="Macht aus dem Stick ein eigenes WLAN der Box, zum Beispiel für DJI-Kameras oder ein Handy. Der Stick ist dann nicht mehr mit einem anderen WLAN verbunden.">Hotspot-Modus</span>`;
  const show = `<button type="button" class="sec hs-show">${pw ? "Passwort ausblenden" : "Passwort anzeigen"}</button>`;
  const pwRow = pw ? `<div class="hsrow"><div class="pwshow" title="Klicken kopiert das Passwort">${esc(pw)}</div></div>` : "";
  if (c.camera_net) return on ? `<div class="hsrow">${label} <b>An</b> ${show}</div>${pwRow}` : "";
  return (
    `<div class="hsrow">${label}<button type="button" class="hs-toggle hsw${on ? " on" : " sec"}" role="switch" aria-checked="${on}" title="${on ? "Hotspot ausschalten" : "Hotspot einschalten"}"${off}>${on ? "An" : "Aus"}</button>` +
    (on
      ? show
      : `<button type="button" class="sec hs-edit"${hsOpen[c.iface] ? " disabled" : ""}${off}>Einstellen</button>` +
        (c.hotspot
          ? ` <button type="button" class="sec hs-del" title="Entfernt den Hotspot dieser Karte ganz (Einstellungen und Profil), zum Beispiel um ihn auf einer anderen Karte einzurichten"${off}>Löschen</button>`
          : "")) +
    `</div>` +
    (on ? pwRow : hsOpen[c.iface] ? hsPanel(c, busy) : "")
  );
}
function renderWifiDev(d, force) {
  const ups = ((srtlaData && srtlaData.settings) || {}).uplinks || [],
    busy = !d.helper_installed || d.state === "working";
  const html = d.cards.length
    ? d.cards.map((c) => `<div class="wcard" data-iface="${esc(c.iface)}">${devRow(c, ups)}${hsControls(c, busy)}</div>`).join("")
    : '<div class="ph">Keine WLAN-Karte gefunden.</div>';
  const el = $("wifidev"),
    a = document.activeElement;
  if (!force && a && el.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName)) return;
  if (el._html !== html) {
    el.innerHTML = html;
    el._html = html;
  }
}
function hsCard(iface) {
  return ((wifiData && wifiData.cards) || []).find((x) => x.iface === iface);
}
function setHsMsg(t) {
  hsMsg = t;
  $("hsmsg").textContent = t;
}
async function hsPost(body, wait) {
  setHsMsg(wait);
  try {
    await srtlaCall("POST", "/api/wifi", body);
  } catch (x) {
    setHsMsg(x.message);
    return false;
  }
  clearTimeout(wifiTimer);
  wifiTimer = setTimeout(wifiLoad, 1500);
  [6000, 14000].forEach((ms) => setTimeout(wifiLoad, ms));
  return true;
}
async function hsToggle(iface) {
  const c = hsCard(iface);
  if (!c) return;
  if (hsOn0(c)) {
    delete hsPwText[iface];
    await hsPost({ action: "hotspot_stop", iface }, "Hotspot wird beendet …");
    return;
  }
  if (!c.hotspot) {
    hsOpen[iface] = true;
    setHsMsg("Bitte zuerst „Einstellen“: Name und Passwort festlegen, dann einschalten.");
    renderWifiDev(wifiData, true);
    return;
  }
  const body = { action: "hotspot_start", iface };
  if (c.ip) {
    if (
      !confirm(
        (c.ssid
          ? `Die WLAN-Karte ${c.iface} ist gerade mit „${c.ssid}“ verbunden.`
          : `Die WLAN-Karte ${c.iface} ist gerade mit einem WLAN verbunden.`) +
          " Der Hotspot beendet diese Verbindung." +
          "\n\nHast du die Oberfläche über dieses WLAN geöffnet, bricht sie ab. Du erreichst sie danach über den Hotspot (Adresse meist 10.42.0.1) oder über ein anderes Netz.\n\nHotspot einschalten?",
      )
    )
      return;
    body.confirm = true;
  }
  await hsPost(body, "Hotspot wird gestartet …");
}
async function hsSave(iface) {
  const dr = hsDraft[iface];
  if (!dr) return;
  if (
    await hsPost(
      {
        action: "hotspot_save",
        iface,
        ssid: (dr.ssid || "").trim(),
        password: dr.pw || "",
        band: dr.band,
        channel: parseInt(dr.ch, 10) || 0,
      },
      "Speichere die Einstellungen …",
    )
  )
    hsSaving[iface] = true;
}
async function hsShow(iface) {
  if (hsPwText[iface]) {
    delete hsPwText[iface];
    renderWifiDev(wifiData, true);
    return;
  }
  try {
    const r = await srtlaCall("GET", "/api/wifi/hotspot?iface=" + encodeURIComponent(iface));
    hsPwText[iface] = r.password;
    setHsMsg("");
  } catch (x) {
    setHsMsg(x.message);
  }
  renderWifiDev(wifiData, true);
}
$("wifidev").addEventListener("click", (e) => {
  const t = e.target.closest && e.target.closest("button");
  if (!t) return;
  const card = t.closest(".wcard");
  if (!card) return;
  const iface = card.dataset.iface;
  if (t.classList.contains("hs-toggle")) hsToggle(iface);
  else if (t.classList.contains("hs-edit")) {
    hsOpen[iface] = true;
    hsDraft[iface] = hsDefaults(hsCard(iface) || {});
    setHsMsg("");
    renderWifiDev(wifiData, true);
  } else if (t.classList.contains("hs-close")) {
    hsOpen[iface] = false;
    delete hsDraft[iface];
    renderWifiDev(wifiData, true);
  } else if (t.classList.contains("hs-del")) {
    if (
      confirm(
        `Hotspot auf ${iface} löschen?\n\nName, Passwort und Einstellungen dieser Karte werden entfernt. Kameras, die damit verbunden waren, finden ihn dann nicht mehr.`,
      )
    ) {
      delete hsPwText[iface];
      hsPost({ action: "hotspot_delete", iface }, "Hotspot wird gelöscht …");
    }
  } else if (t.classList.contains("hs-save")) hsSave(iface);
  else if (t.classList.contains("hs-show")) hsShow(iface);
  else if (t.classList.contains("hs-gen")) {
    const al = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789",
      a = new Uint32Array(12);
    crypto.getRandomValues(a);
    const dr = hsDraft[iface] || (hsDraft[iface] = hsDefaults(hsCard(iface) || {}));
    dr.pw = [...a].map((n) => al[n % al.length]).join("");
    const inp = card.querySelector(".hs-pw-in");
    if (inp) inp.value = dr.pw;
    setHsMsg("Neues Passwort eingetragen. Mit „Speichern“ wird es übernommen; bitte notieren.");
  }
});
$("wifidev").addEventListener("input", (e) => {
  const card = e.target.closest && e.target.closest(".wcard");
  const dr = card && hsDraft[card.dataset.iface];
  if (!dr) return;
  const c = e.target.classList;
  if (c.contains("hs-ssid")) dr.ssid = e.target.value;
  else if (c.contains("hs-pw-in")) dr.pw = e.target.value;
  else if (c.contains("hs-band")) {
    dr.band = e.target.value;
    const sel = card.querySelector(".hs-ch"),
      chs = HS_CH[dr.band] || HS_CH.bg;
    if (!chs.includes(+dr.ch)) dr.ch = 0;
    sel.innerHTML = chs
      .map((n) => `<option value="${n}"${+dr.ch === n ? " selected" : ""}>${n ? `Kanal ${n}` : "automatisch"}</option>`)
      .join("");
  } else if (c.contains("hs-ch")) dr.ch = parseInt(e.target.value, 10) || 0;
});
function wifiDebug(d) {
  const dbg = (d.scan && d.scan.debug) || [];
  if (!dbg.length || d.state === "working") return "";
  return `<details class="sens" open><summary class="muted">Technische Angaben zur Karte ${esc(d.scan.iface || "")} (die Suche hat nichts gefunden)</summary><pre>${esc(dbg.join("\n"))}</pre></details>`;
}
function wifiPwHint() {
  const saved = ((wifiData && wifiData.saved) || []).includes($("w_ssid").value);
  $("w_pw").placeholder = saved ? "leer = gespeichertes Passwort verwenden" : "leer bei offenem Netz";
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
$("w_scan").addEventListener("click", () => wifiDo({ action: "scan", iface: $("w_if").value }, "Suche läuft …"));
$("w_connect").addEventListener("click", async () => {
  const body = {
    action: "connect",
    iface: $("w_if").value,
    ssid: $("w_ssid").value,
    password: $("w_pw").value,
    hidden: $("w_hidden").checked,
  };
  await wifiDo(body, "Verbinde …");
  $("w_pw").value = "";
});
$("w_disc").addEventListener("click", () => wifiDo({ action: "disconnect", iface: $("w_if").value }, "Trenne …"));
$("w_ssid").addEventListener("input", wifiPwHint);
$("wificard").addEventListener("change", async (e) => {
  const iface = e.target.dataset && e.target.dataset.wup;
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
$("wificard").addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (!a) return;
  e.preventDefault();
  if (a.dataset.ssid !== undefined) {
    $("w_ssid").value = a.dataset.ssid;
    wifiPwHint();
  }
  if (a.dataset.forget !== undefined) wifiDo({ action: "forget", ssid: a.dataset.forget }, "Wird vergessen …");
});
wifiLoad();
setInterval(() => {
  if (due("wifi", "netcard", 60000) && !["w_if", "w_ssid", "w_pw"].includes(document.activeElement.id)) wifiLoad();
}, 10000);
const FREE_ID = "5";
let posFree = { 1: { x: 500, y: 500 }, 2: { x: 500, y: 500 }, 3: { x: 500, y: 500 } };
const STYLE_DEF = () => ({
  visible: true,
  opacity: 100,
  crop: { l: 0, r: 0, t: 0, b: 0 },
  radius: 0,
  border: { enabled: false, width: 6, color: "#ffffff", opacity: 100 },
});
const CROP_W = 1920,
  CROP_H = 1080,
  CROP_KEEP = 32;
let pipStyles = { 1: STYLE_DEF(), 2: STYLE_DEF(), 3: STYLE_DEF() };
const styleOf = (k) => pipStyles[k] || (pipStyles[k] = STYLE_DEF());
const clampN = (v, lo, hi, d) => {
  v = Math.round(+v);
  return isNaN(v) ? d : Math.max(lo, Math.min(hi, v));
};
const hexRgba = (h, a) => {
  const n = parseInt(String(h).slice(1), 16) || 0;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
function styleBlockHtml() {
  const num = (f, l, min, max, step) =>
    `<label class="muted">${l}<input type="number" data-f="${f}" min="${min}" max="${max}" step="${step || 1}"></label>`;
  return `<summary>Aussehen <span class="pvs-sum"></span></summary>
    <label class="muted" style="display:block;margin-top:6px"><input type="checkbox" data-f="vis"> Bild einblenden</label>
    <div class="sech">Ecken</div>
    <div class="pvs-grid">${num("rd", "Eckenrundung (Pixel)", 0, 60)}</div>
    <div class="sech">Beschneiden</div>
    <div class="pvs-info muted">Pixel, die links, rechts, oben und unten abgeschnitten werden, wie bei einem Bild von 1920 × 1080.</div>
    <div class="pvs-grid">${num("cl", "Links", 0, 1888, 2)}${num("cr", "Rechts", 0, 1888, 2)}${num("ct", "Oben", 0, 1048, 2)}${num("cb", "Unten", 0, 1048, 2)}</div>
    <div class="pvs-info muted" data-o="cropinfo"></div>
    <div class="sech">Rahmen</div>
    <label class="muted"><input type="checkbox" data-f="be"> Rahmen um dieses Bild</label>
    <div class="pvs-grid" data-o="bopts">${num("bw", "Dicke (Pixel)", 1, 40)}<label class="muted">Farbe<input type="color" data-f="bc"></label>${num("bo", "Deckkraft (%)", 10, 100)}</div>`;
}
function styleFill(k, force) {
  const st = styleOf(k),
    box = document.querySelector(`.pvs[data-k="${k}"]`);
  if (!box) return;
  const put = (f, v) => {
    const e = box.querySelector(`[data-f="${f}"]`);
    if (!e || (!force && document.activeElement === e)) return;
    if (e.type === "checkbox") e.checked = !!v;
    else e.value = v;
  };
  put("vis", st.visible);
  put("rd", st.radius);
  put("cl", st.crop.l);
  put("cr", st.crop.r);
  put("ct", st.crop.t);
  put("cb", st.crop.b);
  put("be", st.border.enabled);
  put("bw", st.border.width);
  put("bc", st.border.color);
  put("bo", st.border.opacity);
  const c = st.crop,
    cropped = c.l || c.r || c.t || c.b;
  box.querySelector('[data-o="cropinfo"]').textContent = cropped
    ? `Bild nach dem Beschneiden: ${CROP_W - c.l - c.r} × ${CROP_H - c.t - c.b} Pixel. Der Maßstab bleibt, es wird nur abgeschnitten.`
    : "Nicht beschnitten.";
  box.querySelector('[data-o="bopts"]').style.opacity = st.border.enabled ? 1 : 0.5;
  box.querySelectorAll('[data-o="bopts"] input').forEach((e) => (e.disabled = !st.border.enabled));
  const parts = [
    st.visible ? "" : "ausgeblendet",
    cropped ? "beschnitten" : "",
    st.radius ? `Ecken ${st.radius} px` : "",
    st.border.enabled ? `Rahmen ${st.border.width} px` : "",
  ].filter(Boolean);
  box.querySelector(".pvs-sum").textContent = parts.length ? "· " + parts.join(", ") : "· Standard";
}
document.querySelectorAll(".pvs").forEach((box) => {
  const k = +box.dataset.k;
  box.innerHTML = styleBlockHtml();
  const edit = (ev) => {
    const el = ev.target,
      f = el.dataset && el.dataset.f;
    if (!f) return;
    const st = styleOf(k);
    if (f === "vis") st.visible = el.checked;
    else if (f === "rd") st.radius = clampN(el.value, 0, 60, 0);
    else if (f.length === 2 && f[0] === "c") {
      const key = f[1],
        opp = { l: "r", r: "l", t: "b", b: "t" }[key],
        total = key === "l" || key === "r" ? CROP_W : CROP_H;
      st.crop[key] = Math.floor(clampN(el.value, 0, total - CROP_KEEP, 0) / 2) * 2;
      st.crop[key] = Math.max(0, Math.min(st.crop[key], total - CROP_KEEP - st.crop[opp]));
    } else if (f === "be") st.border.enabled = el.checked;
    else if (f === "bw") st.border.width = clampN(el.value, 1, 40, 6);
    else if (f === "bc") st.border.color = /^#[0-9a-fA-F]{6}$/.test(el.value) ? el.value.toLowerCase() : "#ffffff";
    else if (f === "bo") st.border.opacity = clampN(el.value, 10, 100, 100);
    styleFill(k, ev.type === "change");
    renderPreview();
  };
  box.addEventListener("input", edit);
  box.addEventListener("change", edit);
  styleFill(k, true);
});
let pipeData = null,
  pipeDirty = false,
  pipDelayDirty = false,
  pipLive = {},
  pipCams = [],
  pipCorners = [];
let pipPrevMain = "";
const DL = [
  ["p_delay", "n_delay", "v_delay", "main_delay_ms"],
  ["p_delay1", "n_delay1", "v_delay1", "pip_delay_ms"],
  ["p_delay2", "n_delay2", "v_delay2", "pip2_delay_ms"],
  ["p_delay3", "n_delay3", "v_delay3", "pip3_delay_ms"],
];
