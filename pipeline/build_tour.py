#!/usr/bin/env python3
"""Check, bake and package each fixed walk as one self-contained file.

Same posture as the London pipeline and for the same reasons. The content is
hand written, so it gets contract-checked before anything is built; the artefact
is self-contained, because a phone in a foreign city may well have no data; and
the checking is done by re-deriving from the source rather than by trusting what
the baker just produced.

The differences from London are all in the content, not the machinery. Each walk
is one fixed route rather than ten combinations, so there is nothing to
enumerate. Most stops are gated on ANSWERING something you can only see by being
there, which is a better gate than GPS in a city of tall narrow streets. The
ones gated on position carry an explicit pass button, because a walk that dead
ends because a phone could not get a fix is worse than one somebody skipped a
check on.

Most of check() is house style made mechanical. Every rule in docs/house-style.md
marked [checked] is in here, and every one of them is a thing that went wrong
once: a title that gave away its own answer, a distance stated to the metre, a
walking time on a twenty metre stroll, a sentence explaining what you were
supposed to have got out of the last paragraph.

    python3 pipeline/build_tour.py [--only <tour-id>]
"""
import json
import re
import sys
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402

BASE = Path(__file__).resolve().parent.parent
# One directory per town under content/. London lives at the top level of
# content/ and is built by a different pipeline, so a one-level glob picks up
# the fixed walks and nothing else.
SRC_GLOB = "content/*/*.json"
OUT_DIR = BASE / "out" / "walks"
APP = BASE / "app" / "index.html"
MARKER = "<script>\n\"use strict\";"
FORMAT_VERSION = 1

# amber-mile was published at /gdansk/ before there was a second walk and people
# have that link. Anything newer is served at its own id.
LEGACY_PATHS = {"amber-mile": ("gdansk", "amber-mile.html")}

# The shape of a walk is the walk's own business, so each tour may declare it.
# The defaults are the two Gdansk walks, which were written before there was
# anything to declare. A tour that says nothing keeps building exactly as it did.
DEFAULT_CONTRACT = {
    "n_stops": 10,
    "topic_split": [4, 3, 3],
    "question_stops": 7,
    "location_gates": 3,
    # The Main Town of Gdansk is small. Anything outside this is a typo, not a
    # stop. Every tour needs its own box for the same reason.
    "bbox": [54.340, 54.360, 18.635, 18.670],
}
SCREEN_ONLY = ["see below", "see above", "as shown", "click", "scroll", "this page"]
LONG_SENTENCE_WORDS = 34

# Sentences whose only job is to tell you what you were supposed to have got out
# of the last paragraph. Say the thing once and stop.
SUMMING_UP = [
    "worth taking away", "and that is the point", "that is the point",
    "the point is", "what this tells us", "the lesson", "in other words",
    "worth knowing", "the thing that eventually", "needless to say",
    "it is worth remembering", "which is to say",
]

WORD_NUMBERS = {
    "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "a hundred": 100, "one hundred": 100, "two hundred": 200,
    "three hundred": 300, "four hundred": 400, "five hundred": 500,
}


def authored_metres(text):
    """The distance the writer put in the directions, digits or words.

    Returns None when there is nothing to read, which is not an error here.
    Whether a distance is required at all is checked separately.
    """
    m = re.search(r"\b(\d+)\s*metres\b", text)
    if m:
        return int(m.group(1))
    # "a hundred and fifty metres", "two hundred metres", "sixty metres"
    m = re.search(r"\b((?:a|one|two|three|four|five)\s+hundred(?:\s+and\s+\w+)?"
                  r"|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
                  r"\s+metres\b", text)
    if not m:
        return None
    phrase = m.group(1)
    if " and " in phrase:
        head, tail = phrase.split(" and ", 1)
        return WORD_NUMBERS.get(head.strip(), 0) + WORD_NUMBERS.get(tail.strip(), 0)
    return WORD_NUMBERS.get(phrase.strip())


def is_rounded(n):
    """Nearest 5 below 100, nearest 10 below 500, nearest 50 above that."""
    if n < 100:
        return n % 5 == 0
    if n < 500:
        return n % 10 == 0
    return n % 50 == 0


