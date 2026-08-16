#!/usr/bin/env python3
"""Content contracts. Run this before baking, and fix what it says.

Fedora had validate_hunt.py for the same reason: the content is hand-written
JSON, and a hand-written mistake that reaches the phone is discovered by a
tourist standing in the rain.

Two classes of finding. An ERROR means the content is wrong and baking should
not proceed. A WARNING means a human should look, usually because a route is
still a draft or a line will not read well out loud.

    python3 pipeline/validate_content.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from combos import all_combos                      # noqa: E402
import geo                                         # noqa: E402

BASE = Path(__file__).resolve().parent.parent
CONTENT = BASE / "content"

N_TOPICS = 5
PICK = 3
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Generous box around central London. This is here to catch a swapped lat/lon
# or a dropped minus sign, not to police the walk.
LAT_RANGE = (51.46, 51.56)
LON_RANGE = (-0.22, 0.02)

# Everything is written to be spoken by a guide one day, so these are the
# things that only work on a screen.
SCREEN_ONLY = [
    "see below", "see above", "the table below", "as shown", "shown below",
    "click", "scroll", "this page", "on screen", "on the screen", "tap the link",
]
LONG_SENTENCE_WORDS = 34


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")

    def ok(self):
        return not self.errors


def load(name):
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def check_speakable(rep, where, text):
    """Lint prose that a guide will one day read out."""
    low = text.lower()
    for phrase in SCREEN_ONLY:
        if phrase in low:
            rep.warn(where, f"contains {phrase!r}, which only works on a screen")
    for sentence in re.split(r"(?<=[.?!])\s+", text):
        n = len(sentence.split())
        if n > LONG_SENTENCE_WORDS:
            rep.warn(where, f"a sentence runs to {n} words, too long to say aloud")
    if "—" in text:
        rep.warn(where, "contains a long dash; say the thing instead")


def check_spoken_pair(rep, where, written, spoken):
    """A number or a date usually needs a separate spoken form."""
    if spoken is None:
        if re.search(r"\d", written):
            rep.warn(where, "has digits but no spoken form; a guide has to "
                            "guess how to say them")
        return
    if spoken.strip() == written.strip():
        rep.warn(where, "spoken form is identical to the written form; "
                        "set it to null instead")
    if re.search(r"\d", spoken):
        rep.warn(where, "spoken form still contains digits")


def validate_topics(rep, doc):
    topics = doc.get("topics", [])
    if len(topics) != N_TOPICS:
        rep.error("topics", f"expected {N_TOPICS} topics, found {len(topics)}")
    seen = set()
    for t in topics:
        tid = t.get("id", "")
        where = f"topic {tid or '?'}"
        if not ID_RE.match(tid):
            rep.error(where, "id must be lowercase words joined by hyphens")
        if tid in seen:
            rep.error(where, "duplicate topic id")
        seen.add(tid)
        if not t.get("name"):
            rep.error(where, "missing name")
        blurb = t.get("blurb") or ""
        if not blurb:
            rep.error(where, "missing blurb")
        else:
            check_speakable(rep, where + " blurb", blurb)
            check_spoken_pair(rep, where + " blurb", blurb, t.get("blurb_spoken"))
    return topics


def validate_stops(rep, doc, topic_ids):
    # Bench content: written and kept, but deliberately not in any route.
    stops = [s for s in doc.get("stops", []) if not s.get("_unused")]
    seen = {}
    for s in stops:
        sid = s.get("id", "")
        where = f"stop {sid or '?'}"
        if not ID_RE.match(sid):
            rep.error(where, "id must be lowercase words joined by hyphens")
        if sid in seen:
            rep.error(where, "duplicate stop id")
        seen[sid] = s

        if s.get("topic") not in topic_ids:
            rep.error(where, f"topic {s.get('topic')!r} is not one of the five")
        for field in ("title", "where", "look", "after", "directions"):
            if not (s.get(field) or "").strip():
                rep.error(where, f"missing {field}")

        lat, lon = s.get("lat"), s.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            rep.error(where, "lat and lon must both be numbers")
        else:
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1]):
                rep.error(where, f"lat {lat} is outside central London")
            if not (LON_RANGE[0] <= lon <= LON_RANGE[1]):
                rep.error(where, f"lon {lon} is outside central London")

        gate = s.get("gate")
        if gate is not None:
            r = gate.get("radius_m")
            if not isinstance(r, (int, float)) or not (20 <= r <= 250):
                rep.error(where, "gate radius_m should be between 20 and 250")
            if not (gate.get("prompt") or "").strip():
                rep.error(where, "a gated stop needs a gate prompt")
            else:
                check_speakable(rep, where + " gate prompt", gate["prompt"])

        nudge = s.get("nudge")
        if nudge is not None:
            for field in ("prompt", "confirm"):
                if not (nudge.get(field) or "").strip():
                    rep.error(where, f"nudge is missing {field}")
            if nudge.get("prompt"):
                check_speakable(rep, where + " nudge", nudge["prompt"])

        for field in ("look", "after"):
            text = s.get(field) or ""
            if text:
                check_speakable(rep, f"{where} {field}", text)
                check_spoken_pair(rep, f"{where} {field}", text,
                                  s.get(field + "_spoken"))
    return seen


def validate_routes(rep, doc, topics, stops):
    routes = doc.get("routes", {})
    target = doc.get("target_stops", 18)
    per_topic = doc.get("stops_per_topic", 6)

    expected = {key for key, _ in all_combos([t["id"] for t in topics], PICK)}
    got = set(routes)
    for missing in sorted(expected - got):
        rep.error("routes", f"no route for combination {missing}")
    for extra in sorted(got - expected):
        rep.error("routes", f"{extra} is not a combination of three of the five topics")

    n_draft = 0
    for key in sorted(expected & got):
        route = routes[key]
        where = f"route {key}"
        draft = bool(route.get("draft"))
        ids = route.get("stops", [])
        if draft:
            n_draft += 1

        unknown = [i for i in ids if i not in stops]
        for i in unknown:
            rep.error(where, f"stop {i!r} does not exist")
        if unknown:
            continue

        wanted = set(key.split("-"))
        for i in ids:
            t = stops[i]["topic"]
            if t not in wanted:
                rep.error(where, f"stop {i} belongs to topic {t}, which this "
                                 f"combination did not choose")

        if not draft:
            if len(ids) != target:
                rep.error(where, f"has {len(ids)} stops, expected {target}")
            counts = {t: 0 for t in wanted}
            for i in ids:
                counts[stops[i]["topic"]] = counts.get(stops[i]["topic"], 0) + 1
            for t, n in sorted(counts.items()):
                if n != per_topic:
                    rep.error(where, f"topic {t} has {n} stops, expected {per_topic}")

        if len(ids) >= 2:
            points = [(i, stops[i]["lat"], stops[i]["lon"]) for i in ids]
            result = geo.check(points)
            for p in result["problems"]:
                # A draft is allowed to be a bad walk. A shipped route is not.
                (rep.warn if draft else rep.error)(where, p)
            for n in result["notes"]:
                rep.warn(where, n)
            rep.warn(where, f"{len(ids)} stops, {result['total_walk_m']:.0f} m "
                            f"on foot, about {result['total_minutes']:.0f} "
                            f"minutes of walking, {result['reversals']} doubling back")
        elif not draft:
            rep.error(where, "a shipped route needs stops")

    if n_draft:
        rep.warn("routes", f"{n_draft} of {len(expected)} routes are still drafts "
                           f"and will not be baked for release")
    return routes


def main():
    rep = Report()
    topics = validate_topics(rep, load("topics.json"))
    topic_ids = {t["id"] for t in topics}
    stops = validate_stops(rep, load("stops.json"), topic_ids)
    validate_routes(rep, load("routes.json"), topics, stops)

    used = set()
    for r in load("routes.json").get("routes", {}).values():
        used.update(r.get("stops", []))
    for sid in sorted(set(stops) - used):
        rep.error(f"stop {sid}", "is not used by any route")

    for w in rep.warnings:
        print(f"  warn   {w}")
    for e in rep.errors:
        print(f"  ERROR  {e}")
    print(f"\n{len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
