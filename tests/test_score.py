"""Scoring and ranking, on hand-made samples and on the demo data.

Run: python3 -m unittest discover tests
"""

import unittest

from wifiheatmap import demo, score


def sample(place="p", rssi=-60, ping=20.0, recv=4, connected=True, session="s1", ts=0.0):
    return {"kind": "sample", "place": place, "session": session, "ts": ts, "connected": connected,
            "rssi": rssi if connected else None, "noise": -94 if connected else None,
            "band": "5GHz", "bssid": "02:00:00:00:00:01" if connected else None,
            "ping_sent": 4, "ping_recv": recv, "ping_ms": ping if recv else None}


def place(pid="p", name="Place"):
    return {"id": pid, "name": name, "created": "", "pin": None}


class Parts(unittest.TestCase):
    def test_scales(self):
        self.assertEqual((score.lin(-55, -85, -55), score.lin(-70, -85, -55), score.lin(-95, -85, -55)),
                         (100.0, 50.0, 0.0))
        self.assertEqual(score.loglin(20, 400, 20), 100.0)
        self.assertEqual(score.loglin(400, 400, 20), 0.0)
        self.assertAlmostEqual(score.loglin(89.4, 400, 20), 50.0, delta=0.1)   # geometric middle
        self.assertEqual(score.loglin(0, 400, 20), 100.0)   # 0 ms ping: best
        self.assertEqual(score.loglin(0, 1, 50), 0.0)        # 0 Mbit/s: worst

    def test_percentile(self):
        self.assertEqual(score.percentile([10, 20, 30, 40, 50, 60, 70, 80, 90, 500], 90), 90)
        self.assertEqual(score.percentile([5], 90), 5)

    def test_labels(self):
        self.assertEqual([score.label(s) for s in (90, 75, 60, 30, 29, None)],
                         ["great", "great", "ok", "poor", "dead zone", "unranked"])


class Summarize(unittest.TestCase):
    def test_needs_min_samples(self):
        rows = score.summarize([place()], [sample() for _ in range(score.MIN_SAMPLES - 1)])
        self.assertEqual((rows[0]["score"], rows[0]["label"]), (None, "unranked"))
        rows = score.summarize([place()], [sample() for _ in range(score.MIN_SAMPLES)])
        self.assertIsNotNone(rows[0]["score"])

    def test_perfect_place_without_speedtest(self):
        rows = score.summarize([place()], [sample(rssi=-50, ping=10) for _ in range(20)])
        self.assertEqual(rows[0]["parts"], {"signal": 100.0, "latency": 100.0, "loss": 100.0})
        self.assertEqual((rows[0]["score"], rows[0]["label"], rows[0]["why"]), (100, "great", None))

    def test_speed_counts_and_errors_are_ignored(self):
        recs = [sample(rssi=-50, ping=10) for _ in range(20)]
        recs += [{"kind": "speed", "place": "p", "dl_mbps": 1.0, "ul_mbps": 0.5},
                 {"kind": "speed", "place": "p", "error": "no network"}]
        r = score.summarize([place()], recs)[0]
        self.assertEqual((r["speedtests"], r["parts"]["speed"]), (1, 0.0))
        self.assertEqual(r["score"], 80)   # everything perfect but speed (weight 0.20)
        self.assertEqual(r["why"], "slow")

    def test_disconnected_samples_hurt_signal_and_loss(self):
        recs = [sample(rssi=-55) for _ in range(10)] + [sample(connected=False, recv=0) for _ in range(10)]
        r = score.summarize([place()], recs)[0]
        self.assertEqual((r["connected"], r["rssi"], r["loss"]), (0.5, -55, 50.0))
        self.assertEqual(r["parts"]["signal"], 50.0)
        self.assertEqual(r["parts"]["loss"], 0.0)

    def test_p90_catches_spikes(self):
        recs = [sample(ping=20) for _ in range(17)] + [sample(ping=600) for _ in range(3)]
        r = score.summarize([place()], recs)[0]
        self.assertEqual((r["ping_ms"], r["ping_p90"]), (20, 600))
        self.assertIn("laggy", r["why"])

    def test_ranking_and_other_places_ignored(self):
        recs = ([sample("a", rssi=-84, ping=350, recv=3) for _ in range(15)] +
                [sample("b", rssi=-52, ping=15) for _ in range(15)] +
                [sample("c") for _ in range(3)] +
                [sample("gone") for _ in range(30)])   # a place that was deleted
        rows = score.summarize([place("a", "A"), place("b", "B"), place("c", "C")], recs)
        self.assertEqual([r["id"] for r in rows], ["b", "a", "c"])
        self.assertEqual([r["id"] for r in score.best(rows)], ["b"])
        self.assertEqual([r["id"] for r in score.dead(rows)], ["a"])

    def test_sessions_aps_and_time_span(self):
        recs = [sample(session="s1", ts=100.0), sample(session="s2", ts=50.0), sample(session="s2", ts=300.0)]
        r = score.summarize([place()], recs)[0]
        self.assertEqual((r["sessions"], r["aps"], r["bands"], r["first"], r["last"]), (2, 1, ["5GHz"], 50.0, 300.0))


class Demo(unittest.TestCase):
    def test_same_seed_same_data(self):
        self.assertEqual(demo.generate(), demo.generate())
        self.assertNotEqual(demo.generate(seed=1)[1], demo.generate(seed=2)[1])

    def test_demo_ranking_finds_the_personalities(self):
        rows = score.summarize(*demo.generate())
        names = [r["name"] for r in rows]
        self.assertEqual(names[0], "Library L2, window side")
        self.assertEqual([r["name"] for r in score.dead(rows)], ["Library basement"])
        self.assertEqual(rows[-1]["name"], "Bus stop")
        self.assertIsNone(rows[-1]["score"])

    def test_demo_uses_fake_bssids_only(self):
        _, recs = demo.generate()
        bssids = {r["bssid"] for r in recs if r.get("bssid")}
        self.assertTrue(bssids and all(b.startswith("02:00:00:00:") for b in bssids))


if __name__ == "__main__":
    unittest.main()
