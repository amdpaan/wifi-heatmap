"""Per-place stats and a 0-100 score, from the log (samples.py has the record format).

The score blends four parts, each 0-100:
  signal   median RSSI, -85 dBm = 0 to -55 dBm = 100, times the share of samples that were connected
  latency  p90 ping (the spikes you feel), 400 ms = 0 to 20 ms = 100, on a log scale
  loss     ping loss, 8% = 0 to 0% = 100
  speed    median download from the check-in speed tests, 1 Mbit/s = 0 to 50 Mbit/s = 100, log scale
A place without a speed test is scored on the other three, reweighted.
"""

import math
import statistics

WEIGHTS = {"signal": 0.35, "latency": 0.25, "loss": 0.20, "speed": 0.20}
MIN_SAMPLES = 12          # 1 minute at the default 5 s, before a place is ranked
GREAT, OK, POOR = 75, 50, 30   # labels: great / ok / poor / dead zone
BEST_MIN = 60             # a "best study spot" needs at least this
DEAD_MAX = POOR           # a "dead zone" is below this

REASONS = {"signal": "weak signal", "latency": "laggy", "loss": "drops packets", "speed": "slow"}


def lin(v, bad, good):
    return max(0.0, min(100.0, 100.0 * (v - bad) / (good - bad)))


def loglin(v, bad, good):
    if v <= 0:   # as low as it gets: best when lower is better (latency), worst otherwise
        return 100.0 if good < bad else 0.0
    return lin(math.log(v), math.log(bad), math.log(good))


def percentile(values, p):
    """Nearest-rank percentile, so it's always a value that was actually measured."""
    s = sorted(values)
    return s[max(0, math.ceil(p / 100.0 * len(s)) - 1)]


def label(score):
    if score is None:
        return "unranked"
    if score >= GREAT:
        return "great"
    if score >= OK:
        return "ok"
    if score >= POOR:
        return "poor"
    return "dead zone"


def place_stats(samples, speeds):
    """Stats for one place from its sample and (successful) speed records."""
    connected = [s for s in samples if s.get("connected") and s.get("rssi") is not None]
    rssi = [s["rssi"] for s in connected]
    snr = [s["rssi"] - s["noise"] for s in connected if s.get("noise")]
    pings = [s["ping_ms"] for s in samples if s.get("ping_ms") is not None]
    sent = sum(s.get("ping_sent") or 0 for s in samples)
    recv = sum(s.get("ping_recv") or 0 for s in samples)
    dl = [s["dl_mbps"] for s in speeds if s.get("dl_mbps") is not None]
    ul = [s["ul_mbps"] for s in speeds if s.get("ul_mbps") is not None]
    ts = [s["ts"] for s in samples]
    return {
        "samples": len(samples),
        "sessions": len({s.get("session") for s in samples}),
        "connected": round(len(connected) / len(samples), 3) if samples else 0.0,
        "rssi": statistics.median(rssi) if rssi else None,
        "snr": statistics.median(snr) if snr else None,
        "ping_ms": statistics.median(pings) if pings else None,
        "ping_p90": percentile(pings, 90) if pings else None,
        "loss": round(100.0 * (sent - recv) / sent, 1) if sent else None,
        "dl_mbps": statistics.median(dl) if dl else None,
        "ul_mbps": statistics.median(ul) if ul else None,
        "speedtests": len(dl),
        "aps": len({s["bssid"] for s in connected if s.get("bssid")}),
        "bands": sorted({s["band"] for s in connected if s.get("band")}),
        "first": min(ts) if ts else None,
        "last": max(ts) if ts else None,
    }


def parts(st):
    p = {}
    p["signal"] = lin(st["rssi"], -85, -55) * st["connected"] if st["rssi"] is not None else 0.0
    # no ping answered at all: as bad as it gets
    p["latency"] = loglin(st["ping_p90"], 400, 20) if st["ping_p90"] is not None else 0.0
    p["loss"] = lin(st["loss"], 8, 0) if st["loss"] is not None else 0.0
    if st["dl_mbps"] is not None:
        p["speed"] = loglin(st["dl_mbps"], 1, 50)
    return {k: round(v, 1) for k, v in p.items()}


def score(p):
    total = sum(WEIGHTS[k] for k in p)
    return round(sum(WEIGHTS[k] * v for k, v in p.items()) / total)


def summarize(places, records):
    """One row per place, ranked best first; places without enough samples come last, unranked."""
    by_place = {p["id"]: ([], []) for p in places}
    for r in records:
        if r.get("place") not in by_place:
            continue
        if r.get("kind") == "sample":
            by_place[r["place"]][0].append(r)
        elif r.get("kind") == "speed" and not r.get("error"):
            by_place[r["place"]][1].append(r)
    rows = []
    for p in places:
        samples, speeds = by_place[p["id"]]
        st = place_stats(samples, speeds)
        row = {"id": p["id"], "name": p["name"], **st, "parts": {}, "score": None, "why": None}
        if st["samples"] >= MIN_SAMPLES:
            row["parts"] = parts(st)
            row["score"] = score(row["parts"])
            weak = sorted((v, k) for k, v in row["parts"].items() if v < 50)[:3]   # weakest first
            row["why"] = ", ".join(REASONS[k] for _, k in weak) or None
        row["label"] = label(row["score"])
        rows.append(row)
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), -r["samples"]))
    return rows


def best(rows, n=3):
    return [r for r in rows if r["score"] is not None and r["score"] >= BEST_MIN][:n]


def dead(rows, n=3):
    return sorted([r for r in rows if r["score"] is not None and r["score"] < DEAD_MAX],
                  key=lambda r: r["score"])[:n]
