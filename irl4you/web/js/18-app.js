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
      ["c_chat", "c_prev", "c_deck"].forEach((id) => {
        const e = document.getElementById(id);
        if (e) e.open = true;
      });
    buildOrder();
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
    for (const p of ["desktop", "mobile"]) {
      $("vw_" + p).setAttribute("aria-pressed", String(edit === p));
      $("vw_" + p).classList.toggle("on", edit === p);
    }
    $("vw_copy").textContent = edit === "desktop" ? "Von Mobil übernehmen" : "Von Desktop übernehmen";
  }
  function buildList() {
    const box = $("lay_list"),
      v = views[edit];
    box.textContent = "";
    const row = (g, id, txt, sub) => {
      const l = document.createElement("label");
      l.className = "optrow" + (sub ? " sub" : "");
      const c = document.createElement("input");
      c.type = "checkbox";
      c.dataset.id = id;
      c.checked = !v.hidden.includes(id);
      l.appendChild(c);
      const s = document.createElement("span");
      s.textContent = txt;
      l.appendChild(s);
      g.appendChild(l);
    };
    movables().forEach((el) => {
      const g = document.createElement("div");
      g.className = "optgrp";
      row(g, el.id, label(el), false);
      if (el.id === "c_layout") {
        const c = g.querySelector("input");
        c.checked = true;
        c.disabled = true;
        g.firstChild.classList.add("fixed");
        ["opt_design", "opt_order"].forEach((id) => {
          const sub = $(id);
          if (sub) row(g, id, label(sub), true);
        });
      } else if (hideable(el.id)) el.querySelectorAll("details.subsec[id],#statdet").forEach((sub) => row(g, sub.id, label(sub), true));
      box.appendChild(g);
    });
    {
      const g = document.createElement("div");
      g.className = "optgrp";
      row(g, "sm_btn", "Streammodus", false);
      box.appendChild(g);
    }
    {
      const g = document.createElement("div");
      g.className = "optgrp";
      row(g, "hlp_btn", "Hilfe-Knöpfe (i)", false);
      box.appendChild(g);
    }
    {
      const g = document.createElement("div");
      g.className = "optgrp";
      row(g, "heads", "Überschriften von Chat und Vorschau", false);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "helpbtn";
      b.textContent = "i";
      b.setAttribute("aria-label", "Erklärung zeigen");
      b.setAttribute("aria-expanded", "false");
      g.firstChild.appendChild(b);
      const h = document.createElement("div");
      h.className = "ph";
      h.hidden = true;
      h.textContent =
        "Blendet bei Chat und Vorschau die Überschrift und die Kopfzeile aus, um Platz zu sparen. Die Knöpfe (Einstellungen des Chats, Start und Stop der Vorschau) bleiben als kleine Symbole oben rechts über dem Inhalt.";
      b.addEventListener("click", (ev) => {
        ev.preventDefault();
        h.hidden = !h.hidden;
        b.setAttribute("aria-expanded", String(!h.hidden));
      });
      g.appendChild(h);
      box.appendChild(g);
    }
    {
      const g = document.createElement("div");
      g.className = "optgrp";
      const l = document.createElement("label");
      l.className = "optrow";
      const t = document.createElement("span");
      t.textContent = "Fußleiste am Handy";
      l.appendChild(t);
      const sel = document.createElement("select");
      sel.id = "foot_mode";
      sel.style.marginLeft = "8px";
      for (const [v2, txt] of [
        ["auto", "Automatisch"],
        ["always", "Immer anzeigen"],
        ["hide", "Ausblenden bei Chat oder Vorschau"],
        ["off", "Immer ausblenden"],
      ]) {
        const o = document.createElement("option");
        o.value = v2;
        o.textContent = txt;
        sel.appendChild(o);
      }
      sel.value = window.pbFootGet ? window.pbFootGet() : "auto";
      sel.addEventListener("change", () => window.pbFootMode && window.pbFootMode(sel.value));
      l.appendChild(sel);
      g.appendChild(l);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "helpbtn";
      b.textContent = "i";
      b.setAttribute("aria-label", "Erklärung zeigen");
      b.setAttribute("aria-expanded", "false");
      l.appendChild(b);
      const h = document.createElement("div");
      h.className = "ph";
      h.hidden = true;
      h.textContent =
        "Die Knöpfe unten am Handy (Live/Stop, Kameras, Ton). Automatisch: Sie gleiten beim Runterscrollen weg und kommen beim Hochscrollen zurück, solange Chat oder Vorschau zu sehen sind; ohne beide bleiben sie immer da. Diese Einstellung gilt nur für dieses Gerät.";
      g.appendChild(h);
      b.addEventListener("click", (ev) => {
        ev.preventDefault();
        h.hidden = !h.hidden;
        b.setAttribute("aria-expanded", String(!h.hidden));
      });
      box.appendChild(g);
    }
    {
      const g = document.createElement("div");
      g.className = "optgrp";
      const l = document.createElement("label");
      l.className = "optrow";
      const t = document.createElement("span");
      t.textContent = "Anordnung der Fußleiste am Handy";
      l.appendChild(t);
      const sel = document.createElement("select");
      sel.id = "foot_layout";
      sel.style.marginLeft = "8px";
      for (const [v2, txt] of [
        ["one", "Unten, eine Zeile"],
        ["two", "Unten, zwei Zeilen (größere Knöpfe)"],
        ["left", "Links, eine Spalte"],
        ["right", "Rechts, eine Spalte"],
      ]) {
        const o = document.createElement("option");
        o.value = v2;
        o.textContent = txt;
        sel.appendChild(o);
      }
      sel.value = window.pbFootLayoutGet ? window.pbFootLayoutGet() : "one";
      sel.addEventListener("change", () => window.pbFootLayout && window.pbFootLayout(sel.value));
      l.appendChild(sel);
      g.appendChild(l);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "helpbtn";
      b.textContent = "i";
      b.setAttribute("aria-label", "Erklärung zeigen");
      b.setAttribute("aria-expanded", "false");
      l.appendChild(b);
      const h = document.createElement("div");
      h.className = "ph";
      h.hidden = true;
      h.textContent =
        "Eine Zeile ist die bisherige Fußleiste. Zwei Zeilen machen sie größer (für große, gut treffbare Knöpfe): Live und Ton gehen über beide Zeilen, die Kameras stehen 2 × 2. Links oder Rechts stellt die Knöpfe als eine Spalte an den Rand. Diese Einstellung gilt nur für dieses Gerät.";
      g.appendChild(h);
      b.addEventListener("click", (ev) => {
        ev.preventDefault();
        h.hidden = !h.hidden;
        b.setAttribute("aria-expanded", String(!h.hidden));
      });
      const l2 = document.createElement("label");
      l2.className = "optrow";
      const c = document.createElement("input");
      c.type = "checkbox";
      c.id = "foot_info";
      c.checked = window.pbFootInfoGet ? window.pbFootInfoGet() : true;
      c.addEventListener("change", () => window.pbFootInfo && window.pbFootInfo(c.checked));
      l2.appendChild(c);
      const t2 = document.createElement("span");
      t2.textContent = "Info-Knopf (ⓘ) in der Fußleiste anzeigen";
      l2.appendChild(t2);
      g.appendChild(l2);
      box.appendChild(g);
    }
  }
  function buildOrder(focus) {
    const box = $("ord_list"),
      v = views[edit],
      all = orderOf(v)
        .map((id) => $(id))
        .filter((el) => el && !el.hidden);
    box.textContent = "";
    all.forEach((el, i) => {
      const r = document.createElement("div");
      r.className = "ordrow" + (v.hidden.includes(el.id) && hideable(el.id) ? " off" : "");
      const t = document.createElement("span");
      t.textContent = label(el);
      r.appendChild(t);
      const m = document.createElement("span");
      m.className = "mvs";
      for (const [dir, txt, tip] of [
        [-1, "▲", "Menü nach oben schieben"],
        [1, "▼", "Menü nach unten schieben"],
      ]) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "mv";
        b.dataset.id = el.id;
        b.dataset.dir = dir;
        b.textContent = txt;
        b.title = tip;
        b.setAttribute("aria-label", tip);
        b.disabled = dir < 0 ? i === 0 : i === all.length - 1;
        m.appendChild(b);
      }
      r.appendChild(m);
      box.appendChild(r);
    });
    if (focus) {
      const mine = [...box.querySelectorAll("button.mv")].filter((x) => x.dataset.id === focus.id && !x.disabled);
      const b = mine.find((x) => +x.dataset.dir === focus.dir) || mine[0];
      if (b) b.focus();
    }
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
    buildOrder({ id, dir });
  }
  function setEdit(p) {
    edit = p;
    buildList();
    buildOrder();
    buildCtl();
    document.dispatchEvent(new Event("pb-design-changed"));
  }
  $("ord_list").addEventListener("click", (ev) => {
    const b = ev.target.closest("button.mv[data-id]");
    if (!b || b.disabled) return;
    move(b.dataset.id, +b.dataset.dir);
  });
  $("lay_list").addEventListener("change", (e) => {
    const c = e.target.closest("input[data-id]");
    if (!c) return;
    const h = views[edit].hidden,
      id = c.dataset.id,
      i = h.indexOf(id);
    if (c.checked && i >= 0) h.splice(i, 1);
    if (!c.checked && i < 0) h.push(id);
    save(edit);
    if (edit === used()) applyHidden();
    else buildOrder();
  });
  $("lay_showall").addEventListener("click", () => {
    views[edit].hidden = [];
    save(edit);
    if (edit === used()) applyHidden();
    buildList();
    buildOrder();
  });
  $("lay_reset").addEventListener("click", () => {
    views[edit].order = [];
    save(edit);
    if (edit === used()) applyOrder();
    buildOrder();
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
  for (const p of ["desktop", "mobile"]) $("vw_" + p).addEventListener("click", () => setEdit(p));
  $("vw_copy").addEventListener("click", () => {
    views[edit] = norm(JSON.parse(JSON.stringify(views[other(edit)])));
    save(edit);
    if (edit === used()) {
      applyOrder();
      applyHidden();
      applyDesign();
    }
    buildList();
    buildOrder();
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
