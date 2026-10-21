// Kamera-Knöpfe der Fußleiste am Handy: Knopf antippen und wischen (Richtung weg von der Leiste: unten nach oben, links nach rechts, rechts nach links) zeigt alle
// aktiven Kameras. Wer den Finger auf einer Kamera loslässt, legt sie auf den Platz dieses Knopfes; liegt sie schon auf einem anderen Knopf, tauschen beide.
(function () {
  const box = $("mf_tools"),
    MIN = 28;
  let st = null,
    last = 0;
  const dir = () => {
    const l = window.pbFootLayoutGet ? window.pbFootLayoutGet() : "one";
    return l === "left" ? "right" : l === "right" ? "left" : "up";
  };
  const along = (d, dx, dy) => (d === "up" ? -dy : d === "right" ? dx : -dx),
    across = (d, dx, dy) => (d === "up" ? Math.abs(dx) : Math.abs(dy));
  function items(btn) {
    const f = (typeof sendData !== "undefined" && sendData && sendData.footer) || {},
      list = f.all && f.all.length ? f.all : (f.cams || []).map((c) => ({ key: c.key, name: c.name, state: c.state, slot: c.slot }));
    return list.map((c) => ({ key: c.key, name: c.name || c.key, live: c.state !== "offline", slot: c.slot, cur: c.key === btn.dataset.key }));
  }
  function slotName(n) {
    return n === 0 ? "Hauptbild" : n > 0 ? "kleines Bild " + n : "";
  }
  function show(btn, d) {
    const p = document.createElement("div");
    p.id = "mf_pick";
    p.className = "mf-pick";
    p.setAttribute("role", "listbox");
    const h = document.createElement("div");
    h.className = "mf-pick-h";
    h.textContent = "Kamera für diesen Knopf wählen: Finger auf eine Kamera ziehen und loslassen";
    p.appendChild(h);
    for (const c of items(btn)) {
      const it = document.createElement("div");
      it.className = "mf-pick-item" + (c.cur ? " cur" : "");
      it.dataset.key = c.key;
      it.setAttribute("role", "option");
      const dot = document.createElement("span");
      dot.className = "mf-pick-dot" + (c.live ? " live" : "");
      const nm = document.createElement("span");
      nm.className = "mf-pick-name";
      nm.textContent = c.name;
      const tag = document.createElement("span");
      tag.className = "mf-pick-tag";
      tag.textContent = c.cur ? "dieser Knopf" : c.slot >= 0 ? "liegt auf " + slotName(c.slot) + ": tauscht" : "";
      it.append(dot, nm, tag);
      p.appendChild(it);
    }
    const r = $("mfoot").getBoundingClientRect();
    p.style.maxHeight = Math.round(window.innerHeight * 0.7) + "px";
    if (d === "up") {
      p.style.left = p.style.right = "8px";
      p.style.bottom = Math.round(window.innerHeight - r.top + 8) + "px";
    } else {
      p.style.top = "8px";
      p.style.maxWidth = "min(360px, " + Math.round(window.innerWidth - r.width - 24) + "px)";
      if (d === "right") p.style.left = Math.round(r.right + 8) + "px";
      else p.style.right = Math.round(window.innerWidth - r.left + 8) + "px";
    }
    document.body.appendChild(p);
    return p;
  }
  function hit(pick, x, y) {
    const e = document.elementFromPoint(x, y),
      it = e && e.closest ? e.closest(".mf-pick-item") : null;
    return it && pick.contains(it) ? it : null;
  }
  async function finish(x, y, cancel) {
    const s = st;
    st = null;
    const t = cancel ? null : hit(s.pick, x, y);
    s.pick.remove();
    last = Date.now();
    if (!t || t.dataset.key === s.btn.dataset.key) {
      setTimeout(() => (footBusy = false), 400);
      return;
    }
    try {
      const r = await srtlaCall("POST", "/api/pipeline/assign", { slot: +s.btn.dataset.slot, key: t.dataset.key });
      footMsg((r && r.note) || "Kamera gelegt.");
    } catch (e) {
      footMsg(e.message);
    } finally {
      footBusy = false;
      sendLoad();
    }
  }
  box.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".mf-cam");
    st = !b || (e.pointerType === "mouse" && e.button !== 0) ? null : { btn: b, x0: e.clientX, y0: e.clientY, d: dir(), pick: null };
    if (st)
      try {
        b.setPointerCapture(e.pointerId);       // Maus: die Bewegung auch außerhalb der Leiste weiter verfolgen (Finger tut das von selbst)
      } catch (x) {}
  });
  // im Fangen-Schritt, damit die bisherige Bedienung (Lang drücken, Doppeltippen) während des Wischens nicht dazwischenfunkt
  box.addEventListener(
    "pointermove",
    (e) => {
      if (!st) return;
      const dx = e.clientX - st.x0,
        dy = e.clientY - st.y0;
      if (!st.pick) {
        if (along(st.d, dx, dy) < MIN || across(st.d, dx, dy) > along(st.d, dx, dy)) return;
        footBusy = true;
        try {
          st.btn.setPointerCapture(e.pointerId);
          if (navigator.vibrate) navigator.vibrate(15);
        } catch (x) {}
        st.pick = show(st.btn, st.d);
        setTimeout(() => (footBusy = true), 0);      // die bisherige Bedienung bricht beim ersten Weitergeben das Lang-Drücken ab und gibt die Leiste frei: wieder sperren
        return;                                       // dieses eine Ereignis geht weiter, damit das Lang-Drücken (Kamera deaktivieren) nicht mehr auslöst
      }
      e.stopPropagation();
      const t = hit(st.pick, e.clientX, e.clientY);
      st.pick.querySelectorAll(".mf-pick-item.on").forEach((x) => x !== t && x.classList.remove("on"));
      if (t) t.classList.add("on");
    },
    true,
  );
  for (const n of ["pointerup", "pointercancel"])
    box.addEventListener(
      n,
      (e) => {
        if (!st) return;
        if (!st.pick) {
          st = null;
          return;
        }
        e.stopPropagation();
        finish(e.clientX, e.clientY, n === "pointercancel");
      },
      true,
    );
  // nach dem Wischen kein Klick auf den Knopf (kurz drücken würde das Hauptbild tauschen)
  box.addEventListener(
    "click",
    (e) => {
      if (Date.now() - last < 500) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    },
    true,
  );
})();
