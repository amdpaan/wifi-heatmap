"""summary.json for desktop widgets (claude-widget's Wi-Fi Heatmap card): the antenna-bot's mood, what's
being logged right now, the best spot and the dead zones. Rewritten at every check-in, sample and checkout.

Only place names, scores and your own signal / ping: never an SSID or BSSID. The format only ever gains keys.
  generated_at   epoch seconds
  mood, level    the antenna-bot: great / ok / poor / dead / idle, and chest bars lit (0-4), as on the dashboard
  base_mood, base_level   the same from the rankings alone, for when `live` turns out to be stale
  live           null, or {place, since, samples, rssi, ping_ms, loss, connected, ts} while logging
  best           null, or {name, score, label}: the top place, when it's a best study spot
  dead           [{name, score}], worst first (up to 3)
  ranked, places how many places are ranked, of how many
"""

import json
import time

from . import paths, places, samples, score, wifi

MOOD_BY_BARS = ("dead", "dead", "poor", "ok", "great")
MOOD_BY_LABEL = {"great": "great", "ok": "ok", "poor": "poor", "dead zone": "dead"}
LEVEL_BY_MOOD = {"great": 4, "ok": 3, "poor": 2, "dead": 1, "idle": 0}


def build(known, records, now):
    rows = score.summarize(known, records)
    names = {p["id"]: p["name"] for p in known}
    lv = score.live(records, now)
    live = None
    if lv:
        s = lv["sample"] or {}
        live = {"place": names.get(lv["place"], lv["place"]), "since": lv["since"], "samples": lv["samples"],
                "connected": s.get("connected"), "rssi": s.get("rssi"), "ping_ms": s.get("ping_ms"),
                "loss": s.get("loss"), "ts": s.get("ts", lv["since"])}
    ranked = [r for r in rows if r["score"] is not None]
    base_mood = MOOD_BY_LABEL[ranked[0]["label"]] if ranked else "idle"
    mood, level = base_mood, LEVEL_BY_MOOD[base_mood]
    if lv and lv["sample"]:   # logging, with a sample already: follow the live signal
        level = wifi.bar_count(live["rssi"]) if live["connected"] else 0
        mood = MOOD_BY_BARS[level]
    top = score.best(rows, 1)
    return {
        "generated_at": round(now, 1), "mood": mood, "level": level, "live": live,
        "base_mood": base_mood, "base_level": LEVEL_BY_MOOD[base_mood],
        "best": {"name": top[0]["name"], "score": top[0]["score"], "label": top[0]["label"]} if top else None,
        "dead": [{"name": r["name"], "score": r["score"]} for r in score.dead(rows)],
        "ranked": len(ranked), "places": len(rows),
    }


def write(now=None):
    data = build(places.load(), list(samples.read()), time.time() if now is None else now)
    paths.SUPPORT.mkdir(parents=True, exist_ok=True)
    tmp = paths.SUMMARY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(paths.SUMMARY)
    return data
