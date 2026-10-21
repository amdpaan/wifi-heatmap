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
