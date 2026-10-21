"""The log: one JSON object per line in paths.SAMPLES.

Record kinds, all with "ts" (epoch seconds), "place" (a place id) and "session":
  checkin   you started logging at a place
  speed     one networkQuality result (dl_mbps, ul_mbps, rtt_ms, rpm, ...) or {"error": ...}
  sample    Wi-Fi (rssi, noise, channel, band, width, tx_rate, phy, ssid, bssid) + ping (ping_ms, loss, ...)
  checkout  you stopped logging
"""

import json

from . import paths

WIFI_KEYS = ("connected", "rssi", "noise", "channel", "band", "width", "tx_rate", "phy", "ssid", "bssid")


def append(record):
    paths.SUPPORT.mkdir(parents=True, exist_ok=True)
    with open(paths.SAMPLES, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read():
    try:
        f = open(paths.SAMPLES, encoding="utf-8")
    except FileNotFoundError:
        return
    with f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue   # a line cut short by a crash; skip it
