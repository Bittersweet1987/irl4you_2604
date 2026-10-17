async function pipWatchRestart(base) {
  const tok = ++pipWatchTok,
    t0 = Date.now(),
    el = $("pipeerr");
  let seenOther = false;
  for (let i = 0; i < 120 && tok === pipWatchTok; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    let d;
    try {
      d = await srtlaCall("GET", "/api/send");
    } catch (e) {
      continue;
    }
    const sec = Math.round((Date.now() - t0) / 1000);
    if (d.state === "running") {
      if (seenOther || sec >= 4) {
        el.textContent = `Gespeichert. Die Übertragung läuft wieder (nach ${sec} Sekunden).`;
        el.style.color = "var(--ok)";
        setTimeout(() => {
          if (tok === pipWatchTok) el.style.color = "";
        }, 8000);
        return;
      }
    } else if (d.state === "refused" || d.state === "stopped") {
      el.textContent = "Gespeichert, aber die Übertragung läuft nicht: " + (d.message || LIVE_LABEL[d.state] || d.state);
      return;
    } else {
      seenOther = true;
      el.textContent = base + " " + (LIVE_LABEL[d.state] || d.state) + " … (" + sec + " s)";
    }
  }
}
$("p_save").addEventListener("click", pipSave);
pipeLoad();
setInterval(() => {
  if (
    due("pipe", "pipecard", 30000) &&
    ![
      "p_main",
      "p_pip",
      "p_type",
      "p_corner",
      "p_pip2",
      "p_corner2",
      "p_pip3",
      "p_corner3",
      "p_size1",
      "p_size2",
      "p_size3",
      "p_auto",
      "p_always",
      "p_delay",
      "n_delay",
      "p_delay1",
      "n_delay1",
      "p_delay2",
      "n_delay2",
      "p_delay3",
      "n_delay3",
      "p_audio",
    ].includes(document.activeElement.id)
  )
    pipeLoad();
}, 5000);
const LIVE_LABEL = {
  stopped: "Nicht live",
  starting: "Startet…",
  running: "LIVE",
  restarting: "Verbindung wird neu aufgebaut…",
  stopping: "Wird beendet…",
  refused: "Nicht gestartet",
};
let sendData = null,
  pendIgnored = "";
