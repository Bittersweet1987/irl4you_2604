(function () {
  const card = $("c_report"),
    title = $("rp_title"),
    desc = $("rp_desc"),
    go = $("rp_go"),
    msg = $("rp_msg"),
    out = $("rp_out"),
    list = $("rp_cases"),
    logrow = $("rp_logrow");
  let version = "",
    now = 0,
    win = 1800,
    nowAt = 0;
  const kind = () => document.querySelector('input[name="rp_kind"]:checked').value;
  const NEW = "https://github.com/Bittersweet1987/irl4you_2604/issues/new",
    MAXURL = 7000,
    ALPH = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
  const newId = () => {
    const a = new Uint8Array(6);
    (window.crypto || window.msCrypto).getRandomValues(a);
    return "IRL-" + Array.from(a, (x) => ALPH[x % ALPH.length]).join("");
  };
  const clean = (t) =>
    String(t || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 100);
  let draft = { id: "", saved: false, title: "" };
  function sync() {
    const f = kind() === "feature";
    logrow.hidden = f;
    desc.placeholder = f ? "Beschreibung (Pflicht)" : "Beschreibung (freiwillig)";
  }
  document.querySelectorAll('input[name="rp_kind"]').forEach((r) => r.addEventListener("change", sync));
  sync();
  const when = (t) => {
    const d = new Date(t * 1000);
    return d.toLocaleDateString() + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  };
  function paint(cases, issues) {
    list.textContent = "";
    if (!cases.length) {
      const p = document.createElement("div");
      p.className = "muted";
      p.textContent = "Noch keine Fälle.";
      list.appendChild(p);
      return;
    }
    const age = now + (Date.now() - nowAt) / 1000;
    for (const c of cases) {
      const r = document.createElement("div");
      r.className = "rpcase" + (c.done ? " done" : "");
      const d = document.createElement("span");
      d.className = "rpd";
      d.textContent = when(c.t);
      r.appendChild(d);
      const kd = document.createElement("span");
      kd.className = "rpd";
      kd.textContent = c.kind === "feature" ? "Wunsch" : "Problem";
      r.appendChild(kd);
      const id = document.createElement("code");
      id.textContent = c.id;
      id.translate = false;
      r.appendChild(id);
      const t = document.createElement("span");
      t.className = "rpt";
      t.textContent = c.title;
      t.translate = false;
      r.appendChild(t);
      const a = document.createElement("a");
      a.href = (issues || "https://github.com/Bittersweet1987/irl4you_2604/issues") + "?q=" + encodeURIComponent("is:issue " + c.id);
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "Auf GitHub suchen";
      r.appendChild(a);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sec";
      b.classList.add("small");
      b.dataset.id = c.id;
      b.dataset.done = c.done ? "0" : "1";
      b.textContent = c.done ? "Wieder öffnen" : "Erledigt";
      r.appendChild(b);
      if (age - c.t <= win) {
        const x = document.createElement("button");
        x.type = "button";
        x.className = "sec";
        x.classList.add("small");
        x.dataset.id = c.id;
        x.dataset.del = "1";
        x.textContent = "Entfernen";
        x.title = "Nur in den ersten 30 Minuten nach dem Anlegen möglich: Danach bleibt der Eintrag erhalten.";
        r.appendChild(x);
      }
      list.appendChild(r);
    }
  }
  async function load() {
    try {
      const d = await srtlaCall("GET", "/api/support");
      version = d.version || "";
      now = d.now || 0;
      win = d.delete_window || 1800;
      nowAt = Date.now();
      paint(d.cases || [], d.issues);
    } catch (e) {
      list.textContent = "";
    }
  }
  list.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-id]");
    if (!b) return;
    try {
      await srtlaCall(
        "POST",
        "/api/support",
        b.dataset.del ? { action: "delete", id: b.dataset.id } : { action: "done", id: b.dataset.id, done: b.dataset.done === "1" },
      );
      msg.textContent = "";
    } catch (x) {
      msg.textContent = "Fehler: " + x.message;
    }
    load();
  });
  function compose() {
    const f = kind() === "feature",
      t = clean(title.value),
      body0 = desc.value.trim();
    if (t.length < 3) {
      msg.textContent = "Bitte einen Titel eintragen (mindestens 3 Zeichen).";
      return null;
    }
    if (f && !body0) {
      msg.textContent = "Bei einem Wunsch ist die Beschreibung Pflicht.";
      return null;
    }
    if (!draft.id || (draft.saved && t !== draft.title)) draft = { id: newId(), saved: false, title: "" };
    const id = draft.id,
      ttl = (f ? "[FEATURE] " : "[ISSUE] ") + t + " (" + id + ")";
    let body =
        (body0 ? body0 + "\n\n" : "") +
        "---\nBox-Version: " +
        (version || "?") +
        "\nSupport-Nummer: " +
        id +
        (!f && $("rp_log").checked ? "\nProtokoll: als Datei angehängt" : ""),
      short = false;
    let url = NEW + "?title=" + encodeURIComponent(ttl) + "&body=" + encodeURIComponent(body);
    while (url.length > MAXURL && body.length > 200) {
      body = body.slice(0, Math.floor(body.length * 0.8));
      short = true;
      url = NEW + "?title=" + encodeURIComponent(ttl) + "&body=" + encodeURIComponent(body + "\n[gekürzt]");
    }
    return { f, t, id, url, short };
  }
  function show(c) {
    out.textContent = "";
    out.hidden = false;
    const a = document.createElement("a");
    a.className = "rpgo";
    a.href = c.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "Formular auf GitHub öffnen";
    out.appendChild(a);
    const p = document.createElement("div");
    p.textContent =
      "Das Formular öffnet in einem neuen Tab. Dort bei GitHub anmelden und unten auf „Submit new issue“ klicken." +
      (c.short ? " Die Beschreibung war für den Link zu lang und ist gekürzt: bitte auf GitHub vervollständigen." : "");
    out.appendChild(p);
    const q = document.createElement("div");
    q.appendChild(document.createTextNode("Deine Support-Nummer: "));
    const k = document.createElement("code");
    k.textContent = c.id;
    q.appendChild(k);
    out.appendChild(q);
    const lm = document.createElement("div");
    lm.className = "muted";
    out.appendChild(lm);
    a.addEventListener("click", (ev) => {
      const n = compose();
      if (!n) {
        ev.preventDefault();
        return;
      }
      a.href = n.url;
      if (!draft.saved) {
        draft.saved = true;
        draft.title = n.t;
        srtlaCall("POST", "/api/support", { action: "create", kind: n.f ? "feature" : "issue", title: n.t, id: n.id }).then(load, () => {});
        if (!n.f && $("rp_log").checked)
          logsDownloadTo(go, lm).then(() => {
            lm.textContent += " Datei auf GitHub ins Textfeld ziehen.";
          });
      }
    });
  }
  go.addEventListener("click", () => {
    msg.textContent = "";
    out.hidden = true;
    if (draft.saved) draft = { id: "", saved: false, title: "" };
    const c = compose();
    if (c) show(c);
  });
  card.addEventListener("toggle", () => {
    if (card.open) load();
  });
})();
(function () {
  const on = $("na_on"),
    ack = $("na_ack"),
    ackRow = $("na_ack_row"),
    card = $("na_card"),
    addr = $("na_addr"),
    prefix = $("na_prefix"),
    info = $("na_info"),
    err = $("na_err"),
    save = $("na_save"),
    box = $("opt_netaddr");
  let last = null,
    ready = false;
  function render(d) {
    last = d;
    err.textContent = "";
    card.textContent = "";
    for (const c of d.cards || []) {
      const o = document.createElement("option");
      o.value = c.mac;
      o.textContent = c.name + " · " + c.mac + (c.addrs && c.addrs.length ? " · " + c.addrs.join(", ") : "");
      o.translate = false;
      card.appendChild(o);
    }
    if (d.mac && ![...card.options].some((o) => o.value === d.mac)) {
      const o = document.createElement("option");
      o.value = d.mac;
      o.textContent = d.mac;
      o.translate = false;
      card.appendChild(o);
    }
    if (d.mac) card.value = d.mac;
    if (document.activeElement !== on) on.checked = !!d.enabled;
    if (d.enabled && document.activeElement !== addr) {
      addr.value = d.addr || "";
      prefix.value = d.prefix || 24;
    }
    ready = !!d.installed && (d.cards || []).length > 0;
    gate();
    info.textContent = !d.installed
      ? "Kommt mit dem nächsten Software-Update."
      : !(d.cards || []).length
        ? "Keine LAN-Netzkarte gefunden."
        : d.enabled
          ? d.present
            ? `Aktiv: ${d.addr}/${d.prefix}`
            : "Eingestellt, aber gerade nicht auf der Karte. Sie wird gesetzt, sobald die Karte hochfährt."
          : "Aus. Die Box nutzt nur die Adresse vom Router.";
  }
  function gate() {
    ackRow.hidden = !on.checked;
    save.disabled = !ready || (on.checked && !ack.checked);
  }
  on.addEventListener("change", gate);
  ack.addEventListener("change", gate);
  async function load() {
    try {
      render(await srtlaCall("GET", "/api/netaddr"));
    } catch (e) {}
  }
  save.addEventListener("click", async () => {
    err.textContent = "";
    save.disabled = true;
    try {
      const body = on.checked
        ? { enable: true, ack: ack.checked, mac: card.value, addr: addr.value.trim(), prefix: parseInt(prefix.value, 10) }
        : { enable: false };
      render(await srtlaCall("POST", "/api/netaddr", body));
      ack.checked = false;
      gate();
    } catch (x) {
      err.textContent = x.message;
      gate();
    }
  });
  box.addEventListener("toggle", () => {
    if (box.open) load();
  });
})();
(function () {
  const card = $("c_ctl"),
    list = $("ctl_list");
  let sig = "",
    data = null,
    busy = false;
  function build(d) {
    const fnOpts = '<option value="">–</option>' + d.functions.map((f) => `<option value="${esc(f.id)}">${esc(f.name)}</option>`).join("");
    list.innerHTML = d.controllers
      .map(
        (c) =>
          `<div class="ctlhd" data-addr="${esc(c.addr)}"><b>${esc(c.name)}</b><span class="muted ctlst"></span></div>` +
          (c.assumed && c.keys.length
            ? '<div class="ph" style="margin:0 0 4px">Der Controller war noch nicht verbunden. Gezeigt wird die übliche Gamepad-Belegung. Sobald er verbunden ist, erscheinen seine echten Tasten, Ihre Auswahl bleibt erhalten.</div>'
            : "") +
          (c.keys.length
            ? c.keys
                .map(
                  (k) =>
                    `<div class="ctlrow" data-addr="${esc(c.addr)}" data-code="${k.code}"><span class="ctlkey">${esc(k.name)}</span><select aria-label="${esc(k.name)}">${fnOpts}</select></div>`,
                )
                .join("")
            : '<div class="muted" style="margin:6px 0">Noch keine Tasten bekannt. Controller einschalten und eine Taste drücken, dann erscheint die Liste.</div>'),
      )
      .join("");
  }
  function paint(d) {
    d.controllers.forEach((c) => {
      const hd = list.querySelector(`.ctlhd[data-addr="${c.addr}"] .ctlst`);
      if (hd) hd.textContent = c.present ? "verbunden" : "getrennt";
      c.keys.forEach((k) => {
        const row = list.querySelector(`.ctlrow[data-addr="${c.addr}"][data-code="${k.code}"]`);
        if (!row) return;
        const sel = row.querySelector("select"),
          v = c.map[String(k.code)] || "";
        if (sel.value !== v && document.activeElement !== sel) sel.value = v;
      });
    });
    const l = d.last || {};
    list.querySelectorAll(".ctlrow.hit").forEach((r) => r.classList.remove("hit"));
    if (l.age != null && l.age < 2) {
      const r = list.querySelector(`.ctlrow[data-addr="${l.addr}"][data-code="${l.code}"]`);
      if (r) r.classList.add("hit");
    }
    $("ctl_err").textContent = d.error || "";
  }
  async function poll() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const d = await srtlaCall("GET", "/api/controller-keys");
      data = d;
      const show = d.controllers.length > 0;
      if (card.hidden === show) {
        card.hidden = !show;
        document.dispatchEvent(new Event("pb-menus-changed"));
      }
      const s = JSON.stringify([
        d.functions.map((f) => f.id),
        d.controllers.map((c) => [c.addr, c.name, c.assumed, c.keys.map((k) => k.code)]),
      ]);
      if (s !== sig && !list.contains(document.activeElement)) {
        sig = s;
        build(d);
      }
      if (s === sig) paint(d);
    } catch (e) {}
    busy = false;
  }
  list.addEventListener("change", async (e) => {
    const sel = e.target.closest("select"),
      row = e.target.closest(".ctlrow");
    if (!sel || !row) return;
    try {
      await srtlaCall("POST", "/api/controller-keys", { addr: row.dataset.addr, code: +row.dataset.code, fn: sel.value });
      $("ctl_err").textContent = "";
    } catch (err) {
      $("ctl_err").textContent = err.message || "Fehler";
    }
    poll();
  });
  let n = 0;
  poll();
  setInterval(() => {
    n++;
    if ((!card.hidden && card.open) || n % 7 === 0) poll();
  }, 700);
})();
(function () {
  const KEY = "pb_cards_open";
  let st = {};
  try {
    st = JSON.parse(localStorage.getItem(KEY) || "{}") || {};
  } catch (e) {
    st = {};
  }
  const cards = [...document.querySelectorAll("details.card[id]")];
  cards.forEach((d) => {
    if (d.id in st) d.open = !!st[d.id];
    d.addEventListener("toggle", () => {
      st[d.id] = d.open;
      try {
        localStorage.setItem(KEY, JSON.stringify(st));
      } catch (e) {}
    });
  });
  $("fold_all").addEventListener("click", () => cards.forEach((d) => (d.open = false)));
  $("unfold_all").addEventListener("click", () => cards.forEach((d) => (d.open = true)));
  $("fold_toggle").addEventListener("click", () => {
    const any = cards.some((d) => d.open);
    cards.forEach((d) => (d.open = !any));
  });
})();
const LOG_NAME = { sparsam: "Sparsam", ausfuehrlich: "Ausführlich" };
async function logLoad() {
  let d;
  try {
    d = await srtlaCall("GET", "/api/logmode");
  } catch (e) {
    return;
  }
  document.querySelectorAll('input[name="logmode"]').forEach((r) => {
    r.checked = r.value === d.mode;
    r.disabled = !d.helper_installed;
  });
  $("log_badge").textContent = LOG_NAME[d.mode] || "–";
  logModeNow = d.mode;
  if (!d.helper_installed)
    $("logmsg").textContent =
      "Der Helfer ist noch nicht installiert. Er kommt mit dem nächsten Software-Update (oder install.sh erneut ausführen).";
  try {
    const b = await srtlaCall("GET", "/api/logs");
    $("lg_dl").disabled = !b.helper_installed;
    if (!b.helper_installed) $("lg_msg").textContent = "Kommt mit dem nächsten Software-Update.";
  } catch (e) {}
}
async function logsDownloadTo(btn, msg) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  btn.disabled = true;
  msg.textContent = "Wird gesammelt …";
  try {
    let st = await srtlaCall("POST", "/api/logs", { action: "collect" });
    const t0 = Date.now();
    while (st.state !== "done") {
      if (st.state === "error") throw new Error(st.message || "unbekannter Fehler");
      if (Date.now() - t0 > 170000) throw new Error("Zeitüberschreitung beim Sammeln");
      await wait(1500);
      try {
        st = await srtlaCall("GET", "/api/logs");
      } catch (e) {}
    }
    const r = await fetch("/api/logs/file");
    if (!r.ok) throw new Error("Datei konnte nicht geladen werden");
    const blob = await r.blob(),
      now = new Date();
    const name =
      "irl4you-protokolle-" +
      now.getFullYear() +
      pad2(now.getMonth() + 1) +
      pad2(now.getDate()) +
      "-" +
      pad2(now.getHours()) +
      pad2(now.getMinutes()) +
      ".txt";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 20000);
    const off = -now.getTimezoneOffset() / 60;
    msg.textContent =
      `Heruntergeladen: ${name} (${Math.max(1, Math.round(blob.size / 1024))} KB). ` +
      (off ? `Zeiten in der Datei sind UTC (bei dir UTC${off > 0 ? "+" : ""}${off}).` : "Zeiten in der Datei sind UTC.") +
      (logModeNow === "sparsam" ? " Im Modus „Sparsam“ fehlt die Zeit vor dem letzten Start der Box." : "");
  } catch (x) {
    msg.textContent = "Fehler: " + x.message;
  }
  btn.disabled = false;
}
