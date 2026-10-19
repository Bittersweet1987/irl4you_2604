// Umschalter nach Designvorgabe (docs/DESIGN.md): Ein <select data-seg> mit 2 bis 4 festen, kurzen Optionen erscheint als Knopfgruppe (.seg).
// Das Select bleibt die Datenquelle (Wert lesen/setzen, "change", disabled wie bisher); die Knöpfe spiegeln es.
function segEnhance(sel) {
  const box = document.createElement("div");
  box.className = "seg";
  box.setAttribute("role", "group");
  const lab = sel.getAttribute("aria-label") || (sel.closest("label") ? sel.closest("label").firstChild.textContent.trim() : "");
  if (lab) box.setAttribute("aria-label", lab);
  const btns = Array.from(sel.options).map((o) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = o.textContent;
    b.dataset.value = o.value;
    b.addEventListener("click", () => {
      if (sel.value === o.value) return;
      sel.value = o.value;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    });
    box.appendChild(b);
    return b;
  });
  const sync = () => btns.forEach((b) => {
    b.classList.toggle("on", b.dataset.value === sel.value);
    b.setAttribute("aria-pressed", String(b.dataset.value === sel.value));
    b.disabled = sel.disabled;
  });
  // Skripte setzen den Wert und disabled direkt (ohne Ereignis): beides mitziehen
  const hook = (prop) => {
    const d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, prop);
    Object.defineProperty(sel, prop, {
      configurable: true,
      get() { return d.get.call(this); },
      set(v) { d.set.call(this, v); sync(); },
    });
  };
  ["value", "selectedIndex", "disabled"].forEach(hook);
  sel.addEventListener("change", sync);
  sel.style.display = "none";
  sel.after(box);
  sync();
}
document.querySelectorAll("select[data-seg]").forEach(segEnhance);
