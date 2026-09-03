#!/usr/bin/env python3
"""How much a walk climbs, and how much of that climbing it wasted.

A street graph is drawn flat. It will happily tell you that a hundred metres is
a hundred metres whether it gains forty of them or none, so the route that reads
best on paper is often the one that drops to a gate and comes back up for
nothing. In a town on a hill that is the difference between a nice walk and a
bad afternoon.

The number that matters is not total ascent. A walk that starts at the bottom
and ends at the top has to climb, and there is no complaint in that. What is
worth complaining about is climbing the same metres twice:

    reclimb = ascent - max(0, end - start)

Every metre of that was gained, given away, and gained again. Zero means the
walk only ever climbed towards where it was going.

Heights come from data/elevation/<tour>.json, fetched by fetch_elevation.py.
No file means no profile, reported as a note rather than a failure, exactly as
with the routing second opinions.

    python3 pipeline/terrain.py --tour borough-rotherhithe
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402
import streets                                     # noqa: E402

BASE = Path(__file__).resolve().parent.parent
ELEV_DIR = BASE / "data" / "elevation"

# The ground is sampled every ten metres and the DEM is accurate to a few, so a
# change under this is noise. Summing noise over a kilometre invents a hill.
NOISE_M = 2.0
STEP_M = 15.0               # how often to take a height along a leg
# Past this a stop's height is a guess about somewhere else.
MAX_LOOKUP_M = 40.0
# A cell about 55 m on a side, so a lookup only ever scans its own
# neighbourhood rather than every sample in the town.
CELL = 0.0005


class Terrain:
    def __init__(self, doc):
        self.dataset = doc.get("dataset")
        self.cells = {}
        for lat, lon, ele in doc["points"]:
            self.cells.setdefault(
                (int(lat / CELL), int(lon / CELL)), []).append((lat, lon, ele))

    def height(self, lat, lon):
        """Ground height here, or None if nothing was sampled close enough."""
        ci, cj = int(lat / CELL), int(lon / CELL)
        best = None
        for i in range(ci - 1, ci + 2):
            for j in range(cj - 1, cj + 2):
                for plat, plon, ele in self.cells.get((i, j), ()):
                    d = geo.haversine_m(lat, lon, plat, plon)
                    if best is None or d < best[0]:
                        best = (d, ele)
        if best is None or best[0] > MAX_LOOKUP_M:
            return None
        return best[1]

    def along(self, line, step_m=STEP_M):
        """Heights at regular intervals along a polyline, gaps dropped."""
        out = []
        carry = 0.0
        pts = [tuple(p) for p in line]
        for a, b in zip(pts, pts[1:]):
            d = geo.haversine_m(a[0], a[1], b[0], b[1])
            if d == 0:
                continue
            travelled = carry
            while travelled <= d:
                f = travelled / d
                out.append((a[0] + (b[0] - a[0]) * f,
                            a[1] + (b[1] - a[1]) * f))
                travelled += step_m
            carry = travelled - d
        if pts:
            out.append(pts[-1])
        return [h for h in (self.height(*p) for p in out) if h is not None]

    def profile(self, line):
        """Ascent, descent and reclimb along one polyline."""
        hs = self.along(line)
        return summarise(hs)


def summarise(heights):
    """Ascent and descent from a list of heights, ignoring noise.

    Hysteresis rather than a plain sum of deltas: without it, a metre of DEM
    jitter every fifteen metres adds sixty metres of imaginary climbing to a
    kilometre of level street.
    """
    out = {"ascent": 0.0, "descent": 0.0, "start": None, "end": None,
           "high": None, "low": None, "reclimb": 0.0}
    if not heights:
        return out
    mark = heights[0]
    for h in heights[1:]:
        if h - mark > NOISE_M:
            out["ascent"] += h - mark
            mark = h
        elif mark - h > NOISE_M:
            out["descent"] += mark - h
            mark = h
    out["start"], out["end"] = heights[0], heights[-1]
    out["high"], out["low"] = max(heights), min(heights)
    out["reclimb"] = out["ascent"] - max(0.0, out["end"] - out["start"])
    for k in ("ascent", "descent", "reclimb"):
        out[k] = round(out[k], 1)
    return out


def load(tour_id):
    path = ELEV_DIR / f"{tour_id}.json"
    if not path.exists():
        return None
    return Terrain(json.loads(path.read_text(encoding="utf-8")))


def walk_profile(tour, town=None, ground=None):
    """The whole walk, leg by leg, keyed by the arriving stop's id.

    Returns (legs, total). Empty when there is no height data for this town.
    """
    town = town or streets.load(tour["id"])
    ground = ground or load(tour["id"])
    if town is None or ground is None:
        return {}, summarise([])
    legs, whole = {}, []
    stops = tour["stops"]
    for before, after in zip(stops, stops[1:]):
        r = town.route((before["lat"], before["lon"]), (after["lat"], after["lon"]))
        if r is None:
            continue
        hs = ground.along(r["path"])
        legs[after["id"]] = summarise(hs)
        whole += hs
    return legs, summarise(whole)


def main():
    args = sys.argv[1:]
    which = args[args.index("--tour") + 1] if "--tour" in args else "all"
    for path in sorted(BASE.glob("content/*/*.json")):
        tour = json.loads(path.read_text(encoding="utf-8"))
        if which not in ("all", tour["id"]):
            continue
        ground = load(tour["id"])
        if ground is None:
            print(f"{tour['id']}: no elevation data; run the Fetch map data "
                  f"workflow with what: elevation")
            continue
        legs, total = walk_profile(tour, ground=ground)
        print(f"\n{tour['name']} ({tour['id']}) — {ground.dataset}")
        for stop_id, p in legs.items():
            print(f"  {stop_id:<16} {p['start']:6.0f} m -> {p['end']:6.0f} m   "
                  f"up {p['ascent']:5.0f}  down {p['descent']:5.0f}")
        print(f"  {'WHOLE WALK':<16} {total['start']:6.0f} m -> "
              f"{total['end']:6.0f} m   up {total['ascent']:5.0f}  "
              f"down {total['descent']:5.0f}   reclimb {total['reclimb']:.0f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
