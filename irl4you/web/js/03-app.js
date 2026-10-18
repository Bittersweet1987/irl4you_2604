$("cams").addEventListener("change", async (e) => {
  if (!e.target.classList.contains("camnetsel")) return;
  if (e.target.dataset.dji) {
    const addr = djiAddrOfKey(e.target.dataset.dji);
    if (!addr || !e.target.value) {
      if (!addr) alert("Die Kamera ist im Kamera-Dienst nicht bekannt.");
      return;
    }
    netChg[e.target.dataset.dji] = { iface: e.target.value, reconn: false, busy: false, okAt: 0 };
    paintNetNotes();
    djiUpdate(addr, { wifi_ifname: e.target.value });
    setTimeout(() => {
      tick();
      djiLoad();
    }, 900);
    return;
  }
  const r = await fetch("/api/cameras/" + e.target.dataset.id, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ iface: e.target.value }),
  });
  if (!r.ok) alert((await r.json().catch(() => ({}))).error || "Verbindung konnte nicht gesetzt werden");
  tick();
});
$("cams").addEventListener("click", async (e) => {
  if (e.target.classList.contains("camreconn")) {
    const addr = djiAddrOfKey(e.target.dataset.dji);
    if (!addr) {
      alert("Die Kamera ist im Kamera-Dienst nicht bekannt.");
      return;
    }
    const key = e.target.dataset.dji,
      dc = ((typeof djiData !== "undefined" && djiData.cameras) || []).find((x) => x.rtmp_key === key);
    netChg[key] = Object.assign(netChg[key] || { iface: dc ? dc.wifi_ifname : "", busy: false, okAt: 0 }, {
      reconn: true,
      busy: false,
      okAt: 0,
    });
    if (dc && !netChg[key].iface) netChg[key].iface = dc.wifi_ifname;
    e.target.blur();
    await djiCmd({ cmd: "reconnect", addr });
    paintNetNotes();
    setTimeout(() => {
      tick();
      djiLoad();
    }, 900);
    return;
  }
  if (!e.target.classList.contains("ren")) return;
  e.preventDefault();
  await renameCam(e.target.dataset.id, e.target.dataset.name);
});
async function renameCam(id, old) {
  const n = prompt("Neuer Name der Kamera (z. B. Rucksack, Brust, Helm):", old);
  if (!n || n.trim() === old) return;
  const r = await fetch("/api/cameras/" + id, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: n }),
  });
  if (!r.ok) alert((await r.json().catch(() => ({}))).error || "Umbenennen fehlgeschlagen");
  tick();
}
$("addcam").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("formerr").textContent = "";
  const r = await fetch("/api/cameras", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: $("f_name").value, key: $("f_key").value }),
  });
  if (!r.ok) {
    $("formerr").textContent = (await r.json()).error;
    return;
  }
  $("f_name").value = "";
  $("f_key").value = "";
  tick();
});
$("logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  location.reload();
});
const LOC = () => (window.PB_I18N ? PB_I18N.locale() : "de-DE");
const fmtT = (t) => (t ? new Date(t * 1000).toLocaleString(LOC()) : "nie");
function progSet(id, show, pct, text, since) {
  const b = $(id);
  if (!b) return;
  b.hidden = !show;
  if (!show) {
    b.dataset.since = "";
    return;
  }
  if (!b.dataset.since || since) b.dataset.since = String(since || b.dataset.since || Date.now());
  b.querySelector(".bar>i").style.width = Math.max(4, Math.min(100, pct || 0)) + "%";
  b.querySelector(".progpct").textContent = pct > 0 ? pct + " %" : "";
  b.querySelector(".progtxt").textContent = text || "";
  progTick();
}
function progTick() {
  document.querySelectorAll(".prog:not([hidden])").forEach((b) => {
    const s = +b.dataset.since;
    if (!s) return;
    const sec = Math.max(0, Math.floor((Date.now() - s) / 1000)),
      el = b.querySelector(".progel");
    el.textContent = "⏱ " + Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
  });
}
setInterval(progTick, 1000);
const DJI_STATE = {
  idle: ["Getrennt", 0],
  searching: ["Sucht", 1],
  connecting: ["Verbindet", 2],
  pairing: ["Koppelt", 3],
  preparing: ["Bereitet vor", 4],
  wifi: ["WLAN wird übergeben", 5],
  configuring: ["Stellt ein", 6],
  starting: ["Stream startet", 6],
  streaming: ["Streamt", 0],
  status: ["Nur Akku", 0],
  stopping: ["Beendet", 0],
  error: ["Fehler", 0],
};
const DJI_BUSY = ["searching", "connecting", "pairing", "preparing", "wifi", "configuring", "starting", "stopping"];
const DJI_STAB = [
  ["off", "Aus"],
  ["rocksteady", "RockSteady"],
  ["rocksteadyplus", "RockSteady+"],
  ["horizonbalancing", "HorizonBalancing"],
  ["horizonsteady", "HorizonSteady"],
];
let djiData = { available: false, cameras: [], wifi_options: [], scan: [] },
  djiStruct = "",
  djiRecv = Date.now(),
  djiOpen = {},
  djiPend = {};
