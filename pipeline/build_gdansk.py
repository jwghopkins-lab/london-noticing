#!/usr/bin/env python3
"""Check, bake and package the Gdansk tour as one self-contained file.

Same posture as the London pipeline and for the same reasons. The content is
hand written, so it gets contract-checked before anything is built; the artefact
is self-contained, because a phone in a foreign city may well have no data; and
the checking is done by re-deriving from the source rather than by trusting what
the baker just produced.

The differences from London are all in the content, not the machinery. There is
one fixed route rather than ten, so there are no combinations to enumerate. Most
stops are gated on ANSWERING something you can only see by being there, which
is a better gate than GPS in a city of tall narrow streets. The three that are
gated on position carry an explicit pass button, because a walk that dead ends
because a phone could not get a fix is worse than one somebody skipped a check on.

    python3 pipeline/build_gdansk.py [--out dist/amber-mile.html]
"""
import json
import re
import sys
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "content" / "gdansk" / "tour.json"
APP = BASE / "app" / "index.html"
MARKER = "<script>\n\"use strict\";"
FORMAT_VERSION = 1

N_STOPS = 10
TOPIC_SPLIT = [4, 3, 3]
N_QUESTION_GATES = 7
N_LOCATION_GATES = 3
# The Main Town is small. Anything outside this is a typo, not a stop.
LAT_RANGE = (54.340, 54.360)
LON_RANGE = (18.635, 18.670)
SCREEN_ONLY = ["see below", "see above", "as shown", "click", "scroll", "this page"]
LONG_SENTENCE_WORDS = 34


def check(tour):
    """Contract-check the tour. Returns (errors, notes)."""
    errors, notes = [], []
    stops = tour["stops"]

    if len(stops) != N_STOPS:
        errors.append(f"{len(stops)} stops, expected {N_STOPS}")

    topic_ids = {t["id"] for t in tour["topics"]}
    counts = {}
    seen = set()
    for i, s in enumerate(stops):
        where = f"stop {i + 1} ({s.get('id', '?')})"
        if s["id"] in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(s["id"])
        if s["topic"] not in topic_ids:
            errors.append(f"{where}: unknown topic {s['topic']!r}")
        counts[s["topic"]] = counts.get(s["topic"], 0) + 1

        for field in ("title", "where", "look", "after"):
            if not (s.get(field) or "").strip():
                errors.append(f"{where}: missing {field}")
        if not (LAT_RANGE[0] <= s["lat"] <= LAT_RANGE[1]) \
           or not (LON_RANGE[0] <= s["lon"] <= LON_RANGE[1]):
            errors.append(f"{where}: coordinate is not in the Main Town")

        # Every stop after the first must say how to walk to it. This is the
        # whole point of the addition: being told what to look at is no use if
        # you cannot find the place.
        if i > 0:
            d = (s.get("directions") or "").strip()
            if not d:
                errors.append(f"{where}: no directions from the previous stop")
            else:
                if len(d.split()) < 25:
                    notes.append(f"{where}: directions are only {len(d.split())} "
                                 f"words, probably not detailed enough")
                if not re.search(r"(left|right|straight|north|south|east|west)", d, re.I):
                    errors.append(f"{where}: directions never say which way to turn")
                if not re.search(r"\d|metre", d, re.I):
                    notes.append(f"{where}: directions give no distance")
        elif s.get("directions"):
            errors.append(f"{where}: the first stop cannot have directions to it")

        q, g = s.get("question"), s.get("gate")
        if q and g:
            errors.append(f"{where}: has both a question and a location gate; pick one")
        if not q and not g:
            errors.append(f"{where}: has neither a question nor a location gate")
        if q:
            if not (q.get("ask") or "").strip():
                errors.append(f"{where}: question has nothing to ask")
            if not q.get("answers"):
                errors.append(f"{where}: question accepts no answers")
            for a in q.get("answers", []):
                if not str(a).strip():
                    errors.append(f"{where}: blank accepted answer")
            if not (q.get("hint") or "").strip():
                notes.append(f"{where}: no hint, so a stuck walker stays stuck")
        if g:
            r = g.get("radius_m")
            if not isinstance(r, (int, float)) or not (20 <= r <= 150):
                errors.append(f"{where}: gate radius should be between 20 and 150")
            if not g.get("allow_pass"):
                notes.append(f"{where}: location gate with no pass button")

        for field in ("look", "after", "directions"):
            text = s.get(field) or ""
            for phrase in SCREEN_ONLY:
                if phrase in text.lower():
                    notes.append(f"{where} {field}: contains {phrase!r}, screen only")
            for sentence in re.split(r"(?<=[.?!])\s+", text):
                if len(sentence.split()) > LONG_SENTENCE_WORDS:
                    notes.append(f"{where} {field}: a sentence runs to "
                                 f"{len(sentence.split())} words")
            if "—" in text:
                notes.append(f"{where} {field}: contains a long dash")
        if re.search(r"\d", s.get("after", "")) and not s.get("after_spoken"):
            notes.append(f"{where}: digits in the explainer but no spoken form")

    split = sorted(counts.values(), reverse=True)
    if split != TOPIC_SPLIT:
        errors.append(f"topic split is {split}, expected {TOPIC_SPLIT}")

    n_q = sum(1 for s in stops if s.get("question"))
    n_g = sum(1 for s in stops if s.get("gate"))
    if n_q != N_QUESTION_GATES:
        errors.append(f"{n_q} question stops, expected {N_QUESTION_GATES}")
    if n_g != N_LOCATION_GATES:
        errors.append(f"{n_g} location-gated stops, expected {N_LOCATION_GATES}")

    return errors, notes


