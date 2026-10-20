function alertParts(a) {
  if (a.kind === "usb") {
    const power = a.why === "emi" || a.why === "over";
    const nm = a.name ? ` <b translate="no">${esc(a.name)}</b>` : "";
    const where =
      a.port || a.ids
        ? ` <span class="muted" translate="no">(${esc([a.port ? "USB " + a.port : "", a.ids].filter(Boolean).join(", "))})</span>`
        : "";
    return {
      main:
        `<span>${USB_LABEL[a.cat] || USB_LABEL.other}</span>${nm} · <span>${alertWhen(a.t)}</span>` +
        (a.back ? ` · <span>wieder da</span>` : "") +
        (power ? ` · <span>Bitte Stromversorgung prüfen</span>` : ""),
      info:
        (power
          ? "Der USB-Anschluss wurde abgeschaltet (Störung oder Spannungseinbruch). Netzteil und USB-Hub prüfen, den Adapter möglichst direkt am Board anstecken."
          : "Das USB-Gerät wurde getrennt, abgezogen oder ausgefallen. Kabel und Stromversorgung prüfen.") + where,
    };
  }
  if (a.kind === "cam") {
    const dji = a.cam === "dji";
    return {
      main: `<span>${dji ? "DJI-Kamera ausgefallen" : "Kamera ausgefallen"}</span> <b translate="no">${esc(a.name || "")}</b> · <span>${alertWhen(a.t)}</span>`,
      info: dji
        ? "Bluetooth getrennt, Akku leer oder Kamera ausgeschaltet. Kamera aufwecken und die Verbindung prüfen."
        : "Die Kamera sendet nicht mehr. Akku, WLAN-Verbindung und Kabel prüfen.",
    };
  }
  if (a.kind === "hdmi" && a.src === "usb")
    return {
      main: `<span>USB-Kamera: nicht gefunden</span> · <span>${alertWhen(a.t)}</span>`,
      info: "Kamera anstecken und einschalten: Sie muss sich als USB-Webcam (UVC) melden, bei Action-Kameras im Webcam-Modus.",
    };
  if (a.kind === "hdmi")
    return {
      main: `<span>HDMI: kein Signal</span> · <span>${alertWhen(a.t)}</span>`,
      info: "Kabel prüfen und die Kamera einschalten: Sie muss ein Bild ausgeben.",
    };
  if (a.kind === "dstate" && (a.names || []).length)
    return { main: a.text || "", info: `<span>Wartet im Kernel:</span> <b translate="no">${esc(a.names.join(", "))}</b>` };
  return { main: a.text || "", info: "" };
}
const alertText = (a) => alertParts(a).main;
function alertBox(x) {
  const p = alertParts(x);
  const close =
    x.kind === "usb" || x.kind === "cam" || x.kind === "hdmi"
      ? `<button type="button" class="abtn" data-akind="${x.kind}" data-at="${x.t}" aria-label="Schließen" title="Schließen">×</button>`
      : "";
  return `<div class="alert ${x.level}">${close}<span class="atx">${p.main}</span>${p.info ? `<button type="button"class="ibtn"aria-expanded="false"aria-label="Hilfe anzeigen"title="Hilfe">i</button><div class="hlp">${p.info}</div>` : ""}</div>`;
}
function paintHealth() {
  const un = !!(typeof pipeDirty !== "undefined" && (pipeDirty || pipDelayDirty));
  const note = '<a href="#p_save" class="unsavedlnk">Noch nicht gespeicherte Änderungen in „Bild-in-Bild“ Anpassungen</a>';
  const shown = lastAlerts.filter((x) => !dismissedAlerts.has(x.kind + ":" + x.t));
  const items = shown.map((a) => `<span class="${a.level}">${alertText(a)}</span>`);
  const hl = $("livehealth"),
    phone = getComputedStyle(hl).display === "none";
  const h = (
    un ? [`<span class="crit">${note}</span>`].concat(items) : items.length ? items : ['<span class="ok">● Alles im grünen Bereich</span>']
  ).join(" · ");
  const a = shown.map(alertBox).join("") + (un && phone ? `<div class="alert crit">${note}</div>` : "");
  const sig = h + "|" + a;
  if (sig === healthSig) return;
  healthSig = sig;
  hl.innerHTML = h;
  $("alerts").innerHTML = a;
  $("alerts")
    .querySelectorAll(".ibtn")
    .forEach((b) => {
      b._hlp = [b.nextElementSibling];
    });
}
setInterval(paintHealth, 500);
document.addEventListener("click", async (e) => {
  const b = e.target.closest && e.target.closest("button.abtn");
  if (!b) return;
  const key = b.dataset.akind + ":" + b.dataset.at;
  dismissedAlerts.add(key);
  paintHealth();
  try {
    await srtlaCall("POST", "/api/alerts/dismiss", { kind: b.dataset.akind, t: parseInt(b.dataset.at, 10) });
  } catch (x) {
    dismissedAlerts.delete(key);
    paintHealth();
  }
});
document.addEventListener("click", (e) => {
  const l = e.target.closest && e.target.closest("a.unsavedlnk");
  if (!l) return;
  e.preventDefault();
  const c = $("pipecard");
  c.open = true;
  const b = $("p_save");
  b.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => b.focus({ preventScroll: true }), 400);
});
let connNames = {};
const ifd = (n) => (connNames[n] ? `${n} (${connNames[n]})` : n);
const connRen = (iface) =>
  `<a href="#" class="connren" data-iface="${esc(iface)}" title="Verbindung benennen" aria-label="Verbindung benennen">✎</a>`;
