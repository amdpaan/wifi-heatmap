"""Where everything lives. Nothing personal is ever written inside the repo."""

import os
from pathlib import Path

SUPPORT = Path(os.environ.get("WIFI_HEATMAP_HOME",
                              Path.home() / "Library/Application Support/wifi-heatmap"))
SAMPLES = SUPPORT / "samples.jsonl"
PLACES = SUPPORT / "places.json"
LATEST = SUPPORT / "wifi-latest.json"   # rewritten every few seconds by the helper app while logging
HELPER_APP = SUPPORT / "WiFi Heatmap Helper.app"
HELPER_BIN = HELPER_APP / "Contents/MacOS/wifi-heatmap-helper"
