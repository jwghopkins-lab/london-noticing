#!/usr/bin/env python3
"""Every pub and bar in the London box, from OpenStreetMap.

Two uses. Their websites are the crawl list: the quiz search starts from the
pubs' own sites rather than from listings. And their positions are where the
map puts a confirmed quiz, since a pub's OSM point is usually on the building.

Writes pub-quiz/data/osm/pubs.json. Data (c) OpenStreetMap contributors, ODbL.
"""
import json
from pathlib import Path

from overpass import BOX, fetch, r5

OUT = Path(__file__).resolve().parent.parent / "data" / "osm"
KEEP = ("name", "alt_name", "old_name", "brand", "operator", "website", "contact:website", "url",
        "addr:housenumber", "addr:street", "addr:postcode", "addr:city", "amenity")

raw = fetch(f"""[out:json][timeout:240];
nwr["amenity"~"^(pub|bar|biergarten)$"]({BOX});
out center tags;""")
pubs = []
for el in raw["elements"]:
    t = el.get("tags", {})
    lat = el.get("lat", el.get("center", {}).get("lat"))
    lon = el.get("lon", el.get("center", {}).get("lon"))
    if lat is None or not t.get("name"):
        continue
    pubs.append({"osm": f"{el['type']}/{el['id']}", "lat": r5(lat), "lon": r5(lon),
                 **{k: v for k, v in t.items() if k in KEEP}})
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "pubs.json").write_text(json.dumps(pubs, ensure_ascii=False, indent=0))
print(f"{len(pubs)} named pubs and bars, {sum(1 for p in pubs if p.get('website') or p.get('contact:website') or p.get('url'))} with a website")
