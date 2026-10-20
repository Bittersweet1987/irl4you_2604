function djiDynamic() {
  const d = djiData,
    box = $("djicams");
  nearAutoScan();
  for (const c of d.cameras || []) {
    const card = box.querySelector(`.dcam[data-addr="${c.addr}"]`);
    if (!card) continue;
    let [txt, step] = DJI_STATE[c.state] || [c.state, 0],
      col =
        c.state === "streaming" || c.state === "status"
          ? "var(--ok)"
          : c.state === "error"
            ? "var(--crit)"
            : c.state === "idle"
              ? "var(--muted)"
              : c.state === "pairing"
                ? "var(--warn)"
                : "var(--accent)";
    if (step) txt += ` (${step}/6)`;
    if ((c.state === "idle" || c.state === "error") && c.publishing) {
      txt = "Stream läuft (ohne Bluetooth)";
      col = "var(--warn)";
    }
    const e = card.querySelector(".dstate");
    e.textContent = txt;
    e.style.color = col;
    card.querySelector(".ddot").style.background =
      c.state === "streaming" || c.state === "status" ? "var(--ok)" : c.state === "idle" || c.state === "error" ? "var(--crit)" : "var(--warn)";
    if (!card.querySelector(".d-name").matches(":focus")) {
      const nm = djiName(c);
      card.querySelector(".dname").textContent = nm;
    }
    {
      const b = card.querySelector(".dbatt"),
        a = c.battery_age,
        stale = a != null && a > 600;
      b.textContent = c.battery != null ? (c.charging ? "🔌 " : "") + c.battery + " %" + (stale ? " (alt)" : "") : "";
      b.style.color = c.battery == null ? "" : c.battery > 75 ? "var(--ok)" : c.battery < 25 ? "var(--crit)" : "";
      b.style.opacity = stale ? ".6" : "";
    }
    let det = c.detail || (c.state === "idle" ? (c.in_range ? "In Reichweite" : "Zuletzt nicht gesehen") : "");
    const left = Math.max(0, (c.retry_in || 0) - Math.floor((Date.now() - djiRecv) / 1000));
    if (c.state === "error" && c.retry_in && c.autoconnect) det += (det ? " – " : "") + "neuer Versuch in " + left + " s";
    const dt = card.querySelector(".ddetail");
    dt.textContent = det ? "· " + det : "";
    dt.style.color = c.state === "error" ? "var(--crit)" : "";
    const active = (c.state !== "idle" && !(c.state === "error" && !c.autoconnect)) || c.publishing;
    card.querySelector(".d-connect").hidden = active;
    card.querySelector(".dact2").hidden = !active;
    card.querySelector(".dact3").hidden = active;
    const so = card.querySelector(".d-statusonly");
    if (so !== document.activeElement) so.checked = !!c.status_only;
    so.disabled = !!(c.mode_locked !== undefined ? c.mode_locked : c.locked);
    card.querySelectorAll(".dstep-conn,.dstep-video").forEach((x) => {
      x.hidden = !!c.status_only;
    });
    card.querySelector(".d-auto").closest("label").hidden = !!c.status_only;
    djiNearby(card);
    const wo = (d.wifi_options || []).find((o) => o.ifname === c.wifi_ifname),
      editing = !c.locked && (djiEdit[c.addr] || !c.wifi_ifname);
    const needNet = djiNeedsNet(c),
      isNew = !!djiNew[c.addr] || (needNet && !(c.saved || []).length),
      sig = (nearNets().find((n) => n.ssid === c.ssid) || {}).signal;
    card.querySelector(".dsumtxt").textContent = c.wifi_ifname === "manual" ? "Manuell" : c.wifi_ifname ? (wo && wo.ssid ? wo.ssid : c.wifi_ifname) : "Noch keine Verbindung gewählt";
    card.querySelector(".dsumwl").innerHTML = !c.wifi_ifname
      ? ""
      : needNet
        ? c.ssid
          ? "<b>" + esc(c.ssid) + "</b>" + (sig != null ? " " + wlBars(sig) + " " + sig + " %" : "")
          : "noch kein Netz eingetragen"
        : "Name und Passwort setzt die Box selbst";
    card.querySelector(".dwlk").hidden = !c.wifi_ifname;
    const eb = card.querySelector(".d-wedit");
    eb.hidden = !!c.locked || !c.wifi_ifname;
    eb.textContent = editing ? "Fertig" : "Bearbeiten";
    card.querySelector(".dedit").hidden = !editing;
    card.querySelector(".d-lockhint").hidden = !c.locked;
    card.querySelector(".dlock").hidden = !c.locked;
    card.querySelector(".dconn").disabled = !!c.locked;
    const ss = card.querySelector(".d-ssid");
    if (ss && ss !== document.activeElement && !djiPend[c.addr] && !djiNew[c.addr] && ss.value !== (c.ssid || "")) ss.value = c.ssid || "";
    card.querySelector(".d-nearrow").hidden = !isNew;
    const sv = card.querySelector(".d-saved");
    if (sv && sv !== document.activeElement) {
      const names = c.saved || [],
        have = [...sv.options].slice(1, -1).map((o) => o.value);
      if (JSON.stringify(names) !== JSON.stringify(have))
        sv.innerHTML =
          '<option value="">– gespeicherte Netze –</option>' +
          names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("") +
          '<option value="__new__">Weiteres Netz anlegen …</option>';
      sv.value = djiNew[c.addr] ? "__new__" : names.includes(c.ssid) ? c.ssid : "";
      card.querySelector(".d-savedrow").hidden = !names.length;
      card.querySelector(".d-saveddel").disabled = !!djiNew[c.addr] || !names.includes(c.ssid);
    }
    const pw = card.querySelector(".d-pw");
    if (pw && pw !== document.activeElement)
      pw.placeholder = !djiNew[c.addr] && (c.saved || []).includes(c.ssid) ? "Passwort gespeichert – leer lassen, um es zu behalten" : "Passwort";
    card.querySelector(".dsum-video").textContent = `· ${c.resolution || ""} ${c.fps || 30} fps · ${(c.bitrate || 6000) / 1000} Mbit/s`;
    const au = card.querySelector(".d-auto");
    if (au !== document.activeElement) au.checked = !!c.autoconnect;
  }
}
function btRender(d) {
  const el = $("btcard");
  if (!el) return;
  const ad = d.available ? d.adapters || [] : [],
    pr = d.available ? d.adapter_problems || [] : [],
    dr = d.driver || {};
  const drTxt = d.available && dr.message && ["working", "waiting", "failed", "unsupported"].includes(dr.state) ? dr.message : "";
  let h = "";
  if (!d.available)
    h = `<div class="wstat bad"><span class="wdot"></span><span class="wgrow">${esc(d.reason || "Der Bluetooth-Dienst ist nicht erreichbar")}</span></div>`;
  else {
    h =
      ad
        .map(
          (a) =>
            `<div class="wstat${a.powered ? " ok" : ""}"><span class="wdot"></span><span class="wgrow"><b>${esc(a.label || a.name || (a.usb_id ? "Bluetooth-Stick" : "Eingebauter Bluetooth-Adapter"))}</b>${devDet(a)}${dnLink(a)} · ${a.powered ? "bereit" : "ausgeschaltet"}</span></div>`,
        )
        .join("") +
      pr
        .map(
          (x) =>
            `<div class="wstat bad"><span class="wdot"></span><span class="wgrow"><b>${esc(x.label || x.name)}</b> <span class="muted">(${esc(x.id)})</span>${dnLink(x)} · nicht nutzbar<div class="muted" style="margin-top:3px">${esc(x.hint)}</div></span></div>`,
        )
        .join("");
    if (!ad.length && !pr.length)
      h =
        '<div class="wstat bad"><span class="wdot"></span><span class="wgrow">Kein Bluetooth-Adapter gefunden. Für DJI-Kameras einen USB-Bluetooth-Stick einstecken.</span></div>';
    if (drTxt)
      h += `<div class="ph"${dr.state === "failed" || dr.state === "unsupported" ? ' style="color:var(--crit)"' : ""}>${esc(drTxt)}</div>`;
  }
  setHtml(el, h);
}
let btdrvTimer = 0;
function btdrvRender(d) {
  const msg = $("btdrvmsg"),
    go = $("btdrv_go");
  if (!msg || !go) return;
  const run = d.state === "working",
    ch = d.chip || null;
  progSet("btdrvprog", run, d.steps ? Math.round((100 * (d.step || 0)) / d.steps) : 0, d.step_text || "");
  go.disabled = !d.helper_installed || run || !!(ch && ch.state === "working");
  const done = !!d.helper_installed && !run && (d.state === "ok" || (!!ch && ch.state === "ok" && (d.state === "none" || !d.state)));
  go.className = done ? "sec" : "";
  let bad = d.state === "failed" || d.state === "unsupported",
    show;
  if (!d.helper_installed) show = "Der Treiber-Helfer ist auf dieser Box noch nicht installiert (install.sh erneut ausführen).";
  else if (ch && (d.state === "none" || !d.state)) {
    bad = ch.state === "failed" || ch.state === "unsupported";
    show = (d.manual || ch.manual || ch.state !== "ok") && ch.message;
  } else show = (d.manual || bad || run || d.state === "waiting") && d.message;
  msg.textContent = show || "";
  msg.style.color = bad || !d.helper_installed ? "var(--crit)" : "";
  clearTimeout(btdrvTimer);
  btdrvTimer = setTimeout(btdrvLoad, run ? 1500 : 15000);
}
async function btdrvLoad() {
  try {
    const r = await fetch("/api/btdriver");
    if (r.ok) btdrvRender(await r.json());
  } catch (e) {
    clearTimeout(btdrvTimer);
    btdrvTimer = setTimeout(btdrvLoad, 3000);
  }
}
$("btdrv_go").onclick = async () => {
  $("btdrv_go").disabled = true;
  try {
    const r = await fetch("/api/btdriver", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      $("btdrvmsg").textContent = j.error || "Fehler";
      $("btdrvmsg").style.color = "var(--crit)";
      $("btdrv_go").disabled = false;
      return;
    }
    $("btdrvmsg").textContent = "Wird gestartet …";
    $("btdrvmsg").style.color = "";
    clearTimeout(btdrvTimer);
    btdrvTimer = setTimeout(btdrvLoad, 1500);
  } catch (e) {
    $("btdrvmsg").textContent = "Keine Verbindung zur Box";
    $("btdrv_go").disabled = false;
  }
};
btdrvLoad();
function phoneAge(s) {
  return s == null ? "" : s < 90 ? "gerade eben" : s < 5400 ? `vor ${Math.round(s / 60)} Min.` : `vor ${Math.round(s / 3600)} Std.`;
}
function phoneRender(d) {
  const el = $("phonecard");
  if (!el) return;
  const list = d.available ? d.phones || [] : [],
    pr = d.phone_pairing || {};
  setHtml(
    el,
    list.length
      ? list
          .map((p) => {
            const lvl = p.percent == null ? "" : p.percent > 75 ? " ok" : p.percent < 25 ? " bad" : "";
            const val = p.percent == null ? (p.reading ? "wird gelesen …" : "noch kein Wert") : `${p.percent} %`;
            return (
              `<div class="wstat${lvl}" data-addr="${esc(p.addr)}"><span class="wdot"></span><span class="wgrow"><b>${esc(p.name)}</b> · ${esc(val)}${p.age != null ? `<span class="muted">· ${esc(phoneAge(p.age))}</span>` : ""}` +
              `${p.error ? `<div class="muted"style="margin-top:3px;color:var(--crit)">${esc(p.error)}</div>` : ""}</span>` +
              `<button type="button" class="ph-read"${p.reading ? " disabled" : ""}>Jetzt lesen</button> <button type="button" class="ph-del">Entfernen</button></div>`
            );
          })
          .join("")
      : '<div class="muted" style="margin:6px 0">Noch kein Handy gekoppelt.</div>',
  );
  const b = $("ph_pair");
  b.disabled = !d.available;
  b.textContent = pr.active ? "Abbrechen" : "Handy koppeln";
  const m = $("ph_msg");
  m.textContent = pr.active
    ? `Die Box ist jetzt noch ${pr.left} Sekunden sichtbar. Am Handy in den Bluetooth-Einstellungen nach neuen Geräten suchen und „irl4you“ auswählen.`
    : pr.message || "";
}
$("ph_pair").onclick = async () => {
  const on = (djiData.phone_pairing || {}).active;
  if (await djiCmd({ cmd: on ? "phone_pair_stop" : "phone_pair" })) djiLoad();
};
$("phonecard").addEventListener("click", async (e) => {
  const b = e.target.closest("button"),
    row = e.target.closest("[data-addr]");
  if (!b || !row) return;
  const addr = row.dataset.addr;
  if (b.classList.contains("ph-read")) {
    if (await djiCmd({ cmd: "phone_read", addr })) djiLoad();
  } else if (b.classList.contains("ph-del")) {
    if (
      confirm("Dieses Handy entfernen? Die Kopplung wird aufgehoben, zum erneuten Abfragen muss es neu gekoppelt werden.") &&
      (await djiCmd({ cmd: "phone_remove", addr }))
    )
      djiLoad();
  }
});
function ctrlRender(d) {
  const el = $("ctrlcard");
  if (!el) return;
  const ok = d.available,
    list = ok ? d.controllers || [] : [],
    sc = d.ctrl_scan || {};
  setHtml(
    el,
    list.length
      ? list
          .map(
            (c) =>
              `<div class="wstat${c.connected ? " ok" : ""}" data-addr="${esc(c.addr)}"><span class="wdot"></span><span class="wgrow"><b>${esc(c.name)}</b> · ${c.pairing ? "Koppeln …" : c.connected ? "verbunden" : "getrennt"}` +
              `${c.battery != null ? `<span class="muted">· Akku ${esc(c.battery)}%</span>` : ""}</span><button type="button" class="ct-del">Entfernen</button></div>`,
          )
          .join("")
      : '<div class="muted" style="margin:6px 0">Noch kein Controller gekoppelt.</div>',
  );
  const all = $("ct_all").checked,
    found = (d.ctrl_found || []).filter((r) => all || r.input);
  const f = $("ctrlfound");
  setHtml(
    f,
    found
      .map(
        (r) =>
          `<div class="dscan" data-addr="${esc(r.addr)}"><div>${esc(r.name || "(ohne Name)")} <span class="muted">${esc(r.addr)} · ${esc(r.rssi)} dBm</span></div><button type="button" class="ct-pair"${(d.controllers || []).some((c) => c.pairing) ? " disabled" : ""}>Koppeln</button></div>`,
      )
      .join(""),
  );
  const b = $("ct_scan");
  b.disabled = !ok || !!sc.active;
  b.textContent = sc.active ? "Suche läuft …" : "Nach Controllern suchen";
  const m = $("ct_msg");
  m.textContent =
    d.ctrl_message ||
    sc.message ||
    (!sc.active && (d.ctrl_found || []).length && !found.length
      ? "Kein Controller erkannt. Mit „Alle Geräte zeigen“ siehst du alle Geräte in der Nähe."
      : "");
  m.style.color = d.ctrl_message ? "var(--crit)" : "";
}
$("ct_scan").onclick = async () => {
  if (await djiCmd({ cmd: "ctrl_scan" })) djiLoad();
};
$("ct_all").onchange = () => ctrlRender(djiData);
$("ctrlcard").addEventListener("click", async (e) => {
  const b = e.target.closest(".ct-del"),
    row = e.target.closest("[data-addr]");
  if (!b || !row) return;
  if (
    confirm("Diesen Controller entfernen? Die Kopplung wird aufgehoben.") &&
    (await djiCmd({ cmd: "ctrl_remove", addr: row.dataset.addr }))
  )
    djiLoad();
});
$("ctrlfound").addEventListener("click", async (e) => {
  const b = e.target.closest(".ct-pair"),
    row = e.target.closest("[data-addr]");
  if (!b || !row) return;
  if (await djiCmd({ cmd: "ctrl_pair", addr: row.dataset.addr })) djiLoad();
});
const djiAway = (c) => !(c.publishing || ["streaming", "status", "starting", "configuring", "pairing"].includes(c.state));
const djiSorted = (l) =>
  (l || [])
    .map((c, i) => [djiAway(c) ? 1 : 0, i, c])
    .sort((x, y) => x[0] - y[0] || x[1] - y[1])
    .map((x) => x[2]);
