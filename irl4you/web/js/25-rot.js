// Kamera-Rotation: Einstellungen (im Bildaufbau und als Popup in der Fußleiste), geteilter Stand und Schnellumschalter.
// Der Sendeteil wechselt die Kameras der gewählten Bilder reihum nach der Wechselzeit; was fest bleiben soll, wählt man hier ab.
(function () {
  const SLOT_NAMES = ["main", "pip", "pip2", "pip3"],
    SLOT_LABEL = { main: "Hauptbild", pip: "Kleines Bild 1", pip2: "Kleines Bild 2", pip3: "Kleines Bild 3" };
  let data = null,
    busy = false,
    saveT = null,
    pending = {};
  const hosts = new Set();
  const el = (tag, cls, txt) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  };
  const chk = (label, checked, on, hint) => {
    const l = el("label", "chk rotchk"),
      i = el("input");
    i.type = "checkbox";
    i.checked = !!checked;
    i.addEventListener("change", () => on(i.checked));
    l.append(i, el("span", "", label));
    if (hint) l.append(el("span", "muted rothint", hint));
    return l;
  };
  function render(host) {
    host.textContent = "";
    if (!data) {
      host.append(el("div", "muted", "Wird geladen …"));
      return;
    }
    const r = data.rotation || {},
      free = SLOT_NAMES.filter((s) => data.slots[s]);
    if (!data.pip) {
      host.append(el("div", "ph", "Die Rotation braucht Bild-in-Bild: Zuerst im Bildaufbau mindestens ein kleines Bild festlegen und speichern."));
      return;
    }
    host.append(chk("Rotation aktiv", r.on, (v) => save({ on: v })));
    const body = el("div", "rotbody");
    body.hidden = !r.on;
    body.append(el("div", "sech", "Welche Bilder wechseln"));
    const sg = el("div", "seg"),
      b1 = el("button", r.all ? "on" : "", "Alle Bilder"),
      b2 = el("button", r.all ? "" : "on", "Nur diese Bilder");
    for (const [b, all] of [[b1, true], [b2, false]]) {
      b.type = "button";
      b.setAttribute("aria-pressed", String(r.all === all));
      b.addEventListener("click", () => save({ all }));
      sg.append(b);
    }
    body.append(sg);
    if (!r.all) {
      const sl = el("div", "rotslots");
      for (const s of free) sl.append(chk(SLOT_LABEL[s], (r.slots || []).includes(s), (v) => save({ slots: free.filter((x) => (x === s ? v : (r.slots || []).includes(x))) })));
      body.append(sl);
    }
    body.append(el("div", "sech", "Wechselzeit"));
    const row = el("div", "rotsec"),
      inp = el("input");
    inp.type = "number";
    inp.min = 5;
    inp.max = 3600;
    inp.step = 1;
    inp.inputMode = "numeric";
    inp.value = r.seconds || 30;
    inp.setAttribute("aria-label", "Wechselzeit in Sekunden");
    inp.addEventListener("change", () => save({ seconds: +inp.value }));
    row.append(inp, el("span", "muted", "Sekunden (5 bis 3600)"));
    body.append(row);
    body.append(el("div", "sech", "Kameras für den Wechsel"));
    const pool = Array.isArray(r.pool) ? r.pool : null,
      cur = (k) => (pool ? pool.includes(k) : true);
    const list = el("div", "rotcams");
    for (const c of data.cameras || []) {
      const tag = [c.inactive ? "deaktiviert" : "", !c.online ? "nicht verbunden" : "", c.slot >= 0 ? SLOT_LABEL[SLOT_NAMES[c.slot]] : ""].filter(Boolean).join(" · ");
      list.append(
        chk(c.name, cur(c.key), (v) => {
          const keys = (data.cameras || []).map((x) => x.key),
            now = new Set(pool || keys);
          v ? now.add(c.key) : now.delete(c.key);
          save({ pool: keys.filter((k) => now.has(k)) });
        }, tag),
      );
    }
    body.append(list);
    body.append(
      el(
        "div",
        "ph",
        "Wechseln dürfen nur verbundene Kameras, die nicht deaktiviert sind. Kameras auf Bildern, die nicht wechseln, werden nie getauscht. Eine deaktivierte Kamera kommt in die Rotation, sobald sie wieder aktiv ist.",
      ),
    );
    host.append(body);
    host.append(el("div", "ph rotmsg", host.dataset.msg || ""));
  }
  const paint = () => hosts.forEach(render);
  let sig = "";
  async function load() {
    try {
      data = await srtlaCall("GET", "/api/pipeline/rotation");
    } catch (e) {}
    const now = JSON.stringify(data);
    if (now !== sig) {
      sig = now;
      if (![...hosts].some((h) => h.contains(document.activeElement))) paint();      // nichts neu zeichnen, solange gerade getippt wird
      document.dispatchEvent(new Event("pb-rot-changed"));
    }
    return data;
  }
  async function post(body) {
    try {
      data = await srtlaCall("POST", "/api/pipeline/rotation", body);
      hosts.forEach((h) => (h.dataset.msg = "Gespeichert."));
    } catch (e) {
      hosts.forEach((h) => (h.dataset.msg = e.message || "Nicht gespeichert"));
      try {
        data = await srtlaCall("GET", "/api/pipeline/rotation");
      } catch (x) {}
    }
    paint();
    document.dispatchEvent(new Event("pb-rot-changed"));
    return data;
  }
  function save(ch) {
    pending = Object.assign(pending, ch);
    if (data) data.rotation = Object.assign({}, data.rotation, ch);
    paint();
    clearTimeout(saveT);
    saveT = setTimeout(() => {
      const b = pending;
      pending = {};
      post(b);
    }, 250);
  }
  // Popup (Schnellzugriff aus der Fußleiste)
  const pop = el("div", "rotpop");
  pop.hidden = true;
  pop.id = "rot_pop";
  const box = el("div", "rotpop-box"),
    head = el("div", "rotpop-h"),
    close = el("button", "sec small", "Schließen"),
    pform = el("div", "rotform");
  close.type = "button";
  head.append(el("b", "", "Kamera-Rotation"), close);
  box.append(head, pform);
  pop.append(box);
  document.body.append(pop);
  hosts.add(pform);
  const shut = () => {
    pop.hidden = true;
  };
  close.addEventListener("click", shut);
  pop.addEventListener("click", (e) => {
    if (e.target === pop) shut();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !pop.hidden) shut();
  });
  window.pbRotation = {
    data: () => data,
    load,
    on: () => !!(data && data.pip && data.rotation && data.rotation.on),
    available: () => !!(data && data.pip),
    toggle: async () => {
      if (!data) await load();
      if (!data || !data.pip) return false;
      await post({ on: !(data.rotation && data.rotation.on) });
      return true;
    },
    open: async () => {
      pop.hidden = false;
      await load();
    },
  };
  const sec = $("rot_form");
  if (sec) {
    hosts.add(sec);
    $("pipe_rot").addEventListener("toggle", () => {
      if ($("pipe_rot").open) load();
    });
  }
  load();
  setInterval(() => {
    if (!document.hidden && (!pop.hidden || ($("pipe_rot") && $("pipe_rot").open) || document.documentElement.classList.contains("mfpage2"))) load();
  }, 5000);
})();
