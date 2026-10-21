"""Made-up places and samples, for tests, `wifi-heatmap demo` and (later) screenshots.

Every place has a personality, so the ranking has something to find. Fake BSSIDs are locally
administered MACs (02:...), never real ones, and the network is "Demo-WiFi".
"""

import random
import statistics
from datetime import datetime, timedelta

from .places import slug

# name, RSSI mean/sd, base ping ms, spike chance, loss chance per ping, disconnect chance,
# download Mbit/s, band, access points, sessions, samples per session
PROFILES = [
    ("Library L2, window side", -53, 3, 16, 0.02, 0.002, 0.0, 70, "5GHz", 2, 3, 90),
    ("Computer lab 3", -58, 3, 14, 0.02, 0.002, 0.0, 85, "5GHz", 1, 2, 80),
    ("Lecture hall A", -66, 4, 26, 0.06, 0.01, 0.0, 25, "5GHz", 2, 3, 70),
    ("Cafeteria", -62, 5, 30, 0.10, 0.015, 0.0, 18, "5GHz", 3, 4, 60),   # crowded at lunch, see LUNCH
    ("Hostel lounge", -73, 5, 45, 0.15, 0.03, 0.02, 7, "2.4GHz", 1, 2, 60),
    ("Library basement", -83, 4, 70, 0.30, 0.09, 0.10, 2, "2.4GHz", 1, 2, 50),
    ("Bus stop", -79, 5, 90, 0.30, 0.05, 0.10, 2, "2.4GHz", 1, 1, 6),     # too few samples to rank
]
LUNCH = (12, 14)   # the cafeteria's ping x3, loss x3 and speed /4 between these hours


def generate(seed=7, start=datetime(2026, 10, 19, 8, 0), interval=5):
    """Returns (places, records) in the same shapes as places.json and samples.jsonl."""
    rnd = random.Random(seed)
    places, records = [], []
    for idx, (name, rssi_mu, rssi_sd, base_ping, spike, loss, drop, dl, band, aps, sessions, per) \
            in enumerate(PROFILES, 1):
        pid = slug(name)
        places.append({"id": pid, "name": name, "created": start.isoformat(), "pin": None})
        channels = [36, 44, 149] if band == "5GHz" else [1, 6, 11]
        for k in range(sessions):
            day = start + timedelta(days=rnd.randrange(5))
            hour = 12 if name == "Cafeteria" and k % 2 == 0 else rnd.choice([9, 10, 15, 16, 20])
            t = day.replace(hour=hour, minute=rnd.randrange(60)).timestamp()
            lunch = name == "Cafeteria" and LUNCH[0] <= hour < LUNCH[1]
            base = {"place": pid, "session": f"demo{idx}{k}"}
            records.append(dict(kind="checkin", ts=t, **base))
            speed = dl / 4 if lunch else dl
            d = max(0.3, rnd.gauss(speed, speed * 0.2))
            records.append(dict(kind="speed", ts=t + 1, **base, dl_mbps=round(d, 1), ul_mbps=round(d * 0.4, 1),
                                rtt_ms=float(base_ping), rpm=round(60000 / base_ping / 2), dl_mb=9.0, ul_mb=20.0,
                                secs=10.5))
            for i in range(per):
                ts = t + 12 + i * interval
                rec = dict(kind="sample", ts=round(ts, 1), **base)
                if rnd.random() < drop:
                    rec.update(connected=False, ping_sent=4, ping_recv=0, loss=100.0,
                               ping_ms=None, ping_min=None, ping_max=None, jitter_ms=None)
                    records.append(rec)
                    continue
                rssi = round(rnd.gauss(rssi_mu, rssi_sd))
                ap = rnd.randrange(aps) + 1
                rec.update(connected=True, rssi=rssi, noise=round(rnd.gauss(-94, 2)), channel=rnd.choice(channels),
                           band=band, width=80 if band == "5GHz" else 20,
                           tx_rate=float(max(6, min(866, round(866 * (rssi + 90) / 40)))),
                           phy="802.11ac" if band == "5GHz" else "802.11n", ssid="Demo-WiFi",
                           bssid=f"02:00:00:00:{idx:02x}:{ap:02x}")
                rec.update(fake_ping(rnd, base_ping * (3 if lunch else 1), spike, loss * (3 if lunch else 1)))
                records.append(rec)
            records.append(dict(kind="checkout", ts=round(t + 12 + per * interval, 1), **base))
    return places, records


