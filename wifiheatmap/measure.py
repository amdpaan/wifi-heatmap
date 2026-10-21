"""Latency (ping to a public host) and speed (macOS's built-in networkQuality)."""

import json
import re
import subprocess
import time

PING_HOST = "1.1.1.1"


def ping(host=PING_HOST, count=4, interval=0.25, timeout=3):
    """A short burst of pings. -i 0.25 is the fastest macOS allows without root."""
    r = subprocess.run(["ping", "-q", "-c", str(count), "-i", str(interval), "-t", str(timeout), host],
                       capture_output=True, text=True, timeout=timeout + 5, check=False)
    return parse_ping(r.stdout, count)


def parse_ping(text, count=4):
    out = {"ping_sent": count, "ping_recv": 0, "loss": 100.0,
           "ping_ms": None, "ping_min": None, "ping_max": None, "jitter_ms": None}
    m = re.search(r"(\d+) packets transmitted, (\d+) packets received", text)
    if m:
        sent, recv = int(m.group(1)), int(m.group(2))
        out.update(ping_sent=sent, ping_recv=recv, loss=round(100.0 * (sent - recv) / sent, 1) if sent else 100.0)
    m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", text)
    if m:
        mn, avg, mx, sd = (round(float(x), 1) for x in m.groups())
        out.update(ping_ms=avg, ping_min=mn, ping_max=mx, jitter_ms=sd)
    return out


def speedtest(max_secs=10):
    """One capped networkQuality run. Uncapped runs take ~40 s and 100+ MB; capped at 10 s it's ~11 s
    and ~30 MB with similar results."""
    t0 = time.time()
    try:
        r = subprocess.run(["networkQuality", "-M", str(max_secs), "-c"],
                           capture_output=True, text=True, timeout=max_secs + 60, check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return {"error": str(ex)}
    out = parse_speed(r.stdout)
    out["secs"] = round(time.time() - t0, 1)
    return out


def parse_speed(text):
    try:
        d = json.loads(text)
    except ValueError:
        return {"error": (text.strip() or "no output from networkQuality")[:200]}
    if "dl_throughput" not in d and "ul_throughput" not in d:
        return {"error": str(d.get("error_code") or d.get("error") or "no result")[:200]}

    def num(k, scale=1):
        return round(d[k] / scale, 1) if isinstance(d.get(k), (int, float)) else None

    # throughput is in bits/s and transfers in bytes, so /1e6 gives Mbit/s and MB
    return {"dl_mbps": num("dl_throughput", 1e6), "ul_mbps": num("ul_throughput", 1e6),
            "rtt_ms": num("base_rtt"), "rpm": num("responsiveness"),
            "dl_mb": num("dl_bytes_transferred", 1e6), "ul_mb": num("ul_bytes_transferred", 1e6)}
