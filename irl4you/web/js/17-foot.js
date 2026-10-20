// Optionen: Einstellungen der Fußleiste am Handy (gelten nur für dieses Gerät), von 18-app.js unter "Weitere Elemente" eingehängt.
window.pbFootRows = function (box) {
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
      box.appendChild(g);
    }
};
