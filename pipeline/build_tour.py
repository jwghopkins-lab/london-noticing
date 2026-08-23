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
import streets                                     # noqa: E402

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

# Riddle furniture. This is a tour guide, not a treasure hunt: the puzzle
# framing is a hangover from the project this player was copied out of, where
# the whole point was withholding an answer. Here the point is showing somebody
# a thing. A guide says "there is a painting of that story on the wall". They do
# not say "somewhere in here is a painting. Go and find it."
RIDDLE_PHRASES = [
    "somewhere in here", "somewhere on", "somewhere along", "see if you can",
    "can you spot", "can you find", "your task", "the answer lies",
    "look carefully and", "look closely and", "if you look carefully",
    "not what it seems", "the trick is", "all is not", "reveals itself",
    "hidden in plain sight", "go and find it", "hunt for", "seek out",
    "riddle", "puzzle", "clue is",
]

# A guide standing next to you is brief. The explainer is read on the spot,
# usually standing up, often in the sun, and 180 words is ninety seconds of
# being talked at. These are the numbers the Noble Val rewrite was cut to.
LOOK_WORDS_MAX = 80
LOOK_WORDS_NOTE = 60
AFTER_WORDS_MAX = 130
AFTER_WORDS_NOTE = 110
AFTER_PARAS_MAX = 4

# Where a coordinate came from. This exists because a stop was placed by guess,
# a compass bearing was then written to match the guess, and both were wrong the
# same way, so nothing could catch it: the walker was sent east to somewhere
# that is north west. Recording the provenance makes the guessing visible in the
# data, and lets the checks below know which claims are worth cross-examining.
COORD_SOURCES = {"osm", "surveyed", "published", "estimated"}

COMPASS = {
    "north east": 45, "north-east": 45, "northeast": 45,
    "south east": 135, "south-east": 135, "southeast": 135,
    "south west": 225, "south-west": 225, "southwest": 225,
    "north west": 315, "north-west": 315, "northwest": 315,
    "north": 0, "east": 90, "south": 180, "west": 270,
}
# A leg can bend, so the written bearing need not be the straight-line one, but
# one of the bearings written down should point roughly the way the walk goes.
COMPASS_TOLERANCE_DEG = 70

# Directions have to say where they start from, BY NAME. The walker who asked
# "where was I supposed to start?" was standing in a church doorway reading
# "Leave the square on the far side from the bridge". That has an origin phrase
# in it and still names nothing: which square, and which side is the bridge on
# when you cannot see it? So a generic phrase is not enough. The first sentence
# has to contain a word that identifies the stop you are standing at.
#
# Words too common to identify anything. Without this list "square" counts as
# naming the previous stop, which is exactly the sentence that failed.
GENERIC_WORDS = {
    "place", "street", "square", "town", "main", "road", "corner", "where",
    "running", "between", "north", "south", "east", "west", "along", "which",
    "other", "things", "people", "little", "great", "small", "first", "second",
    "third", "front", "there", "under", "above", "below", "right", "left",
    "side", "sides", "close", "about", "metres", "walk", "still", "inside",
}

# Words that introduce a street name, so an invented one can be caught. Every
# street the directions name has to exist in the town's OSM extract.
STREET_PREFIXES = {
    "rue", "place", "boulevard", "avenue", "chemin", "quai", "impasse",
    "ruelle", "venelle", "route", "cour", "passage", "sentier", "allee",
    "ulica", "brama", "targ", "dwor", "via", "calle", "piazza",
}
CONNECTORS = {"de", "du", "des", "la", "le", "les", "d", "l"}
# A compass word this close after a street name, in the same sentence, is a
# claim about THAT street rather than about the leg as a whole. This is the
# exact shape of the fault it exists to catch: "take Rue du Pont des Vierges
# south east out of the square" welded the bearing of a different segment onto
# a street that actually runs north east.
BEARING_ATTACH_CHARS = 60
# Turn-by-turn is only honest where the route is fully named and short. In a
# medieval town a quarter of the walking is down lanes with no name on them, and
# no turn sequence written for those can be followed. Those legs say what to
# head for instead.
SIMPLE_MAX_TURNS = 4
# How close counts as being on a street rather than merely near one.
STANDING_ON_M = 30
TURN_CLAIMS = re.compile(r"\b(turn|take the|first|second|third)\s+"
                         r"(left|right|turning)", re.I)

