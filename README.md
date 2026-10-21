# wifi-heatmap

[![tests](https://github.com/amdpaan/wifi-heatmap/actions/workflows/tests.yml/badge.svg)](https://github.com/amdpaan/wifi-heatmap/actions/workflows/tests.yml)

A Wi-Fi heatmap for your campus, for macOS. While you move between study spots, wifi-heatmap logs your own
connection's signal strength, latency and speed, then shows which spots are great and which are dead zones,
on a map you provide.

Everything runs locally on your Mac. It only measures your own connection: it reads your Wi-Fi details,
pings a public host and runs an occasional short speed test. It never scans or captures anyone else's
devices or traffic.

**Status:** early. Logging, ranking and the map dashboard work; the mascot and an installer are next.

## Requirements

- macOS 14 or later (tested on macOS 27, Apple Silicon)
- Command Line Tools (`xcode-select --install`), which provide `swiftc` and `python3` (3.9+)

## Try it

```sh
git clone https://github.com/amdpaan/wifi-heatmap ~/Projects/wifi-heatmap
cd ~/Projects/wifi-heatmap
tools/build-helper.sh                         # builds the Wi-Fi helper app (once, and after updates)
bin/wifi-heatmap now                          # your Wi-Fi and ping right now; allow Location when asked
bin/wifi-heatmap log --place "Library L2"     # check in and log every 5 s until Ctrl-C
```

`log` runs one short speed test when you check in (about 10 s and 30 MB; skip it with `--no-speedtest`),
then reads the signal and pings `1.1.1.1` every 5 seconds:

```
Logging at Library L2 every 5 s. Ctrl-C to stop.
Speed: 48.2 Mbit/s down, 21.7 Mbit/s up, RTT 14.0 ms (10.2 s, ~31 MB)
10:02:11  ▂▄▆·  -61 dBm  SNR 33  ch 36 (5GHz)   433 Mbps  ping   18 ms  loss 0%
10:02:16  ▂▄▆·  -63 dBm  SNR 31  ch 36 (5GHz)   390 Mbps  ping   21 ms  loss 0%
^C
Library L2: 2 samples over 0m05s, median signal -62 dBm, median ping 20 ms, 0% loss
```

Once a place has a minute of samples, `rank` scores it. `demo` shows the same ranking for made-up places:

```
$ bin/wifi-heatmap demo
    Place                    Score             Signal   p90 ping   Loss     Download
 1. Library L2, window side     99  great      -53 dBm      21 ms     0%     67 Mbit/s
 2. Computer lab 3              96  great      -58 dBm      18 ms     0%     89 Mbit/s
 3. Lecture hall A              70  ok         -66 dBm      66 ms     1%     23 Mbit/s
 4. Cafeteria                   56  ok         -62 dBm     225 ms     3%     12 Mbit/s  (laggy)
 5. Hostel lounge               35  poor       -73 dBm     201 ms     6%      7 Mbit/s  (laggy, drops packets, weak signal)
 6. Library basement             6  dead zone  -83 dBm     393 ms    17%      2 Mbit/s  (drops packets, laggy, weak signal)
Not ranked yet (needs 12 samples): Bus stop (6)

Best study spots: Library L2, window side, Computer lab 3, Lecture hall A
Dead zones: Library basement
```

## Dashboard

```sh
bin/wifi-heatmap serve           # opens http://127.0.0.1:8766/
bin/wifi-heatmap serve --demo    # the same with a made-up campus (changes nothing)
bin/wifi-heatmap serve --lan     # also from your phone on the same Wi-Fi, with a private link
```

- **Map:** upload a campus map or floor plan (PNG, JPEG or WebP) and drop a pin for each place. Each pin
  shows the place's score, with a glow in its colour (great, ok, poor, dead zone).
- **Rankings:** every place with its score, signal, p90 ping, loss, download and why it lost points.
- **Place sheet:** click a place for its score parts, all its stats, its score by hour of the day (is the
  cafeteria slow at lunch?) and its recent visits. Rename it or move its pin from there.
- **Check in:** start and stop logging from the dashboard (or your phone, with `--lan`). Logging from the
  terminal shows up live too.

Like net-watch's dashboard, it only answers `127.0.0.1` unless you pass `--lan`; then other devices need the
token in the link it prints. The uploaded map stays in your data folder.

## More commands

`speedtest [--place NAME]`, `place list`, `place add NAME`, `place rename OLD NEW`
(renaming keeps the history).

## How it works

- **Wi-Fi details** come from CoreWLAN, through a small Swift helper (`helper/main.swift`): signal (RSSI),
  noise, channel, band, width, transmit rate and PHY mode. These need no permission.
- **Which access point** (SSID and BSSID) needs Location Services since macOS 14, and macOS only grants that
  to an app, so the helper is built as `WiFi Heatmap Helper.app`. wifi-heatmap never reads your location.
  The app is signed with a local certificate created in your login keychain, so macOS remembers your
  approval across rebuilds.
- **Latency** is a burst of 4 pings; **speed** is macOS's built-in `networkQuality`, capped at 10 seconds.
- **The score** (0–100) blends signal (median RSSI, −85 to −55 dBm), latency (90th-percentile ping, so
  spikes count, 400 to 20 ms), packet loss (8% to 0%) and download speed (1 to 50 Mbit/s), weighted
  35/25/20/20. Without a speed test, the other three are reweighted. See `wifiheatmap/score.py`.
- **Your data** stays in `~/Library/Application Support/wifi-heatmap` (`samples.jsonl`, `places.json`,
  `maps/`), never in the repo.

## Planned

- An installer, and screenshots here.
- An original pixel mascot, the antenna-bot, whose antenna bars show the signal.
- A tile for [claude-widget](https://github.com/amdpaan/claude-widget).

## Tests

```sh
/usr/bin/python3 -m unittest discover tests
```

## License

MIT
