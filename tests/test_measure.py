"""Parsing ping and networkQuality output. Fixtures are made up, in the format macOS prints.

Run: python3 -m unittest discover tests
"""

import json
import unittest

from wifiheatmap import measure, wifi

PING_OK = """PING 1.1.1.1 (1.1.1.1): 56 data bytes

--- 1.1.1.1 ping statistics ---
4 packets transmitted, 3 packets received, 25.0% packet loss
round-trip min/avg/max/stddev = 20.517/29.331/42.482/8.344 ms
"""

PING_ALL_LOST = """PING 1.1.1.1 (1.1.1.1): 56 data bytes

--- 1.1.1.1 ping statistics ---
4 packets transmitted, 0 packets received, 100.0% packet loss
"""

NQ = {"base_rtt": 57.13, "dl_throughput": 6096169, "ul_throughput": 22135912, "responsiveness": 26.15,
      "dl_bytes_transferred": 9123456, "ul_bytes_transferred": 21987654, "interface_name": "en0"}


class Ping(unittest.TestCase):
    def test_some_lost(self):
        p = measure.parse_ping(PING_OK)
        self.assertEqual((p["ping_sent"], p["ping_recv"], p["loss"]), (4, 3, 25.0))
        self.assertEqual((p["ping_min"], p["ping_ms"], p["ping_max"], p["jitter_ms"]), (20.5, 29.3, 42.5, 8.3))

    def test_all_lost(self):
        p = measure.parse_ping(PING_ALL_LOST)
        self.assertEqual((p["ping_recv"], p["loss"], p["ping_ms"]), (0, 100.0, None))

    def test_no_output(self):   # e.g. no route to host: count everything as lost
        p = measure.parse_ping("", count=4)
        self.assertEqual((p["ping_sent"], p["loss"], p["ping_ms"]), (4, 100.0, None))


class Speed(unittest.TestCase):
    def test_result(self):
        s = measure.parse_speed(json.dumps(NQ))
        self.assertEqual(s, {"dl_mbps": 6.1, "ul_mbps": 22.1, "rtt_ms": 57.1, "rpm": 26.1,
                             "dl_mb": 9.1, "ul_mb": 22.0})

    def test_garbage(self):
        self.assertIn("error", measure.parse_speed("networkQuality: no network"))

    def test_error_json(self):
        self.assertEqual(measure.parse_speed('{"error_code": -1009}'), {"error": "-1009"})


class Bars(unittest.TestCase):
    def test_bars(self):
        self.assertEqual([wifi.bars(r) for r in (-45, -60, -70, -78, -90, None)],
                         ["▂▄▆█", "▂▄▆·", "▂▄··", "▂···", "····", "····"])


if __name__ == "__main__":
    unittest.main()