function djiRender(d) {
  djiData = d;
  djiRecv = Date.now();
  btRender(d);
  phoneRender(d);
  ctrlRender(d);
  const note = $("djinote"),
    box = $("djicams");
  if (!d.available) {
    note.textContent = d.reason || "Bluetooth nicht verfügbar";
    note.style.color = "var(--crit)";
    $("d_scan").disabled = true;
    box.innerHTML = "";
    djiStruct = "";
    $("djiscan").innerHTML = "";
    $("djiadapt").textContent = "";
    return;
  }
  note.textContent =
    d.bleak === false
      ? "Die Bluetooth-Bibliothek (bleak) ist nicht installiert. install.sh erneut ausführen (braucht Internet)."
      : d.scan_error || "";
  note.style.color = note.textContent ? "var(--crit)" : "";
  {
    const pr = (d.adapter_problems || []).map((x) => x.hint),
      ad = d.adapters || [];
    const el = $("djiadapt");
    const dr = d.driver || {},
      drTxt = dr.message && ["working", "waiting", "failed", "unsupported"].includes(dr.state) ? dr.message : "";
    const bad = pr.length || !ad.length || dr.state === "failed" || dr.state === "unsupported";
    if (pr.length && !drTxt) {
      el.textContent = pr.join(" ");
    } else if (pr.length) {
      el.textContent = drTxt;
    } else {
      el.textContent = (ad.length ? "" : "Kein Bluetooth-Adapter gefunden. ") + drTxt;
    }
    el.style.color = bad ? "var(--crit)" : "";
  }
  $("d_scan").disabled = !!d.scanning;
  $("d_scan").textContent = d.scanning ? "Suche läuft …" : "Nach DJI-Kameras suchen";
  const cams = djiSorted(d.cameras);
  const sig = JSON.stringify([
    cams.map((c) => c.addr + "|" + (c.saved || []).join(",") + "|" + c.wifi_ifname + "|" + (c.locked ? 1 : 0) + "|" + (djiAway(c) ? 1 : 0)),
    (d.wifi_options || []).map((o) => [o.ifname, o.ssid, o.type, o.ip, o.secret_missing]),
  ]);
  const ae = document.activeElement,
    typing =
      box.contains(ae) &&
      (ae.tagName === "TEXTAREA" ||
        ae.tagName === "SELECT" ||
        (ae.tagName === "INPUT" && !/^(button|checkbox|radio|submit|reset)$/.test(ae.type)));
  if (sig !== djiStruct && !typing) {
    djiStruct = sig;
    box.innerHTML = cams.length
      ? cams.map(djiCardHtml).join("")
      : '<div class="muted" style="margin-top:8px">Noch keine DJI-Kamera eingerichtet. Kamera einschalten, Bluetooth aktivieren, nahe an die Box legen und suchen.</div>';
  }
  djiDynamic();
  $("djiscan").innerHTML = (d.scan || [])
    .map(
      (r) =>
        `<div class="dscan"><div>${esc(r.name)} <span class="muted">${esc(r.model)} · ${esc(r.addr)} · ${esc(r.rssi)} dBm</span></div>${r.paired ? '<span class="muted">hinzugefügt</span>' : `<button type="button"class="d-add"data-addr="${esc(r.addr)}"data-name="${esc(r.name)}"data-model="${esc(r.model)}"data-kind="${esc(r.kind)}">Hinzufügen</button>`}</div>`,
    )
    .join("");
}
let djiBusyLoad = false;
async function djiLoad() {
  if (djiBusyLoad) return;
  djiBusyLoad = true;
  try {
    const r = await fetch("/api/dji");
    if (r.ok) djiRender(await r.json());
  } catch (e) {}
  djiBusyLoad = false;
}
async function djiCmd(body) {
  try {
    const r = await fetch("/api/dji/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      $("djierr").textContent = j.error || "Fehler";
      return false;
    }
    $("djierr").textContent = "";
    return true;
  } catch (e) {
    $("djierr").textContent = "Keine Verbindung zur Box";
    return false;
  }
}
function djiUpdate(addr, ch) {
  const p = djiPend[addr] || (djiPend[addr] = { ch: {} });
  Object.assign(p.ch, ch);
  clearTimeout(p.t);
  p.t = setTimeout(async () => {
    const c = p.ch;
    delete djiPend[addr];
    if (await djiCmd(Object.assign({ cmd: "update", addr }, c))) tick();
    djiLoad();
  }, 400);
}
setInterval(() => {
  if (!document.hidden) djiDynamic();
}, 1000);
(function djiFastLoop() {
  const busy =
    djiData.available &&
    (djiData.scanning ||
      (djiData.phone_pairing || {}).active ||
      (djiData.phones || []).some((p) => p.reading) ||
      (djiData.ctrl_scan || {}).active ||
      (djiData.controllers || []).some((c) => c.pairing) ||
      (djiData.cameras || []).some((c) => DJI_BUSY.includes(c.state)));
  Promise.resolve(busy && !document.hidden ? djiLoad() : null).finally(() => setTimeout(djiFastLoop, 1000));
})();
