"""summary.json for desktop widgets.

Run: python3 -m unittest discover tests
"""

import json
import time
import unittest

from test_log import Base, run

from wifiheatmap import demo, paths, summary


class Build(unittest.TestCase):
    def test_demo_without_live(self):
        places, records = demo.generate()
        d = summary.build(places, records, now=time.time())
        self.assertEqual((d["mood"], d["level"], d["live"]), ("great", 4, None))
        self.assertEqual(d["best"], {"name": "Library L2, window side", "score": d["best"]["score"], "label": "great"})
        self.assertEqual([x["name"] for x in d["dead"]], ["Library basement"])
        self.assertEqual((d["ranked"], d["places"]), (6, 7))

    def test_live_follows_the_signal(self):
        places = [{"id": "p", "name": "Lab", "pin": None}]
        base = {"place": "p", "session": "s"}
        recs = [dict(kind="checkin", ts=100.0, **base),
                dict(kind="sample", ts=105.0, connected=True, rssi=-76, ping_ms=40.0, loss=0.0,
                     ssid="Demo-WiFi", bssid="02:00:00:00:00:01", **base)]
        d = summary.build(places, recs, now=110)
        self.assertEqual((d["mood"], d["level"]), ("dead", 1))
        self.assertEqual((d["base_mood"], d["base_level"]), ("idle", 0))   # nothing ranked yet
        self.assertEqual((d["live"]["place"], d["live"]["rssi"], d["live"]["samples"]), ("Lab", -76, 1))
        text = json.dumps(d)
        self.assertNotIn("Demo-WiFi", text)              # never the network name...
        self.assertNotIn("02:00:00:00:00:01", text)      # ...or the access point

    def test_checked_in_waiting_for_first_sample(self):
        recs = [{"kind": "checkin", "ts": 100.0, "place": "p", "session": "s"}]
        d = summary.build([{"id": "p", "name": "Lab", "pin": None}], recs, now=101)
        self.assertEqual((d["mood"], d["live"]["samples"]), ("idle", 0))

    def test_empty(self):
        d = summary.build([], [], now=1)
        self.assertEqual((d["mood"], d["level"], d["best"], d["dead"], d["places"]), ("idle", 0, None, [], 0))


class Written(Base):
    def test_log_keeps_it_current(self):
        run("log", "--place", "Library L2", "--count", "12", "--interval", "0", "--no-speedtest")
        d = json.loads(paths.SUMMARY.read_text())
        self.assertIsNone(d["live"])   # checked out
        self.assertEqual((d["ranked"], d["best"]), (1, {"name": "Library L2", "score": 62, "label": "ok"}))
        self.assertEqual((d["mood"], d["level"]), ("ok", 3))
        self.assertTrue(str(paths.SUMMARY).startswith(str(paths.SUPPORT)))


if __name__ == "__main__":
    unittest.main()
