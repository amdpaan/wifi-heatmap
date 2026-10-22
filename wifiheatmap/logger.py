"""One logging session at a place: check in, a speed test, then Wi-Fi + ping every few seconds until
stopped. Used by `wifi-heatmap log` (stopped with Ctrl-C) and by the dashboard's Check in button
(stopped with an Event)."""

import statistics
import threading
import time
import uuid

from . import measure, samples, wifi
from . import summary as summary_file


class Session:
    def __init__(self, place, interval=5.0, speedtest=True, out=None):
        self.place, self.interval, self.speedtest = place, interval, speedtest
        self.out = out or (lambda *a, **k: None)
        self.base = {"place": place["id"], "session": uuid.uuid4().hex[:8]}
        self.n, self.rssi, self.pings, self.sent, self.lost = 0, [], [], 0, 0
        self.started = None

    def run(self, stop=None, count=None):
        """Log until `stop` is set, `count` samples are taken or Ctrl-C. Raises wifi.HelperMissing
        before writing anything if the Wi-Fi can't be read at all."""
        stop = stop or threading.Event()
        reader = wifi.Reader()
        streaming = reader.start()
        try:
            first = reader.read()
            self.out("start", first=first, streaming=streaming)
            samples.append(dict(kind="checkin", ts=round(time.time(), 1), **self.base))
            self.refresh()
            if self.speedtest and not stop.is_set():
                self.out("speedtest")
                s = measure.speedtest()
                samples.append(dict(kind="speed", ts=round(time.time(), 1), **self.base, **s))
                self.out("speed", result=s)
            self.started = time.time()
            try:
                while not stop.is_set() and (count is None or self.n < count):
                    t0 = time.time()
                    self.take(reader)
                    if count is None or self.n < count:
                        stop.wait(max(0.0, self.interval - (time.time() - t0)))
            except KeyboardInterrupt:
                pass
            samples.append(dict(kind="checkout", ts=round(time.time(), 1), **self.base))
            self.refresh()
        finally:
            reader.stop()
        return self.summary()

    def take(self, reader):
        w = reader.read()
        rec = dict(kind="sample", ts=round(time.time(), 1), **self.base,
                   **{k: w.get(k) for k in samples.WIFI_KEYS}, **measure.ping())
        samples.append(rec)
        self.n += 1
        if rec.get("rssi") is not None:
            self.rssi.append(rec["rssi"])
        if rec.get("ping_ms") is not None:
            self.pings.append(rec["ping_ms"])
        self.sent += rec["ping_sent"]
        self.lost += rec["ping_sent"] - rec["ping_recv"]
        self.out("sample", rec=rec)
        self.refresh()

    def refresh(self):
        """Rewrite summary.json for widgets. Never stops the logging if it fails."""
        try:
            summary_file.write()
        except (OSError, ValueError) as e:
            self.out("summary_error", error=e)

    def summary(self):
        mins, secs = divmod(int(time.time() - (self.started or time.time())), 60)
        parts = [f"{self.n} samples over {mins}m{secs:02d}s"]
        if self.rssi:
            parts.append(f"median signal {statistics.median(self.rssi):.0f} dBm")
        if self.pings:
            parts.append(f"median ping {statistics.median(self.pings):.0f} ms")
        if self.sent:
            parts.append(f"{100.0 * self.lost / self.sent:.0f}% loss")
        return f"{self.place['name']}: " + ", ".join(parts)
