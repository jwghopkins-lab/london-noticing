#!/usr/bin/env python3
"""Route between stops along the real streets, from the OpenStreetMap extract.

The point of this file is to stop the walk being written from memory. Before it
existed, a stop was placed by eye and the directions were written to match the
guess; a walker was sent east to somewhere that is north west, and several stop
coordinates turned out to be up to a hundred metres off, which the tightened
location gates would have failed on.

Now the coordinates come from OSM, the distances come from routing along the
actual street graph, and the authored prose is checked against both.

    python3 pipeline/streets.py --tour two-white-eagles --find "Maison Romane"
    python3 pipeline/streets.py --tour two-white-eagles --near 44.1504 1.7551
    python3 pipeline/streets.py --tour two-white-eagles --route
"""
import heapq
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OSM_DIR = BASE / "data" / "osm"
# A stop further than this from any walkable way is in a field, or wrong.
MAX_SNAP_M = 60.0


def fold(text):
    """Accents and case removed, so 'Pelisserie' matches 'Pélisserie'."""
    s = unicodedata.normalize("NFD", str(text))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


class Town:
    def __init__(self, doc):
        self.doc = doc
        self.streets = doc["streets"]
        self.places = doc["places"]
        self.water = doc.get("water", [])
        self.adj = {}
        self.edge_name = {}
        for way in self.streets:
            line = way["line"]
            for a, b in zip(line, line[1:]):
                ka, kb = tuple(a), tuple(b)
                if ka == kb:
                    continue
                d = geo.haversine_m(a[0], a[1], b[0], b[1])
                self.adj.setdefault(ka, []).append((kb, d))
                self.adj.setdefault(kb, []).append((ka, d))
                self.edge_name[frozenset((ka, kb))] = way["name"]
        self.nodes = list(self.adj)

    # ---- lookup ----------------------------------------------------------
    def find_place(self, name):
        want = fold(name)
        hits = [p for p in self.places if want == fold(p["name"])]
        if not hits:
            hits = [p for p in self.places if want in fold(p["name"])]
        return hits[0] if hits else None

    def street(self, name):
        """Every point of every way carrying this name."""
        want = fold(name)
        pts = [tuple(p) for w in self.streets
               if w["name"] and fold(w["name"]) == want for p in w["line"]]
        return pts

    def has_street(self, name):
        return bool(self.street(name))

    def street_middle(self, name):
        """A point actually on the street, nearest its centre of gravity.

        Not the average of the points: on a bent street the average can sit in
        somebody's garden, and a location gate centred there opens nowhere.
        """
        pts = self.street(name)
        if not pts:
            return None
        clat = sum(p[0] for p in pts) / len(pts)
        clon = sum(p[1] for p in pts) / len(pts)
        return min(pts, key=lambda p: geo.haversine_m(p[0], p[1], clat, clon))

    def nearest_node(self, lat, lon):
        return min(self.nodes, key=lambda n: geo.haversine_m(lat, lon, n[0], n[1]))

    def snap(self, lat, lon):
        n = self.nearest_node(lat, lon)
        return n, geo.haversine_m(lat, lon, n[0], n[1])

    def named_here(self, lat, lon, within=40.0):
        """What OSM calls the ways passing close to a point."""
        names = {}
        for way in self.streets:
            if not way["name"]:
                continue
            d = min(geo.haversine_m(lat, lon, p[0], p[1]) for p in way["line"])
            if d <= within:
                names[way["name"]] = min(d, names.get(way["name"], 1e9))
        return sorted(names.items(), key=lambda kv: kv[1])

    # ---- routing ---------------------------------------------------------
    def route(self, a, b):
        """Shortest walk along the street graph between two coordinates."""
        start, _ = self.snap(*a)
        goal, _ = self.snap(*b)
        if start == goal:
            return {"metres": 0.0, "path": [start], "legs": [], "bearing": None}
        dist = {start: 0.0}
        prev = {}
        seen = set()
        q = [(0.0, start)]
        while q:
            d, node = heapq.heappop(q)
            if node in seen:
                continue
            seen.add(node)
            if node == goal:
                break
            for nxt, step in self.adj.get(node, ()):
                nd = d + step
                if nd < dist.get(nxt, float("inf")):
                    dist[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(q, (nd, nxt))
        if goal not in dist:
            return None
        path = [goal]
        while path[-1] != start:
            path.append(prev[path[-1]])
        path.reverse()
        return {"metres": dist[goal], "path": path,
                "legs": self._legs(path),
                "bearing": geo.bearing_deg(path[0][0], path[0][1],
                                           path[1][0], path[1][1])}

    def _legs(self, path):
        """Collapse the path into named stretches, with a turn at each join."""
        out = []
        for a, b in zip(path, path[1:]):
            name = self.edge_name.get(frozenset((a, b)))
            d = geo.haversine_m(a[0], a[1], b[0], b[1])
            brg = geo.bearing_deg(a[0], a[1], b[0], b[1])
            if out and out[-1]["name"] == name:
                out[-1]["metres"] += d
                out[-1]["end_bearing"] = brg
            else:
                out.append({"name": name, "metres": d,
                            "bearing": brg, "end_bearing": brg})
        for before, after in zip(out, out[1:]):
            after["turn"] = turn_word(before["end_bearing"], after["bearing"])
        return out


def turn_word(before, after):
    d = (after - before + 540.0) % 360.0 - 180.0
    if abs(d) < 25:
        return "straight on"
    if abs(d) > 150:
        return "back the way you came"
    side = "right" if d > 0 else "left"
    return f"{'sharp ' if abs(d) > 100 else '' }{side}"


def compass_word(deg):
    return ["north", "north east", "east", "south east", "south", "south west",
            "west", "north west"][int((deg + 22.5) % 360 // 45)]


def load(tour_id):
    path = OSM_DIR / f"{tour_id}.json"
    if not path.exists():
        return None
    return Town(json.loads(path.read_text(encoding="utf-8")))


def _tour_stops(tour_id):
    for path in sorted(BASE.glob("content/*/*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["id"] == tour_id:
            return doc
    raise SystemExit(f"no tour {tour_id}")


def main():
    args = sys.argv[1:]
    tour_id = args[args.index("--tour") + 1] if "--tour" in args else None
    town = load(tour_id)
    if town is None:
        raise SystemExit(f"no map data for {tour_id}; run the Fetch map data workflow")

    if "--find" in args:
        name = args[args.index("--find") + 1]
        p = town.find_place(name)
        if p:
            print(f"place  {p['name']}  {p['lat']},{p['lon']}  {p['tags']}")
        mid = town.street_middle(name)
        if mid:
            print(f"street {name}  middle {mid[0]},{mid[1]}  "
                  f"({len(town.street(name))} points)")
        if not p and not mid:
            print(f"nothing called {name!r} in the extract")
        return 0

    if "--near" in args:
        i = args.index("--near")
        lat, lon = float(args[i + 1]), float(args[i + 2])
        node, d = town.snap(lat, lon)
        print(f"nearest walkable point {node[0]},{node[1]} at {d:.0f} m")
        for name, dd in town.named_here(lat, lon, 60):
            print(f"  {dd:5.0f} m  {name}")
        for p in sorted(town.places,
                        key=lambda p: geo.haversine_m(lat, lon, p["lat"], p["lon"]))[:8]:
            print(f"  {geo.haversine_m(lat, lon, p['lat'], p['lon']):5.0f} m  "
                  f"{p['name']}  {p['tags']}")
        return 0

    doc = _tour_stops(tour_id)
    stops = doc["stops"]
    print(f"{doc['name']}: routed along the real streets\n")
    total = 0.0
    for a, b in zip(stops, stops[1:]):
        r = town.route((a["lat"], a["lon"]), (b["lat"], b["lon"]))
        if r is None:
            print(f"{a['id']} -> {b['id']}: NO ROUTE")
            continue
        total += r["metres"]
        print(f"{a['id']} -> {b['id']}: {r['metres']:.0f} m, "
              f"heading {compass_word(r['bearing'])}")
        for leg in r["legs"]:
            if leg["metres"] < 8:
                continue
            print(f"    {leg.get('turn', 'set off'):<20} "
                  f"{leg['name'] or '(unnamed way)':<32} {leg['metres']:5.0f} m")
    print(f"\ntotal {total:.0f} m on the actual streets")
    for s in stops:
        node, d = town.snap(s["lat"], s["lon"])
        flag = "" if d <= MAX_SNAP_M else "   <-- nowhere near a street"
        print(f"  {s['id']:<16} {d:5.0f} m from the nearest walkable way{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
