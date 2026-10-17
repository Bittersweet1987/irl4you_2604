let logModeNow = "";
const pad2 = (n) => String(n).padStart(2, "0");
const logsDownload = () => logsDownloadTo($("lg_dl"), $("lg_msg"));
$("lg_dl").addEventListener("click", logsDownload);
document.querySelectorAll('input[name="logmode"]').forEach((r) =>
  r.addEventListener("change", async () => {
    if (!r.checked) return;
    $("logmsg").textContent = "Wird umgestellt …";
    try {
      await srtlaCall("POST", "/api/logmode", { mode: r.value });
    } catch (x) {
      $("logmsg").textContent = x.message;
      logLoad();
      return;
    }
    setTimeout(async () => {
      await logLoad();
      $("logmsg").textContent =
        r.value === "sparsam"
          ? "Umgestellt: Protokolle nur noch im Arbeitsspeicher."
          : "Umgestellt: Protokolle werden dauerhaft gespeichert.";
    }, 3000);
  }),
);
$("c_logs").addEventListener("toggle", () => {
  if ($("c_logs").open) logLoad();
});
logLoad();
const THEME_ICONS = {
  dark: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  light: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>',
};
function curTheme() {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}
function setTheme(t, save) {
  document.documentElement.setAttribute("data-theme", t);
  if (save) {
    try {
      localStorage.setItem("pb_theme", t);
    } catch (e) {}
  }
  const b = $("theme_btn");
  b.innerHTML = THEME_ICONS[t];
  b.title = t === "dark" ? "Auf hell wechseln" : "Auf dunkel wechseln";
  b.setAttribute("aria-label", b.title);
  const m = document.querySelector('meta[name="theme-color"]');
  if (m) m.content = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  frameBg();
}
function frameBg() {
  if (typeof window !== "undefined" && window.top !== window) {
    try {
      top.document.body.style.background = getComputedStyle(document.body).backgroundColor;
    } catch (e) {}
  }
}
$("theme_btn").addEventListener("click", () => setTheme(curTheme() === "dark" ? "light" : "dark", true));
setTheme(curTheme(), false);
