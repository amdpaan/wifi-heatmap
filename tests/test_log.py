"""Places and the log command, end to end with a fake Wi-Fi helper and fake ping / speed test.
The fake access point uses a locally administered MAC (02:...), never a real one.

Run: python3 -m unittest discover tests
"""

import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HOME = tempfile.mkdtemp()
os.environ["WIFI_HEATMAP_HOME"] = HOME

from wifiheatmap import cli, measure, paths, places, samples  # noqa: E402

FAKE_WIFI = {"connected": True, "rssi": -61, "noise": -94, "channel": 36, "band": "5GHz", "width": 80,
             "tx_rate": 433.0, "phy": "802.11ac", "ssid": "Demo-WiFi", "bssid": "02:00:00:00:00:01",
             "location": "authorized", "pid": 1}
FAKE_PING = {"ping_sent": 4, "ping_recv": 3, "loss": 25.0, "ping_ms": 30.0, "ping_min": 20.0,
             "ping_max": 40.0, "jitter_ms": 5.0}
FAKE_SPEED = {"dl_mbps": 50.0, "ul_mbps": 20.0, "rtt_ms": 12.0, "rpm": 900.0, "dl_mb": 10.0, "ul_mb": 5.0,
              "secs": 11.0}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), \
            mock.patch.object(measure, "ping", return_value=dict(FAKE_PING)), \
            mock.patch.object(measure, "speedtest", return_value=dict(FAKE_SPEED)):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(HOME, ignore_errors=True)
        os.makedirs(HOME)
        helper = Path(HOME) / "fake-helper"
        helper.write_text(f"#!{sys.executable}\nprint({json.dumps(json.dumps(FAKE_WIFI))})\n")
        helper.chmod(helper.stat().st_mode | stat.S_IEXEC)
        os.environ["WIFI_HEATMAP_HELPER"] = str(helper)

    def tearDown(self):
        os.environ.pop("WIFI_HEATMAP_HELPER", None)


class Places(Base):
    def test_add_and_find(self):
        p = places.add("  Library   L2 ")
        self.assertEqual((p["id"], p["name"]), ("library-l2", "Library L2"))
        self.assertEqual(places.find(places.load(), "library l2")["id"], "library-l2")
        with self.assertRaises(places.PlaceError):
            places.add("library l2")

    def test_same_slug_gets_a_suffix(self):
        places.add("Café 1")
        self.assertEqual(places.add("Caf 1")["id"], "caf-1-2")

    def test_rename_keeps_id(self):
        places.add("Library L2")
        p = places.rename("Library L2", "Library L2, window side")
        self.assertEqual((p["id"], places.load()[0]["name"]), ("library-l2", "Library L2, window side"))


class Log(Base):
    def test_log_writes_checkin_speed_samples_checkout(self):
        code, out, _ = run("log", "--place", "Library L2", "--count", "3", "--interval", "0")
        self.assertEqual(code, 0)
        recs = list(samples.read())
        self.assertEqual([r["kind"] for r in recs], ["checkin", "speed", "sample", "sample", "sample", "checkout"])
        self.assertEqual({r["place"] for r in recs}, {"library-l2"})
        self.assertEqual(len({r["session"] for r in recs}), 1)
        s = recs[2]
        self.assertEqual((s["rssi"], s["bssid"], s["ping_ms"], s["loss"]), (-61, "02:00:00:00:00:01", 30.0, 25.0))
        self.assertNotIn("pid", s)
        self.assertIn("New place: Library L2", out)
        self.assertIn("▂▄▆·  -61 dBm  SNR 33", out)
        self.assertIn("3 samples", out)
        self.assertIn("median signal -61 dBm, median ping 30 ms, 25% loss", out)

    def test_no_speedtest(self):
        run("log", "--place", "Library L2", "--count", "1", "--interval", "0", "--no-speedtest")
        self.assertEqual([r["kind"] for r in samples.read()], ["checkin", "sample", "checkout"])

    def test_typo_needs_new(self):
        places.add("Library L2")
        code, _, err = run("log", "--place", "Library L3", "--count", "1", "--interval", "0")
        self.assertEqual(code, 1)
        self.assertIn("Did you mean 'Library L2'", err)
        self.assertEqual(list(samples.read()), [])
        code, out, _ = run("log", "--place", "Library L3", "--new", "--count", "1", "--interval", "0")
        self.assertEqual(code, 0)
        self.assertEqual(len(places.load()), 2)

    def test_disconnected(self):
        Path(os.environ["WIFI_HEATMAP_HELPER"]).write_text(
            f"#!{sys.executable}\nprint('{{\"connected\": false, \"location\": \"authorized\"}}')\n")
        code, out, _ = run("log", "--place", "Lab", "--count", "1", "--interval", "0", "--no-speedtest")
        self.assertEqual(code, 0)
        self.assertIn("not connected to Wi-Fi", out)

    def test_place_list_counts(self):
        run("log", "--place", "Library L2", "--count", "2", "--interval", "0", "--no-speedtest")
        code, out, _ = run("place")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"Library L2 +2 samples")

    def test_missing_helper(self):
        os.environ["WIFI_HEATMAP_HELPER"] = str(Path(HOME) / "nope")
        code, _, err = run("now")
        self.assertEqual(code, 1)
        self.assertIn("tools/build-helper.sh", err)

    def test_data_stays_in_home(self):
        run("log", "--place", "Library L2", "--count", "1", "--interval", "0")
        self.assertTrue(str(paths.SAMPLES).startswith(HOME))
        self.assertTrue(paths.SAMPLES.exists() and paths.PLACES.exists())


if __name__ == "__main__":
    unittest.main()
