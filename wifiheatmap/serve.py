"""wifi-heatmap serve: the dashboard and its JSON API on a small local web server (stdlib http.server).

Access rules (the same as net-watch's dashboard):
- By default it binds 127.0.0.1, and requests must carry a localhost Host header. That stops DNS rebinding:
  a web page you visit can't point its own domain at 127.0.0.1 and read your places.
- With --lan it binds 0.0.0.0 so your phone can open it. Requests from other machines then need the token
  (printed in the URL once, then kept in a SameSite cookie). Without it they get nothing, not even reads.
- Writes are POSTs with a JSON body (or an image, for the map). Browsers can't send those cross-site without
  a CORS preflight, which we never answer.
- --demo serves made-up data and refuses every write.
- /api/phone (the phone link with the token, and its QR code) only ever answers this Mac itself.
"""

import hmac
import ipaddress
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import demo, logger, paths, places, samples, score, wifi

WEB = Path(__file__).parent / "web"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}
PLACE_PATH = re.compile(r"^/api/places/([a-z0-9-]{1,80})$")
COOKIE = "wifiheatmap_token"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 10_000
MAX_MAP = 15_000_000
# Only raster images: an uploaded SVG could carry script when opened directly.
MAP_TYPES = {"image/png": ("png", b"\x89PNG"), "image/jpeg": ("jpg", b"\xff\xd8\xff"), "image/webp": ("webp", b"RIFF")}
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",  # the LAN token can be in the URL
    "Cache-Control": "no-store",
}