try {
  djiOpen = JSON.parse(localStorage.getItem("pbDjiOpen") || "{}") || {};
} catch (e) {
  djiOpen = {};
}
const djiName = (c) => (camsByKey[c.rtmp_key] || {}).name || c.name;
const djiIsOther = (c) => (djiData.wifi_options || []).some((o) => o.ifname === c.wifi_ifname && (o.type === "other" || o.secret_missing));
const djiNeedsNet = (c) => c.wifi_ifname === "manual" || djiIsOther(c);
function djiCardHtml(c) {
  const opts = djiData.wifi_options || [],
    known = opts.some((o) => o.ifname === c.wifi_ifname);
  const netOpts = opts
    .map((o) => {
      const lb =
        o.type === "other"
          ? `${o.ifname} · ${o.ip}`
          : o.type === "hotspot"
            ? `${o.ssid} (WLAN-Hotspot an ${o.ifname}, ${o.ip})`
            : `${o.ssid} (WLAN-Netz an ${o.ifname}, ${o.ip})`;
      return `<option value="${esc(o.ifname)}"${c.wifi_ifname === o.ifname ? " selected" : ""}>${esc(lb)}</option>`;
    })
    .join("");
  const missing =
    c.wifi_ifname && c.wifi_ifname !== "manual" && !known
      ? `<option value="${esc(c.wifi_ifname)}" selected>${esc(c.wifi_ifname)} (nicht verbunden)</option>`
      : "";
  const res = ["480p", "720p", "1080p"].map((r) => `<option${c.resolution === r ? " selected" : ""}>${r}</option>`).join("");
  const stab = DJI_STAB.map((x) => `<option value="${x[0]}"${c.stabilization === x[0] ? " selected" : ""}>${x[1]}</option>`).join("");
  const saved = (c.saved || []).map((n) => `<option value="${esc(n)}"${n === c.ssid ? " selected" : ""}>${esc(n)}</option>`).join("");
  const st = djiOpen[c.addr] || {},
    op = (k) => (st[k] ? " open" : "");
  const other = djiIsOther(c);
  return `<details class="dcam" data-addr="${esc(c.addr)}" data-sec="cam"${op("cam")}>
  <summary><span class="dname"></span><span class="dright"><span class="dstate"></span> <span class="dbatt muted"></span></span></summary>
  <div class="dbody">
    <div class="dsub muted">${esc(c.model || "")} <span class="ddetail"></span></div>
    <div class="actions"><button type="button" class="d-connect">Verbinden</button><button type="button" class="sec d-reconnect">Neu verbinden</button><button type="button" class="sec d-disconnect">Trennen</button></div>
    <div class="actions" style="justify-content:space-between;align-items:center"><label class="chk" style="margin:0"><input type="checkbox" class="d-auto"${c.autoconnect ? " checked" : ""}> Automatisch verbinden und streamen</label><button type="button" class="del d-remove">Entfernen</button></div>
    <label class="chk"><input type="checkbox" class="d-statusonly"${c.status_only ? " checked" : ""}> Nur Akkustand lesen (Kamera sendet per HDMI)</label>
    <label class="f">Name<input class="d-name" maxlength="40" value="${esc(djiName(c))}"></label>
    <details class="dsec" data-sec="conn"${op("conn")}><summary>Verbindung <span class="muted dsum-conn"></span></summary>
      <label class="f">Verbindung der Kamera<select class="d-wifi"><option value="">– wählen –</option>${netOpts}${missing}<option value="manual"${c.wifi_ifname === "manual" ? " selected" : ""}>Manuell (WLAN-Name, Passwort, Adresse)</option></select></label>
      <div class="ph d-lockhint" style="margin-top:4px" hidden>Die Kamera ist verbunden. Änderungen an der Verbindung gelten ab der nächsten Verbindung, die laufende bleibt bestehen. <button type="button" class="sec d-reconnect" style="margin-left:6px;padding:3px 10px">Jetzt neu verbinden</button></div>
      <div class="ph" style="margin-top:4px">Ein WLAN-Hotspot oder -Netz der Box: Die Kamera bekommt Name und Passwort selbst. Jede andere Verbindung (Ethernet, USB-Router, Modem): Hier den WLAN-Namen und das Passwort eintragen, dem die Kamera beitreten soll. Die Adresse der Box kommt aus der gewählten Verbindung.</div>
      <div class="d-manual dnet"${djiNeedsNet(c) ? "" : " hidden"}>
        <div class="f d-savedrow"${(c.saved || []).length ? "" : " hidden"}><span class="flh"><span>Gespeicherte Netze</span><button type="button" class="flb crit d-saveddel">Löschen</button></span><select class="d-saved"><option value="">– gespeicherte Netze –</option>${saved}</select></div>
        <div class="f d-nearrow"><span class="flh"><span>Netze in der Nähe</span><button type="button" class="flb d-nearscan">Netze suchen</button></span><select class="d-nearby"><option value="">– Netz wählen –</option></select><div class="d-nearmsg" role="status"></div></div>
        <label class="f">WLAN-Name der Kamera<input class="d-ssid" maxlength="32" autocomplete="off" value="${esc(c.ssid || "")}"></label>
        <label class="f">WLAN-Passwort<input class="d-pw" type="password" maxlength="63" autocomplete="new-password" placeholder=""></label>
        <label class="f d-iprow"${other ? " hidden" : ""}>Adresse der Box in diesem Netz<input class="d-ip" maxlength="45" value="${esc(c.ip || "")}"></label>
      </div>
    </details>
    <details class="dsec" data-sec="video"${op("video")}><summary>Bild und Stream <span class="muted dsum-video"></span></summary>
      <div class="dgrid"><label class="f">Auflösung<select class="d-res">${res}</select></label>
        <label class="f">Bildrate<select class="d-fps"><option value="25"${c.fps === 25 ? " selected" : ""}>25 fps</option><option value="30"${c.fps !== 25 ? " selected" : ""}>30 fps</option></select></label>
        <label class="f">Bitrate (Mbit/s)<input class="d-br" type="number" min="0.5" max="16" step="0.5" value="${(c.bitrate || 6000) / 1000}"></label>
        <label class="f">Stabilisierung<select class="d-stab">${stab}</select></label></div>
      <div class="ph">Die Kamera sendet auf den Schlüssel <code>${esc(c.rtmp_key || "")}</code>. Bildrate: 25 oder 30 (60 gibt es beim DJI-Livestream nicht).</div>
    </details>
  </div></details>`;
}
let nearAuto = 0;
function nearNets() {
  const seen = new Set(),
    out = [];
  for (const n of ((typeof wifiData !== "undefined" && wifiData && wifiData.scan && wifiData.scan.nets) || [])
    .slice()
    .sort((a, b) => (b.signal || 0) - (a.signal || 0)))
    if (n.ssid && !seen.has(n.ssid)) {
      seen.add(n.ssid);
      out.push(n);
    }
  return out;
}
function nearAutoScan() {
  if (nearAuto && Date.now() - nearAuto > 300000) nearAuto = 0;
  if (
    typeof wifiData === "undefined" ||
    !wifiData ||
    !$("w_if").value ||
    nearNets().length ||
    nearAuto ||
    (typeof sendData !== "undefined" && sendData && sendData.active) ||
    !(djiData.cameras || []).some(djiNeedsNet)
  )
    return;
  nearAuto = Date.now();
  srtlaCall("POST", "/api/wifi", { action: "scan", iface: $("w_if").value })
    .then(() => [3000, 8000].forEach((ms) => setTimeout(wifiLoad, ms)))
    .catch(() => {});
}
function djiNearby(card) {
  const man = card.querySelector(".d-manual"),
    sel = card.querySelector(".d-nearby");
  if (!man || !sel || man.hidden || man.offsetParent === null) return;
  const nets = nearNets();
  const sig = JSON.stringify(nets.map((n) => [n.ssid, Math.round((n.signal || 0) / 10), n.security]));
  if (sel.dataset.sig === sig || document.activeElement === sel) return;
  sel.dataset.sig = sig;
  sel.innerHTML =
    '<option value="">' +
    (nets.length ? "– Netz wählen –" : "– keine Netze gefunden –") +
    "</option>" +
    nets
      .map(
        (n) => `<option value="${esc(n.ssid)}">${esc(n.ssid)} · ${n.security && n.security !== "offen" ? "🔒 " : ""}${n.signal} %</option>`,
      )
      .join("");
}
