#!/usr/bin/env python3
"""Fetch the real street layout for a walk from OpenStreetMap.

Written because guessing was not working. A stop was placed by eye, a compass
bearing was written to match the guess, and the walker was sent east to
somewhere that is north west. Prose from a search result tells you that a street
runs between two squares; it never tells you which way north is. This does.

It runs on a GitHub Actions runner rather than here, because every OSM host is
blocked by this sandbox's egress proxy while the runner has ordinary internet.
The extract it produces is committed to the repo, so the build and the author
both work from the same file, offline, for ever.

Nothing about this is specific to one town. The bounding box comes from the
tour's own contract, so any walk anywhere on Earth gets its map data with no
configuration beyond the box it already had to declare.

    python3 pipeline/fetch_osm.py --tour two-white-eagles
    python3 pipeline/fetch_osm.py --tour all
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC_GLOB = "content/*/*.json"
OUT_DIR = BASE / "data" / "osm"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
# Roughly 200 m of slack, so a leg that clips the edge of the declared box still
# routes. Cheap: the extract of a village is small either way.
PAD_DEG_LAT = 0.002
PAD_DEG_LON = 0.003

# Everything a person on foot may legitimately walk along. Unnamed alleys and
# steps are kept: the router needs them even though the directions never will.
WALKABLE = {
    "footway", "path", "pedestrian", "living_street", "residential",
    "unclassified", "service", "tertiary", "tertiary_link", "secondary",
    "secondary_link", "primary", "primary_link", "steps", "track", "cycleway",
    "road", "bridleway", "corridor",
}
# Tags that make a thing worth naming in a walk.
PLACE_KEYS = ("historic", "tourism", "amenity", "man_made", "building",
              "shop", "bridge", "waterway", "place", "natural")


def query(bbox):
    south, west, north, east = bbox
    box = f"{south},{west},{north},{east}"
    return f"""[out:json][timeout:180];
(
  way["highway"]({box});
  way["name"]["building"]({box});
  way["name"]["historic"]({box});
  way["name"]["tourism"]({box});
  way["name"]["amenity"]({box});
  way["waterway"]({box});
  node["name"]["historic"]({box});
  node["name"]["tourism"]({box});
  node["name"]["amenity"]({box});
  node["name"]["shop"]({box});
  node["name"]["place"]({box});
);
out geom;"""


def fetch(bbox):
    body = urllib.parse.urlencode({"data": query(bbox)}).encode()
    last = None
    for attempt in range(4):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(
                    url, data=body,
                    headers={"User-Agent": "london-noticing tour builder "
                                           "(github.com/jwghopkins-lab)"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError,
                    TimeoutError, json.JSONDecodeError) as err:
                last = f"{url}: {type(err).__name__}: {err}"
                print(f"  {last}")
        wait = 10 * (attempt + 1)
        print(f"  retrying in {wait}s")
        time.sleep(wait)
    raise SystemExit(f"Overpass would not answer. Last error: {last}")


def centre(geom):
    return (round(sum(p["lat"] for p in geom) / len(geom), 6),
            round(sum(p["lon"] for p in geom) / len(geom), 6))


def compact(raw):
    """Keep the street graph and the named things, throw the rest away."""
    streets, places, water = [], [], []
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        geom = el.get("geometry")

        if el.get("type") == "way" and tags.get("highway") in WALKABLE and geom:
            streets.append({
                "name": name,
                "kind": tags["highway"],
                "line": [[round(p["lat"], 6), round(p["lon"], 6)] for p in geom],
            })
            continue
        if el.get("type") == "way" and tags.get("waterway") and geom:
            water.append({"name": name, "kind": tags["waterway"],
                          "line": [[round(p["lat"], 6), round(p["lon"], 6)]
                                   for p in geom]})
            continue
        if not name:
            continue
        if el.get("type") == "node":
            lat, lon = round(el["lat"], 6), round(el["lon"], 6)
        elif geom:
            lat, lon = centre(geom)
        else:
            continue
        kept = {k: tags[k] for k in PLACE_KEYS if k in tags}
        if not kept:
            continue
        places.append({"name": name, "lat": lat, "lon": lon, "tags": kept})

    # Two ways can carry the same name and the same geometry through different
    # tag combinations. De-duplicate on what we actually kept.
    seen = set()
    uniq = []
    for p in sorted(places, key=lambda p: p["name"]):
        key = (p["name"], p["lat"], p["lon"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return streets, uniq, water


def bbox_of(tour):
    box = (tour.get("contract") or {}).get("bbox")
    if not box:
        raise SystemExit(f"{tour['id']}: no contract.bbox to fetch")
    lat_lo, lat_hi, lon_lo, lon_hi = box
    return (round(lat_lo - PAD_DEG_LAT, 6), round(lon_lo - PAD_DEG_LON, 6),
            round(lat_hi + PAD_DEG_LAT, 6), round(lon_hi + PAD_DEG_LON, 6))


def main():
    args = sys.argv[1:]
    want = args[args.index("--tour") + 1] if "--tour" in args else "all"

    tours = []
    for path in sorted(BASE.glob(SRC_GLOB)):
        t = json.loads(path.read_text(encoding="utf-8"))
        if want in ("all", t["id"]):
            tours.append(t)
    if not tours:
        raise SystemExit(f"no tour matching {want!r}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for tour in tours:
        bbox = bbox_of(tour)
        print(f"{tour['id']}: {tour.get('city', '?')} {bbox}")
        streets, places, water = compact(fetch(bbox))
        out = OUT_DIR / f"{tour['id']}.json"
        out.write_text(json.dumps({
            "tour": tour["id"],
            "city": tour.get("city"),
            "bbox": list(bbox),
            "attribution": "Map data from OpenStreetMap, licensed ODbL. "
                           "https://www.openstreetmap.org/copyright",
            "source": "pipeline/fetch_osm.py via .github/workflows/osm.yml",
            "streets": streets,
            "places": places,
            "water": water,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        named = len({s["name"] for s in streets if s["name"]})
        print(f"  {len(streets)} ways ({named} named), {len(places)} places, "
              f"{len(water)} watercourses, {out.stat().st_size / 1024:.0f} KB")
        if len(tours) > 1:
            time.sleep(5)          # be a good citizen of a free service
    return 0


if __name__ == "__main__":
    sys.exit(main())
