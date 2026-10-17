try {
  var t = localStorage.getItem("pb_theme"),
    d = localStorage.getItem("pb_design"),
    e = document.documentElement;
  if (d === "klar" || d === "kompakt" || d === "kompakt-std" || d === "kontrast" || d === "cockpit" || d === "mischpult")
    e.setAttribute("data-design", d);
  else d = "";
  if (t === "light" || t === "dark") e.setAttribute("data-theme", t);
  else if (d === "klar") e.setAttribute("data-theme", "light");
} catch (e) {}
