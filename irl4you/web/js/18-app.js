(function () {
  const KEY = "pb_layout",
    VKEY = "pb_views",
    MKEY = "pb_view_mode",
    main = document.querySelector("main");
  const blank = () => ({ order: [], hidden: [], design: "" });
  const ids = (a) => (Array.isArray(a) ? a : []).filter((x) => typeof x === "string");
  const norm = (v) => ({
    order: ids(v && v.order),
    hidden: ids(v && v.hidden),
    design:
      v &&
      (v.design === "klar" ||
        v.design === "kompakt" ||
        v.design === "kompakt-std" ||
        v.design === "kontrast" ||
        v.design === "cockpit" ||
        v.design === "mischpult")
        ? v.design
        : "",
  });
  const views = { desktop: blank(), mobile: blank() };
  let mode = "auto",
    edit = "",
    legacy = false,
    saveT = 0,
    savePending = new Set(),
    loadedAt = 0;
  try {
    const c = JSON.parse(localStorage.getItem(VKEY) || "null");
    if (c && c.desktop && c.mobile) {
      views.desktop = norm(c.desktop);
      views.mobile = norm(c.mobile);
    } else {
      const o = JSON.parse(localStorage.getItem(KEY) || "{}") || {},
        d = localStorage.getItem("pb_design") || "";
      views.desktop = norm(Object.assign({}, o, { design: d }));
      views.mobile = norm(Object.assign({}, o, { design: d }));
      legacy = true;
    }
  } catch (e) {}
  try {
    const m = localStorage.getItem(MKEY);
    if (m === "desktop" || m === "mobile") mode = m;
  } catch (e) {}
  const modeCookie = () => {
    try {
      document.cookie = "pb_view_mode=" + (mode === "mobile" ? "mobile; max-age=31536000" : "; max-age=0") + "; path=/; SameSite=Lax";
    } catch (e) {}
  };
  modeCookie();
  const phoneQ = window.matchMedia ? matchMedia("(max-width:620px)") : null;
  const used = () => (mode === "desktop" || mode === "mobile" ? mode : phoneQ && phoneQ.matches ? "mobile" : "desktop");
  const other = (p) => (p === "desktop" ? "mobile" : "desktop");
  const cache = () => {
    try {
      localStorage.setItem(VKEY, JSON.stringify(views));
    } catch (e) {}
  };
  const allCards = () => [...main.children].filter((el) => el.matches("details.card[id]"));
  const movables = () => allCards().filter((el) => !el.hidden);
  const DEFAULT = allCards().map((e) => e.id);
  const EYE =
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    EYE_OFF =
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.7 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 4.1-.9M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  const hideable = (id) => id !== "c_layout" && id !== "livecard";
  const label = (el) => {
    const s = el.querySelector(":scope>summary");
    if (!s) return el.id;
    const h = s.querySelector(".sumh");
    if (h) {
      const c = h.cloneNode(true);
      c.querySelectorAll("button,.badge,.ibtn").forEach((x) => x.remove());
      return c.textContent.trim();
    }
    let t = "";
    s.childNodes.forEach((n) => {
      if (n.nodeType === 3) t += n.textContent;
    });
    return t.trim() || el.id;
  };
  const orderOf = (v) => {
    const res = v.order.filter((id) => DEFAULT.includes(id));
    DEFAULT.forEach((id, i) => {
      if (res.includes(id)) return;
      let k = i - 1;
      while (k >= 0 && !res.includes(DEFAULT[k])) k--;
      res.splice(k < 0 ? 0 : res.indexOf(DEFAULT[k]) + 1, 0, id);
    });
    return res;
  };
  function applyOrder() {
    orderOf(views[used()]).forEach((id) => main.appendChild($(id)));
  }
  function applyHidden() {
    const st = views[used()];
    document.querySelectorAll("[data-pbhide]").forEach((e) => e.removeAttribute("data-pbhide"));
    st.hidden.forEach((id) => {
      const e = document.getElementById(id);
      if (e && hideable(id)) e.setAttribute("data-pbhide", "");
    });
    document.documentElement.classList.toggle("nohelp", st.hidden.includes("hlp_btn"));
    const compact = st.hidden.includes("heads");
    document.documentElement.classList.toggle("nohead", compact);
    if (compact)
      ["c_chat", "c_hub", "c_prev", "c_deck"].forEach((id) => {
        const e = document.getElementById(id);
        if (e) e.open = true;
      });
  }
  function applyDesign() {
    const id = views[used()].design,
      r = document.documentElement;
    if (id) r.setAttribute("data-design", id);
    else r.removeAttribute("data-design");
    try {
      if (id) localStorage.setItem("pb_design", id);
      else localStorage.removeItem("pb_design");
    } catch (e) {}
    setTheme(curTheme(), false);
    document.dispatchEvent(new Event("pb-design-changed"));
  }
  function applyAll() {
    applyOrder();
    applyHidden();
    applyDesign();
    buildList();
    buildCtl();
  }
  function msg(t, bad) {
    const e = $("vw_msg");
    if (!e) return;
    e.textContent = t || "";
    e.style.color = bad ? "var(--crit)" : "";
  }
  function save(p) {
    cache();
    savePending.add(p);
    clearTimeout(saveT);
    saveT = setTimeout(async () => {
      const todo = [...savePending];
      savePending.clear();
      try {
        for (const q of todo)
          await srtlaCall("POST", "/api/layout", { profile: q, order: views[q].order, hidden: views[q].hidden, design: views[q].design });
        msg("✓ Gespeichert (gilt für alle Geräte)");
        setTimeout(() => {
          const e = $("vw_msg");
          if (e && e.textContent.startsWith("✓")) e.textContent = "";
        }, 3000);
      } catch (x) {
        todo.forEach((q) => savePending.add(q));
        msg("Nicht auf der Box gespeichert: " + ((x && x.message) || "keine Verbindung") + " (gilt vorerst nur in diesem Browser)", true);
      }
    }, 500);
  }
  async function load() {
    if (savePending.size) return;
    try {
      let r = await srtlaCall("GET", "/api/layout");
      if (!r.set) {
        r = await srtlaCall("POST", "/api/layout", { init: { desktop: views.desktop, mobile: views.mobile } });
      }
      const n = { desktop: norm(r.desktop), mobile: norm(r.mobile) };
      if (JSON.stringify(n) !== JSON.stringify(views)) {
        views.desktop = n.desktop;
        views.mobile = n.mobile;
        cache();
        applyAll();
      } else if (legacy) {
        cache();
      }
      legacy = false;
      loadedAt = Date.now();
    } catch (e) {}
  }
  function buildCtl() {
    const now = $("view_now");
    if (!now) return;
    const u = used(),
      n = window.innerWidth;
    now.textContent = `Dieses Gerät zeigt gerade die Ansicht ${u === "mobile" ? "Mobil" : "Desktop"} (${mode === "auto" ? "automatisch, Fensterbreite " + n + " Pixel" : "von Hand gewählt"}).`;
    $("view_mode").value = mode;
    for (const p of ["desktop", "mobile"])
      for (const k of ["vw_", "mv_"]) {
        $(k + p).classList.toggle("on", edit === p);
        $(k + p).setAttribute("aria-pressed", String(edit === p));
      }
    $("vw_copy").textContent = edit === "desktop" ? "Von Mobil übernehmen" : "Von Desktop übernehmen";
  }
  function buildList() {
    const box = $("lay_list"),
      v = views[edit];
    if (box.querySelector(".mcard.drag")) return;
    box.textContent = "";
    const tile = (id, txt) => {
      const off = id === "foot_info" ? !(window.pbFootInfoGet && window.pbFootInfoGet()) : v.hidden.includes(id),
        t = document.createElement("button");
      t.type = "button";
      t.className = "mtile sub" + (off ? " off" : "");
      t.dataset.id = id;
      t.setAttribute("aria-pressed", String(!off));
      t.textContent = txt;
      return t;
    };
    const head = (el) => {
      const off = v.hidden.includes(el.id),
        fixed = el.id === "c_layout",
        r = document.createElement("div");
      r.className = "mrow" + (off && !fixed ? " off" : "");
      const g = document.createElement("span");
      g.className = "mgrip";
      g.tabIndex = 0;
      g.dataset.id = el.id;
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", "Menü verschieben: ziehen oder Pfeiltasten hoch und runter");
      g.title = "Zum Verschieben ziehen";
      g.textContent = "⠿";
      const n = document.createElement("span");
      n.className = "mname";
      n.textContent = label(el);
      const e = document.createElement("button");
      e.type = "button";
      e.className = "meye";
      e.dataset.id = el.id;
      e.disabled = fixed;
      e.setAttribute("aria-pressed", String(!off || fixed));
      e.setAttribute("aria-label", label(el) + (off ? " einblenden" : " ausblenden"));
      e.title = fixed ? "Optionen bleiben immer sichtbar" : off ? "Einblenden" : "Ausblenden";
      e.innerHTML = off && !fixed ? EYE_OFF : EYE;
      r.append(g, n, e);
      return r;
    };
    const page = document.createElement("div");
    page.className = "minipage " + edit;
    orderOf(v)
      .map((id) => $(id))
      .filter((el) => el && !el.hidden)
      .forEach((el) => {
      const c = document.createElement("div");
      c.className = "mcard";
      c.dataset.id = el.id;
      c.appendChild(head(el));
      const subs =
        v.hidden.includes(el.id) && el.id !== "c_layout"
          ? []
          : el.id === "c_layout"
          ? ["opt_design"].map((id) => $(id)).filter(Boolean)
          : hideable(el.id)
            ? [...el.querySelectorAll("details.subsec[id],#statdet")]
            : [];
      if (subs.length) {
        const w = document.createElement("div");
        w.className = "msubs";
        subs.forEach((sub) => w.appendChild(tile(sub.id, label(sub))));
        c.appendChild(w);
      }
      page.appendChild(c);
    });
    box.appendChild(page);
    {
      const h = document.createElement("div");
      h.className = "sech";
      h.textContent = "Weitere Elemente";
      box.appendChild(h);
    }
    {
      const w = document.createElement("div");
      w.className = "msubs flat";
      [
        ["sm_btn", "Streammodus"],
        ["hlp_btn", "Hilfe-Knöpfe (i)"],
        ["heads", "Überschriften von Chat und Vorschau"],
        ["foot_info", "Info-Knopf (ⓘ) in der Fußleiste"],
      ].forEach(([id, txt]) => w.appendChild(tile(id, txt)));
      box.appendChild(w);
    }
    window.pbFootRows(box);
  }
  function move(id, dir) {
    const v = views[edit],
      all = orderOf(v).filter((x) => $(x) && !$(x).hidden),
      i = all.indexOf(id),
      j = i + dir;
    if (i < 0 || j < 0 || j >= all.length) return;
    [all[i], all[j]] = [all[j], all[i]];
    const rest = orderOf(v).filter((x) => !all.includes(x));
    v.order = all.concat(rest);
    save(edit);
    if (edit === used()) applyOrder();
    buildList();
    const b = $("lay_list").querySelector('.mgrip[data-id="' + id + '"]');
    if (b) b.focus();
  }
  function setEdit(p) {
    edit = p;
    buildList();
    buildCtl();
    document.dispatchEvent(new Event("pb-design-changed"));
  }
  function setHidden(id, hide) {
    const h = views[edit].hidden,
      i = h.indexOf(id);
    if (!hide && i >= 0) h.splice(i, 1);
    if (hide && i < 0) h.push(id);
    save(edit);
    if (edit === used()) applyHidden();
  }
  $("lay_list").addEventListener("click", (e) => {
    const t = e.target.closest("button.mtile[data-id],button.meye[data-id]");
    if (!t || t.disabled) return;
    if (t.dataset.id === "foot_info") window.pbFootInfo(!window.pbFootInfoGet());
    else setHidden(t.dataset.id, !views[edit].hidden.includes(t.dataset.id));
    buildList();
    const again = [...$("lay_list").querySelectorAll("button.mtile,button.meye")].find((x) => x.dataset.id === t.dataset.id);
    if (again) again.focus();
  });
  $("lay_list").addEventListener("keydown", (e) => {
    const g = e.target.closest(".mgrip");
    if (g && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      move(g.dataset.id, e.key === "ArrowUp" ? -1 : 1);
    }
  });
  $("lay_list").addEventListener("pointerdown", (e) => {
    const g = e.target.closest(".mgrip"),
      page = g && g.closest(".minipage"),
      card = g && g.closest(".mcard");
    if (!g || !page || e.button > 0) return;
    e.preventDefault();
    g.setPointerCapture(e.pointerId);
    card.classList.add("drag");
    page.classList.add("dragging");
    // Nichts wird während des Ziehens im DOM umgehängt (sonst verliert der Griff den Zeiger): die gezogene Karte folgt dem Zeiger,
    // die anderen weichen per transform aus, erst beim Loslassen wird die Reihenfolge übernommen.
    const cards = [...page.children],
      from = cards.indexOf(card),
      pageY = (y) => y + window.scrollY,
      tops = cards.map((c) => pageY(c.getBoundingClientRect().top)),
      mids = cards.map((c, i) => tops[i] + c.offsetHeight / 2),
      slot = (tops[from + 1] || tops[from] + card.offsetHeight + 8) - tops[from],
      off = Math.max(0, Math.min(card.offsetHeight, pageY(e.clientY) - tops[from]));
    let to = from;
    const over = (ev) => {
      if (ev.clientY < 90) window.scrollBy(0, -14);
      else if (ev.clientY > window.innerHeight - 60) window.scrollBy(0, 14);
      const dy = pageY(ev.clientY) - off - tops[from],
        center = tops[from] + dy + card.offsetHeight / 2;
      to = cards.filter((c, i) => i !== from && mids[i] < center).length;
      card.style.transform = "translateY(" + dy + "px)";
      cards.forEach((c, i) => {
        if (i === from) return;
        const k = i < from ? i : i - 1,
          shift = i < from ? (k >= to ? slot : 0) : k < to ? -slot : 0;
        c.style.transform = shift ? "translateY(" + shift + "px)" : "";
      });
    };
    const end = () => {
      if (!card.classList.contains("drag")) return;
      for (const [t, f] of [["pointermove", over], ["pointerup", end], ["pointercancel", end], ["mouseup", end]]) document.removeEventListener(t, f);
      g.removeEventListener("lostpointercapture", end);
      cards.forEach((c) => (c.style.transform = ""));
      card.classList.remove("drag");
      page.classList.remove("dragging");
      const ids = cards.filter((c) => c !== card).map((c) => c.dataset.id),
        v = views[edit];
      ids.splice(to, 0, card.dataset.id);
      if (ids.join() === orderOf(v).filter((x) => ids.includes(x)).join()) return;
      v.order = ids.concat(orderOf(v).filter((x) => !ids.includes(x)));
      save(edit);
      if (edit === used()) applyOrder();
      buildList();
    };
    for (const [t, f] of [["pointermove", over], ["pointerup", end], ["pointercancel", end], ["mouseup", end]]) document.addEventListener(t, f);
    g.addEventListener("lostpointercapture", end);
  });
  $("lay_showall").addEventListener("click", () => {
    views[edit].hidden = [];
    save(edit);
    if (edit === used()) applyHidden();
    buildList();
  });
  $("lay_reset").addEventListener("click", () => {
    views[edit].order = [];
    save(edit);
    if (edit === used()) applyOrder();
    buildList();
  });
  $("view_mode").addEventListener("change", (e) => {
    mode = e.target.value;
    try {
      if (mode === "auto") localStorage.removeItem(MKEY);
      else localStorage.setItem(MKEY, mode);
    } catch (x) {}
    modeCookie();
    if (window.top !== window) {
      try {
        top.location.reload();
        return;
      } catch (x) {}
    }
    if (mode === "mobile" && phoneQ && !phoneQ.matches) {
      location.reload();
      return;
    }
    edit = used();
    applyAll();
    document.dispatchEvent(new Event("pb-design-changed"));
  });
  for (const p of ["desktop", "mobile"]) for (const k of ["vw_", "mv_"]) $(k + p).addEventListener("click", () => setEdit(p));
  $("vw_copy").addEventListener("click", () => {
    views[edit] = norm(JSON.parse(JSON.stringify(views[other(edit)])));
    save(edit);
    if (edit === used()) {
      applyOrder();
      applyHidden();
      applyDesign();
    }
    buildList();
    buildCtl();
  });
  window.pbViews = {
    used: () => used(),
    edit: () => edit,
    design: () => views[edit].design,
    setDesign: (id) => {
      views[edit].design =
        id === "klar" || id === "kompakt" || id === "kompakt-std" || id === "kontrast" || id === "cockpit" || id === "mischpult" ? id : "";
      save(edit);
      if (edit === used()) applyDesign();
    },
  };
  document.addEventListener("pb-menus-changed", () => {
    applyOrder();
    applyHidden();
    buildList();
  });
  if (phoneQ)
    phoneQ.addEventListener("change", () => {
      if (mode === "auto") {
        applyAll();
      }
    });
  window.addEventListener("resize", () => {
    if (mode === "auto") buildCtl();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && Date.now() - loadedAt > 5000) load();
  });
  edit = used();
  applyOrder();
  applyHidden();
  applyDesign();
  buildList();
  buildCtl();
  document.addEventListener("pb-design-changed", () => setTimeout(frameBg, 50));
  frameBg();
  load();
})();