document.addEventListener("click", async (e) => {
  const a = e.target.closest && e.target.closest("a.connren");
  if (!a) return;
  e.preventDefault();
  const n = prompt(`Eigener Name für ${a.dataset.iface} (leer lassen = kein Name):`, connNames[a.dataset.iface] || "");
  if (n === null) return;
  try {
    await srtlaCall("POST", "/api/devname", { key: "net:" + a.dataset.iface, name: n });
  } catch (x) {
    alert(x.message);
    return;
  }
  if (n.trim()) connNames[a.dataset.iface] = n.trim().replace(/\s+/g, " ");
  else delete connNames[a.dataset.iface];
  srtlaLoad();
  tick();
});
function setRates(net) {
  lastNet = net;
  document.querySelectorAll("[data-rate]").forEach((e) => {
    const r = net[e.dataset.rate];
    e.textContent = r ? fmt(r.tx_mbit) : "–";
  });
}
$("b_ups").addEventListener("change", async (e) => {
  const iface = e.target.dataset && e.target.dataset.up;
  if (!iface || !srtlaData) return;
  const st = srtlaData.settings,
    ups = new Set(st.uplinks);
  e.target.checked ? ups.add(iface) : ups.delete(iface);
  $("neterr").textContent = "";
  try {
    await srtlaCall("POST", "/api/srtla/settings", { uplinks: [...ups] });
    $("upinfo").textContent = "Sendewege gespeichert. Die Änderung wirkt innerhalb weniger Sekunden, ohne Neustart.";
  } catch (x) {
    $("neterr").textContent = x.message;
  }
  srtlaLoad();
});
async function srtlaLoad() {
  try {
    srtlaData = await srtlaCall("GET", "/api/srtla");
  } catch (e) {
    return;
  }
  const d = srtlaData,
    sel = $("srv_sel");
  sel.innerHTML = d.servers.length
    ? d.servers
        .map(
          (s) =>
            `<option value="${esc(s.id)}"${s.id === d.selected ? " selected" : ""}>${esc(s.name)} · ${esc(s.host)}:${s.port}${s.has_streamid ? " · Stream-ID gespeichert" : ""}</option>`,
        )
        .join("")
    : '<option value="">Noch kein Server angelegt</option>';
  $("srv_edit").disabled = $("srv_del").disabled = !d.servers.length;
  const st = d.settings;
  if (document.activeElement.id !== "b_min") $("b_min").value = st.min_kbps;
  if (document.activeElement.id !== "b_max") $("b_max").value = st.max_kbps;
  if (document.activeElement.id !== "b_lat") $("b_lat").value = st.latency_ms;
  if (document.activeElement.id !== "b_spread") $("b_spread").value = st.spread || "best";
  connNames = d.conn_names || {};
  $("b_ups").innerHTML =
    (d.interfaces || [])
      .map(
        (o) =>
          `<div class="wstat${o.ip ? " ok" : ""}"><span class="wdot"></span><span class="wgrow"><b>${esc(o.label)}</b>${connNames[o.iface] ? " (" + esc(connNames[o.iface]) + ")" : ""} ${connRen(o.iface)} · ${esc(o.ip)}</span><span class="muted"><b data-rate="${esc(o.iface)}">–</b> Mbit/s ↑</span><label><input type="checkbox" data-up="${esc(o.iface)}"${st.uplinks.includes(o.iface) ? " checked" : ""}> Zum Senden verwenden</label></div>`,
      )
      .join("") +
    (st.uplinks || [])
      .filter((u) => !(d.interfaces || []).some((o) => o.iface === u))
      .map(
        (u) =>
          `<div class="wstat"><span class="wdot"></span><span class="wgrow"><b>${esc(ifd(u))}</b> ${connRen(u)} · gerade nicht verbunden</span><label><input type="checkbox" data-up="${esc(u)}" checked> Zum Senden verwenden</label></div>`,
      )
      .join("");
  if (!$("b_ups").innerHTML) $("b_ups").innerHTML = '<span class="muted">keine Netzwerke gefunden</span>';
  if (lastNet) setRates(lastNet);
  const cur = d.servers.find((s) => s.id === d.selected);
  if (wifiData) wifiLoad();
  $("srtlainfo").textContent = cur
    ? `Gewählter Server: ${cur.name} (${cur.host}:${cur.port}). `
    : "Legen Sie einen Server an, um ihn später zum Senden zu wählen.";
}
function srtlaFormReset() {
  srtlaEdit = null;
  $("srvform").reset();
  $("srv_save").textContent = "Server hinzufügen";
  $("srv_cancel").hidden = true;
  $("s_sid").placeholder = "Stream-ID (optional)";
}
$("srv_sel").addEventListener("change", async (e) => {
  if (!e.target.value) return;
  try {
    await srtlaCall("POST", "/api/srtla/select", { id: e.target.value });
    $("srtlaerr").textContent = "";
  } catch (x) {
    $("srtlaerr").textContent = x.message;
  }
  srtlaLoad();
  askRestart();
});
$("srv_edit").addEventListener("click", () => {
  const s = srtlaData && srtlaData.servers.find((x) => x.id === $("srv_sel").value);
  if (!s) return;
  srtlaEdit = s.id;
  $("s_name").value = s.name;
  $("s_host").value = s.host;
  $("s_port").value = s.port;
  $("s_sid").value = "";
  $("s_sid").placeholder = s.has_streamid ? "Stream-ID (leer lassen = behalten)" : "Stream-ID (optional)";
  $("srv_save").textContent = "Änderungen speichern";
  $("srv_cancel").hidden = false;
  $("s_name").focus();
});
$("srv_cancel").addEventListener("click", srtlaFormReset);
$("srv_del").addEventListener("click", async () => {
  const id = $("srv_sel").value;
  if (!id || !confirm("Diesen Server löschen?")) return;
  try {
    await srtlaCall("DELETE", "/api/srtla/" + id);
    $("srtlaerr").textContent = "";
  } catch (x) {
    $("srtlaerr").textContent = x.message;
  }
  srtlaFormReset();
  srtlaLoad();
  askRestart();
});
$("srvform").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("srtlaerr").textContent = "";
  const body = { name: $("s_name").value, host: $("s_host").value, port: +$("s_port").value, streamid: $("s_sid").value };
  try {
    if (srtlaEdit) await srtlaCall("POST", "/api/srtla/" + srtlaEdit, body);
    else await srtlaCall("POST", "/api/srtla", body);
    srtlaFormReset();
  } catch (x) {
    $("srtlaerr").textContent = x.message;
  }
  srtlaLoad();
  askRestart();
});
async function saveSrtlaSettings(note) {
  $("srtlaerr").textContent = "";
  const ups = [...document.querySelectorAll("#b_ups [data-up]")].filter((c) => c.checked).map((c) => c.dataset.up);
  try {
    await srtlaCall("POST", "/api/srtla/settings", {
      min_kbps: +$("b_min").value,
      max_kbps: +$("b_max").value,
      latency_ms: +$("b_lat").value,
      uplinks: ups,
      spread: $("b_spread").value,
    });
    await srtlaLoad();
    $("srtlainfo").textContent =
      note ||
      (sendData && sendData.active
        ? "Gespeichert. Gilt erst nach einem Neustart der Sendung (Knopf oben bei Live)."
        : "Einstellungen gespeichert. Gilt ab dem nächsten Start der Sendekette.");
    askRestart();
  } catch (x) {
    $("srtlaerr").textContent = x.message;
  }
}
$("b_save").addEventListener("click", () => saveSrtlaSettings());
$("b_save_spread").addEventListener("click", () => saveSrtlaSettings());
srtlaLoad();
function devDet(c) {
  const det = [c.usb_id].filter(Boolean).join(", ");
  return det ? ` <span class="muted">(${esc(det)})</span>` : "";
}
const dnLink = (c) =>
  c.key
    ? ` <a href="#" class="dn muted" data-dn="${esc(c.key)}" data-dnname="${esc(c.custom ? c.label || "" : "")}" data-dnlabel="${esc(c.label || c.name || "")}" title="Eigenen Namen für dieses Gerät vergeben (leer = Standardname)">umbenennen</a>`
    : "";
