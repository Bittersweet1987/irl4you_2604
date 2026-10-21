// Fußleiste, zweite Seite: Rotation ein/aus, Rotation-Einstellungen als Popup und Sperren der Oberfläche.
// Sperren: Die Ansicht bleibt genau so stehen (aufgeklappte Menüs, Scrollstand), im Inhalt lässt sich nichts mehr anklicken oder scrollen; Kopfzeile und Fußleiste bleiben bedienbar.
(function () {
  const root = document.documentElement,
    page = $("mf_page"),
    rot = $("mf_rot"),
    set = $("mf_rotset"),
    lock = $("mf_lock"),
    main = document.querySelector("main");
  let locked = false,
    y0 = 0;
  function paint() {
    const p = window.pbRotation,
      on = !!(p && p.on());
    rot.classList.toggle("on", on);
    rot.setAttribute("aria-pressed", String(on));
    rot.querySelector(".mf-state").textContent = p && !p.available() ? "nicht möglich" : on ? "an" : "aus";
    lock.classList.toggle("on", locked);
    lock.setAttribute("aria-pressed", String(locked));
    lock.querySelector(".mf-state").textContent = locked ? "gesperrt" : "frei";
  }
  page.addEventListener("click", () => {
    const on = !root.classList.contains("mfpage2");
    root.classList.toggle("mfpage2", on);
    page.setAttribute("aria-pressed", String(on));
    if (on && window.pbRotation) window.pbRotation.load();
    paint();
    if (typeof sizeFoot === "function") sizeFoot();
  });
  rot.addEventListener("click", async () => {
    const p = window.pbRotation;
    if (!p) return;
    const ok = await p.toggle();
    if (!ok && typeof footMsg === "function") footMsg("Die Rotation braucht Bild-in-Bild: Zuerst im Bildaufbau ein kleines Bild festlegen.");
    paint();
  });
  set.addEventListener("click", () => window.pbRotation && window.pbRotation.open());
  const stop = (e) => {
    if (locked && !e.target.closest("header, #mfoot, #rot_pop, .mf-pick")) e.preventDefault();
  };
  function setLock(v) {
    if (v === locked) return;
    locked = v;
    if (v) y0 = window.scrollY;
    root.classList.toggle("locked", v);
    if (main) main.inert = v;
    if (v) window.scrollTo(0, y0);
    paint();
  }
  lock.addEventListener("click", () => setLock(!locked));
  // Scrollen per Finger, Mausrad und Tasten im gesperrten Zustand verhindern (Kopfzeile, Fußleiste und Popup bleiben bedienbar)
  for (const n of ["touchmove", "wheel"]) document.addEventListener(n, stop, { passive: false });
  document.addEventListener("keydown", (e) => {
    if (locked && [" ", "PageDown", "PageUp", "Home", "End", "ArrowUp", "ArrowDown"].includes(e.key) && !e.target.closest("input, select, textarea")) e.preventDefault();
  });
  window.addEventListener("scroll", () => {
    if (locked && Math.abs(window.scrollY - y0) > 1) window.scrollTo(0, y0);
  });
  document.addEventListener("pb-rot-changed", paint);
  paint();
})();
