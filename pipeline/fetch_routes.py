#!/usr/bin/env python3
"""Ask other routing engines to walk the same legs, and keep their answers.

The reason this exists is a complaint about stop 4 of the Noble Val walk, which
came with the observation that Google does not have those lanes quite right
either. That is the useful part. If three independent engines disagree about how
to get from A to B, the honest conclusion is not that two of them are wrong: it
is that the ground there cannot be described as a sequence of turns, and a walk
that tries will send somebody the wrong way. So the disagreement itself is the
signal, and what it buys is permission to stop pretending.

Why not Google, which is what was actually asked for. Two reasons, and neither
is laziness. The Directions API needs a billed key, which this project does not
have and should not need. And its terms do not allow the results to be stored or
shown next to a map that is not Google's, so committing their geometry into a
public repo is not something to do casually. What is used instead:

    routed-foot   FOSSGIS's OSRM, walking profile
    valhalla      FOSSGIS's Valhalla, pedestrian costing

Two separate engines, no key, and ODbL data that can be committed like the
Overpass extract already is.

The honest caveat, which belongs in the open: all three of us — these two and
our own Dijkstra in streets.py — read the same OpenStreetMap data. So this is
not the fully independent second opinion a commercial router would be. It still
catches a great deal, because the engines build their graphs differently, snap
to the network differently, and treat steps, alleys and access tags
differently; a leg they all agree on is a leg the map states plainly. And the
strongest signal in confidence.py needs no second engine at all: whether there
is another way round of much the same length.

Runs on a GitHub Actions runner, like fetch_osm.py, because this sandbox cannot
reach any map host. The answers are committed to data/routes/<tour>.json so the
build and the author work from the same file, offline.

    python3 pipeline/fetch_routes.py --tour two-white-eagles
    python3 pipeline/fetch_routes.py --tour all
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC_GLOB = "content/*/*.json"
OUT_DIR = BASE / "data" / "routes"

OSRM = ("https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
        "{a_lon},{a_lat};{b_lon},{b_lat}"
        "?overview=full&geometries=geojson&alternatives=3&steps=false")
VALHALLA = "https://valhalla1.openstreetmap.de/route"

# Both are volunteer-run and free. Walk in, do not stampede.
PAUSE_S = 1.5
TIMEOUT_S = 45


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "london-noticing walk checker (github.com/jwghopkins-lab)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "london-noticing walk checker "
                               "(github.com/jwghopkins-lab)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def retry(fn, *args):
    """Three goes, backing off. A flaky answer must not become a verdict.

    A leg with no answer is recorded as no answer, never as agreement. The
    scorer treats a missing engine as a reason to be less sure, not more.
    """
    last = None
    for attempt in range(3):
        try:
            return fn(*args), None
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, ValueError, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(2 ** attempt)
    return None, last


def osrm_leg(a, b):
    url = OSRM.format(a_lat=a[0], a_lon=a[1], b_lat=b[0], b_lon=b[1])
    doc, err = retry(get, url)
    if doc is None:
        return {"engine": "osrm-foot", "error": err}
    routes = doc.get("routes") or []
    if not routes:
        return {"engine": "osrm-foot", "error": "no route"}
    out = {
        "engine": "osrm-foot",
        "metres": round(routes[0]["distance"], 1),
        # GeoJSON is lon,lat. Everything else in this repo is lat,lon, so it is
        # turned round here rather than at each place that reads it.
        "line": [[round(p[1], 6), round(p[0], 6)]
                 for p in routes[0]["geometry"]["coordinates"]],
        "alternatives": [round(r["distance"], 1) for r in routes[1:]],
    }
    return out


def valhalla_leg(a, b):
    payload = {
        "locations": [{"lat": a[0], "lon": a[1]}, {"lat": b[0], "lon": b[1]}],
        "costing": "pedestrian",
        "directions_options": {"units": "kilometers"},
    }
    doc, err = retry(post, VALHALLA, payload)
    if doc is None:
        return {"engine": "valhalla-pedestrian", "error": err}
    trip = doc.get("trip") or {}
    legs = trip.get("legs") or []
    if not legs:
        return {"engine": "valhalla-pedestrian", "error": "no route"}
    return {
        "engine": "valhalla-pedestrian",
        "metres": round(float(trip["summary"]["length"]) * 1000.0, 1),
        "line": decode_shape(legs[0]["shape"]),
    }


def decode_shape(encoded, precision=6):
    """Valhalla's polyline, which is Google's format at 1e-6 rather than 1e-5."""
    factor = float(10 ** precision)
    out, lat, lon, i = [], 0, 0, 0
    while i < len(encoded):
        for target in ("lat", "lon"):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[i]) - 63
                i += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if target == "lat":
                lat += delta
            else:
                lon += delta
        out.append([round(lat / factor, 6), round(lon / factor, 6)])
    return out


def tours(which):
    for path in sorted(BASE.glob(SRC_GLOB)):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if which in ("all", doc["id"]):
            yield doc


def main():
    args = sys.argv[1:]
    which = args[args.index("--tour") + 1] if "--tour" in args else "all"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    found = 0
    for doc in tours(which):
        found += 1
        stops = doc["stops"]
        legs = []
        for before, after in zip(stops, stops[1:]):
            a = (before["lat"], before["lon"])
            b = (after["lat"], after["lon"])
            print(f"  {doc['id']}: {before['id']} -> {after['id']}", flush=True)
            answers = [osrm_leg(a, b)]
            time.sleep(PAUSE_S)
            answers.append(valhalla_leg(a, b))
            time.sleep(PAUSE_S)
            for ans in answers:
                if "error" in ans:
                    print(f"    {ans['engine']}: {ans['error']}")
                else:
                    print(f"    {ans['engine']}: {ans['metres']:.0f} m")
            legs.append({"from": before["id"], "to": after["id"],
                         "from_at": [a[0], a[1]], "to_at": [b[0], b[1]],
                         "answers": answers})

        out = OUT_DIR / f"{doc['id']}.json"
        out.write_text(json.dumps({
            "tour": doc["id"],
            "note": "Second opinions from independent routing engines. "
                    "Data from OpenStreetMap, licensed ODbL.",
            "legs": legs,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  wrote {out.relative_to(BASE)}: {len(legs)} legs")

    if not found:
        # A town whose extract has arrived but whose stops are not written yet
        # has no legs to ask about. That is where every new town starts, so it
        # is a message rather than a failure.
        print(f"no walk written for {which!r} yet, so there are no legs to "
              f"route; come back after the stops exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