const SM_LOCKED = ["srtlacard", "rcard"];
function setSM(on) {
  document.body.classList.toggle("sm", on);
  document.querySelector("#sm_btn .smtx").textContent = on ? "Streammodus: an" : "Streammodus: aus";
  $("sm_btn").title = on ? "Streammodus ist an" : "Streammodus ist aus";
  $("sm_btn").classList.toggle("smon", on);
  SM_LOCKED.forEach((id) => {
    const c = $(id);
    c.classList.toggle("locked", on);
    if (on) c.open = false;
  });
  $("srtlalock").hidden = !on;
  $("rlock").hidden = !on;
  try {
    localStorage.setItem("pb_sendemodus", on ? "1" : "0");
  } catch (e) {}
}
SM_LOCKED.forEach((id) => {
  $(id).addEventListener("toggle", () => {
    if ($(id).classList.contains("locked") && $(id).open) $(id).open = false;
  });
  $(id)
    .querySelector("summary")
    .addEventListener("click", (e) => {
      if ($(id).classList.contains("locked")) e.preventDefault();
    });
});
$("sm_btn").addEventListener("click", () => setSM(!document.body.classList.contains("sm")));
let smStart = false;
try {
  smStart = localStorage.getItem("pb_sendemodus") === "1";
} catch (e) {}
async function sendLoad() {
  let d;
  try {
    d = await srtlaCall("GET", "/api/send");
  } catch (e) {
    return;
  }
  sendData = d;
  updHdrLive(d);
  renderFoot(d);
  $("livestate").textContent = LIVE_LABEL[d.state] || d.state;
  $("livestate").style.color =
    d.state === "running" ? "var(--ok)" : d.state === "restarting" ? "var(--warn)" : d.state === "refused" ? "var(--crit)" : "";
  $("liveserver").textContent = d.server ? "Server: " + d.server.name : "";
  const pend = d.active && d.pending && d.pending.length ? d.pending : [];
  if (!pend.length) pendIgnored = "";
  $("livepending").hidden = !pend.length || pend.join("|") === pendIgnored;
  if (pend.length)
    $("livepending_t").textContent = `Noch nicht übernommen: ${pend.join(", ")}. ` + "Das gilt erst nach einem Neustart der Sendung.";
  {
    const a = d.autostart || {},
      cb = $("auto_on");
    if (document.activeElement !== cb) cb.checked = !!a.enabled;
    const st = $("autostatus");
    if (a.phase === "wartet") {
      st.hidden = false;
      st.textContent = a.until
        ? `Automatischer Start: wartet auf eine sendende Kamera (bis ${new Date(a.until * 1000).toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" })} Uhr)`
        : "Automatischer Start: wartet auf eine sendende Kamera";
    } else if (a.phase === "aufgegeben" || a.phase === "abgebrochen") {
      st.hidden = false;
      st.textContent = a.message || "Automatischer Start beendet";
    } else st.hidden = true;
  }
  const why = [];
  if (d.state === "refused" && d.message) why.push(d.message);
  {
    const nc = d.net_conflict,
      cards = nc && Array.isArray(nc.cards) ? nc.cards : [],
      nets = nc && Array.isArray(nc.nets) ? nc.nets : [];
    $("nethint").hidden = cards.length < 2;
    $("nethint_cards").textContent = cards.join(", ") + (nets.length ? " (" + nets.join(", ") + ")" : "");
  }
  $("srvhint").hidden = !(!d.active && d.no_server);
  $("livehint").hidden = !(!d.active && d.no_layout);
  if (!d.active)
    why.push(
      ...d.reasons.filter(
        (r) => !(d.no_layout && r === "Kein Bildaufbau gespeichert") && !(d.no_server && r === "Kein SRTLA-Server ausgewählt"),
      ),
    );
  if (d.active && d.failover && d.failover.waiting)
    why.push(
      (d.failover.inactive || []).length ? "Keine aktive Kamera sendet, warte auf ein Signal" : "Keine Kamera sendet, warte auf ein Signal",
    );
  else if (d.active && d.failover && d.failover.degraded) {
    const nm = (k) => (camsByKey[k] || {}).name || k;
    why.push(`Notbetrieb: es senden ${d.failover.layout.map(nm).join(", ")} (fehlende Kameras kommen nach 60 s stabilem Signal zurück)`);
  }
  if (d.active && d.always_note) why.push(d.always_note);
  if (d.active && d.last && d.last_age != null && d.last_age < 180) why.push(d.last);
  if (d.active && d.restarts) {
    const e = d.restarts.encoder || d.restarts.belacoder || 0,
      n = d.restarts.srtla || d.restarts.srtla_send || 0;
    if (e || n)
      why.push(
        "Seit dem Start automatisch neu gestartet: " +
          [e ? `Encoder ${e}×` : "", n ? `Netzverbindung ${n}×` : ""].filter(Boolean).join(", "),
      );
  }
  $("livewhy").textContent = why.join(" · ");
}
async function askRestart() {
  await sendLoad();
  const pend = (sendData && sendData.active && sendData.pending) || [];
  if (!pend.length || $("rdlg").open) return;
  $("rdlg_t").textContent = "Geändert: " + pend.join(", ") + ". Das gilt erst nach einem Neustart der Sendung.";
  $("rdlg").showModal();
}
$("live_topipe").addEventListener("click", () => {
  const c = $("pipecard");
  c.open = true;
  c.scrollIntoView({ behavior: "smooth", block: "start" });
});
$("live_tosrv").addEventListener("click", () => {
  const c = $("srtlacard");
  c.open = true;
  c.scrollIntoView({ behavior: "smooth", block: "start" });
});
$("live_ignore").addEventListener("click", () => {
  pendIgnored = ((sendData && sendData.pending) || []).join("|");
  $("livepending").hidden = true;
});
$("rdlg_go").addEventListener("click", async () => {
  $("rdlg").close();
  await restartNow();
});
async function restartNow() {
  try {
    await srtlaCall("POST", "/api/send", { action: "restart", confirm: true });
    $("liveerr").textContent = "";
  } catch (x) {
    $("liveerr").textContent = x.message;
  }
  sendLoad();
}
$("auto_help_btn").addEventListener("click", () => {
  const h = $("auto_help");
  h.hidden = !h.hidden;
  $("auto_help_btn").setAttribute("aria-expanded", String(!h.hidden));
});
$("auto_on").addEventListener("change", async (e) => {
  try {
    await srtlaCall("POST", "/api/autostart", { enabled: e.target.checked });
    $("liveerr").textContent = "";
  } catch (x) {
    $("liveerr").textContent = x.message;
    e.target.checked = !e.target.checked;
  }
  sendLoad();
});
$("live_restart").addEventListener("click", async () => {
  if (!confirm("Die Sendung jetzt kurz neu starten?\n\nDas Bild ist dabei einige Sekunden weg.")) return;
  try {
    await srtlaCall("POST", "/api/send", { action: "restart", confirm: true });
    $("liveerr").textContent = "";
  } catch (x) {
    $("liveerr").textContent = x.message;
  }
  sendLoad();
});
const isPhone = () => window.matchMedia("(max-width:620px)").matches;
async function doLiveStart() {
  const s = sendData && sendData.server;
  if (!s) return;
  try {
    await srtlaCall("POST", "/api/send", { action: "start", confirm: true });
    $("liveerr").textContent = "";
  } catch (x) {
    $("liveerr").textContent = x.message;
    if (isPhone()) footMsg(x.message);
    else alert(x.message);
  }
  setTimeout(sendLoad, 800);
}
function seamlessTo(main, key) {
  const g = (sendData && sendData.swap_group) || [];
  return !!(sendData && sendData.active && g.includes(main) && g.includes(key));
}
$("swapbtns").addEventListener("click", async (e) => {
  const b = e.target.closest(".swapto");
  if (!b) return;
  try {
    const r = await srtlaCall("POST", "/api/pipeline/swap", { with: b.dataset.key });
    $("liveerr").textContent = (r && r.note) || "Getauscht.";
    pipeDirty = false;
    pipeLoad();
  } catch (x) {
    $("liveerr").textContent = x.message;
  }
});
async function doLiveStop() {
  try {
    await srtlaCall("POST", "/api/send", { action: "stop" });
  } catch (x) {
    $("liveerr").textContent = x.message;
  }
  setTimeout(sendLoad, 800);
}
function placeSig() {
  const sig = $("net_sig"),
    dots = $("cam_dots"),
    hold = $("hdr_sig"),
    gear = $("chat_opt"),
    up = $("liveup");
  if (!sig || !dots || !hold || !gear || !up) return;
  const want = isPhone() && document.body.classList.contains("streaming");
  if (want) {
    if (sig.parentNode !== hold) {
      hold.appendChild(sig);
      hold.appendChild(dots);
    }
  } else {
    if (sig.parentNode !== up.parentNode) up.before(sig);
    if (dots.parentNode !== gear.parentNode) gear.before(dots);
  }
}
setTimeout(placeSig, 0);
if (window.matchMedia) matchMedia("(max-width:620px)").addEventListener("change", placeSig);
$("hdr_more").addEventListener("click", () => {
  const o = document.body.classList.toggle("hdr-open");
  $("hdr_more").setAttribute("aria-expanded", o ? "true" : "false");
});
function updHdrLive(d) {
  {
    const on = !!d.active && d.state !== "stopping";
    if (on !== document.body.classList.contains("streaming")) {
      document.body.classList.toggle("streaming", on);
      document.body.classList.remove("hdr-open");
      $("hdr_more").setAttribute("aria-expanded", "false");
      placeSig();
    }
  }
  const b = $("hdr_live"),
    live = !!d.active,
    busy = d.state === "restarting" || d.state === "starting" || d.state === "stopping";
  b.hidden = false;
  b.className = "livebtn" + (live && !busy ? " on" : "") + (busy ? " busy" : "");
  b.textContent = busy
    ? LIVE_LABEL[d.state] === "Wird beendet…"
      ? "Wird beendet…"
      : "Verbinde …"
    : live
      ? "● LIVE"
      : window.matchMedia && matchMedia("(max-width:620px)").matches
        ? "Live"
        : "Live gehen";
  b.disabled = busy || (!live && !d.can_start);
  b.title = busy
    ? LIVE_LABEL[d.state] || ""
    : live
      ? "Es wird gesendet. Klicken beendet die Sendung."
      : d.can_start
        ? "Nicht live. Klicken startet die Sendung."
        : "Kann nicht starten: " + ((d.reasons || []).join(" · ") || "Bedingungen nicht erfüllt");
  const pl = $("prev_live");
  pl.hidden = live || busy;
  pl.disabled = !d.can_start;
  pl.title = b.title;
  const f = $("mf_live");
  f.className = "mf-live" + (live && !busy ? " on" : "") + (busy ? " busy" : "");
  f.textContent = busy ? "…" : live ? "Stop" : "Live";
  f.disabled = b.disabled;
  f.title = b.title;
}
async function liveToggle() {
  if (sendData && sendData.active) await doLiveStop();
  else await doLiveStart();
}
$("hdr_live").addEventListener("click", liveToggle);
$("prev_live").addEventListener("click", liveToggle);
$("mf_live").addEventListener("click", liveToggle);
const FIC = (() => {
  const o =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
    x = '<path d="M4 4l16 16"/></svg>';
  const cam =
      '<path d="M3 8.5A2.5 2.5 0 0 1 5.5 6H8l1.5-2h5L16 6h2.5A2.5 2.5 0 0 1 21 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/><circle cx="12" cy="13" r="3.6"/>',
    pip = '<rect x="3" y="5" width="18" height="14" rx="2.5"/><rect x="12" y="11" width="6" height="5" rx="1.2"/>',
    spk = '<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
    mic = '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"/>';
  return { cam: o + cam + "</svg>", pip: o + pip + "</svg>", pipoff: o + pip + x, spk: o + spk + "</svg>", micoff: o + mic + x };
})();
function camLabels(cams) {
  const w = cams.map((c) =>
      String(c.name || c.key || "?")
        .trim()
        .split(/\s+/),
    ),
    n = cams.map(() => 1),
    lab = (i) => w[i].slice(0, n[i]).join(" ");
  for (let r = 0; r < 6; r++) {
    const grow = cams.map((_, i) => n[i] < w[i].length && cams.some((_, j) => j !== i && lab(j) === lab(i)));
    if (!grow.some(Boolean)) break;
    grow.forEach((g, i) => {
      if (g) n[i]++;
    });
  }
  return Object.fromEntries(cams.map((c, i) => [c.key, lab(i)]));
}
let footBusy = false,
  footMsgT = null;
function footMsg(t, ms) {
  const m = $("mf_msg");
  clearTimeout(footMsgT);
  m.textContent = t || "";
  m.hidden = !t;
  m.dataset.info = "";
  m.style.fontSize = "";
  if (t)
    footMsgT = setTimeout(() => {
      m.hidden = true;
    }, ms || 6000);
}
