"""This Mac's own Wi-Fi connection, read by the Swift helper (helper/main.swift).

The helper app streams the latest sample to paths.LATEST while we log; that's the only way to get the
SSID and BSSID (Location permission). When the app isn't installed or its sample goes stale, we run
the helper binary directly instead, which gives everything except the SSID and BSSID.
WIFI_HEATMAP_HELPER points at another command that prints one sample (tests use a fake one).
"""

import json
import os
import signal
import subprocess
import time

from . import paths


class HelperMissing(Exception):
    pass


class Reader:
    def __init__(self, interval=2.0):
        self.interval = interval
        self.started = 0.0
        self.streaming = False
        self.helper_pid = None

    def start(self, wait=5.0):
        """Start the helper app streaming. Returns False (and keeps using --once) if it can't."""
        if os.environ.get("WIFI_HEATMAP_HELPER") or not paths.HELPER_APP.exists():
            return False
        self.started = time.time()
        r = subprocess.run(["open", "-g", "-n", str(paths.HELPER_APP), "--args",
                            "--stream", str(paths.LATEST), "--interval", str(self.interval),
                            "--parent", str(os.getpid())],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            return False
        deadline = time.time() + wait
        while time.time() < deadline:
            if self._latest():
                self.streaming = True
                return True
            time.sleep(0.2)
        return False

    def _latest(self):
        try:
            d = json.loads(paths.LATEST.read_text())
        except (OSError, ValueError):
            return None
        ts = d.get("ts", 0)
        if ts < self.started or time.time() - ts > 3 * self.interval + 2:
            return None   # left over from an earlier run, or the helper died
        self.helper_pid = d.get("pid")
        return d

    def read(self):
        d = self._latest() if self.streaming else None
        return d if d is not None else once()

    def stop(self):
        if self.helper_pid:
            try:
                os.kill(self.helper_pid, signal.SIGTERM)
            except OSError:
                pass
        self.streaming = False


def once():
    cmd = os.environ.get("WIFI_HEATMAP_HELPER")
    cmd = [cmd] if cmd else [str(paths.HELPER_BIN), "--once"]
    if not os.path.exists(cmd[0]):
        raise HelperMissing("The Wi-Fi helper isn't built yet. Run: tools/build-helper.sh")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise HelperMissing(f"The Wi-Fi helper failed: {(r.stderr or r.stdout).strip()[:200]}")


BAR_STEPS = (-80, -72, -65, -55)   # dBm for 1-4 bars (the dashboard's app.js uses the same)


def bar_count(rssi):
    return 0 if rssi is None else sum(rssi >= t for t in BAR_STEPS)


def bars(rssi):
    """Signal bars like the menu bar's, from RSSI in dBm."""
    n = bar_count(rssi)
    return "▂▄▆█"[:n] + "·" * (4 - n)
