#!/usr/bin/env python3
"""Fetch the OpenStreetMap layers the quiz map is drawn from.

Runs on a GitHub runner: the authoring sandbox cannot reach any map host, and
the artifact viewer will not load map tiles, so the basemap ships inside the
page as vectors.

Writes two files:

    pub-quiz/data/osm/pubs.json     every pub and bar in the London box, with
                                    the tags that help match one to a quiz
    pub-quiz/data/osm/basemap.json  the Thames, big parks, main roads, stations
                                    and neighbourhood names, simplified

Data from OpenStreetMap, licensed ODbL.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import LineString, Polygon, MultiPolygon, shape
from shapely.ops import unary_union
import osm2geojson

OUT = Path(__file__).resolve().parent.parent / "data" / "osm"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
# Greater London and a little over.
BOX = "51.28,-0.52,51.70,0.34"
UA = "london-noticing pub quiz map (github.com/jwghopkins-lab)"

# Metres-ish tolerances in degrees at London's latitude (1e-5 deg lat ~ 1.1 m).
TOL = {"water": 0.00008, "park": 0.0001, "road": 0.00006, "waterway": 0.00008}
MIN_AREA_M2 = {"water": 15000, "park": 60000}
M2_PER_DEG2 = 111320 * 69400  # lat metres * lon metres at 51.5N


def fetch(q):
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(4):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=400) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError,
                    TimeoutError, json.JSONDecodeError) as err:
                last = f"{url}: {type(err).__name__}: {err}"
                print(f"  {last}", flush=True)
        time.sleep(15 * (attempt + 1))
    raise SystemExit(f"Overpass would not answer. Last error: {last}")


def r5(x):
    return round(x, 5)


def ring(coords):
    return [[r5(y), r5(x)] for x, y in coords]  # stored as [lat, lon] for Leaflet


def polys(geojson, kind):
    out = []
    geoms = []
    for f in geojson["features"]:
        try:
            g = shape(f["geometry"])
        except Exception:
            continue
        if g.geom_type in ("Polygon", "MultiPolygon") and g.is_valid:
            geoms.append(g)
    if not geoms:
        return out
    merged = unary_union(geoms).simplify(TOL[kind], preserve_topology=True)
    parts = merged.geoms if isinstance(merged, MultiPolygon) else [merged]
    for p in parts:
        if not isinstance(p, Polygon) or p.area * M2_PER_DEG2 < MIN_AREA_M2[kind]:
            continue
        out.append([ring(p.exterior.coords)] + [ring(i.coords) for i in p.interiors])
    return out


def lines(geojson, kind, key=None):
    out = {}
    for f in geojson["features"]:
        g = shape(f["geometry"])
        tags = f["properties"].get("tags", {})
        cls = tags.get(key, "x") if key else "x"
        segs = g.geoms if g.geom_type == "MultiLineString" else [g]
        for s in segs:
            if not isinstance(s, LineString):
                continue
            s = s.simplify(TOL[kind])
            out.setdefault(cls, []).append(ring(s.coords))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("pubs and bars", flush=True)
    raw = fetch(f"""[out:json][timeout:300];
nwr["amenity"~"^(pub|bar|biergarten)$"]({BOX});
out center tags;""")
    keep = ("name", "alt_name", "old_name", "brand", "operator", "website",
            "contact:website", "url", "addr:housenumber", "addr:street",
            "addr:postcode", "addr:city", "amenity", "disused:amenity")
    pubs = []
    for el in raw["elements"]:
        t = el.get("tags", {})
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or not t.get("name"):
            continue
        pubs.append({"osm": f"{el['type']}/{el['id']}", "lat": r5(lat), "lon": r5(lon),
                     **{k: v for k, v in t.items() if k in keep}})
    (OUT / "pubs.json").write_text(json.dumps(pubs, ensure_ascii=False, indent=0))
    print(f"  {len(pubs)} named pubs and bars", flush=True)

    base = {"attribution": "© OpenStreetMap contributors, ODbL"}

    print("water", flush=True)
    g = osm2geojson.json2geojson(fetch(f"""[out:json][timeout:300];
(nwr["natural"="water"]({BOX}); nwr["waterway"="riverbank"]({BOX}); nwr["landuse"="reservoir"]({BOX}););
out geom;"""))
    base["water"] = polys(g, "water")

    print("canals and rivers", flush=True)
    g = osm2geojson.json2geojson(fetch(f"""[out:json][timeout:300];
way["waterway"~"^(canal|river)$"]({BOX});
out geom;"""))
    base["waterways"] = lines(g, "waterway", "waterway")

    print("parks", flush=True)
    g = osm2geojson.json2geojson(fetch(f"""[out:json][timeout:300];
(nwr["leisure"~"^(park|common|nature_reserve)$"]({BOX}); nwr["landuse"~"^(recreation_ground|forest|meadow)$"]({BOX}); nwr["natural"="wood"]({BOX}); nwr["landuse"="cemetery"]({BOX}););
out geom;"""))
    base["parks"] = polys(g, "park")

    print("roads", flush=True)
    g = osm2geojson.json2geojson(fetch(f"""[out:json][timeout:400];
way["highway"~"^(motorway|trunk|primary|secondary)$"]({BOX});
out geom;"""))
    base["roads"] = lines(g, "road", "highway")

    print("stations and places", flush=True)
    raw = fetch(f"""[out:json][timeout:300];
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
            kind = ("tube" if t.get("station") == "subway" or "London Underground" in t.get("network", "")
                    else "dlr" if "Docklands" in t.get("network", "") else "rail")
            stations.append({"n": t["name"], "lat": r5(lat), "lon": r5(lon), "k": kind})
        else:
            places.append({"n": t["name"], "lat": r5(lat), "lon": r5(lon), "p": t["place"]})
    base["stations"] = stations
    base["places"] = places

    (OUT / "basemap.json").write_text(json.dumps(base, separators=(",", ":")))
    size = (OUT / "basemap.json").stat().st_size
    print(f"basemap {size/1e6:.1f} MB: {len(base['water'])} water, {len(base['parks'])} parks, "
          f"{sum(len(v) for v in base['roads'].values())} road lines, {len(stations)} stations, "
          f"{len(places)} places", flush=True)


if __name__ == "__main__":
    main()
