"""Draws the app icon: the antenna-bot in its "great" mood, from the pixel map in wifiheatmap/web/app.js
(so the art has one source in this repo), on a rounded square. Standard library only.

Usage: python3 tools/icon.py <out.png> [size]
"""

import re
import struct
import sys
import zlib
from pathlib import Path

APP_JS = Path(__file__).resolve().parent.parent / "wifiheatmap/web/app.js"
COLORS = {   # the light theme's bot colours (style.css), with the "great" status green
    "o": "1c2124", "a": "1c2124", "w": "39474e", "b": "a9bcc4", "d": "7f959f", "s": "22313a",
    "e": "7ff0c8", "m": "7ff0c8", "y": "fab219", "t": "0ca30c",
    "1": "0ca30c", "2": "0ca30c", "3": "0ca30c", "4": "0ca30c",
}
TOP, BOTTOM = (0xf2, 0xf6, 0xf3), (0xd3, 0xdf, 0xd8)   # background gradient


def bot_rows(layers=("happy", "sparks")):
    js = APP_JS.read_text()
    base = re.findall(r'"([^"]{16})"', js[js.index("const BOT = ["):js.index("];", js.index("const BOT = ["))])
    rows = list(base)
    for name in layers:
        m = re.search(r'"%s": \{([^}]*)\}' % name, js)
        for y, row in re.findall(r'(\d+): "([^"]{16})"', m.group(1)):
            y = int(y)
            rows[y] = "".join(b if c == "." else c for b, c in zip(rows[y], row))
    return rows


def rgb(hexstr):
    return tuple(int(hexstr[i:i + 2], 16) for i in (0, 2, 4))


def draw(size=1024):
    rows = bot_rows()
    inset, radius = size * 100 // 1024, size * 185 // 1024   # macOS app icon grid: 824/1024 with round corners
    cell = size * 30 // 1024
    ox = (size - 16 * cell) // 2
    oy = (size - 22 * cell) // 2 + size * 10 // 1024
    px = bytearray(size * size * 4)
    for y in range(size):
        t = (y - inset) / max(1, size - 2 * inset)
        bg = tuple(round(a + (b - a) * min(1, max(0, t))) for a, b in zip(TOP, BOTTOM))
        for x in range(size):
            # rounded square: distance from the nearest corner centre
            cx = min(max(x, inset + radius), size - inset - radius - 1)
            cy = min(max(y, inset + radius), size - inset - radius - 1)
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            inside = inset <= x < size - inset and inset <= y < size - inset
            alpha = 0 if not inside else max(0.0, min(1.0, radius - d + 0.5))
            if not alpha:
                continue
            gx, gy = (x - ox) // cell, (y - oy) // cell
            c = rows[gy][gx] if 0 <= gx < 16 and 0 <= gy < 22 and x >= ox and y >= oy else "."
            r, g, b = rgb(COLORS[c]) if c in COLORS else bg
            i = (y * size + x) * 4
            px[i:i + 4] = bytes((r, g, b, round(alpha * 255)))
    return png(size, size, px)


def png(w, h, rgba):
    raw = b"".join(b"\0" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    Path(sys.argv[1]).write_bytes(draw(int(sys.argv[2]) if len(sys.argv) > 2 else 1024))
