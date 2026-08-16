#!/usr/bin/env python3
"""Check a baked artefact against the content, independently of the baker.

This file exists because a generator should not be its own judge. Nothing here
imports bake.py or reuses any of its helpers. It re-derives what the artefact
ought to contain straight from the content files, and compares.

Two ways to run it. bake.py calls verify() on each artefact before writing it,
so a bad artefact never reaches disk. Running this file directly re-checks the
artefacts that are already on disk, which is the check worth doing after a
deploy, or after somebody has edited a file in out/ by hand.

    python3 pipeline/verify_bakes.py [--out out]
"""
import json
import sys
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONTENT = BASE / "content"
FORMAT_VERSION = 1

REQUIRED_STOP_FIELDS = ("id", "topic", "title", "where", "lat", "lon",
                        "look", "after", "directions")


def _haversine_m(lat1, lon1, lat2, lon2):
    """Deliberately a second implementation, not an import from geo.py.

    If both the baker and the checker were wrong in the same way, an imported
    function would agree with itself and prove nothing.
    """
    r = 6371008.8
    p1, p2 = radians(lat1), radians(lat2)
    a = (sin(radians(lat2 - lat1) / 2) ** 2
         + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * asin(sqrt(a))


def verify(artefact, topics_doc, stops_doc, routes_doc):
    """Return a list of plain-English problems. Empty means the artefact is good."""
    problems = []
    key = artefact.get("combo_key")

    if artefact.get("format") != FORMAT_VERSION:
        problems.append(f"format is {artefact.get('format')!r}, expected {FORMAT_VERSION}")

    topics_by_id = {t["id"]: t for t in topics_doc["topics"]}
    stops_by_id = {s["id"]: s for s in stops_doc["stops"]}
    routes = routes_doc["routes"]
    target = routes_doc.get("target_stops", 18)
    per_topic = routes_doc.get("stops_per_topic", 6)

    # The key must be the canonical name for its own topic list.
    listed = [t["id"] for t in artefact.get("topics", [])]
    if key != "-".join(sorted(listed)):
        problems.append(f"combo_key {key!r} does not match its topics {listed}")
    for tid in listed:
        if tid not in topics_by_id:
            problems.append(f"topic {tid!r} is not one of the five")
        elif artefact_name := next((t["name"] for t in artefact["topics"]
                                    if t["id"] == tid), None):
            if artefact_name != topics_by_id[tid]["name"]:
                problems.append(f"topic {tid} is named {artefact_name!r} in the "
                                f"artefact but {topics_by_id[tid]['name']!r} in "
                                f"the content")

    route = routes.get(key)
    if route is None:
        problems.append(f"no route in the lookup for {key!r}")
        return problems

    # The route lookup is authoritative. The artefact must carry exactly the
    # stops it names, in exactly the order it names them.
    want_ids = list(route.get("stops", []))
    got_ids = [s.get("id") for s in artefact.get("stops", [])]
    if got_ids != want_ids:
        problems.append(f"stop order is {got_ids}, but the route lookup says {want_ids}")
        return problems

    chosen = set(key.split("-"))
    for stop in artefact.get("stops", []):
        sid = stop.get("id")
        source = stops_by_id.get(sid)
        if source is None:
            problems.append(f"stop {sid!r} is not in the stop library")
            continue

        for field in REQUIRED_STOP_FIELDS:
            if stop.get(field) in (None, ""):
                problems.append(f"stop {sid} is missing {field}, so the artefact "
                                f"is not self-contained")

        # Text must be byte-identical to the content. A baker that reflows,
        # trims or re-wraps prose changes what a guide will read aloud.
        for field in ("title", "where", "look", "after", "look_spoken",
                      "after_spoken", "directions"):
            if stop.get(field) != source.get(field):
                problems.append(f"stop {sid}: {field} does not match the content file")
        for field in ("lat", "lon", "gate", "nudge", "topic"):
            if stop.get(field) != source.get(field):
                problems.append(f"stop {sid}: {field} does not match the content file")

        if stop.get("topic") not in chosen:
            problems.append(f"stop {sid} is topic {stop.get('topic')}, which this "
                            f"combination did not choose")

    if not route.get("draft"):
        if len(got_ids) != target:
            problems.append(f"{len(got_ids)} stops, expected {target}")
        counts = {}
        for stop in artefact["stops"]:
            counts[stop["topic"]] = counts.get(stop["topic"], 0) + 1
        for tid in sorted(chosen):
            if counts.get(tid, 0) != per_topic:
                problems.append(f"topic {tid} has {counts.get(tid, 0)} stops, "
                                f"expected {per_topic}")

    # Recompute the walk from the coordinates rather than trusting the numbers
    # the baker wrote next to them.
    stops = artefact.get("stops", [])
    if len(stops) >= 2:
        total = sum(_haversine_m(stops[i]["lat"], stops[i]["lon"],
                                 stops[i + 1]["lat"], stops[i + 1]["lon"])
                    for i in range(len(stops) - 1))
        claimed = artefact.get("walk", {}).get("total_walk_m")
        if claimed is None:
            problems.append("the artefact does not say how far the walk is")
        elif abs(claimed - total * 1.3) > 1.0:
            problems.append(f"walk distance is stated as {claimed:.0f} m but the "
                            f"coordinates give {total * 1.3:.0f} m")

    claimed_gated = artefact.get("gated_stops")
    actual_gated = sum(1 for s in stops if s.get("gate"))
    if claimed_gated != actual_gated:
        problems.append(f"says {claimed_gated} gated stops, has {actual_gated}")

    if artefact.get("walk", {}).get("n_stops") != len(stops):
        problems.append("the stop count in the walk summary disagrees with the stops")

    return problems


def main():
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else BASE / "out"
    topics_doc = json.loads((CONTENT / "topics.json").read_text(encoding="utf-8"))
    stops_doc = json.loads((CONTENT / "stops.json").read_text(encoding="utf-8"))
    routes_doc = json.loads((CONTENT / "routes.json").read_text(encoding="utf-8"))

    files = sorted(p for p in out.glob("*.json") if p.name != "manifest.json")
    if not files:
        print(f"no artefacts in {out} — run bake.py first")
        return 1

    bad = 0
    for path in files:
        artefact = json.loads(path.read_text(encoding="utf-8"))
        problems = verify(artefact, topics_doc, stops_doc, routes_doc)
        if problems:
            bad += 1
            print(f"  FAILED  {path.name}")
            for p in problems:
                print(f"          {p}")
        else:
            print(f"  ok      {path.name}")
    print(f"\n{len(files) - bad} good, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