def bake(tour):
    stops = []
    for s in tour["stops"]:
        stops.append({
            "id": s["id"], "topic": s["topic"], "title": s["title"],
            "where": s["where"], "lat": s["lat"], "lon": s["lon"],
            "directions": s.get("directions"),
            "gate": s.get("gate"), "nudge": None, "question": s.get("question"),
            "look": s["look"], "look_spoken": s.get("look_spoken"),
            "after": s["after"], "after_spoken": s.get("after_spoken"),
            "audio": None,
        })
    metrics = geo.check([(s["id"], s["lat"], s["lon"]) for s in stops])
    return {
        "format": FORMAT_VERSION,
        "combo_key": tour["id"],
        "mode": "fixed",
        # Turn by turn, written by hand along the actual streets. The player
        # must not bolt a computed heading on top: that distance is a straight
        # line times a detour factor, and across an open square it overstates.
        # On this walk it said 152 metres directly above a hand-measured 120.
        "directions_style": "turn_by_turn",
        "name": tour["name"],
        "tagline": tour.get("tagline"),
        "city": tour.get("city"),
        "intro": tour["intro"],
        "outro": tour.get("outro"),
        "draft": False,
        "topics": tour["topics"],
        "stops": stops,
        "walk": {"n_stops": len(stops),
                 "total_walk_m": metrics["total_walk_m"],
                 "total_minutes": metrics["total_minutes"],
                 "reversals": metrics["reversals"],
                 "legs": metrics["legs"]},
        "gated_stops": sum(1 for s in stops if s["gate"]),
        "question_stops": sum(1 for s in stops if s["question"]),
    }, metrics