def check(tour):
    """Contract-check the tour. Returns (errors, notes)."""
    errors, notes = [], []
    stops = tour["stops"]
    c = dict(DEFAULT_CONTRACT, **tour.get("contract", {}))
    lat_lo, lat_hi, lon_lo, lon_hi = c["bbox"]

    if len(stops) != c["n_stops"]:
        errors.append(f"{len(stops)} stops, expected {c['n_stops']}")

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
        if not (lat_lo <= s["lat"] <= lat_hi) or not (lon_lo <= s["lon"] <= lon_hi):
            errors.append(f"{where}: coordinate is outside the walk's own town")

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
                metres = authored_metres(d)
                if metres is None:
                    notes.append(f"{where}: directions give no distance")
                else:
                    if not is_rounded(metres):
                        errors.append(f"{where}: {metres} metres is weirdly exact; "
                                      f"round it")
                    # "about 23 metres, a minute or two" was the complaint.
                    if metres < 100 and re.search(r"minute", d, re.I):
                        errors.append(f"{where}: a walking time on a {metres} metre "
                                      f"leg; drop it")
        elif s.get("directions"):
            errors.append(f"{where}: the first stop cannot have directions to it")

        q, g = s.get("question"), s.get("gate")
        # Still one or the other, not both. The player renders a single action
        # per stop and the gate wins, so a stop carrying both would drop its
        # question silently. Combining the two needs a player change first.
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
            # "The Golden House" told you the answer was gold before you looked.
            title = (s.get("title") or "").lower()
            for a in q.get("answers", []):
                word = str(a).strip().lower()
                if len(word) > 2 and re.search(rf"\b{re.escape(word)}\b", title):
                    errors.append(f"{where}: the title gives away the answer "
                                  f"{word!r}; rename it")
            ask = (q.get("ask") or "").lower()
            if " or " not in ask:                   # a multiple choice may list it
                for a in q.get("answers", []):
                    word = str(a).strip().lower()
                    if len(word) > 2 and re.search(rf"\b{re.escape(word)}\b", ask):
                        notes.append(f"{where}: the question contains its own "
                                     f"answer {word!r}")
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
            for phrase in SUMMING_UP:
                if phrase in text.lower():
                    errors.append(f"{where} {field}: {phrase!r} is summing up; cut it")
            for sentence in re.split(r"(?<=[.?!])\s+", text):
                if len(sentence.split()) > LONG_SENTENCE_WORDS:
                    notes.append(f"{where} {field}: a sentence runs to "
                                 f"{len(sentence.split())} words")
            if "—" in text:
                notes.append(f"{where} {field}: contains a long dash")
        if re.search(r"\d", s.get("after", "")) and not s.get("after_spoken"):
            notes.append(f"{where}: digits in the explainer but no spoken form")

    for field in ("outro",):
        text = tour.get(field) or ""
        for phrase in SUMMING_UP:
            if phrase in text.lower():
                errors.append(f"{field}: {phrase!r} is summing up; cut it")

    split = sorted(counts.values(), reverse=True)
    if split != c["topic_split"]:
        errors.append(f"topic split is {split}, expected {c['topic_split']}")

    n_q = sum(1 for s in stops if s.get("question"))
    n_g = sum(1 for s in stops if s.get("gate"))
    if n_q != c["question_stops"]:
        errors.append(f"{n_q} question stops, expected {c['question_stops']}")
    if n_g != c["location_gates"]:
        errors.append(f"{n_g} location-gated stops, expected {c['location_gates']}")

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
        # The address it is served at, so tooling can report a real URL rather
        # than guessing one from the id.
        "served_at": LEGACY_PATHS.get(tour["id"], (tour.get("served_at", tour["id"]),))[0],
        # Turn by turn, written by hand along the actual streets. The player
        # must not bolt a computed heading on top: that distance is a straight
        # line times a detour factor, and across an open square it overstates.
        # On the first walk it said 152 metres directly above a hand-measured 120.
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


def build_one(path, page_src):
    tour = json.loads(path.read_text(encoding="utf-8"))
    tid = tour["id"]
    print(f"\n{tour['name']} ({tid}) from {path.name}")

    errors, notes = check(tour)
    for n in notes:
        print(f"  note   {n}")
    for e in errors:
        print(f"  ERROR  {e}")
    if errors:
        print(f"  {len(errors)} errors. Nothing built.")
        return False

    artefact, metrics = bake(tour)
    problems = verify(artefact, tour)
    for pr in problems:
        print(f"  FAILED {pr}")
    if problems:
        return False

    # A walk may name the address it is served at, because the id makes a poor
    # URL when the name is evocative rather than geographic.
    served_dir, dist_name = LEGACY_PATHS.get(
        tid, (tour.get("served_at", tid), f"{tid}.html"))

    # A subdirectory, not out/ itself. The London tools glob out/*.json and
    # will happily treat anything they find there as one of their own routes,
    # which is exactly what happened the first time.
    baked = OUT_DIR / f"{tid}.json"
    baked.parent.mkdir(parents=True, exist_ok=True)
    baked.write_text(json.dumps(artefact, ensure_ascii=False, indent=2), encoding="utf-8")

    # The player retitles itself at runtime, but the tag has to be right in the
    # file itself: anything reading the page without running it (a browser tab
    # before load, a link preview, a gallery listing) only sees the markup.
    page = re.sub(r"<title>[^<]*</title>", f"<title>{tour['name']}</title>",
                  page_src, count=1)
    payload = json.dumps({"tour": artefact}, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace(MARKER, f'<script>window.NOTICING_BUNDLE = {payload};</script>\n'
                                + MARKER, 1)
    out = BASE / "dist" / dist_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

    # Its own address on the served site. Each walk is a separate thing handed
    # to a separate group of people, so they get separate URLs and separate
    # saved progress rather than a picker.
    served = BASE / "app" / served_dir / "index.html"
    served.parent.mkdir(parents=True, exist_ok=True)
    served.write_text(page, encoding="utf-8")

    print(f"  {artefact['walk']['n_stops']} stops, "
          f"{artefact['walk']['total_walk_m'] / 1000:.2f} km on foot, "
          f"{artefact['walk']['total_minutes']:.0f} min walking, "
          f"{artefact['question_stops']} questions, "
          f"{artefact['gated_stops']} location gates")
    for leg in metrics["legs"]:
        print(f"    {leg['from']:<20} -> {leg['to']:<20} "
              f"{leg['walk_m']:>5.0f} m  {leg['minutes']:>4.1f} min")
    for n in metrics["notes"]:
        print(f"  note   {n}")
    print(f"  wrote /{served_dir}/  ({out.stat().st_size / 1024:.0f} KB)")
    return True


def main():
    args = sys.argv[1:]
    only = args[args.index("--only") + 1] if "--only" in args else None

    page_src = APP.read_text(encoding="utf-8")
    files = sorted(BASE.glob(SRC_GLOB))
    if not files:
        print(f"no tours matching {SRC_GLOB}")
        return 1

    built = failed = 0
    for path in files:
        if only and json.loads(path.read_text(encoding="utf-8"))["id"] != only:
            continue
        if build_one(path, page_src):
            built += 1
        else:
            failed += 1

    print(f"\n{built} built, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
