const $ = (id) => document.getElementById(id);
var pbUpdating = 0;
(function () {
  const f = window.fetch.bind(window);
  let gone = false;
  window.fetch = function (u, o) {
    return f(u, o).then((r) => {
      if (r.status === 401 && !gone && !pbUpdating && String(u).indexOf("/api/") === 0 && String(u).indexOf("/api/login") !== 0) {
        gone = true;
        location.reload();
      }
      return r;
    });
  };
})();
const _last = {};
function due(key, card, idleMs) {
  if (document.hidden) return false;
  const c = card && $(card);
  if (!c || c.open) return true;
  const n = Date.now();
  if (!_last[key] || n - _last[key] >= idleMs) {
    _last[key] = n;
    return true;
  }
  return false;
}
const fmt = (v, d = 1) => (v == null ? "–" : Number(v).toFixed(d));
const ROLE = { main: "Hauptbild", pip: "Bild-in-Bild", extra: "Weitere" };
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
function setHtml(el, html) {
  if (el.dataset.h === html) return;
  el.dataset.h = html;
  el.innerHTML = html;
}
let camsByKey = {};
const camDotCls = (c) =>
  "dot" + (c.state === "live" ? (c.pic === "wartet" || c.pic === "aus" ? " wait" : "") : c.state === "unknown" ? " unk" : " off");
const camDotTitle = (c) =>
  c.state !== "live"
    ? c.state === "unknown"
      ? "Status unbekannt"
      : "Kein Signal"
    : c.pic === "an"
      ? "Sendet und ist im Bild"
      : c.pic === "wartet"
        ? `Sendet, kommt in ${c.pic_wait} s ins Bild`
        : c.pic === "aus"
          ? "Sendet, ist noch nicht im Bild"
          : "Sendet";
function upDot(u) {
  if (!u) return '<span class="dot unk" title="Nicht in Betrieb (keine Sendung)"></span>';
  const rtt = u.srtt == null ? "" : `, Laufzeit ${u.srtt} ms`;
  if (u.state === "an") return `<span class="dot" title="Wird genutzt${rtt}"></span>`;
  if (u.state === "reserve")
    return `<span class="dot wait" title="In Reserve${rtt} (Laufzeit zu hoch oder unruhig, es werden kaum Pakete gesendet)"></span>`;
  return '<span class="dot off" title="Nicht verbunden oder kein Netz"></span>';
}
function battHtml(c) {
  if (c.battery == null) return "";
  const col = c.battery > 75 ? "var(--ok)" : c.battery < 25 ? "var(--crit)" : "",
    age = c.battery_age,
    stale = age != null && age > 600;
  const when = stale ? ` (Stand vor ${age >= 3600 ? Math.round(age / 3600) + " Std." : Math.round(age / 60) + " Min."})` : "";
  return `<span class="batt${stale ? " stale" : ""}" style="${col ? "color:" + col : ""}" title="Akku ${c.battery} %${c.charging ? ", am Ladekabel (lädt oder wird versorgt)" : ""}${when}">${c.charging ? "🔌 " : ""}${c.battery} %</span>`;
}
function paintCamDots(list) {
  const el = $("cam_dots");
  if (!el) return;
  const l = camSorted(list || [])
    .filter((c) => !c.parked)
    .slice(0, 4);
  setHtml(el, l.map((c) => `<span class="${camDotCls(c)}" title="${esc(camDotTitle(c))}"></span>`).join(""));
  el.setAttribute("aria-label", l.length ? l.map((c) => c.name).join(", ") : "");
}
const camSeenLive = {};
const CAM_HOLD_TOP_MS = 120000;
function camSorted(list) {
  const nowMs = Date.now();
  for (const c of list) if (c.state === "live" || c.state === "unknown") camSeenLive[c.id] = nowMs;
  const quiet = (c) =>
    c.parked ? 2 : c.state === "live" || c.state === "unknown" || nowMs - (camSeenLive[c.id] || 0) < CAM_HOLD_TOP_MS ? 0 : 1;
  return list.slice().sort((x, y) => quiet(x) - quiet(y));
}
function renderCamLights(list) {
  list = camSorted(list).filter((c) => !c.parked);
  const any = list.some((c) => c.battery != null),
    box = $("camlights");
  box.classList.toggle("hasbatt", any);
  const head =
    '<div class="hrow"><div class="sech">Kameras</div>' +
    (any && list.length ? '<div class="sech mid">Akku</div><div class="sech">&nbsp;</div>' : "") +
    "</div>";
  setHtml(
    box,
    list.length
      ? head +
          list
            .map(
              (c) =>
                `<div class="row"><span class="nm"><span class="${camDotCls(c)}" title="${esc(camDotTitle(c))}"></span>${esc(c.name)}</span>${any ? `<span class="battcell">${battHtml(c)}</span>` : ""}<span>${c.state === "live" ? `<b>${fmt(c.mbit)}</b><span class="unit">Mbit/s</span>` : '<span class="unit">–</span>'}</span></div>`,
            )
            .join("")
      : '<div class="muted">Noch keine Kamera angelegt.</div>',
  );
}
let netOpts = [];
const netLabel = (o) =>
  `${o.label}${connNames[o.iface] ? " (" + connNames[o.iface] + ")" : ""} · ${o.cam_ip || o.ip}${o.cam_ip && o.cam_ip !== o.ip ? " (feste Adresse)" : ""}`;
