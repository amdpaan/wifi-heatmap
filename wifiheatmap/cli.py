"""Command line: wifi-heatmap <command>. Run `wifi-heatmap --help`."""

import argparse
import statistics
import sys
import time
import uuid
from collections import Counter
from datetime import datetime

from . import measure, paths, places, samples, wifi


class CliError(Exception):
    pass


def resolve_place(name, new=False):
    """An existing place, or a new one. A name close to an existing one needs --new, so a typo
    doesn't quietly split one place's history in two."""
    known = places.load()
    p = places.find(known, name)
    if p:
        return p
    close = places.similar(known, name)
    if close and not new:
        raise CliError(f"No place called {name!r}. Did you mean {', '.join(repr(c) for c in close)}? "
                       f"Add --new to create it anyway.")
    p = places.add(name)
    print(f"New place: {p['name']}")
    return p


def fmt_ms(v):
    return "  —  " if v is None else f"{v:>4.0f} ms"


def line(rec):
    t = datetime.fromtimestamp(rec["ts"]).strftime("%H:%M:%S")
    if not rec.get("connected"):
        return f"{t}  ····  not connected to Wi-Fi"
    snr = rec["rssi"] - rec["noise"] if rec.get("noise") else None
    return (f"{t}  {wifi.bars(rec['rssi'])} {rec['rssi']:>4} dBm  SNR {snr if snr is not None else '—':>2}  "
            f"ch {rec.get('channel')} ({rec.get('band') or '?'})  {rec.get('tx_rate') or 0:>4.0f} Mbps  "
            f"ping {fmt_ms(rec.get('ping_ms'))}  loss {rec['loss']:.0f}%")


def speed_line(s):
    if s.get("error"):
        return f"Speed test failed: {s['error']}"
    return (f"Speed: {s['dl_mbps']} Mbit/s down, {s['ul_mbps']} Mbit/s up, "
            f"RTT {s['rtt_ms']} ms ({s.get('secs')} s, ~{(s.get('dl_mb') or 0) + (s.get('ul_mb') or 0):.0f} MB)")


def bssid_note(w, streaming):
    if w.get("bssid"):
        return None
    if not paths.HELPER_APP.exists():
        return "No access point (BSSID): build the helper app with tools/build-helper.sh"
    if w.get("location") in ("denied", "restricted"):
        return ("No access point (BSSID): allow \"WiFi Heatmap Helper\" in System Settings > "
                "Privacy & Security > Location Services")
    if not streaming:
        return "No access point (BSSID): the helper app didn't start, so only the signal is read"
    if w.get("location") == "not_determined":
        return ("No access point (BSSID) yet: macOS is asking whether \"WiFi Heatmap Helper\" may use "
                "Location Services. Allow it, then run this again.")
    return None


# ---------- commands ----------

def cmd_now(a):
    reader = wifi.Reader()
    streaming = reader.start()
    try:
        w = reader.read()
        # Keep the helper running so a Location prompt stays up while you answer it. CoreLocation
        # briefly says "not determined" even when it's allowed, so only mention it after 3 s.
        started, told = time.time(), False
        while streaming and w.get("location") == "not_determined" and time.time() - started < 60:
            if not told and time.time() - started > 3:
                print("macOS is asking whether \"WiFi Heatmap Helper\" may use Location Services "
                      "(only to read the access point's BSSID). Waiting up to 60 s...", flush=True)
                told = True
            time.sleep(0.5)
            w = reader.read()
    finally:
        reader.stop()
    rec = dict(w, ts=time.time(), **measure.ping())
    print(line(rec))
    if w.get("connected"):
        print(f"Network: {w.get('ssid') or '(hidden)'}   AP: {w.get('bssid') or '(hidden)'}   "
              f"{w.get('phy') or ''}, {w.get('width') or '?'} MHz wide")
    note = bssid_note(w, streaming)
    if note:
        print(note)
    return 0


