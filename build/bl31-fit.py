#!/usr/bin/env python3
"""Ersetzt die BL31-Teile (atf-1..3) im FIT u-boot.itb des Orange-Pi-Vendor-U-Boots durch die aus einer BL31-ELF.
Aufruf: mkfit.py alt.itb bl31.elf neu.itb   (alles andere bleibt Byte für Byte gleich)"""
import sys, struct, hashlib, subprocess, shutil
old, elf, new = sys.argv[1:4]
d = open(old, "rb").read()
BASE = 0x800
def get(n, p, t="x"):
    return subprocess.check_output(["fdtget", "-t", t, old, f"/images/{n}", p]).split()
sizes = {n: int(get(n, "data-size", "u")[0]) for n in ("uboot", "atf-1", "atf-2", "atf-3", "fdt")}
offs = {n: int(get(n, "data-offset", "u")[0]) for n in sizes}
blob = {n: d[BASE + offs[n]: BASE + offs[n] + sizes[n]] for n in sizes}
# ELF-LOAD-Segmente
e = open(elf, "rb").read()
phoff, = struct.unpack_from("<Q", e, 0x20); phentsize, phnum = struct.unpack_from("<HH", e, 0x36)
segs = {}
for i in range(phnum):
    pt, fl, off, va, pa, fsz, msz, al = struct.unpack_from("<IIQQQQQQ", e, phoff + i * phentsize)
    if pt == 1 and fsz: segs[pa] = e[off:off + fsz]
print({hex(k): hex(len(v)) for k, v in segs.items()})
first = min(segs)  # Hauptteil (niedrigste Adresse)
img = {"atf-1": (first, segs[first])}
others = sorted(a for a in segs if a != first)
# atf-2 hatte 0xff100000, atf-3 0xf0000: nach Adresse zuordnen
img["atf-2"] = (0xff100000, segs[0xff100000]); img["atf-3"] = (0xf0000, segs[0xf0000])
assert set(others) == {0xff100000, 0xf0000}, others
out = bytearray(d[:BASE]); tmp = new + ".dtb"
open(tmp, "wb").write(d[:BASE])
order = ["uboot", "atf-1", "atf-2", "atf-3", "fdt"]
pos = 0; layout = {}
for n in order:
    data = img[n][1] if n in img else blob[n]
    layout[n] = (pos, data)
    pos += (len(data) + 0x1ff) // 0x200 * 0x200
for n in order:
    o, data = layout[n]
    fp = ["fdtput", "-t", "u", tmp]
    subprocess.check_call(fp + [f"/images/{n}", "data-size", str(len(data))])
    subprocess.check_call(fp + [f"/images/{n}", "data-offset", str(o)])
    if n in img: subprocess.check_call(fp + [f"/images/{n}", "load", str(img[n][0])])
    h = hashlib.sha256(data).digest()
    subprocess.check_call(["fdtput", "-t", "x", tmp, f"/images/{n}/hash", "value"] + [h[i:i+4].hex() for i in range(0, 32, 4)])
hdr = open(tmp, "rb").read()
assert len(hdr) <= BASE, len(hdr)
res = bytearray(hdr.ljust(BASE, b"\0"))
for n in order:
    o, data = layout[n]
    res += data.ljust((len(data) + 0x1ff) // 0x200 * 0x200, b"\0")
# Gesamtlänge wie im Original auffüllen (Sektor-Ausrichtung)
open(new, "wb").write(res.ljust(len(d), b"\0") if len(res) <= len(d) else res)
print("ok", hex(len(res)))