function devInfo(c) {
  const label = c.label || c.name;
  if (label) return ` · ${esc(label)}${devDet(c)}${dnLink(c)}`;
  if (c.usb_id) return ` · <span class="muted">USB ${esc(c.usb_id)}</span>${dnLink(c)}`;
  return (c.driver ? ` · <span class="muted">Treiber ${esc(c.driver)}</span>` : "") + dnLink(c);
}
async function devRename(a) {
  const cur = a.dataset.dnname || a.dataset.dnlabel || "";
  const n = prompt("Name dieses Geräts (leer lassen = Standardname):", cur);
  if (n === null) return;
  try {
    await srtlaCall("POST", "/api/devname", { key: a.dataset.dn, name: n });
  } catch (x) {
    alert(x.message);
    return;
  }
  wifiLoad();
  djiLoad();
}
document.addEventListener("click", (e) => {
  const a = e.target.closest && e.target.closest("a.dn");
  if (a) {
    e.preventDefault();
    devRename(a);
  }
});
let wifiData = null,
  wifiTimer = null,
  wifiSig = null;
const HS_CH = { bg: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], a: [0, 36, 40, 44, 48] };
const hsOn0 = (c) => !!(c.hotspot && c.hotspot.running);
let hsOpen = {},
  hsDraft = {},
  hsPwText = {},
  hsSaving = {},
  hsMsg = "";
