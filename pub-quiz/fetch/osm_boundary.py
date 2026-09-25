#!/usr/bin/env python3
"""The Greater London boundary, so the map keeps to London.

The crawl box is a rectangle, and a rectangle round London takes in Epping,
Epsom and Potters Bar. locate.py drops any quiz whose pub is outside this
outline.

Writes pub-quiz/data/osm/london.json: {"rings": [[[lat, lon], ...], ...]}.
Data (c) OpenStreetMap contributors, ODbL.
"""
import json
from pathlib import Path

import osm2geojson
from shapely.geometry import MultiPolygon, shape

from overpass import fetch, r5

OUT = Path(__file__).resolve().parent.parent / "data" / "osm"

raw = fetch("""[out:json][timeout:180];
rel["boundary"="administrative"]["admin_level"="5"]["name"="Greater London"];
out geom;""")
feats = [f for f in osm2geojson.json2geojson(raw)["features"] if f["geometry"]["type"] in ("Polygon", "MultiPolygon")]
if not feats:
    raise SystemExit("no Greater London polygon came back")
g = shape(feats[0]["geometry"]).simplify(0.0003, preserve_topology=True)
rings = []
for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
    rings.append([[r5(y), r5(x)] for x, y in p.exterior.coords])
    rings += [[[r5(y), r5(x)] for x, y in i.coords] for i in p.interiors]
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "london.json").write_text(json.dumps({"attribution": "(c) OpenStreetMap contributors, ODbL", "rings": rings}))
print(f"Greater London: {len(rings)} rings, {sum(len(r) for r in rings)} points")
