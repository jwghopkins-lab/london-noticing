#!/usr/bin/env python3
"""Bake one self-contained artefact per combination.

The harness is the piece genuinely worth reusing from the TRIVIUM tour-kit
extract. Per combination: gather the content, produce the artefact, hand it to
an INDEPENDENT checker, write one self-contained file, and record a per-combo
failure without aborting the rest of the run.

Two deliberate habits, both bought with someone else's pain:

  Self-contained. The phone on the walk may have no signal. An artefact that
  needs a second request for its own stop text is not an artefact.

  Verification is separate from generation. A generator that grades itself
  grades itself generously, so the checking lives in verify_bakes.py and
  re-derives everything from the content files rather than trusting anything
  passed to it.

Note what this file does NOT do. It does not choose stops. The route lookup is
authoritative: it fixes which stops a combination gets and the order they are
walked in. The first version of this script scored stops and then looked up an
authored order, and every route failed verification because the scoring picked
a different set from the one the order was written for.

    python3 pipeline/bake.py [--out out] [--include-drafts]
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from combos import all_combos                      # noqa: E402
import geo                                         # noqa: E402
import verify_bakes                                # noqa: E402

BASE = Path(__file__).resolve().parent.parent
CONTENT = BASE / "content"
APP_ROUTES = BASE / "app" / "routes"
FORMAT_VERSION = 1


def load(name):
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def stop_artefact(stop):
    """One stop, with everything the player needs and nothing it does not.

    The id is copied through unchanged and never regenerated. Audio files will
    be attached to these ids later, so a renamed stop is a broken recording.
    """
    return {
        "id": stop["id"],
        "topic": stop["topic"],
        "title": stop["title"],
        "where": stop["where"],
        "lat": stop["lat"],
        "lon": stop["lon"],
        "gate": stop.get("gate"),
        "nudge": stop.get("nudge"),
        "look": stop["look"],
        "look_spoken": stop.get("look_spoken"),
        "after": stop["after"],
        "after_spoken": stop.get("after_spoken"),
        # Reserved so a later audio build has somewhere to put itself without
        # changing the artefact shape the player already reads.
        "audio": None,
    }


def build(key, topic_ids, topics_by_id, stops_by_id, route):
    ids = route.get("stops", [])
    stops = [stop_artefact(stops_by_id[i]) for i in ids]
    points = [(s["id"], s["lat"], s["lon"]) for s in stops]
    metrics = geo.check(points)
    return {
        "format": FORMAT_VERSION,
        "combo_key": key,
        "draft": bool(route.get("draft")),
        "topics": [
            {"id": t, "name": topics_by_id[t]["name"],
             "blurb": topics_by_id[t]["blurb"],
             "blurb_spoken": topics_by_id[t].get("blurb_spoken")}
            for t in sorted(topic_ids)
        ],
        "stops": stops,
        "walk": {
            "n_stops": len(stops),
            "total_walk_m": metrics["total_walk_m"],
            "total_minutes": metrics["total_minutes"],
            "reversals": metrics["reversals"],
            "legs": metrics["legs"],
        },
        "gated_stops": sum(1 for s in stops if s["gate"]),
        "note": route.get("note"),
    }


def main():
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else BASE / "out"
    include_drafts = "--include-drafts" in args

    topics_doc = load("topics.json")
    stops_doc = load("stops.json")
    routes_doc = load("routes.json")
    topics_by_id = {t["id"]: t for t in topics_doc["topics"]}
    stops_by_id = {s["id"]: s for s in stops_doc["stops"]}
    routes = routes_doc["routes"]

    out.mkdir(parents=True, exist_ok=True)
    manifest = {"format": FORMAT_VERSION, "combos": []}
    failures = 0

    for key, topic_ids in all_combos(list(topics_by_id), 3):
        route = routes.get(key)
        entry = {"combo_key": key, "topics": sorted(topic_ids)}
        if route is None:
            entry.update(status="missing", problems=["no route for this combination"])
            manifest["combos"].append(entry)
            failures += 1
            print(f"  MISSING  {key}")
            continue

        draft = bool(route.get("draft"))
        if draft and not include_drafts:
            entry.update(status="draft", n_stops=len(route.get("stops", [])),
                         problems=[])
            manifest["combos"].append(entry)
            print(f"  draft    {key}  ({len(route.get('stops', []))} stops, not baked)")
            continue

        # One combination failing must never take the other nine with it.
        try:
            artefact = build(key, topic_ids, topics_by_id, stops_by_id, route)
            problems = verify_bakes.verify(artefact, topics_doc, stops_doc, routes_doc)
            if problems:
                entry.update(status="failed", problems=problems)
                failures += 1
                print(f"  FAILED   {key}")
                for p in problems:
                    print(f"           {p}")
            else:
                path = out / f"{key}.json"
                path.write_text(json.dumps(artefact, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                entry.update(status="ok", n_stops=len(artefact["stops"]),
                             total_walk_m=artefact["walk"]["total_walk_m"],
                             total_minutes=artefact["walk"]["total_minutes"],
                             gated_stops=artefact["gated_stops"],
                             draft=artefact["draft"], problems=[])
                print(f"  ok       {key}  {artefact['walk']['n_stops']} stops, "
                      f"{artefact['walk']['total_walk_m']:.0f} m, "
                      f"{artefact['walk']['total_minutes']:.0f} min, "
                      f"{artefact['gated_stops']} gated")
        except Exception as err:                      # noqa: BLE001
            entry.update(status="error", problems=[f"{type(err).__name__}: {err}"])
            failures += 1
            print(f"  ERROR    {key}: {type(err).__name__}: {err}")
        manifest["combos"].append(entry)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # The player fetches artefacts as static files, so they have to sit next to
    # the page. Copy rather than symlink: the deploy step is a file copy too.
    APP_ROUTES.mkdir(parents=True, exist_ok=True)
    for old in APP_ROUTES.glob("*.json"):
        old.unlink()
    for f in out.glob("*.json"):
        shutil.copy2(f, APP_ROUTES / f.name)

    # The picker needs the five topics before any route is chosen, and it is the
    # one thing the page loads that is not a route. Emitted rather than copied,
    # so the private notes in the content file stay out of the served site.
    baked_keys = {c["combo_key"] for c in manifest["combos"] if c["status"] == "ok"}
    (BASE / "app" / "topics.json").write_text(json.dumps({
        "format": FORMAT_VERSION,
        "pick": 3,
        "topics": [{"id": t["id"], "name": t["name"], "blurb": t["blurb"],
                    "blurb_spoken": t.get("blurb_spoken")}
                   for t in topics_doc["topics"]],
        "available": sorted(baked_keys),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    baked = sum(1 for c in manifest["combos"] if c["status"] == "ok")
    print(f"\n{baked} baked, {failures} failed, "
          f"{sum(1 for c in manifest['combos'] if c['status'] == 'draft')} drafts")
    print(f"artefacts in {out} and {APP_ROUTES}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