def _haversine(lat1, lon1, lat2, lon2):
    """A second implementation on purpose. See verify_bakes.py for why."""
    r = 6371008.8
    p1, p2 = radians(lat1), radians(lat2)
    a = (sin(radians(lat2 - lat1) / 2) ** 2
         + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * asin(sqrt(a))


def verify(artefact, source):
    """Re-derive the artefact from the source file and complain about drift."""
    problems = []
    src = {s["id"]: s for s in source["stops"]}
    if [s["id"] for s in artefact["stops"]] != [s["id"] for s in source["stops"]]:
        problems.append("stop order does not match the source")
        return problems
    for s in artefact["stops"]:
        o = src[s["id"]]
        for field in ("title", "where", "look", "after", "look_spoken",
                      "after_spoken", "directions", "lat", "lon", "topic",
                      "gate", "question"):
            if s.get(field) != o.get(field):
                problems.append(f"{s['id']}: {field} does not match the source")
        for field in ("title", "where", "look", "after"):
            if not s.get(field):
                problems.append(f"{s['id']}: {field} is empty, not self-contained")
        if s.get("question") and not s["question"].get("answers"):
            problems.append(f"{s['id']}: question with no answers would be unpassable")
    total = sum(_haversine(artefact["stops"][i]["lat"], artefact["stops"][i]["lon"],
                           artefact["stops"][i + 1]["lat"], artefact["stops"][i + 1]["lon"])
                for i in range(len(artefact["stops"]) - 1))
    if abs(artefact["walk"]["total_walk_m"] - total * 1.3) > 1.0:
        problems.append("the stated walking distance disagrees with the coordinates")
    if artefact["gated_stops"] != sum(1 for s in artefact["stops"] if s.get("gate")):
        problems.append("the gated stop count is wrong")
    return problems


def main():
    args = sys.argv[1:]
    out = (Path(args[args.index("--out") + 1]) if "--out" in args
           else BASE / "dist" / "amber-mile.html")

    tour = json.loads(SRC.read_text(encoding="utf-8"))
    errors, notes = check(tour)
    for n in notes:
        print(f"  note   {n}")
    for e in errors:
        print(f"  ERROR  {e}")
    if errors:
        print(f"\n{len(errors)} errors. Nothing built.")
        return 1

    artefact, metrics = bake(tour)
    problems = verify(artefact, tour)
    for pr in problems:
        print(f"  FAILED {pr}")
    if problems:
        return 1

    # A subdirectory, not out/ itself. The London tools glob out/*.json and
    # will happily treat anything they find there as one of their own routes,
    # which is exactly what happened the first time.
    baked = BASE / "out" / "gdansk" / "amber-mile.json"
    baked.parent.mkdir(parents=True, exist_ok=True)
    baked.write_text(json.dumps(artefact, ensure_ascii=False, indent=2), encoding="utf-8")

    page = APP.read_text(encoding="utf-8")
    # The player retitles itself at runtime, but the tag has to be right in the
    # file itself: anything reading the page without running it (a browser tab
    # before load, a link preview, a gallery listing) only sees the markup.
    page = re.sub(r"<title>[^<]*</title>", f"<title>{tour['name']}</title>", page, count=1)
    payload = json.dumps({"tour": artefact}, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace(MARKER, f'<script>window.NOTICING_BUNDLE = {payload};</script>\n'
                                + MARKER, 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

    # Its own address on the served site. Gdansk is a different walk in a
    # different country, and sharing a page with London would be confusing, so
    # it gets its own directory and its own index rather than a link off the
    # front page.
    served = BASE / "app" / "gdansk" / "index.html"
    served.parent.mkdir(parents=True, exist_ok=True)
    served.write_text(page, encoding="utf-8")

    print(f"\n  {artefact['walk']['n_stops']} stops, "
          f"{artefact['walk']['total_walk_m'] / 1000:.2f} km on foot, "
          f"{artefact['walk']['total_minutes']:.0f} min walking, "
          f"{artefact['question_stops']} questions, "
          f"{artefact['gated_stops']} location gates")
    for leg in metrics["legs"]:
        print(f"    {leg['from']:<14} -> {leg['to']:<14} "
              f"{leg['walk_m']:>5.0f} m  {leg['minutes']:>4.1f} min")
    for n in metrics["notes"]:
        print(f"  note   {n}")
    print(f"\n{baked}\n{out}\n{served}\nwritten "
          f"({out.stat().st_size / 1024:.0f} KB each)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
