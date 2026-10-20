$("djicams").addEventListener(
  "toggle",
  (e) => {
    const d = e.target,
      card = d.closest && d.closest(".dcam");
    if (!card || !d.dataset || !d.dataset.sec) return;
    (djiOpen[card.dataset.addr] = djiOpen[card.dataset.addr] || {})[d.dataset.sec] = d.open;
    try {
      localStorage.setItem("pbDjiOpen", JSON.stringify(djiOpen));
    } catch (x) {}
  },
  true,
);
const djiAddr = (e) => {
  const c = e.target.closest && e.target.closest(".dcam");
  return c ? c.dataset.addr : null;
};
$("djicams").addEventListener("change", (e) => {
  const addr = djiAddr(e);
  if (!addr) return;
  const t = e.target,
    card = t.closest(".dcam"),
    cl = t.classList;
  if (cl.contains("d-wifi")) {
    const other = (djiData.wifi_options || []).some((o) => o.ifname === t.value && (o.type === "other" || o.secret_missing));
    card.querySelector(".d-manual").hidden = !(t.value === "manual" || other);
    card.querySelector(".d-iprow").hidden = other;
    djiUpdate(addr, { wifi_ifname: t.value });
  } else if (cl.contains("d-nearby")) {
    if (t.value) {
      const cam = (djiData.cameras || []).find((x) => x.addr === addr) || {};
      card.querySelector(".d-ssid").value = t.value;
      card.querySelector(".d-pw").value = "";
      if ((cam.saved || []).includes(t.value)) djiCmd({ cmd: "use_saved", addr, ssid: t.value }).then(() => djiLoad());
      else djiUpdate(addr, { ssid: t.value, password: "" });
      t.value = "";
      card.querySelector(".d-pw").focus();
    }
  } else if (cl.contains("d-saved")) {
    djiNew[addr] = t.value === "__new__" ? { base: ((djiData.cameras || []).find((x) => x.addr === addr) || {}).ssid || "" } : null;
    if (djiNew[addr]) {
      card.querySelector(".d-ssid").value = "";
      card.querySelector(".d-pw").value = "";
      card.querySelector(".d-ssid").focus();
      djiDynamic();
    } else if (t.value) {
      djiEdit[addr] = false;
      card.querySelector(".d-ssid").value = t.value;
      card.querySelector(".d-pw").value = "";
      djiCmd({ cmd: "use_saved", addr, ssid: t.value }).then(() => djiLoad());
    }
  } else if (cl.contains("d-ssid")) djiUpdate(addr, { ssid: t.value });
  else if (cl.contains("d-pw")) djiUpdate(addr, { password: t.value });
  else if (cl.contains("d-ip")) djiUpdate(addr, { ip: t.value });
  else if (cl.contains("d-res")) djiUpdate(addr, { resolution: t.value });
  else if (cl.contains("d-fps")) djiUpdate(addr, { fps: parseInt(t.value) });
  else if (cl.contains("d-stab")) djiUpdate(addr, { stabilization: t.value });
  else if (cl.contains("d-statusonly")) djiCmd({ cmd: "update", addr, status_only: t.checked }).then(() => djiLoad());
  else if (cl.contains("d-auto")) djiCmd({ cmd: "update", addr, autoconnect: t.checked }).then(() => djiLoad());
});
$("djicams").addEventListener("input", (e) => {
  const addr = djiAddr(e);
  if (!addr) return;
  const t = e.target,
    cl = t.classList;
  if (cl.contains("d-br")) {
    const v = parseFloat(t.value);
    if (v >= 0.5 && v <= 16) djiUpdate(addr, { bitrate: Math.round(v * 1000) });
  } else if (cl.contains("d-name")) {
    if (t.value.trim()) djiUpdate(addr, { name: t.value.trim() });
  } else if (cl.contains("d-ssid") || cl.contains("d-pw") || cl.contains("d-ip")) {
    const cam = (djiData.cameras || []).find((x) => x.addr === addr) || {};
    if (cam.locked) return;
    djiUpdate(addr, cl.contains("d-ssid") ? { ssid: t.value } : cl.contains("d-pw") ? { password: t.value } : { ip: t.value });
  }
});
$("djicams").addEventListener("click", async (e) => {
  const addr = djiAddr(e);
  if (!addr) return;
  const cl = e.target.classList;
  if (cl.contains("d-remove")) {
    if (confirm("Diese Kamera entfernen? Sie verschwindet auch aus der Kameraliste.") && (await djiCmd({ cmd: "remove", addr }))) {
      try {
        if (document.activeElement && $("djicams").contains(document.activeElement)) document.activeElement.blur();
      } catch (x) {}
      djiStruct = "";
      tick();
      djiLoad();
    }
  } else if (cl.contains("d-wedit")) {
    djiEdit[addr] = !djiEdit[addr];
    if (!djiEdit[addr]) djiNew[addr] = false;
    djiDynamic();
    return;
  } else if (cl.contains("d-saveddel")) {
    const sel = e.target.closest(".d-savedrow").querySelector(".d-saved");
    if (sel.value && confirm("Dieses gespeicherte Netz löschen?")) await djiCmd({ cmd: "delete_saved", addr, ssid: sel.value });
  } else if (cl.contains("d-nearscan")) {
    const row = e.target.closest(".d-nearrow"),
      msg = row.querySelector(".d-nearmsg");
    nearAuto = Date.now();
    row.querySelector(".d-nearby").dataset.sig = "";
    if (!wifiDefaultIface()) {
      msg.textContent = "Keine WLAN-Karte gefunden. Name und Passwort lassen sich auch von Hand eintragen.";
      return;
    }
    msg.textContent = "Suche läuft …";
    const err = await wifiDo({ action: "scan", iface: wifiDefaultIface() }, "Suche läuft …");
    if (err) {
      msg.textContent = err;
      return;
    }
    setTimeout(async () => {
      await wifiLoad();
      msg.textContent = nearNets().length ? "" : "Keine Netze gefunden. Steckt ein WLAN-Stick, und läuft keine Sendung?";
    }, 9000);
    return;
  } else if (cl.contains("d-connect")) await djiCmd({ cmd: "connect", addr });
  else if (cl.contains("d-reconnect")) await djiCmd({ cmd: "reconnect", addr });
  else if (cl.contains("d-disconnect")) await djiCmd({ cmd: "disconnect", addr });
  else return;
  djiLoad();
});
$("djiscan").addEventListener("click", async (e) => {
  const b = e.target.closest && e.target.closest(".d-add");
  if (!b) return;
  if (await djiCmd({ cmd: "add", addr: b.dataset.addr, name: b.dataset.name, model: b.dataset.model, kind: b.dataset.kind })) {
    djiStruct = "";
    tick();
  }
  djiLoad();
});
$("d_scan").onclick = async () => {
  await djiCmd({ cmd: "scan" });
  djiLoad();
};
let hdmiData = null,
  hdmiDirty = false,
  hdmiBusy = false;
