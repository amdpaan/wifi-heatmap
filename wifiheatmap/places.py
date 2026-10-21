"""Your named places ("Library L2, window side"). Samples refer to a place by its id, which never
changes, so renaming a place keeps its history. A place's pin on the map comes in milestone 3."""

import difflib
import json
import re
from datetime import datetime

from . import paths


class PlaceError(Exception):
    pass


def load():
    try:
        return json.loads(paths.PLACES.read_text()).get("places", [])
    except FileNotFoundError:
        return []


def save(places):
    paths.SUPPORT.mkdir(parents=True, exist_ok=True)
    tmp = paths.PLACES.with_suffix(".tmp")
    tmp.write_text(json.dumps({"places": places}, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(paths.PLACES)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "place"


def find(places, name):
    key = name.strip().lower()
    for p in places:
        if p["id"] == key or p["name"].lower() == key:
            return p
    return None


def similar(places, name):
    names = {p["name"].lower(): p["name"] for p in places}
    return [names[n] for n in difflib.get_close_matches(name.strip().lower(), names, n=3, cutoff=0.75)]


def add(name):
    name = " ".join(name.split())
    if not name:
        raise PlaceError("A place needs a name.")
    places = load()
    if find(places, name):
        raise PlaceError(f"There's already a place called {name!r}.")
    ids = {p["id"] for p in places}
    pid, n = slug(name), 2
    while pid in ids:
        pid, n = f"{slug(name)}-{n}", n + 1
    p = {"id": pid, "name": name, "created": datetime.now().astimezone().isoformat(timespec="seconds"), "pin": None}
    save(places + [p])
    return p


def rename(old, new):
    new = " ".join(new.split())
    if not new:
        raise PlaceError("A place needs a name.")
    places = load()
    p = find(places, old)
    if not p:
        raise PlaceError(f"No place called {old!r}.")
    other = find(places, new)
    if other and other is not p:
        raise PlaceError(f"There's already a place called {new!r}.")
    p["name"] = new
    save(places)
    return p


def set_pin(pid, pin):
    """pin is {"x": 0-1, "y": 0-1} as a share of the map's width and height, or None to remove it."""
    places = load()
    p = next((p for p in places if p["id"] == pid), None)
    if not p:
        raise PlaceError(f"No place with id {pid!r}.")
    if pin is not None:
        x, y = float(pin["x"]), float(pin["y"])
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise PlaceError("A pin must be inside the map.")
        pin = {"x": round(x, 4), "y": round(y, 4)}
    p["pin"] = pin
    save(places)
    return p
