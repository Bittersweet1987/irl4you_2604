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
    const tile = (id, txt, cls, parentOff) => {
      const off = v.hidden.includes(id),
        t = document.createElement("button");
      t.type = "button";
      t.className = "mtile " + cls + (off ? " off" : "") + (parentOff ? " dim" : "");
      t.dataset.id = id;
      t.setAttribute("aria-pressed", String(!off));
      if (cls === "head") {
        const n = document.createElement("span");
        n.textContent = txt;
        const e = document.createElement("span");
        e.setAttribute("aria-hidden", "true");
        e.textContent = off ? "○" : "●";
        t.append(n, e);
      } else t.textContent = txt;
      return t;
    };
    const page = document.createElement("div");
    page.className = "minipage " + edit;
    movables().forEach((el) => {
      const c = document.createElement("div");
      c.className = "mcard" + (el.classList.contains("wide") ? " wide" : "");
      const head = tile(el.id, label(el), "head", false);
      if (el.id === "c_layout") {
        head.classList.remove("off");
        head.classList.add("fixed");
        head.disabled = true;
        head.setAttribute("aria-pressed", "true");
      }
      c.appendChild(head);
      const subs =
        v.hidden.includes(el.id) && el.id !== "c_layout"
          ? []
          : el.id === "c_layout"
          ? ["opt_design", "opt_order"].map((id) => $(id)).filter(Boolean)
          : hideable(el.id)
            ? [...el.querySelectorAll("details.subsec[id],#statdet")]
            : [];
      if (subs.length) {
        const w = document.createElement("div");
        w.className = "msubs";
        subs.forEach((sub) => w.appendChild(tile(sub.id, label(sub), "sub", false)));
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
      ].forEach(([id, txt]) => w.appendChild(tile(id, txt, "sub", false)));
      box.appendChild(w);
    }
    window.pbFootRows(box);
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
  function setHidden(id, hide) {
    const h = views[edit].hidden,
      i = h.indexOf(id);
    if (!hide && i >= 0) h.splice(i, 1);
    if (hide && i < 0) h.push(id);
    save(edit);
    if (edit === used()) applyHidden();
    else buildOrder();
  }
  $("lay_list").addEventListener("change", (e) => {
    const c = e.target.closest("input[data-id]");
    if (c) setHidden(c.dataset.id, !c.checked);
  });
  $("lay_list").addEventListener("click", (e) => {
    const t = e.target.closest("button.mtile[data-id]");
    if (!t || t.disabled) return;
    setHidden(t.dataset.id, !views[edit].hidden.includes(t.dataset.id));
    buildList();
    const again = [...$("lay_list").querySelectorAll("button.mtile")].find((x) => x.dataset.id === t.dataset.id);
    if (again) again.focus();
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
