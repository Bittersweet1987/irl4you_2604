// Streamerhub-Chat: Adresse des Chat-Overlays eintragen; die Box ruft die Seite selbst auf (Weiterleiter auf eigenem Port) und zeigt sie hier im Rahmen.
(function () {
  const wrap = $("hub_wrap"),
    msg = $("hub_msg"),
    inU = $("hub_in"),
    inH = $("hub_h"),
    inMH = $("hub_mh"),
    box = $("hub_optbox"),
    gear = $("hub_opt");
  let saved = { url: "", height: 600, mobile_height: 500, port: 8782 },
    shown = null,
    loaded = false;
  const clean = (v) => {
    v = String(v || "").trim();
    if (!v) return "";
    let u;
    try {
      u = new URL(v);
    } catch (e) {
      return null;
    }
    return v.length <= 500 && u.protocol === "https:" && u.hostname && !u.username && !u.password ? u.href : null;
  };
  const mob = () => window.pbViews && window.pbViews.used() === "mobile",
    high = () => (mob() ? saved.mobile_height : saved.height);
  function note(t) {
    msg.hidden = !t;
    msg.textContent = t || "";
  }
  function src() {
    const u = new URL(saved.url),
      h = location.hostname.includes(":") ? "[" + location.hostname + "]" : location.hostname;
    return "http://" + h + ":" + saved.port + u.pathname + u.search;
  }
  function render(force) {
    const k = saved.url + "|" + location.hostname;
    if (!force && k === shown) {
      const f = wrap.querySelector("iframe");
      if (f) f.style.height = high() + "px";
      return;
    }
    shown = k;
    wrap.textContent = "";
    if (!loaded) return note("Wird geladen …");
    if (!saved.url) return note("Adresse des Chat-Overlays über ⚙ eintragen.");
    if (location.protocol !== "http:") return note("Der Streamerhub-Chat geht nur, wenn die Box über http geöffnet ist (nicht über https).");
    note("");
    const f = document.createElement("iframe");
    f.src = src();
    f.title = "Streamerhub-Chat";
    f.loading = "lazy";
    f.referrerPolicy = "no-referrer";
    f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
    f.style.height = high() + "px";
    wrap.appendChild(f);
  }
  function fill() {
    inU.value = saved.url;
    inH.value = saved.height;
    inMH.value = saved.mobile_height;
  }
  function take(d) {
    if (!d || typeof d !== "object") return;
    saved = { url: d.url || "", height: +d.height || 600, mobile_height: +d.mobile_height || 500, port: +d.port || 8782 };
    if (box.hidden) fill();
  }
  async function load() {
    try {
      take(await srtlaCall("GET", "/api/hub"));
      if (!loaded) {
        loaded = true;
        if (!saved.url) {
          box.hidden = false;
          gear.setAttribute("aria-expanded", "true");
          fill();
        }
      }
      render();
    } catch (e) {
      if (!loaded) note("Der Streamerhub-Chat konnte nicht von der Box geladen werden.");
    }
  }
  gear.addEventListener("click", () => {
    box.hidden = !box.hidden;
    gear.setAttribute("aria-expanded", box.hidden ? "false" : "true");
    if (!box.hidden) {
      fill();
      inU.focus();
    }
  });
  const save = async () => {
    const u = clean(inU.value);
    if (u === null) return note("Die Adresse muss mit https:// beginnen.");
    try {
      take(await srtlaCall("POST", "/api/hub", { url: u, height: +inH.value || 600, mobile_height: +inMH.value || 500 }));
    } catch (e) {
      return note("Nicht auf der Box gespeichert: " + ((e && e.message) || "keine Verbindung"));
    }
    box.hidden = true;
    gear.setAttribute("aria-expanded", "false");
    render(true);
  };
  $("hub_save").addEventListener("click", save);
  for (const x of [inU, inH, inMH])
    x.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        save();
      }
    });
  document.addEventListener("pb-design-changed", () => render());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
  setTimeout(load, 400);
})();