function hdmiIsUsb(d) {
  return !!(d && d.settings && d.settings.source === "usb");
}
function hdmiSignalText(d) {
  if (!d.service) return d.message || "";
  if (hdmiIsUsb(d)) {
    const u = d.usb || {};
    if (!u.present) return u.power && d.message ? d.message : "Keine USB-Kamera angeschlossen";
    return (
      [u.name, u.format].filter(Boolean).join(" · ") +
      (u.format && !u.audio && (d.settings || {}).audio !== "none" ? " · kein Ton der Kamera gefunden" : "")
    );
  }
  if (d.available === false) return "Diese Box hat keinen HDMI-Eingang";
  if (d.signal_known === false) return "";
  const s = d.signal || {};
  return s.locked ? `Signal ${s.width}×${s.height} · ${Math.round(s.fps)} Hz` : "Kein HDMI-Signal";
}
function hdmiStateText(d) {
  if (!d.service) return "Dienst fehlt";
  if (d.available === false) return "kein HDMI-Eingang";
  return (
    {
      off: "aus",
      waiting: hdmiIsUsb(d) ? "wartet auf Kamera" : "wartet auf Signal",
      starting: "startet …",
      streaming: "sendet",
      error: "Fehler",
    }[d.state] || ""
  );
}
function hdmiButtons() {
  const usable = !!(hdmiData && hdmiData.service && hdmiData.available !== false) && !hdmiBusy;
  ["hdmi_on", "hdmi_source", "hdmi_fps", "hdmi_br", "hdmi_audio", "hdmi_fmt", "hdmi_save"].forEach((id) => {
    $(id).disabled = !usable;
  });
  if (hdmiIsUsb(hdmiData)) $("hdmi_fps").disabled = true;
}
function hdmiFill(d) {
  hdmiData = d;
  const st = hdmiStateText(d),
    e = $("hdmi_state");
  e.textContent = st;
  e.style.color = d.state === "streaming" ? "var(--ok)" : d.state === "error" || !d.service ? "var(--crit)" : "";
  $("hdmi_signal").textContent = hdmiSignalText(d);
  const s = d.settings || {},
    usb = hdmiIsUsb(d);
  $("hdmi_name").textContent = usb ? "USB-Webcam" : "HDMI-Eingang";
  $("hdmi_audio").options[0].textContent = usb ? "Ton der Kamera" : "HDMI-Ton";
  $("hdmi_vsum").textContent =
    `${usb ? "" : s.fps + " fps · "}${(s.bitrate / 1000).toFixed(1).replace(/\.0$/, "")} Mbit/s · ${s.audio === "none" ? "ohne Ton" : usb ? "Ton der Kamera" : "HDMI-Ton"}`;
  if (!hdmiDirty) {
    $("hdmi_source").value = s.source || "hdmi";
    $("hdmi_on").checked = !!s.enabled;
    $("hdmi_fps").value = String(s.fps);
    $("hdmi_br").value = String(s.bitrate / 1000);
    $("hdmi_audio").value = s.audio;
    $("hdmi_fmt").value = s.usb_format || "auto";
  }
  $("hdmi_fmtrow").hidden = !usb;
  const err = $("hdmi_err");
  if (d.state === "error" && d.message) {
    err.textContent = d.message;
    err.style.color = "";
  } else if (err.dataset.keep !== "1") err.textContent = "";
  hdmiButtons();
}
async function hdmiLoad() {
  let d;
  try {
    d = await srtlaCall("GET", "/api/hdmi");
  } catch (e) {
    return;
  }
  hdmiFill(d);
}
async function hdmiPost(body, done) {
  const err = $("hdmi_err");
  err.dataset.keep = "";
  err.textContent = "";
  hdmiBusy = true;
  hdmiButtons();
  try {
    const d = await srtlaCall("POST", "/api/hdmi", body);
    hdmiDirty = false;
    hdmiFill(d);
    if (done) {
      err.textContent = done;
      err.style.color = "var(--ok)";
      err.dataset.keep = "1";
    }
    tick();
  } catch (x) {
    err.textContent = x.message;
    err.style.color = "";
    err.dataset.keep = "1";
  }
  hdmiBusy = false;
  hdmiButtons();
}
$("hdmi_on").addEventListener("change", () => hdmiPost({ enabled: $("hdmi_on").checked }));
$("hdmi_source").addEventListener("change", () => hdmiPost({ source: $("hdmi_source").value }));
$("hdmi_save").addEventListener("click", () =>
  hdmiPost(
    {
      bitrate: Math.round(parseFloat($("hdmi_br").value) * 1000),
      fps: parseInt($("hdmi_fps").value, 10),
      audio: $("hdmi_audio").value,
      usb_format: $("hdmi_fmt").value,
    },
    "Gespeichert.",
  ),
);
["input", "change"].forEach((ev) =>
  $("hdmi_vsec").addEventListener(ev, () => {
    hdmiDirty = true;
  }),
);
$("hdmi_cam").addEventListener("toggle", () => {
  if ($("hdmi_cam").open) hdmiLoad();
});
hdmiLoad();
setInterval(() => {
  if (due("hdmi", "c_cams", 20000)) hdmiLoad();
}, 3000);
let netBusy = false;
async function netRender() {
  const r = await fetch("/api/network");
  if (!r.ok) return;
  const d = await r.json();
  netOpts = d.options || [];
  const sel = $("netsel");
  if (document.activeElement === sel || netBusy) return;
  sel.innerHTML =
    d.options
      .map(
        (o) =>
          `<option value="${esc(o.iface)}"${(d.selected ? o.iface === d.selected : o.ip === d.ip) ? " selected" : ""}>${esc(o.label)} · ${esc(o.cam_ip || o.ip)}${o.cam_ip && o.cam_ip !== o.ip ? " (feste Adresse)" : ""}</option>`,
      )
      .join("") || "<option>keine Netzwerke</option>";
  const keyHint = "<Schlüssel>";
  $("netinfo").textContent = d.selected
    ? `Adresse für die Kamera: rtmp://${d.ip}:1935/publish/${keyHint}`
    : `Adresse für die Kamera: rtmp://${d.ip}:1935/publish/${keyHint} (Standardweg, noch nicht gewählt)`;
}
$("netsel").addEventListener("change", async (e) => {
  netBusy = true;
  const r = await fetch("/api/network", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ iface: e.target.value }),
  });
  netBusy = false;
  if (!r.ok) $("djierr").textContent = (await r.json()).error;
  netRender();
  tick();
});
let srtlaEdit = null,
  srtlaData = null;