# The authored distances on a leg should add up to what the router says it is.
DIST_TOLERANCE_FRAC = 0.25
DIST_TOLERANCE_M = 25.0

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


def all_authored_metres(text):
    """Every distance written into a piece of directions, not just the first.

    A leg is often described in parts, "fifty metres, then another seventy".
    Those have to add up to the routed length or one of them is wrong.
    """
    out = []
    for m in re.finditer(r"\b(\d+)\s*metres\b", text):
        out.append(int(m.group(1)))
    for m in re.finditer(r"\b((?:a|one|two|three|four|five)\s+hundred"
                         r"(?:\s+and\s+\w+)?|ten|twenty|thirty|forty|fifty|sixty"
                         r"|seventy|eighty|ninety)\s+metres\b", text):
        phrase = m.group(1)
        if " and " in phrase:
            head, tail = phrase.split(" and ", 1)
            out.append(WORD_NUMBERS.get(head.strip(), 0)
                       + WORD_NUMBERS.get(tail.strip(), 0))
        else:
            out.append(WORD_NUMBERS.get(phrase.strip(), 0))
    return [n for n in out if n]


def street_mentions(text):
    """Candidate street names in the text, as (character position, tokens)."""
    toks = [(m.group(0), m.start()) for m in re.finditer(r"[\w'\u2019-]+", text)]
    found = []
    for i, (w, pos) in enumerate(toks[:-1]):
        # Capitalised, or it is the ordinary word: "the two rivers made the
        # place. The Aveyron carried the trade" is not a street called Place.
        if not w[:1].isupper() or streets.fold(w) not in STREET_PREFIXES:
            continue
        nxt = toks[i + 1][0]
        if not (nxt[:1].isupper() or streets.fold(nxt).strip("'\u2019") in CONNECTORS):
            continue
        found.append((pos, [t for t, _ in toks[i:i + 6]]))
    return found


def resolve_street(town, tokens):
    """The longest form of a mention that the map actually knows."""
    for n in range(len(tokens), 1, -1):
        name = " ".join(tokens[:n])
        if town.has_street(name):
            # The map's spelling, not the author's: "Rue Amelie Galup" has to
            # come back as "Rue Amélie Galup" or nothing downstream will match.
            return town.canonical(name) or name
    return None


def compass_positions(text):
    """Compass words with where they sit in the text."""
    t = text.lower()
    out, spans = [], []
    for word in sorted(COMPASS, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(word)}\b", t):
            # "west" sits inside "north west". Without this the compound is read
            # twice, once correctly and once as a bearing 45 degrees out.
            if any(m.start() < e and m.end() > b for b, e in spans):
                continue
            spans.append((m.start(), m.end()))
            out.append((m.start(), COMPASS[word], word))
    return sorted(out)


def attached_street(text, pos, mentions):
    """The street a compass word at `pos` is talking about, if any."""
    best = None
    for mpos, tokens in mentions:
        if mpos >= pos or pos - mpos > BEARING_ATTACH_CHARS:
            continue
        if re.search(r"[.!?]|\n\n", text[mpos:pos]):
            continue          # a new sentence is a new subject
        if best is None or mpos > best[0]:
            best = (mpos, tokens)
    return best


def compass_claims(text):
    """Every compass bearing written into a piece of directions, in order.

    Compounds are matched before their parts, so "north east" is one claim of 45
    degrees rather than a claim of north and a claim of east.
    """
    t = text.lower()
    found = []
    for word in sorted(COMPASS, key=len, reverse=True):
        pat = re.compile(rf"\b{re.escape(word)}\b")
        while True:
            m = pat.search(t)
            if not m:
                break
            found.append((m.start(), COMPASS[word]))
            t = t[:m.start()] + ("#" * (m.end() - m.start())) + t[m.end():]
    return [deg for _, deg in sorted(found)]