class Refused(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def map_file():
    for ext, _ in MAP_TYPES.values():
        f = paths.MAPS / f"map.{ext}"
        if f.exists():
            return f
    return None


class App:
    interval = 5.0   # seconds between samples when logging from the dashboard

    def __init__(self, demo_mode=False, lan=False, token=None, verbose=False):
        self.demo, self.lan, self.token, self.verbose = demo_mode, lan, token, verbose
        self.lock = threading.Lock()
        self.session = self.thread = self.stop = None
        self.session_error = None
        self._cache = (None, [])
        if demo_mode:
            p, r = demo.generate()
            self._demo = (demo.with_pins(p), r)

    # ---- data
    def places(self):
        return self._demo[0] if self.demo else places.load()

    def records(self):
        if self.demo:
            return self._demo[1]
        try:
            st = paths.SAMPLES.stat()
            key = (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return []
        if self._cache[0] != key:   # re-read only when the log changed
            self._cache = (key, list(samples.read()))
        return self._cache[1]

    def logging_here(self):
        return bool(self.thread and self.thread.is_alive())

    def live(self, now):
        if self.demo:
            return dict(demo.live(now), owner="demo")
        lv = score.live(self.records(), now)
        if lv:
            lv["owner"] = "web" if self.logging_here() and lv["session"] == self.session.base["session"] else "terminal"
        return lv

    def state(self):
        now = time.time()
        known = self.places()
        rows = score.summarize(known, self.records())
        pins = {p["id"]: p.get("pin") for p in known}
        for r in rows:
            r["pin"] = pins.get(r["id"])
        mf = None if self.demo else map_file()
        return {
            "now": now, "demo": self.demo, "places": rows,
            "best": [r["id"] for r in score.best(rows)], "dead": [r["id"] for r in score.dead(rows)],
            "map": ({"url": "/map"} if self.demo else {"url": f"/map?v={int(mf.stat().st_mtime)}"} if mf else None),
            "live": self.live(now), "session_error": self.session_error,
            "min_samples": score.MIN_SAMPLES,
            "thresholds": {"great": score.GREAT, "ok": score.OK, "poor": score.POOR},
        }

    def phone(self, port):
        """The links (and a QR code for the first) that open the dashboard on a phone on the same network."""
        if not self.lan:
            return {"lan": False}
        hosts = [h for h in (local_ip(), local_hostname()) if h]
        links = ["http://%s:%d/?t=%s" % (h, port, self.token) for h in hosts]
        return {"lan": True, "links": links, "qr": qr_rows(links[0]) if links else None}

    def detail(self, pid):
        d = score.detail(self.places(), self.records(), pid)
        if d is None:
            raise Refused(404, "No such place")
        return d

    # ---- writes
    def writable(self):
        if self.demo:
            raise Refused(403, "This is the demo: nothing can be changed.")

    def checkin(self, name, new=False, speedtest=True):
        self.writable()
        with self.lock:
            if self.logging_here():
                raise Refused(409, "Already logging. Stop first.")
            lv = score.live(self.records(), time.time())
            if lv:
                raise Refused(409, "You're logging from the terminal. Stop it there first.")
            if not (paths.HELPER_APP.exists() or paths.HELPER_BIN.exists()
                    or os.environ.get("WIFI_HEATMAP_HELPER")):
                raise Refused(400, "The Wi-Fi helper isn't built yet. Run: tools/build-helper.sh")
            known = places.load()
            p = places.find(known, name)
            if not p:
                close = places.similar(known, name)
                if close and not new:
                    raise Refused(409, "No place called %r. Did you mean %s?" % (name, ", ".join(close)))
                p = places.add(name)
            self.session_error = None
            self.session = logger.Session(p, interval=self.interval, speedtest=speedtest)
            self.stop = threading.Event()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            return p

    def _run(self):
        try:
            self.session.run(self.stop)
        except Exception as e:   # keep serving; show what went wrong
            self.session_error = "Logging stopped: %s" % e

    def checkout(self):
        self.writable()
        if not self.logging_here():
            raise Refused(409, "Not logging from the dashboard.")
        self.stop.set()
        self.thread.join(timeout=15)
        return self.session.summary()

    def save_map(self, ctype, data):
        self.writable()
        kind = MAP_TYPES.get(ctype)
        if not kind:
            raise Refused(415, "The map must be a PNG, JPEG or WebP image.")
        ext, magic = kind
        if not data.startswith(magic) or (ext == "webp" and data[8:12] != b"WEBP"):
            raise Refused(400, "That file isn't a %s image." % ext.upper())
        paths.MAPS.mkdir(parents=True, exist_ok=True)
        for other, _ in MAP_TYPES.values():
            (paths.MAPS / f"map.{other}").unlink(missing_ok=True)
        tmp = paths.MAPS / f"map.{ext}.tmp"
        tmp.write_bytes(data)
        tmp.replace(paths.MAPS / f"map.{ext}")

    def map_bytes(self):
        if self.demo:
            return demo.DEMO_MAP.encode(), "image/svg+xml"
        f = map_file()
        if not f:
            raise Refused(404, "No map yet")
        ctype = next(t for t, (ext, _) in MAP_TYPES.items() if f.suffix == "." + ext)
        return f.read_bytes(), ctype


class Handler(BaseHTTPRequestHandler):
    server_version = "wifi-heatmap"
    sys_version = ""
    app = None  # type: App

    def log_message(self, fmt, *args):
        if self.app.verbose:
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    # ---- plumbing
    def send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        for k, v in dict(HEADERS, **(extra or {})).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj), "application/json")

    def error(self, code, message):
        self.json({"error": message}, code)

    def from_loopback(self):
        ip = ipaddress.ip_address(self.client_address[0])
        return ip.is_loopback or (getattr(ip, "ipv4_mapped", None) is not None and ip.ipv4_mapped.is_loopback)

    def host_name(self):
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            return host[1:].split("]")[0]
        return host.rsplit(":", 1)[0] if host.count(":") == 1 else host

    def cookie_token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE:
                return value
        return None

    def token_ok(self, value):
        return bool(value and self.app.token and hmac.compare_digest(value, self.app.token))

    def allowed(self, url):
        """Apply the access rules. Sends the refusal itself and returns False when not allowed."""
        if self.from_loopback():
            if self.host_name() in LOCAL_HOSTS:
                return True
            self.error(403, "Host not allowed. Open http://127.0.0.1:%d/" % self.server.server_port)
            return False
        if not self.app.lan:  # can't happen when bound to 127.0.0.1, but don't rely on it
            self.error(403, "LAN access is off.")
            return False
        query = urllib.parse.parse_qs(url.query)
        if self.token_ok((query.get("t") or [None])[0]):
            # Swap the token in the URL for a cookie, so it doesn't sit in history or get shared by accident
            self.send(302, extra={"Location": url.path or "/",
                                  "Set-Cookie": "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"
                                                % (COOKIE, self.app.token)})
            return False
        if self.token_ok(self.cookie_token()):
            return True
        self.send(401, "wifi-heatmap: open the link with the token that `wifi-heatmap serve --lan` printed.")
        return False

    def raw_body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise Refused(413, "Too large")
        return self.rfile.read(length)

    def body(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise Refused(400, "Content-Type must be application/json")
        try:
            data = json.loads(self.raw_body(MAX_BODY) or b"{}")
        except ValueError:
            raise Refused(400, "Body must be JSON")
        if not isinstance(data, dict):
            raise Refused(400, "Body must be a JSON object")
        return data

    # ---- routes
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if not self.allowed(url):
            return
        try:
            if url.path in STATIC:
                name, ctype = STATIC[url.path]
                return self.send(200, (WEB / name).read_bytes(), ctype)
            if url.path == "/api/state":
                return self.json(self.app.state())
            if url.path == "/api/phone":
                if not self.from_loopback():
                    raise Refused(403, "The phone link is only shown on the Mac itself.")
                return self.json(self.app.phone(self.server.server_port))
            if url.path == "/map":
                data, ctype = self.app.map_bytes()
                return self.send(200, data, ctype)
            m = PLACE_PATH.match(url.path)
            if m:
                return self.json(self.app.detail(m.group(1)))
            self.error(404, "Not found")
        except Refused as e:
            self.error(e.code, str(e))

    do_HEAD = do_GET

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        if not self.allowed(url):
            return
        try:
            if url.path == "/api/map":
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                self.app.writable()
                self.app.save_map(ctype, self.raw_body(MAX_MAP))
                return self.json({"ok": True})
            data = self.body()
            if url.path == "/api/checkin":
                name = data.get("place")
                if not isinstance(name, str) or not name.strip() or len(name) > 80:
                    raise Refused(400, "place must be a name, at most 80 characters")
                p = self.app.checkin(name, bool(data.get("new")), data.get("speedtest", True) is not False)
                return self.json({"ok": True, "place": p})
            if url.path == "/api/checkout":
                return self.json({"ok": True, "summary": self.app.checkout()})
            if url.path == "/api/places":
                self.app.writable()
                name = data.get("name")
                if not isinstance(name, str) or len(name) > 80:
                    raise Refused(400, "name must be text, at most 80 characters")
                return self.json({"ok": True, "place": places.add(name)})
            m = PLACE_PATH.match(url.path)
            if m:
                self.app.writable()
                pid = m.group(1)
                if not any(p["id"] == pid for p in places.load()):
                    raise Refused(404, "No such place")
                if "name" in data:
                    if not isinstance(data["name"], str) or len(data["name"]) > 80:
                        raise Refused(400, "name must be text, at most 80 characters")
                    places.rename(pid, data["name"])
                if "pin" in data:
                    pin = data["pin"]
                    if pin is not None and not (isinstance(pin, dict) and all(
                            isinstance(pin.get(k), (int, float)) for k in ("x", "y"))):
                        raise Refused(400, "pin must be {x, y} or null")
                    places.set_pin(pid, pin)
                return self.json({"ok": True})
            self.error(404, "Not found")
        except Refused as e:
            self.error(e.code, str(e))
        except places.PlaceError as e:
            self.error(400, str(e))


def make_server(app, host="127.0.0.1", port=8766):
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def lan_token(rotate=False):
    """A stable token in config.json (so a phone bookmark keeps working); --new-token rotates it."""
    try:
        cfg = json.loads(paths.CONFIG.read_text())
    except (OSError, ValueError):
        cfg = {}
    if rotate or not cfg.get("lan_token"):
        cfg["lan_token"] = secrets.token_urlsafe(18)
        paths.SUPPORT.mkdir(parents=True, exist_ok=True)
        paths.CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        paths.CONFIG.chmod(0o600)
    return cfg["lan_token"]


def local_ip():
    """This Mac's address on its Wi-Fi (en0), or another interface's if it's on Ethernet."""
    for iface in ("en0", "en1"):
        r = subprocess.run(["/usr/sbin/ipconfig", "getifaddr", iface], capture_output=True, text=True)
        if r.stdout.strip():
            return r.stdout.strip()
    return None


_qr_cache = {}


def qr_rows(text):
    """The QR code for text as rows of "0"/"1", from the Wi-Fi helper (CoreImage), or None."""
    if text not in _qr_cache:
        try:
            r = subprocess.run([str(paths.HELPER_BIN), "--qr", text], capture_output=True, text=True, timeout=5)
            rows = r.stdout.split()
            _qr_cache[text] = rows if r.returncode == 0 and rows and all(set(x) <= {"0", "1"} for x in rows) else None
        except (OSError, subprocess.TimeoutExpired):
            _qr_cache[text] = None
    return _qr_cache[text]


def local_hostname():
    name = subprocess.run(["/usr/sbin/scutil", "--get", "LocalHostName"], capture_output=True,
                          text=True).stdout.strip()
    return (name + ".local") if name else None