def fake_ping(rnd, base, spike, loss, count=4):
    rtts = []
    for _ in range(count):
        if rnd.random() < loss:
            continue
        rtt = base * rnd.lognormvariate(0, 0.25)
        if rnd.random() < spike:
            rtt *= rnd.uniform(4, 10)
        rtts.append(rtt)
    if not rtts:
        return {"ping_sent": count, "ping_recv": 0, "loss": 100.0,
                "ping_ms": None, "ping_min": None, "ping_max": None, "jitter_ms": None}
    return {"ping_sent": count, "ping_recv": len(rtts), "loss": round(100.0 * (count - len(rtts)) / count, 1),
            "ping_ms": round(statistics.mean(rtts), 1), "ping_min": round(min(rtts), 1),
            "ping_max": round(max(rtts), 1), "jitter_ms": round(statistics.pstdev(rtts), 1)}


# Where each demo place sits on DEMO_MAP, as a share of its width and height.
PINS = {
    "Library L2, window side": (0.215, 0.27), "Library basement": (0.30, 0.42), "Computer lab 3": (0.60, 0.22),
    "Lecture hall A": (0.80, 0.30), "Cafeteria": (0.50, 0.62), "Hostel lounge": (0.83, 0.78),
    "Bus stop": (0.10, 0.86),
}
LIVE_PLACE = "Cafeteria"   # the demo dashboard pretends you're logging here


def with_pins(places):
    for p in places:
        x, y = PINS[p["name"]]
        p["pin"] = {"x": x, "y": y}
    return places


def live(now, seed=None):
    """A pretend session at LIVE_PLACE that started four minutes ago, with a fresh sample each call."""
    rnd = random.Random(seed if seed is not None else int(now // 5))
    pid = slug(LIVE_PLACE)
    rssi = round(rnd.gauss(-62, 3))
    sample = dict(kind="sample", ts=now, place=pid, session="demolive", connected=True, rssi=rssi,
                  noise=-94, channel=44, band="5GHz", width=80, tx_rate=float(round(866 * (rssi + 90) / 40)),
                  phy="802.11ac", ssid="Demo-WiFi", bssid="02:00:00:00:04:02",
                  **fake_ping(rnd, 30, 0.1, 0.015))
    return {"place": pid, "session": "demolive", "since": now - 240, "samples": 48, "sample": sample,
            "speed": {"dl_mbps": 17.2, "ul_mbps": 6.9}}


# A made-up campus, drawn for the demo and screenshots. Real maps are your own image, never committed.
DEMO_MAP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 640" width="1000" height="640">
<rect width="1000" height="640" fill="#e4ead9"/>
<path d="M0 560 C 250 540, 420 600, 1000 575 L1000 610 C 420 635, 250 575, 0 595 Z" fill="#c9c6bb"/>
<path d="M120 0 L150 640 M0 470 C 300 450, 640 500, 1000 455" stroke="#f5f2e9" stroke-width="18" fill="none"/>
<path d="M470 120 L480 560" stroke="#f5f2e9" stroke-width="12" fill="none"/>
<g fill="#cfd8c0"><circle cx="420" cy="80" r="34"/><circle cx="700" cy="520" r="28"/><circle cx="60" cy="300" r="40"/></g>
<g fill="#f7f4ec" stroke="#8a8577" stroke-width="3">
<rect x="160" y="90" width="230" height="210" rx="6"/>
<rect x="520" y="70" width="170" height="140" rx="6"/>
<rect x="720" y="110" width="220" height="150" rx="6"/>
<rect x="380" y="330" width="230" height="120" rx="6"/>
<rect x="740" y="410" width="200" height="120" rx="6"/>
</g>
<path d="M160 230 H390" stroke="#8a8577" stroke-width="2" stroke-dasharray="6 6"/>
<rect x="40" y="535" width="110" height="34" rx="4" fill="#f7f4ec" stroke="#8a8577" stroke-width="3"/>
<g font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="22" fill="#5b574d" text-anchor="middle">
<text x="275" y="125">Library</text><text x="205" y="285" font-size="15">basement</text>
<text x="605" y="105">Labs</text><text x="830" y="145">Lecture halls</text>
<text x="495" y="365">Cafeteria</text><text x="840" y="445">Hostel</text>
<text x="95" y="525" font-size="17">Bus stop</text>
</g>
</svg>
"""
