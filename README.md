# wifi-heatmap

[![tests](https://github.com/amdpaan/wifi-heatmap/actions/workflows/tests.yml/badge.svg)](https://github.com/amdpaan/wifi-heatmap/actions/workflows/tests.yml)

A Wi-Fi heatmap for your campus, for macOS. While you move between study spots, wifi-heatmap logs your own
connection's signal strength, latency and speed, then shows which spots are great and which are dead zones,
on a map you provide.

Everything runs locally on your Mac. It only measures your own connection: it reads your Wi-Fi details,
pings a public host and runs an occasional short speed test. It never scans or captures anyone else's
devices or traffic.

**Status:** early. Logging works; scoring, the map dashboard and the mascot are next.

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

Other commands: `speedtest [--place NAME]`, `place list`, `place add NAME`, `place rename OLD NEW`
(renaming keeps the history).

## How it works

- **Wi-Fi details** come from CoreWLAN, through a small Swift helper (`helper/main.swift`): signal (RSSI),
  noise, channel, band, width, transmit rate and PHY mode. These need no permission.
- **Which access point** (SSID and BSSID) needs Location Services since macOS 14, and macOS only grants that
  to an app, so the helper is built as `WiFi Heatmap Helper.app`. wifi-heatmap never reads your location.
  The app is signed with a local certificate created in your login keychain, so macOS remembers your
  approval across rebuilds.
- **Latency** is a burst of 4 pings; **speed** is macOS's built-in `networkQuality`, capped at 10 seconds.
- **Your data** stays in `~/Library/Application Support/wifi-heatmap` (`samples.jsonl`, `places.json`),
  never in the repo.

## Planned

- A score per place, with rankings for best study spots and dead zones.
- A local web dashboard: your places as pins on a map, coloured by score.
- An original pixel mascot, the antenna-bot, whose antenna bars show the signal.
- A tile for [claude-widget](https://github.com/amdpaan/claude-widget).

## Tests

```sh
/usr/bin/python3 -m unittest discover tests
```

## License

MIT
