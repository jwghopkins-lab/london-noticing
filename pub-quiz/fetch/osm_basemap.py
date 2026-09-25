#!/usr/bin/env python3
"""The basemap the quiz map is drawn on, from OpenStreetMap.

The artifact viewer will not load map tiles, so the page carries its own map as
vectors: the Thames and docks, big parks, main roads, stations and
neighbourhood names, simplified to a few metres. Each layer is fetched on its
own, and one that Overpass will not serve is left out rather than sinking the
rest.

Writes pub-quiz/data/osm/basemap.json. Data (c) OpenStreetMap contributors, ODbL.
"""
import json
from pathlib import Path

import osm2geojson
from shapely.geometry import LineString, MultiPolygon, Polygon, shape
from shapely.ops import unary_union

from overpass import BOX, fetch, r5

OUT = Path(__file__).resolve().parent.parent / "data" / "osm"
# Degrees at London's latitude: 1e-5 deg of latitude is about 1.1 m.
TOL = {"water": 0.00008, "park": 0.0001, "road": 0.00006, "waterway": 0.00008}
MIN_AREA_M2 = {"water": 15000, "park": 60000}
M2_PER_DEG2 = 111320 * 69400


def ring(coords):
    return [[r5(y), r5(x)] for x, y in coords]  # [lat, lon], as Leaflet wants


def polys(gj, kind):
    geoms = []
    for f in gj["features"]:
        try:
            g = shape(f["geometry"])
        except Exception:
            continue
        if g.geom_type in ("Polygon", "MultiPolygon"):
            geoms.append(g if g.is_valid else g.buffer(0))
    if not geoms:
        return []
    merged = unary_union(geoms).simplify(TOL[kind], preserve_topology=True)
    parts = merged.geoms if isinstance(merged, MultiPolygon) else [merged]
    return [[ring(p.exterior.coords)] + [ring(i.coords) for i in p.interiors]
            for p in parts if isinstance(p, Polygon) and p.area * M2_PER_DEG2 >= MIN_AREA_M2[kind]]


def lines(gj, kind, key):
    out = {}
    for f in gj["features"]:
        try:
            g = shape(f["geometry"])
        except Exception:
            continue
        cls = f["properties"].get("tags", {}).get(key, "x")
        for s in (g.geoms if g.geom_type == "MultiLineString" else [g]):
            if isinstance(s, LineString):
                out.setdefault(cls, []).append(ring(s.simplify(TOL[kind]).coords))
    return out


def geo(q):
    return osm2geojson.json2geojson(fetch(q, timeout=400))


base = {"attribution": "(c) OpenStreetMap contributors, ODbL"}
LAYERS = {
    "water": lambda: polys(geo(f"""[out:json][timeout:300];
(nwr["natural"="water"]({BOX}); nwr["waterway"="riverbank"]({BOX}); nwr["landuse"="reservoir"]({BOX}););
out geom;"""), "water"),
    "waterways": lambda: lines(geo(f"""[out:json][timeout:300];
way["waterway"~"^(canal|river)$"]({BOX});
out geom;"""), "waterway", "waterway"),
    "parks": lambda: polys(geo(f"""[out:json][timeout:300];
(nwr["leisure"~"^(park|common|nature_reserve|golf_course)$"]({BOX}); nwr["landuse"~"^(recreation_ground|forest|meadow|cemetery)$"]({BOX}); nwr["natural"="wood"]({BOX}););
out geom;"""), "park"),
    "roads": lambda: {**lines(geo(f"""[out:json][timeout:300];
way["highway"~"^(motorway|trunk|primary)$"]({BOX});
out geom;"""), "road", "highway"), **lines(geo(f"""[out:json][timeout:300];
way["highway"="secondary"]({BOX});
out geom;"""), "road", "highway")},
}
for name, fn in LAYERS.items():
    print(name, flush=True)
    try:
        base[name] = fn()
    except Exception as err:
        print(f"  {name} left out: {err}", flush=True)

print("stations and places", flush=True)
try:
    raw = fetch(f"""[out:json][timeout:240];
(nwr["railway"="station"]["name"]({BOX}); node["place"~"^(suburb|neighbourhood|quarter|town)$"]["name"]({BOX}););
out center tags;""")
    stations, places = [], []
    for el in raw["elements"]:
        t = el.get("tags", {})
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None:
            continue
        if t.get("railway") == "station":
            net = t.get("network", "")
            kind = ("tube" if t.get("station") == "subway" or "Underground" in net
                    else "dlr" if "Docklands" in net else "rail")
            stations.append({"n": t["name"], "lat": r5(lat), "lon": r5(lon), "k": kind})
        else:
            places.append({"n": t["name"], "lat": r5(lat), "lon": r5(lon), "p": t["place"]})
    base["stations"], base["places"] = stations, places
except Exception as err:
    print(f"  stations and places left out: {err}", flush=True)

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "basemap.json").write_text(json.dumps(base, separators=(",", ":")))
print(f"basemap {(OUT / 'basemap.json').stat().st_size / 1e6:.1f} MB: " +
      ", ".join(f"{k} {len(v) if isinstance(v, list) else sum(len(x) for x in v.values())}"
                for k, v in base.items() if k != "attribution"))
