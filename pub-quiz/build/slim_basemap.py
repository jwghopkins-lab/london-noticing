#!/usr/bin/env python3
"""Cut the basemap down to what a phone should have to download.

    python3 pub-quiz/build/slim_basemap.py

Reads  pub-quiz/data/osm/basemap.json       (as fetched, about 4.6 MB)
Writes pub-quiz/data/osm/basemap-slim.json  (what the page carries)

The map is for seeing where the quizzes are and which way to walk, not for
navigating by. So: roads are joined end to end and simplified to about ten
metres, parks under ten hectares go, and every coordinate keeps five decimals
(about a metre).
"""
import json
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import linemerge

OSM = Path(__file__).resolve().parent.parent / "data" / "osm"
M2_PER_DEG2 = 111320 * 69400


def r5(x):
    return round(x, 5)


def merged_lines(lines, tol, min_len_m=0):
    geoms = [LineString([(lon, lat) for lat, lon in l]) for l in lines if len(l) >= 2]
    m = linemerge(MultiLineString(geoms))
    parts = m.geoms if hasattr(m, "geoms") else [m]
    out = []
    for p in parts:
        s = p.simplify(tol)
        if s.length * 90000 < min_len_m:
            continue
        out.append([[r5(y), r5(x)] for x, y in s.coords])
    return out


def slim_polys(polys, tol, min_m2):
    out = []
    for rings in polys:
        p = Polygon([(lon, lat) for lat, lon in rings[0]], [[(lon, lat) for lat, lon in r] for r in rings[1:]])
        if p.area * M2_PER_DEG2 < min_m2:
            continue
        s = p.simplify(tol, preserve_topology=True)
        if s.is_empty or s.geom_type != "Polygon":
            continue
        holes = [h for h in s.interiors if Polygon(h).area * M2_PER_DEG2 >= min_m2 / 4]
        out.append([[[r5(y), r5(x)] for x, y in s.exterior.coords]] + [[[r5(y), r5(x)] for x, y in h.coords] for h in holes])
    return out


b = json.loads((OSM / "basemap.json").read_text())
slim = {
    "attribution": b["attribution"],
    "water": slim_polys(b.get("water", []), 0.00008, 20000),
    "parks": slim_polys(b.get("parks", []), 0.0002, 150000),
    "waterways": {k: merged_lines(v, 0.0001, 300) for k, v in b.get("waterways", {}).items()},
    "roads": {k: merged_lines(v, 0.0001 if k == "secondary" else 0.00008, 60) for k, v in b.get("roads", {}).items()},
    "stations": b.get("stations", []),
    "places": b.get("places", []),
}
(OSM / "basemap-slim.json").write_text(json.dumps(slim, separators=(",", ":")))
for k, v in slim.items():
    if k != "attribution":
        print(f"{k}: {len(json.dumps(v, separators=(',', ':'))) / 1000:.0f} KB")
print(f"total {(OSM / 'basemap-slim.json').stat().st_size / 1e6:.2f} MB")