async function srtlaCall(method, url, body) {
  const hdr = { "Content-Type": "application/json" };
  if (url.indexOf("/api/chat/") === 0 || url.indexOf("/api/twitch/log") === 0) hdr["x-pb-owner"] = pbOwnerKey();
  if (url === "/api/twitch/login" && body && body.action === "start") body.owner = pbOwnerKey();
  const r = await fetch(url, { method, headers: hdr, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Fehler");
  return j;
}
async function uaLoad() {
  try {
    const r = await fetch("/api/uiaccess");
    if (r.ok) uaRender(await r.json());
  } catch (e) {}
  try {
    const r = await fetch("/api/previewaccess");
    if (r.ok) paRender(await r.json());
  } catch (e) {}
}
function paRender(d) {
  const c = $("pa_ext");
  if (c !== document.activeElement) c.checked = !!d.external;
  if (window.pbPrevSync) pbPrevSync(false);
}
$("pa_help_btn").addEventListener("click", () => {
  const h = $("pa_help");
  h.hidden = !h.hidden;
  $("pa_help_btn").setAttribute("aria-expanded", String(!h.hidden));
});
$("pa_ext").addEventListener("change", async (e) => {
  $("pa_err").textContent = "";
  try {
    paRender(await srtlaCall("POST", "/api/previewaccess", { external: e.target.checked }));
    if (window.pbPrevSync) pbPrevSync(true);
  } catch (x) {
    $("pa_err").textContent = x.message;
    e.target.checked = !e.target.checked;
    if (window.pbPrevSync) pbPrevSync(false);
  }
});
function uaRender(d) {
  const c = $("ua_block");
  if (c !== document.activeElement) c.checked = !!d.block_client_wifi;
  const l = d.client_wifi || [];
  $("ua_info").textContent = l.length
    ? `Gast-WLAN der Box: ${l.map((x) => x.iface + " (" + x.ip + ")").join(", ")}`
    : "Die Box ist gerade in keinem Gast-WLAN.";
}
$("ua_block").addEventListener("change", async (e) => {
  $("ua_err").textContent = "";
  try {
    uaRender(await srtlaCall("POST", "/api/uiaccess", { block_client_wifi: e.target.checked }));
  } catch (x) {
    $("ua_err").textContent = x.message;
    e.target.checked = !e.target.checked;
  }
});
let lastNet = null;
let lastAlerts = [],
  healthSig = "";
const dismissedAlerts = new Set();
const USB_LABEL = {
  wlan: "USB-WLAN-Adapter getrennt",
  bt: "USB-Bluetooth-Adapter getrennt",
  net: "USB-Router getrennt",
  cam: "USB-Kamera getrennt",
  other: "USB-Gerät getrennt",
};
function alertWhen(t) {
  const d = new Date((t || 0) * 1000),
    hm = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"),
    today = d.toDateString() === new Date().toDateString();
  return today ? `um ${hm}` : `gestern um ${hm}`;
}