def angle_off(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def naming_words(stop):
    """Words that identify a stop well enough to set off from it."""
    blob = f"{stop.get('title','')} {stop.get('where','')} {stop.get('id','')}"
    blob = blob.lower().replace("-", " ")
    return {w for w in re.findall(r"[a-z]{4,}", blob) if w not in GENERIC_WORDS}


def names_its_start(directions, prev):
    """Does the opening sentence name the place you are setting off from?"""
    first = re.split(r"(?<=[.?!])\s+", directions.strip())[0].lower()
    return any(w in first for w in naming_words(prev))


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
        if s.get("coord_source") not in COORD_SOURCES:
            errors.append(f"{where}: coord_source must be one of "
                          f"{sorted(COORD_SOURCES)}, not {s.get('coord_source')!r}")

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
                prev = stops[i - 1]
                if not names_its_start(d, prev):
                    errors.append(f"{where}: the directions never say where you are "
                                  f"setting off from")
                # A written bearing that disagrees with the coordinates means one
                # of the two is stale. Either way somebody gets sent the wrong way.
                claims = compass_claims(d)
                if claims:
                    if s.get("coord_source") == "estimated":
                        notes.append(f"{where}: a compass bearing into a coordinate "
                                     f"that is only estimated")
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
        n = s.get("nudge")
        if n is not None and not (n.get("prompt") or "").strip():
            errors.append(f"{where}: nudge with no prompt")
        if g:
            r = g.get("radius_m")
            if not isinstance(r, (int, float)) or not (20 <= r <= 150):
                errors.append(f"{where}: gate radius should be between 20 and 150")
            if not g.get("allow_pass"):
                notes.append(f"{where}: location gate with no pass button")

        look, after = s.get("look") or "", s.get("after") or ""
        for phrase in RIDDLE_PHRASES:
            if phrase in look.lower():
                errors.append(f"{where} look: {phrase!r} is treasure-hunt talk; "
                              f"just say what is there")
            if q and phrase in (q.get("ask") or "").lower():
                errors.append(f"{where} question: {phrase!r} is treasure-hunt "
                              f"talk; just ask the question")
        n_look, n_after = len(look.split()), len(after.split())
        if n_look > LOOK_WORDS_MAX:
            errors.append(f"{where}: {n_look} words of look, max {LOOK_WORDS_MAX}")
        elif n_look > LOOK_WORDS_NOTE:
            notes.append(f"{where}: {n_look} words of look, aim under {LOOK_WORDS_NOTE}")
        if n_after > AFTER_WORDS_MAX:
            errors.append(f"{where}: {n_after} words of explainer, max "
                          f"{AFTER_WORDS_MAX}. A guide is brief")
        elif n_after > AFTER_WORDS_NOTE:
            notes.append(f"{where}: {n_after} words of explainer, aim under "
                         f"{AFTER_WORDS_NOTE}")
        paras = after.count("\n\n") + 1
        if paras > AFTER_PARAS_MAX:
            errors.append(f"{where}: {paras} paragraphs of explainer, max "
                          f"{AFTER_PARAS_MAX}")

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

    # ---- checked against the real map, when there is one -------------------
    town = streets.load(tour["id"])
    if town is None:
        notes.append("no OSM extract for this tour; run the Fetch map data "
                     "workflow so the directions can be checked against streets "
                     "that exist")
    else:
        prose = " ".join(
            [tour.get("outro") or "", (tour.get("intro") or {}).get("start", "")]
            + [f"{s.get('directions','') or ''} {s.get('where','')} "
               f"{s.get('look','')} {s.get('after','')}" for s in stops])
        for _, mention in street_mentions(prose):
            if resolve_street(town, mention) is None:
                errors.append(f"no street called {' '.join(mention[:4])!r} in "
                              f"{tour.get('city', 'this town')}; the map says "
                              f"otherwise")
        for i, s in enumerate(stops):
            where = f"stop {i + 1} ({s['id']})"
            snap = town.off_network_m(s["lat"], s["lon"])
            if snap > streets.MAX_SNAP_M:
                errors.append(f"{where}: {snap:.0f} m from the nearest walkable "
                              f"way, so it is not somewhere you can stand")
            if i == 0:
                continue
            r = town.route((stops[i - 1]["lat"], stops[i - 1]["lon"]),
                           (s["lat"], s["lon"]))
            if r is None:
                errors.append(f"{where}: no walking route from the stop before it")
                continue
            said = sum(all_authored_metres(s.get("directions") or ""))
            if said:
                slack = max(DIST_TOLERANCE_M, r["metres"] * DIST_TOLERANCE_FRAC)
                if abs(said - r["metres"]) > slack:
                    errors.append(
                        f"{where}: the directions add up to {said} m but the "
                        f"streets route in {r['metres']:.0f} m")

            # ---- what the map says about this leg ----
            legs = [x for x in r["legs"] if x["metres"] >= 8]
            unnamed = sum(x["metres"] for x in legs if not x["name"])
            heading = {}
            for x in legs:
                if x["name"] and x["metres"] >= heading.get(x["name"], (0, 0))[0]:
                    heading[x["name"]] = (x["metres"], x["bearing"])
            simple = unnamed == 0 and len(legs) <= SIMPLE_MAX_TURNS
            standing = set()
            for pt in ((stops[i - 1]["lat"], stops[i - 1]["lon"]),
                       (s["lat"], s["lon"])):
                standing |= {n for n, _ in town.named_here(*pt, STANDING_ON_M)}

            text = s.get("directions") or ""
            mentions = street_mentions(text)
            named = []
            for pos, tokens in mentions:
                got = resolve_street(town, tokens)
                if got:
                    named.append((pos, got))

            # You cannot send somebody down a street this leg never touches.
            for _, name in named:
                if name not in heading and name not in standing:
                    errors.append(f"{where}: names {name!r}, which is not on the "
                                  f"way from the stop before it")

            # A quarter of this walk is unnamed lanes. Where that is true, a turn
            # sequence cannot be followed, so do not write one.
            if not simple and TURN_CLAIMS.search(text):
                errors.append(
                    f"{where}: {len(legs)} turns and "
                    f"{unnamed / r['metres'] * 100:.0f}% of it down lanes with no "
                    f"name, so counting turnings cannot work. Name the streets "
                    f"and say which way they run instead")

            # Named in the order you meet them. Endpoints are exempt: the street
            # you are standing on and the one you are heading for can be said at
            # any point, and usually are said first.
            routed_order = [x["name"] for x in legs if x["name"]]
            deduped = []
            for name in routed_order:
                if not deduped or deduped[-1] != name:
                    deduped.append(name)
            claimed = [n for _, n in named if n in heading]
            cursor = 0
            for name in claimed:
                while cursor < len(deduped) and deduped[cursor] != name:
                    cursor += 1
                if cursor >= len(deduped):
                    errors.append(f"{where}: names {name!r} out of order; the way "
                                  f"round is {' then '.join(deduped)}")
                    break

            # A bearing next to a street name is a claim about that street.
            for pos, deg, word in compass_positions(text):
                att = attached_street(text, pos, mentions)
                name = resolve_street(town, att[1]) if att else None
                if name and name in heading:
                    if angle_off(deg, heading[name][1]) > COMPASS_TOLERANCE_DEG:
                        errors.append(
                            f"{where}: says {name} runs {word}, but on this leg "
                            f"it runs {streets.compass_word(heading[name][1])}")
                elif angle_off(deg, geo.bearing_deg(
                        stops[i - 1]["lat"], stops[i - 1]["lon"],
                        s["lat"], s["lon"])) > COMPASS_TOLERANCE_DEG:
                    errors.append(f"{where}: says {word}, but the leg goes "
                                  f"{streets.compass_word(geo.bearing_deg(stops[i-1]['lat'], stops[i-1]['lon'], s['lat'], s['lon']))}")

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
            "gate": s.get("gate"), "nudge": s.get("nudge"),
            "question": s.get("question"),
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
                      "gate", "question", "nudge"):
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
