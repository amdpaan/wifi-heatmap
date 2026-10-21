# wifi-heatmap

A Wi-Fi heatmap for your campus, for macOS. While you move between study spots, wifi-heatmap logs your own
connection's signal strength, latency and speed, then shows which spots are great and which are dead zones,
on a map you provide.

Everything runs locally on your Mac. It only measures your own connection: it reads your Wi-Fi details,
pings a public host and runs an occasional short speed test. It never scans or captures anyone else's
devices or traffic.

**Status:** work in progress. Nothing to install yet.

## Planned

- A small Swift helper reads signal (RSSI), noise, channel, transmit rate and access point via CoreWLAN.
- A Python logger (standard library only) adds ping latency and loss, plus a short `networkQuality`
  speed test each time you check in to a place.
- A local web dashboard: your places as pins on a map, coloured by score, with rankings for
  best study spots and dead zones.
- An original pixel mascot, the antenna-bot, whose antenna bars show the signal.

## License

MIT
