"""IRL4YOU BOX Oberfläche: Messwerte des Systems (CPU, Speicher, Temperaturen) und der Sendung."""

import glob
import json
import math
import os
import random
import re
import threading
import time

try:
    import pipbox_preview
except ImportError:
    pipbox_preview = None

from .common import LIMITS, NET_PREFIXES, NET_SKIP, read


ENC_STATS_FILE = "/run/pipbox-send/encoder-stats.json"


THERMAL_NAMES = {"soc-thermal": "SoC", "bigcore0-thermal": "Große Kerne 4–5", "bigcore1-thermal": "Große Kerne 6–7",
                 "littlecore-thermal": "Kleine Kerne 0–3", "center-thermal": "Mitte", "gpu-thermal": "GPU", "npu-thermal": "NPU"}


def devfreq_loads():
    out = {}
    try:
        names = sorted(os.listdir("/sys/class/devfreq"))
    except OSError:
        return out
    for n in names:
        if "gpu" not in n:
            continue
        raw = (read(f"/sys/class/devfreq/{n}/load", "") or "").strip()
        m = re.match(r"^(\d+)@(\d+)Hz$", raw)
        if m:
            out["gpu"] = {"load_pct": int(m.group(1)), "mhz": int(m.group(2)) // 1000000}
    npu = (read("/run/irl4you-npu", "") or "").split()
    if len(npu) == 3 and all(x.isdigit() for x in npu):
        out["npu"] = {"load_pct": max(int(x) for x in npu), "cores": [int(x) for x in npu]}
    return out


def disk_usage(path="/"):
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
    return {"total_gb": round(total / 1e9, 1), "free_gb": round(free / 1e9, 1), "used_gb": round((total - st.f_bfree * st.f_frsize) / 1e9, 1),
            "used_pct": round(100.0 * (1 - free / total), 1) if total else None}


def send_stats():
    """Messwerte der Sendung aus der Statistik von irl4you-encoder (Version 1), in den Feldern, die die Oberfläche kennt."""
    try:
        mtime = os.stat(ENC_STATS_FILE).st_mtime
        if time.time() - mtime > 6:
            return None
        e = json.loads(read(ENC_STATS_FILE, "") or "{}")
    except (OSError, ValueError):
        return None
    if not isinstance(e, dict) or not e:
        return None
    srt = e.get("srt") if isinstance(e.get("srt"), dict) else {}
    rate = e.get("rate") if isinstance(e.get("rate"), dict) else {}
    kb = srt.get("send_kbps")
    d = {"fps": e.get("fps"), "bitrate_kbps": rate.get("kbps"), "rtt_ms": srt.get("rtt_ms"),
         "send_mbps": round(kb / 1000.0, 2) if isinstance(kb, (int, float)) else None,
         "snd_buf_pkts": srt.get("buf_pkts"), "snd_buf_ms": srt.get("buf_ms"), "retrans_total": srt.get("resent"),
         "loss_total": srt.get("lost"), "drop_total": srt.get("dropped"), "sent_total": srt.get("sent")}
    sent = d.get("sent_total")
    out = dict(d)
    out["mtime"] = mtime
    t = d.get("loss_total")
    out["loss_pct"] = round(100.0 * t / sent, 2) if isinstance(t, (int, float)) and isinstance(sent, (int, float)) and sent > 0 and t >= 0 else None
    return out


class Sampler:

    D_GRACE, D_SUSTAIN, D_GAP = 120.0, 15.0, 6.0
    D_BENIGN_NAME = re.compile(r"^(kworker|jbd2|sugov|apt-get|apt|dpkg|mmcqd|kswapd\d*|flush-|ext4|systemd-journal)")
    D_BENIGN_WCHAN = re.compile(r"(__wait_on_buffer|wait_on_page|io_schedule|mmc_blk|jbd2|generic_file_buffered_read|bit_wait|blk_)")

    def __init__(self, demo):
        self.demo = demo
        self.prev_cpu = None
        self.prev_net = None
        self.prev_t = None
        self.sm_net, self.sm_zero = {}, {}
        self.pay_prev, self.pay_sm, self.pay_zero = None, None, 0
        self._lock = threading.Lock()
        self._d_since, self._d_last = None, 0.0

    NET_SMOOTH_S = 4.0
    NET_SMOOTH_GAP_S = 15.0
    NET_ZERO_MBIT, NET_ZERO_N = 0.1, 2

    def smooth_rates(self, raw, dt_s):
        fresh = dt_s is None or dt_s > self.NET_SMOOTH_GAP_S
        a = 1.0 - math.exp(-max(dt_s or 0.0, 0.0) / self.NET_SMOOTH_S)
        out, new, zeros = {}, {}, {}
        for n, r in raw.items():
            p = None if fresh else self.sm_net.get(n)
            cur = {}
            for k in ("rx_mbit", "tx_mbit"):
                z = (self.sm_zero.get((n, k), 0) + 1) if r[k] < self.NET_ZERO_MBIT else 0
                zeros[(n, k)] = z
                cur[k] = r[k] if (p is None or z >= self.NET_ZERO_N) else p[k] + (r[k] - p[k]) * a
            new[n] = cur
            out[n] = {k: round(v, 2) for k, v in cur.items()}
        self.sm_net, self.sm_zero = new, zeros
        return out

    SRT_PAYLOAD_BYTES = 1316

    def payload_rate(self, send):
        def num(k):
            v = send.get(k) if isinstance(send, dict) else None
            return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        t, sent, retr = num("mtime"), num("sent_total"), num("retrans_total")
        if t is None or sent is None or sent < 0:
            self.pay_prev, self.pay_sm, self.pay_zero = None, None, 0
            return None
        unique = sent - (retr if retr is not None and 0 <= retr <= sent else 0.0)
        cur, prev = (t, unique), self.pay_prev
        if prev is not None and t <= prev[0]:
            return None if self.pay_sm is None else round(self.pay_sm, 2)
        self.pay_prev = cur
        dt = None if prev is None else t - prev[0]
        if dt is None or dt > self.NET_SMOOTH_GAP_S or unique < prev[1]:
            self.pay_sm, self.pay_zero = None, 0
            return None
        raw = (unique - prev[1]) * self.SRT_PAYLOAD_BYTES * 8 / dt / 1e6
        if self.pay_sm is None:
            self.pay_sm = raw
        elif raw < self.NET_ZERO_MBIT and self.pay_zero + 1 >= self.NET_ZERO_N:
            self.pay_sm = raw
        else:
            self.pay_sm += (raw - self.pay_sm) * (1.0 - math.exp(-dt / self.NET_SMOOTH_S))
        self.pay_zero = self.pay_zero + 1 if raw < self.NET_ZERO_MBIT else 0
        return round(self.pay_sm, 2)

    @classmethod
    def d_relevant(cls, names):
        return [n for n in (names or []) if not (cls.D_BENIGN_NAME.match(n) or cls.D_BENIGN_WCHAN.search(n.partition("@")[2]))]

    def _d_alert(self, rel, now, uptime):
        if not rel:
            self._d_since = None
            return 0
        if self._d_since is None or now - self._d_last > self.D_GAP:
            self._d_since = now
        self._d_last = now
        if uptime is not None and uptime < self.D_GRACE:
            return 0
        return len(rel) if now - self._d_since >= self.D_SUSTAIN else 0

    def cpu_times(self):
        out = []
        for line in (read("/proc/stat", "") or "").splitlines():
            if line.startswith("cpu") and line[3:4].isdigit():
                v = list(map(int, line.split()[1:]))
                idle = v[3] + (v[4] if len(v) > 4 else 0)
                out.append((sum(v), idle))
        return out

    @staticmethod
    def fan_pwm():
        try:
            for d in sorted(os.listdir("/sys/class/hwmon")):
                base = f"/sys/class/hwmon/{d}"
                if read(base + "/name", "").strip() == "pwmfan":
                    v = read(base + "/pwm1")
                    return int(v) if v is not None and 0 <= int(v) <= 255 else None
        except (OSError, ValueError):
            pass
        return None

    @staticmethod
    def blocked_threads(proc="/proc", limit=20):
        out = []
        for d in sorted(glob.glob(proc + "/[0-9]*/task/[0-9]*")):
            t = read(d + "/stat", "") or ""
            i = t.rfind(")")
            if i < 0 or t[i + 2:i + 3] != "D":
                continue
            name = t[t.find("(") + 1:i].replace(" ", "_")
            wchan = (read(d + "/wchan", "") or "").strip()
            out.append("%s@%s" % (name, wchan if wchan and wchan != "0" else "?"))
            if len(out) >= limit:
                break
        return out

    def net_bytes(self):
        res = {}
        for line in (read("/proc/net/dev", "") or "").splitlines()[2:]:
            name, _, rest = line.partition(":")
            name = name.strip()
            if name.startswith(NET_PREFIXES) and not name.startswith(NET_SKIP) and \
                    (read(f"/sys/class/net/{name}/operstate", "") or "").strip() in ("up", "unknown"):
                f = rest.split()
                res[name] = (int(f[0]), int(f[8]))
        if pipbox_preview:
            res = pipbox_preview.TRAFFIC.adjust(res)
        return res

    def sample(self):
        if self.demo:
            return self.sample_demo()
        with self._lock:
            hit = getattr(self, "_last", None)
            if hit is not None and time.monotonic() - hit[0] < 1.5:
                return dict(hit[1])
            val = self.sample_real()
            self._last = (time.monotonic(), val)
            return dict(val)

    def sample_real(self):
        now = time.time()
        cpu, net = self.cpu_times(), self.net_bytes()
        cores, rates = [], {}
        if self.prev_cpu and len(self.prev_cpu) == len(cpu):
            for (t1, i1), (t0, i0) in zip(cpu, self.prev_cpu):
                dt = max(t1 - t0, 1)
                cores.append(round(100.0 * (1 - (i1 - i0) / dt), 1))
        dt_s = (now - self.prev_t) if self.prev_t else None
        if self.prev_net and dt_s:
            for n, (rx, tx) in net.items():
                p = self.prev_net.get(n)
                if p:
                    rates[n] = {"rx_mbit": max(0.0, round((rx - p[0]) * 8 / dt_s / 1e6, 2)),
                                "tx_mbit": max(0.0, round((tx - p[1]) * 8 / dt_s / 1e6, 2))}
        rates = self.smooth_rates(rates, dt_s)
        self.prev_cpu, self.prev_net, self.prev_t = cpu, net, now

        freqs = []
        i = 0
        while True:
            v = read(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq")
            if v is None:
                break
            freqs.append(int(v) // 1000)
            i += 1
        temps = []
        z = 0
        while True:
            v = read(f"/sys/class/thermal/thermal_zone{z}/temp")
            if v is None:
                break
            temps.append(int(v) / 1000.0)
            z += 1
        mem = {}
        for line in (read("/proc/meminfo", "") or "").splitlines():
            k, _, v = line.partition(":")
            mem[k] = int(v.split()[0]) if v.split() else 0
        total, avail = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
        blocked = 0
        for line in (read("/proc/stat", "") or "").splitlines():
            if line.startswith("procs_blocked"):
                blocked = int(line.split()[1])
        zones = []
        for zi in range(len(temps)):
            zt = (read(f"/sys/class/thermal/thermal_zone{zi}/type", "") or "").strip()
            zones.append({"name": THERMAL_NAMES.get(zt, zt or f"Zone {zi}"), "c": round(temps[zi], 1)})
        out = self.finish(cores, freqs, max(temps) if temps else None,
                          total, avail, rates, blocked, self.fan_pwm(), self.blocked_threads() if blocked > 0 else None)
        send = send_stats()
        out["details"] = {"temps": zones, "accel": devfreq_loads(), "disk": disk_usage("/"), "send": send}
        out["payload_mbit"] = self.payload_rate(send)
        return out

    def sample_demo(self):
        t = time.time()
        cores = [round(max(2, min(99, 45 + 35 * math.sin(t / 7 + k) +
                                  random.uniform(-6, 6))), 1) for k in range(8)]
        freqs = [1800 if k >= 4 else 1416 for k in range(8)]
        temp = 52 + 8 * math.sin(t / 30) + random.uniform(-0.5, 0.5)
        rates = {"eth0": {"rx_mbit": 0.4, "tx_mbit": round(6 + random.uniform(-1, 1), 2)},
                 "eth1": {"rx_mbit": round(13 + random.uniform(-1, 1), 2),
                          "tx_mbit": round(5 + random.uniform(-1, 1), 2)}}
        out = self.finish(cores, freqs, temp, 16 * 1024 * 1024,
                          int(7.4 * 1024 * 1024), rates, 0, int(110 + 40 * math.sin(t / 30)))
        out["details"] = {
            "temps": [{"name": n, "c": round(temp + d + random.uniform(-0.4, 0.4), 1)} for n, d in
                      (("SoC", 0), ("Große Kerne 4–5", 2), ("Große Kerne 6–7", 1.5), ("Kleine Kerne 0–3", -3), ("Mitte", 0), ("GPU", -5), ("NPU", -6))],
            "accel": {"gpu": {"load_pct": int(12 + 8 * math.sin(t / 5)), "mhz": 600}, "npu": {"load_pct": 0, "cores": [0, 0, 0]}},
            "disk": {"total_gb": 62.8, "free_gb": 55.5, "used_gb": 4.6, "used_pct": 8.7},
            "send": {"fps": 29.9, "bitrate_kbps": 9800, "rtt_ms": round(38 + 6 * math.sin(t / 9), 1), "send_mbps": round(9.7 + random.uniform(-0.5, 0.5), 2),
                     "snd_buf_pkts": int(30 + 20 * random.random()), "snd_buf_ms": int(25 + 15 * random.random()), "loss_total": 37,
                     "drop_total": 0, "sent_total": 90210, "loss_pct": 0.04}}
        return out

    def finish(self, cores, freqs, temp, total_kb, avail_kb, rates, blocked, fan_pwm=None, blocked_names=None, now=None, uptime=None):
        cpu_avg = round(sum(cores) / len(cores), 1) if cores else None
        cpu_max = max(cores) if cores else None
        mem_used = round(100.0 * (1 - avail_kb / total_kb), 1) if total_kb else None
        alerts = []
        if temp is not None and temp >= LIMITS["temp_crit"]:
            alerts.append({"level": "crit", "text": f"Temperatur {temp:.0f} °C"})
        elif temp is not None and temp >= LIMITS["temp_warn"]:
            alerts.append({"level": "warn", "text": f"Temperatur {temp:.0f} °C"})
        if cpu_avg is not None and cpu_avg >= LIMITS["cpu_warn"]:
            alerts.append({"level": "warn", "text": f"CPU-Last {cpu_avg:.0f} %"})
        elif cpu_max is not None and cpu_max >= LIMITS["core_warn"]:
            alerts.append({"level": "warn", "text": f"Ein CPU-Kern ist fast voll ({cpu_max:.0f} %)"})
        if mem_used is not None and mem_used >= LIMITS["mem_warn"]:
            alerts.append({"level": "warn", "text": f"RAM {mem_used:.0f} % belegt"})
        rel = self.d_relevant(blocked_names) if blocked > 0 else []
        up = uptime
        if up is None and not self.demo:
            try:
                up = float((read("/proc/uptime", "") or "").split()[0])
            except (ValueError, IndexError):
                up = None
        n = self._d_alert(rel, time.monotonic() if now is None else now, up)
        if n > 0:
            alerts.append({"level": "warn", "text": f"{n} Prozess(e) blockiert (D-State)", "kind": "dstate", "names": rel[:6]})
        return {"time": int(time.time()), "demo": self.demo,
                "cpu": {"cores": cores, "avg": cpu_avg, "max": cpu_max, "freq_mhz": freqs},
                "temp_c": None if temp is None else round(temp, 1),
                "fan_pct": None if fan_pwm is None else round(100.0 * fan_pwm / 255),
                "mem": {"used_pct": mem_used, "avail_mb": avail_kb // 1024,
                        "total_mb": total_kb // 1024},
                "net": rates, "procs_blocked": blocked, "alerts": alerts,
                "encoder": {"fps": 29.9, "bitrate_mbit": 9.8, "max_mbit": 12}
                if self.demo else None}