def cmd_log(a):
    p = resolve_place(a.place, a.new)
    base = {"place": p["id"], "session": uuid.uuid4().hex[:8]}
    reader = wifi.Reader()
    streaming = reader.start()
    first = reader.read()
    print(f"Logging at {p['name']} every {a.interval:g} s. Ctrl-C to stop.")
    note = bssid_note(first, streaming)
    if note:
        print(note)
    samples.append(dict(kind="checkin", ts=round(time.time(), 1), **base))

    if not a.no_speedtest:
        print("Speed test (about 10 s)...", flush=True)
        s = measure.speedtest()
        samples.append(dict(kind="speed", ts=round(time.time(), 1), **base, **s))
        print(speed_line(s))

    started, n, rssi, pings, lost, sent = time.time(), 0, [], [], 0, 0
    try:
        while a.count is None or n < a.count:
            t0 = time.time()
            w = reader.read()
            rec = dict(kind="sample", ts=round(t0, 1), **base,
                       **{k: w.get(k) for k in samples.WIFI_KEYS}, **measure.ping())
            samples.append(rec)
            print(line(rec), flush=True)
            n += 1
            if rec.get("rssi") is not None:
                rssi.append(rec["rssi"])
            if rec.get("ping_ms") is not None:
                pings.append(rec["ping_ms"])
            sent += rec["ping_sent"]
            lost += rec["ping_sent"] - rec["ping_recv"]
            if a.count is None or n < a.count:
                time.sleep(max(0.0, a.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        print()
    finally:
        reader.stop()
        samples.append(dict(kind="checkout", ts=round(time.time(), 1), **base))

    mins, secs = divmod(int(time.time() - started), 60)
    parts = [f"{n} samples over {mins}m{secs:02d}s"]
    if rssi:
        parts.append(f"median signal {statistics.median(rssi):.0f} dBm")
    if pings:
        parts.append(f"median ping {statistics.median(pings):.0f} ms")
    if sent:
        parts.append(f"{100.0 * lost / sent:.0f}% loss")
    print(f"{p['name']}: " + ", ".join(parts))
    return 0


def cmd_speedtest(a):
    p = None
    if a.place:
        p = places.find(places.load(), a.place)
        if not p:
            raise CliError(f"No place called {a.place!r}. See: wifi-heatmap place list")
    print("Speed test (about 10 s)...", flush=True)
    s = measure.speedtest()
    print(speed_line(s))
    if p:
        samples.append(dict(kind="speed", ts=round(time.time(), 1), place=p["id"], session=None, **s))
    return 0 if not s.get("error") else 1


def cmd_place(a):
    if a.action == "add":
        p = places.add(a.name)
        print(f"Added {p['name']} ({p['id']})")
    elif a.action == "rename":
        p = places.rename(a.name, a.new_name)
        print(f"Renamed to {p['name']} ({p['id']}, history kept)")
    else:
        known = places.load()
        if not known:
            print("No places yet. Start with: wifi-heatmap log --place \"Library L2\"")
            return 0
        counts, last = Counter(), {}
        for r in samples.read():
            if r.get("kind") == "sample":
                counts[r.get("place")] += 1
                last[r.get("place")] = r.get("ts")
        for p in known:
            seen = datetime.fromtimestamp(last[p["id"]]).strftime("%d %b %H:%M") if p["id"] in last else "never"
            print(f"{p['name']:<32} {counts[p['id']]:>6} samples   last {seen}")
    return 0


def parser():
    ap = argparse.ArgumentParser(prog="wifi-heatmap",
                                 description="Log your own Wi-Fi per study spot and find the dead zones.")
    sub = ap.add_subparsers(dest="cmd", metavar="command")

    s = sub.add_parser("now", help="show the Wi-Fi and ping right now (logs nothing)")
    s.set_defaults(fn=cmd_now)

    s = sub.add_parser("log", help="check in to a place and log until Ctrl-C")
    s.add_argument("--place", required=True, help='where you are, e.g. "Library L2, window side"')
    s.add_argument("--new", action="store_true", help="create the place even if it looks like an existing one")
    s.add_argument("--interval", type=float, default=5.0, help="seconds between samples (default 5)")
    s.add_argument("--no-speedtest", action="store_true", help="skip the speed test at check-in")
    s.add_argument("--count", type=int, help=argparse.SUPPRESS)   # stop after N samples (tests)
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("speedtest", help="run one capped speed test (~10 s, ~30 MB)")
    s.add_argument("--place", help="also log it for this place")
    s.set_defaults(fn=cmd_speedtest)

    s = sub.add_parser("place", help="list, add or rename places")
    s.add_argument("action", nargs="?", default="list", choices=("list", "add", "rename"))
    s.add_argument("name", nargs="?")
    s.add_argument("new_name", nargs="?")
    s.set_defaults(fn=cmd_place)
    return ap


def main(argv=None):
    ap = parser()
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 0
    if a.cmd == "place" and ((a.action == "add" and not a.name) or (a.action == "rename" and not a.new_name)):
        ap.error("usage: wifi-heatmap place add NAME | place rename OLD NEW")
    try:
        return a.fn(a)
    except (CliError, places.PlaceError, wifi.HelperMissing) as ex:
        print(f"wifi-heatmap: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
