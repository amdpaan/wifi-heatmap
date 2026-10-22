"""Command line: wifi-heatmap <command>. Run `wifi-heatmap --help`."""

import argparse
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime

from . import demo, logger, measure, paths, places, samples, score, summary, wifi


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

    def out(event, **k):
        if event == "start":
            print(f"Logging at {p['name']} every {a.interval:g} s. Ctrl-C to stop.")
            note = bssid_note(k["first"], k["streaming"])
            if note:
                print(note)
        elif event == "speedtest":
            print("Speed test (about 10 s)...", flush=True)
        elif event == "speed":
            print(speed_line(k["result"]))
        elif event == "sample":
            print(line(k["rec"]), flush=True)

    session = logger.Session(p, interval=a.interval, speedtest=not a.no_speedtest, out=out)
    summary = session.run(count=a.count)
    if a.count is None:
        print()
    print(summary)
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


def print_rank(rows):
    ranked = [r for r in rows if r["score"] is not None]
    waiting = [r for r in rows if r["score"] is None and r["samples"]]
    if not ranked:
        print(f"Nothing ranked yet: a place needs {score.MIN_SAMPLES} samples (1 minute of logging).")
    w = max([len(r["name"]) for r in ranked] + [5])
    if ranked:
        print(f"    {'Place':<{w}}  Score  {'':<9}  Signal   p90 ping   Loss     Download")
    for i, r in enumerate(ranked, 1):
        sig = f"{r['rssi']:.0f} dBm" if r["rssi"] is not None else "—"
        p90 = f"{r['ping_p90']:.0f} ms" if r["ping_p90"] is not None else "—"
        loss = f"{r['loss']:.0f}%" if r["loss"] is not None else "—"
        dl = f"{r['dl_mbps']:.0f} Mbit/s" if r["dl_mbps"] is not None else "no test"
        why = f"  ({r['why']})" if r["why"] else ""
        print(f"{i:>2}. {r['name']:<{w}}  {r['score']:>5}  {r['label']:<9}  {sig:>7}  {p90:>9}  {loss:>5}   "
              f"{dl:>11}{why}")
    if waiting:
        print(f"Not ranked yet (needs {score.MIN_SAMPLES} samples): "
              + ", ".join(f"{r['name']} ({r['samples']})" for r in waiting))
    good, bad = score.best(rows), score.dead(rows)
    if good:
        print("\nBest study spots: " + ", ".join(r["name"] for r in good))
    if bad:
        print("Dead zones: " + ", ".join(r["name"] for r in bad))


def cmd_rank(a):
    known = places.load()
    if not known:
        print("No places yet. Start with: wifi-heatmap log --place \"Library L2\"")
        return 0
    print_rank(score.summarize(known, samples.read()))
    return 0


def cmd_demo(a):
    print("Made-up places and samples (nothing is saved):\n")
    print_rank(score.summarize(*demo.generate()))
    return 0


def cmd_serve(a):
    from . import serve
    app = serve.App(demo_mode=a.demo, lan=a.lan, token=serve.lan_token(a.new_token) if a.lan else None,
                    verbose=a.verbose)
    try:
        server = serve.make_server(app, "0.0.0.0" if a.lan else "127.0.0.1", a.port)
    except OSError as ex:
        raise CliError(f"Can't use port {a.port}: {ex.strerror}. Is the dashboard already running? Try --port.")
    url = f"http://127.0.0.1:{a.port}/"
    print(f"wifi-heatmap dashboard{' (demo)' if a.demo else ''}: {url}")
    if a.lan:
        host = serve.local_hostname() or "<this Mac's name>.local"
        print(f"On your phone (same Wi-Fi): http://{host}:{a.port}/?t={app.token}")
        print("Keep that link private: anyone with it on this network can see your places and start logging.")
    print("Ctrl-C to stop.")
    if not a.no_open:
        subprocess.run(["open", url], check=False)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        if app.logging_here():
            print(app.checkout())
        server.server_close()
    return 0


def cmd_summary(a):
    d = summary.write()
    print(f"Wrote {paths.SUMMARY}: mood {d['mood']}, {d['ranked']} of {d['places']} places ranked"
          + (f", logging at {d['live']['place']}" if d["live"] else ""))
    return 0


def cmd_place(a):
    if a.action == "add":
        p = places.add(a.name)
        summary.write()
        print(f"Added {p['name']} ({p['id']})")
    elif a.action == "rename":
        p = places.rename(a.name, a.new_name)
        summary.write()
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

    s = sub.add_parser("rank", help="score your places: best study spots and dead zones")
    s.set_defaults(fn=cmd_rank)

    s = sub.add_parser("demo", help="the ranking for made-up places (saves nothing)")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("serve", help="open the dashboard: map, rankings, check in from your phone")
    s.add_argument("--demo", action="store_true", help="made-up campus and data (changes nothing)")
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--lan", action="store_true", help="also reachable from your phone on the same Wi-Fi (with a token)")
    s.add_argument("--new-token", action="store_true", help="with --lan: make a new phone link (the old one stops working)")
    s.add_argument("--no-open", action="store_true", help="don't open the browser")
    s.add_argument("--verbose", action="store_true", help="log every request")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("summary", help="rewrite summary.json for desktop widgets (logging does this itself)")
    s.set_defaults(fn=cmd_summary)

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
