#!/usr/bin/env python3
"""Fetch the height of the ground under every street in the extract.

Cordes-sur-Ciel is a town on top of a hill, reached by ramps, and the request
that produced this file was "make sure you aren't sending us up and down more
than necessary". That cannot be checked from a street graph. A map drawn flat
says a hundred metres is a hundred metres whether it climbs forty of them or
none, and the walk that reads best on paper is often the one that goes down to
a gate and back up again for no reason.

So height comes in like the streets do: fetched on a runner, committed, and read
offline for ever afterwards. It belongs to the map rather than to a route, which
means the stops can be reordered a dozen times without fetching anything again.

Source is OpenTopoData's public instance. EU DEM at 25 m for Europe, falling
back to SRTM at 30 m anywhere else, so this works for any town on Earth — the
fallback is automatic and reported.

    python3 pipeline/fetch_elevation.py --tour borough-rotherhithe
    python3 pipeline/fetch_elevation.py --tour all
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OSM_DIR = BASE / "data" / "osm"
OUT_DIR = BASE / "data" / "elevation"

API = "https://api.opentopodata.org/v1/{dataset}"
PRIMARY = "eudem25m"        # Europe, 25 m
FALLBACK = "srtm30m"        # everywhere else, 30 m
BATCH = 100                 # the public instance's limit per call
PAUSE_S = 1.1               # ...and one call a second
TIMEOUT_S = 60

# Terrain does not change meaningfully between two points ten metres apart, and
# OSM geometry is far denser than that round a corner. Thinning keeps the fetch
# to a few dozen calls for a village instead of a few hundred.
SPACING_M = 10.0


def samples(doc):
    """Points along every walkable way, thinned to one per SPACING_M."""
    out, seen = [], set()
    for way in doc["streets"]:
        last = None
        for pt in way["line"]:
            p = (round(pt[0], 6), round(pt[1], 6))
            if last is not None and geo.haversine_m(*last, *p) < SPACING_M:
                continue
            last = p
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def ask(points, dataset):
    locs = "|".join(f"{lat},{lon}" for lat, lon in points)
    url = API.format(dataset=dataset) + "?" + urllib.parse.urlencode(
        {"locations": locs, "interpolation": "bilinear"})
    req = urllib.request.Request(url, headers={
        "User-Agent": "london-noticing walk builder (github.com/jwghopkins-lab)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if doc.get("status") != "OK":
        raise ValueError(doc.get("error", "no status OK"))
    return [x.get("elevation") for x in doc["results"]]


def ask_with_retries(points, dataset):
    last = None
    for attempt in range(3):
        try:
            return ask(points, dataset)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ValueError, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(2 ** attempt + PAUSE_S)
    print(f"    gave up on a batch: {last}")
    return [None] * len(points)


def fetch(points):
    """Heights for every point, with an automatic fall back outside Europe."""
    dataset = PRIMARY
    probe = ask_with_retries(points[:BATCH], dataset)
    got = [e for e in probe if e is not None]
    if len(got) < len(probe) / 2:
        print(f"  {dataset} covers little of this town; using {FALLBACK}")
        dataset = FALLBACK
        probe = ask_with_retries(points[:BATCH], dataset)

    out = list(probe)
    for i in range(BATCH, len(points), BATCH):
        time.sleep(PAUSE_S)
        chunk = points[i:i + BATCH]
        out += ask_with_retries(chunk, dataset)
        print(f"    {min(i + BATCH, len(points))}/{len(points)}", flush=True)
    return dataset, out


def main():
    args = sys.argv[1:]
    want = args[args.index("--tour") + 1] if "--tour" in args else "all"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    found = 0
    for path in sorted(OSM_DIR.glob("*.json")):
        if want not in ("all", path.stem):
            continue
        found += 1
        doc = json.loads(path.read_text(encoding="utf-8"))
        pts = samples(doc)
        print(f"{path.stem}: {len(pts)} points, "
              f"{(len(pts) + BATCH - 1) // BATCH} calls")
        dataset, heights = fetch(pts)

        rows = [[lat, lon, round(float(e), 1)]
                for (lat, lon), e in zip(pts, heights) if e is not None]
        out = OUT_DIR / f"{path.stem}.json"
        out.write_text(json.dumps({
            "tour": path.stem,
            "dataset": dataset,
            "attribution": "Elevation from OpenTopoData. EU DEM (c) European "
                           "Union, Copernicus; SRTM courtesy NASA/USGS.",
            "source": "pipeline/fetch_elevation.py via .github/workflows/osm.yml",
            "points": rows,
        }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        lo = min(r[2] for r in rows) if rows else 0
        hi = max(r[2] for r in rows) if rows else 0
        print(f"  {len(rows)}/{len(pts)} heights from {dataset}, "
              f"{lo:.0f} m to {hi:.0f} m")

    if not found:
        print(f"no map extract matching {want!r}; fetch the streets first")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
