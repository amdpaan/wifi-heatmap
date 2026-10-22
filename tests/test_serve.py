"""The dashboard server: access rules, the demo, writes, map upload and check-in / stop, against a real
server on a free port, with the fake Wi-Fi helper and mocked ping / speed test from test_log.

Run: python3 -m unittest discover tests
"""

import http.client
import json
import os
import threading
import time
import unittest
from unittest import mock

from test_log import FAKE_PING, FAKE_SPEED, Base

from wifiheatmap import measure, paths, places, samples, score, serve

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64   # only the signature is checked


class Server:
    def __init__(self, **kw):
        self.app = serve.App(**kw)
        self.srv = serve.make_server(self.app, port=0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def req(self, method, path, body=None, ctype="application/json", host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host or "127.0.0.1:%d" % self.port}
        if body is not None:
            headers["Content-Type"] = ctype
            body = body if isinstance(body, bytes) else json.dumps(body).encode()
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class Demo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server(demo_mode=True)

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def test_state(self):
        code, st = self.s.req("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertTrue(st["demo"])
        self.assertEqual(st["best"][0], "library-l2-window-side")
        self.assertEqual(st["dead"], ["library-basement"])
        self.assertEqual(st["live"]["owner"], "demo")
        self.assertTrue(all(p["pin"] for p in st["places"]))

    def test_detail_shows_the_lunch_dip(self):
        code, d = self.s.req("GET", "/api/places/cafeteria")
        self.assertEqual(code, 200)
        hours = {h["hour"]: h["score"] for h in d["hours"] if h["score"] is not None}
        self.assertLess(hours[12], min(v for k, v in hours.items() if k != 12) - 10)

    def test_map_and_static(self):
        for path in ("/", "/app.js", "/style.css", "/icon.svg", "/map"):
            code, _ = self.s.req("GET", path)
            self.assertEqual(code, 200, path)

    def test_demo_refuses_writes(self):
        for path, body in (("/api/checkin", {"place": "x"}), ("/api/places", {"name": "x"}),
                           ("/api/places/cafeteria", {"pin": None})):
            code, d = self.s.req("POST", path, body)
            self.assertEqual(code, 403, path)
        code, _ = self.s.req("POST", "/api/map", PNG, ctype="image/png")
        self.assertEqual(code, 403)

    def test_foreign_host_refused(self):   # DNS rebinding
        code, _ = self.s.req("GET", "/api/state", host="evil.example")
        self.assertEqual(code, 403)

    def test_unknown_place_404(self):
        self.assertEqual(self.s.req("GET", "/api/places/nope")[0], 404)


class Real(Base):
    def setUp(self):
        super().setUp()
        self.s = Server()

    def tearDown(self):
        if self.s.app.logging_here():
            self.s.app.stop.set()
            self.s.app.thread.join(5)
        self.s.close()
        super().tearDown()

    def test_empty(self):
        code, st = self.s.req("GET", "/api/state")
        self.assertEqual((code, st["places"], st["map"], st["live"]), (200, [], None, None))

    def test_places_pins_and_rename(self):
        code, d = self.s.req("POST", "/api/places", {"name": "Library L2"})
        self.assertEqual(code, 200)
        pid = d["place"]["id"]
        self.assertEqual(self.s.req("POST", "/api/places/" + pid, {"pin": {"x": 0.25, "y": 0.5}})[0], 200)
        self.assertEqual(places.load()[0]["pin"], {"x": 0.25, "y": 0.5})
        self.assertEqual(self.s.req("POST", "/api/places/" + pid, {"pin": {"x": 2, "y": 0.5}})[0], 400)
        self.assertEqual(self.s.req("POST", "/api/places/" + pid, {"pin": "here"})[0], 400)
        self.assertEqual(self.s.req("POST", "/api/places/" + pid, {"name": "Library L2, window"})[0], 200)
        self.assertEqual(self.s.req("POST", "/api/places/" + pid, {"name": " "})[0], 400)
        self.assertEqual(self.s.req("POST", "/api/places/" + pid, {"pin": None})[0], 200)
        self.assertEqual(places.load()[0], dict(places.load()[0], name="Library L2, window", pin=None))
        self.assertEqual(self.s.req("POST", "/api/places/nope", {"pin": None})[0], 404)

    def test_posts_must_be_json(self):   # no cross-site form posts
        code, _ = self.s.req("POST", "/api/places", b"name=x", ctype="application/x-www-form-urlencoded")
        self.assertEqual(code, 400)

    def test_map_upload(self):
        self.assertEqual(self.s.req("POST", "/api/map", b"<svg/>", ctype="image/svg+xml")[0], 415)
        self.assertEqual(self.s.req("POST", "/api/map", b"not a png", ctype="image/png")[0], 400)
        self.assertEqual(self.s.req("POST", "/api/map", PNG, ctype="image/png")[0], 200)
        code, st = self.s.req("GET", "/api/state")
        self.assertTrue(st["map"]["url"].startswith("/map?v="))
        self.assertEqual(self.s.req("GET", "/map"), (200, PNG))
        self.assertTrue(str(serve.map_file()).startswith(str(paths.SUPPORT)))

    def test_checkin_and_stop(self):
        with mock.patch.object(measure, "ping", return_value=dict(FAKE_PING)), \
                mock.patch.object(measure, "speedtest", return_value=dict(FAKE_SPEED)):
            self.s.app.interval = 0.05
            code, d = self.s.req("POST", "/api/checkin", {"place": "Cafeteria"})
            self.assertEqual(code, 200)
            self.assertEqual(self.s.req("POST", "/api/checkin", {"place": "Cafeteria"})[0], 409)
            deadline = time.time() + 5
            while time.time() < deadline:
                st = self.s.req("GET", "/api/state")[1]
                if st["live"] and st["live"]["samples"] >= 2:
                    break
                time.sleep(0.05)
            self.assertEqual((st["live"]["owner"], st["live"]["place"]), ("web", "cafeteria"))
            self.assertEqual(st["live"]["speed"]["dl_mbps"], 50.0)
            code, d = self.s.req("POST", "/api/checkout", {})
        self.assertEqual(code, 200)
        self.assertIn("Cafeteria:", d["summary"])
        kinds = [r["kind"] for r in samples.read()]
        self.assertEqual((kinds[:2], kinds[-1]), (["checkin", "speed"], "checkout"))
        self.assertIsNone(self.s.req("GET", "/api/state")[1]["live"])
        self.assertEqual(self.s.req("POST", "/api/checkout", {})[0], 409)

    def test_checkin_refused_while_terminal_logs(self):
        places.add("Lab")
        samples.append({"kind": "checkin", "ts": time.time(), "place": "lab", "session": "t1"})
        code, d = self.s.req("POST", "/api/checkin", {"place": "Lab"})
        self.assertEqual(code, 409)
        self.assertIn("terminal", d["error"])
        self.assertEqual(self.s.req("GET", "/api/state")[1]["live"]["owner"], "terminal")

    def test_checkin_typo_needs_new(self):
        places.add("Library L2")
        code, d = self.s.req("POST", "/api/checkin", {"place": "Library L3", "speedtest": False})
        self.assertEqual(code, 409)
        self.assertIn("Did you mean", d["error"])

    def test_checkin_without_helper(self):
        os.environ.pop("WIFI_HEATMAP_HELPER")
        code, d = self.s.req("POST", "/api/checkin", {"place": "Lab"})
        self.assertEqual(code, 400)
        self.assertIn("build-helper", d["error"])


class Phone(Base):
    def test_off_without_lan(self):
        s = Server()
        try:
            self.assertEqual(s.req("GET", "/api/phone"), (200, {"lan": False}))
        finally:
            s.close()

    def test_links_carry_the_token(self):
        s = Server(lan=True, token="tok123")
        try:
            with mock.patch.object(serve, "local_ip", return_value="10.0.0.5"), \
                    mock.patch.object(serve, "local_hostname", return_value="my-mac.local"), \
                    mock.patch.object(serve, "qr_rows", return_value=["101", "010", "101"]):
                code, d = s.req("GET", "/api/phone")
        finally:
            s.close()
        self.assertEqual(code, 200)
        self.assertEqual(d["links"], ["http://10.0.0.5:%d/?t=tok123" % s.port, "http://my-mac.local:%d/?t=tok123" % s.port])
        self.assertEqual(d["qr"], ["101", "010", "101"])

    def test_qr_without_helper_is_none(self):
        serve._qr_cache.clear()
        self.assertIsNone(serve.qr_rows("http://example/"))   # no helper app in the test home


class Live(unittest.TestCase):
    def rec(self, kind, ts, session="a"):
        return {"kind": kind, "ts": ts, "place": "p", "session": session}

    def test_live_and_stale(self):
        recs = [self.rec("checkin", 100), self.rec("sample", 105), self.rec("sample", 110)]
        lv = score.live(recs, now=120)
        self.assertEqual((lv["session"], lv["samples"], lv["since"]), ("a", 2, 100))
        self.assertIsNone(score.live(recs, now=110 + score.LIVE_GRACE + 1))
        self.assertIsNone(score.live(recs + [self.rec("checkout", 111)], now=112))

    def test_speed_test_gets_longer_grace(self):
        recs = [self.rec("checkin", 100)]
        self.assertIsNotNone(score.live(recs, now=100 + score.LIVE_GRACE + 10))
        self.assertIsNone(score.live(recs, now=100 + score.SPEED_GRACE + 1))


if __name__ == "__main__":
    unittest.main()