function camNetHtml(c) {
  if (c.via_src === "hdmi") return `<span class="camnet muted" title="Das Bild kommt vom HDMI-Eingang der Box">HDMI-Eingang</span>`;
  if ((c.key || "").startsWith("dji-")) {
    const own = c.via_src === "dji";
    const nets = netOpts.filter((o) => o.wifi !== false || (own && c.via === o.iface));
    const opts = [`<option value=""${own ? "" : " selected"}>– wählen –</option>`].concat(
      nets.map((o) => `<option value="${esc(o.iface)}"${own && c.via === o.iface ? " selected" : ""}>${esc(netLabel(o))}</option>`),
    );
    if (own && c.via === "manual") opts.push(`<option value="manual" selected disabled>Manuell (in der DJI-Karte)</option>`);
    else if (own && c.via && !netOpts.some((o) => o.iface === c.via))
      opts.push(`<option value="${esc(c.via)}" selected>${esc(c.via)} (nicht verbunden)</option>`);
    return `<span class="camnet withbtn"><select class="camnetsel" data-dji="${esc(c.key)}" title="Verbindung dieser Kamera: Ihre Adresse gilt für dieses Netz. Eine Änderung gilt ab der nächsten Verbindung der Kamera." aria-label="Verbindung">${opts.join("")}</select><button type="button" class="camreconn sec" data-dji="${esc(c.key)}" title="Neu verbinden: Die geänderte Verbindung gilt erst danach (der Stream der Kamera ist kurz weg)" aria-label="Neu verbinden">↻</button></span>`;
  }
  const opts = [`<option value="">Hauptverbindung (Standard)</option>`].concat(
    netOpts.map((o) => `<option value="${esc(o.iface)}"${c.iface === o.iface ? " selected" : ""}>${esc(netLabel(o))}</option>`),
  );
  if (c.iface && !netOpts.some((o) => o.iface === c.iface))
    opts.push(`<option value="${esc(c.iface)}" selected>${esc(c.iface)} (nicht verbunden)</option>`);
  return `<span class="camnet"><select class="camnetsel" data-id="${c.id}" title="Verbindung dieser Kamera: Ihre Adresse gilt für dieses Netz" aria-label="Verbindung">${opts.join("")}</select></span>`;
}
const QR = (() => {
  const EXP = new Uint8Array(512),
    LOG = new Uint8Array(256);
  for (let i = 0, x = 1; i < 255; i++) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 256) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);
  const gen = (n) => {
    let g = [1];
    for (let i = 0; i < n; i++) {
      const r = new Array(g.length + 1).fill(0);
      for (let j = 0; j < g.length; j++) {
        r[j] ^= g[j];
        r[j + 1] ^= mul(g[j], EXP[i]);
      }
      g = r;
    }
    return g;
  };
  const rs = (data, n) => {
    const g = gen(n),
      r = new Array(n).fill(0);
    for (const d of data) {
      const f = d ^ r.shift();
      r.push(0);
      if (f) for (let i = 0; i < n; i++) r[i] ^= mul(g[i + 1], f);
    }
    return r;
  };
  const V = [
    null,
    [26, 10, [[1, 16]]],
    [44, 16, [[1, 28]]],
    [70, 26, [[1, 44]]],
    [100, 18, [[2, 32]]],
    [134, 24, [[2, 43]]],
    [172, 16, [[4, 27]]],
    [196, 18, [[4, 31]]],
    [
      242,
      22,
      [
        [2, 38],
        [2, 39],
      ],
    ],
    [
      292,
      22,
      [
        [3, 36],
        [2, 37],
      ],
    ],
    [
      346,
      26,
      [
        [4, 43],
        [1, 44],
      ],
    ],
  ];
  const VL = [
    null,
    [26, 7, [[1, 19]]],
    [44, 10, [[1, 34]]],
    [70, 15, [[1, 55]]],
    [100, 20, [[1, 80]]],
    [134, 26, [[1, 108]]],
    [172, 18, [[2, 68]]],
    [196, 20, [[2, 78]]],
    [242, 24, [[2, 97]]],
    [292, 30, [[2, 116]]],
    [
      346,
      18,
      [
        [2, 68],
        [2, 69],
      ],
    ],
  ];
  const AL = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]];
  const MASK = [
    (x, y) => (x + y) % 2 === 0,
    (x, y) => y % 2 === 0,
    (x, y) => x % 3 === 0,
    (x, y) => (x + y) % 3 === 0,
    (x, y) => (Math.floor(x / 3) + (y >> 1)) % 2 === 0,
    (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
    (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
    (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
  ];
  function penalty(m, n) {
    let p = 0,
      dark = 0;
    const line = (get) => {
      let run = 1;
      for (let i = 1; i <= n; i++) {
        if (i < n && get(i) === get(i - 1)) run++;
        else {
          if (run >= 5) p += run - 2;
          run = 1;
        }
      }
      for (let i = 0; i + 11 <= n; i++) {
        const w = [];
        for (let k = 0; k < 11; k++) w.push(get(i + k));
        const s = w.join("");
        if (s === "10111010000" || s === "00001011101") p += 40;
      }
    };
    for (let y = 0; y < n; y++) {
      line((i) => m[y][i]);
      line((i) => m[i][y]);
      for (let x = 0; x < n; x++) {
        dark += m[y][x];
        if (x && y && m[y][x] === m[y][x - 1] && m[y][x] === m[y - 1][x] && m[y][x] === m[y - 1][x - 1]) p += 3;
      }
    }
    return p + Math.floor(Math.abs(dark * 20 - n * n * 10) / (n * n)) * 10;
  }
  function make(text, V, ecb) {
    const bytes = [...new TextEncoder().encode(text)];
    let v = 1,
      cap = 0;
    for (; v <= 10; v++) {
      cap = V[v][2].reduce((a, [c, d]) => a + c * d, 0);
      if (bytes.length <= (cap * 8 - (v < 10 ? 12 : 20)) >> 3) break;
    }
    if (v > 10) return null;
    const bits = [],
      put = (val, k) => {
        for (let i = k - 1; i >= 0; i--) bits.push((val >> i) & 1);
      };
    put(4, 4);
    put(bytes.length, v < 10 ? 8 : 16);
    bytes.forEach((b) => put(b, 8));
    put(0, Math.min(4, cap * 8 - bits.length));
    while (bits.length % 8) bits.push(0);
    for (let q = 0; bits.length < cap * 8; q ^= 1) put(q ? 0x11 : 0xec, 8);
    const cw = [];
    for (let i = 0; i < bits.length; i += 8) cw.push(parseInt(bits.slice(i, i + 8).join(""), 2));
    const [, ecn, groups] = V[v],
      blocks = [];
    let pos = 0;
    for (const [c, d] of groups)
      for (let i = 0; i < c; i++) {
        const data = cw.slice(pos, pos + d);
        pos += d;
        blocks.push({ data, ec: rs(data, ecn) });
      }
    const all = [];
    for (let i = 0; i < Math.max(...blocks.map((b) => b.data.length)); i++)
      for (const b of blocks) if (i < b.data.length) all.push(b.data[i]);
    for (let i = 0; i < ecn; i++) for (const b of blocks) all.push(b.ec[i]);
    const n = 17 + 4 * v,
      B = [...Array(n)].map(() => new Array(n).fill(0)),
      fn = [...Array(n)].map(() => new Array(n).fill(false));
    const set = (x, y, val) => {
      B[y][x] = val ? 1 : 0;
      fn[y][x] = true;
    };
    const finder = (cx, cy) => {
      for (let dy = -4; dy <= 4; dy++)
        for (let dx = -4; dx <= 4; dx++) {
          const x = cx + dx,
            y = cy + dy;
          if (x < 0 || y < 0 || x >= n || y >= n) continue;
          const d = Math.max(Math.abs(dx), Math.abs(dy));
          set(x, y, d <= 1 || d === 3);
        }
    };
    finder(3, 3);
    finder(n - 4, 3);
    finder(3, n - 4);
    for (let i = 8; i < n - 8; i++) {
      set(i, 6, i % 2 === 0);
      set(6, i, i % 2 === 0);
    }
    const al = AL[v];
    for (const cy of al)
      for (const cx of al) {
        if ((cx === 6 && cy === 6) || (cx === 6 && cy === al[al.length - 1]) || (cy === 6 && cx === al[al.length - 1])) continue;
        for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    for (let i = 0; i < 9; i++) {
      if (i !== 6) {
        fn[8][i] = true;
        fn[i][8] = true;
      }
    }
    for (let i = 0; i < 8; i++) {
      fn[8][n - 1 - i] = true;
      fn[n - 1 - i][8] = true;
    }
    set(8, n - 8, 1);
    if (v >= 7)
      for (let i = 0; i < 18; i++) {
        const a = n - 11 + (i % 3),
          b = Math.floor(i / 3);
        fn[b][a] = true;
        fn[a][b] = true;
      }
    const bo = [];
    all.forEach((b) => {
      for (let i = 7; i >= 0; i--) bo.push((b >> i) & 1);
    });
    let k = 0;
    for (let right = n - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < n; vert++)
        for (let j = 0; j < 2; j++) {
          const x = right - j,
            y = ((right + 1) & 2) === 0 ? n - 1 - vert : vert;
          if (!fn[y][x]) {
            B[y][x] = k < bo.length ? bo[k] : 0;
            k++;
          }
        }
    }
    const vbits = (() => {
      if (v < 7) return 0;
      let r = v;
      for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >> 11) * 0x1f25);
      return (v << 12) | r;
    })();
    let best = null,
      bestP = 1e9;
    for (let mk = 0; mk < 8; mk++) {
      const m = B.map((r) => r.slice());
      for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (!fn[y][x] && MASK[mk](x, y)) m[y][x] ^= 1;
      const fd = (ecb << 3) | mk;
      let r = fd;
      for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >> 9) * 0x537);
      const fb = ((fd << 10) | r) ^ 0x5412,
        bit = (i) => (fb >> i) & 1;
      for (let i = 0; i <= 5; i++) m[i][8] = bit(i);
      m[7][8] = bit(6);
      m[8][8] = bit(7);
      m[8][7] = bit(8);
      for (let i = 9; i < 15; i++) m[8][14 - i] = bit(i);
      for (let i = 0; i < 8; i++) m[8][n - 1 - i] = bit(i);
      for (let i = 8; i < 15; i++) m[n - 15 + i][8] = bit(i);
      m[n - 8][8] = 1;
      if (v >= 7)
        for (let i = 0; i < 18; i++) {
          const a = n - 11 + (i % 3),
            b = Math.floor(i / 3),
            t = (vbits >> i) & 1;
          m[b][a] = t;
          m[a][b] = t;
        }
      const pn = penalty(m, n);
      if (pn < bestP) {
        bestP = pn;
        best = m;
      }
    }
    return best;
  }
  const matrix = (text) => make(text, V, 0) || make(text, VL, 1);
  const svg = (text) => {
    const m = matrix(text);
    if (!m) return "";
    const n = m.length;
    let d = "";
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (m[y][x]) d += `M${x + 4} ${y + 4}h1v1h-1z`;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n + 8} ${n + 8}" width="220" height="220" shape-rendering="crispEdges" role="img" aria-label="QR-Code"><rect width="100%" height="100%" fill="#fff"/><path d="${d}" fill="#000"/></svg>`;
  };
  return { matrix, svg };
})();
const larixLink = (url, name) => "larix://set/v1?conn[][url]=" + encodeURIComponent(url) + "&conn[][name]=" + encodeURIComponent(name);
