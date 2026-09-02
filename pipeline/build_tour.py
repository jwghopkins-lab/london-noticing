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
import confidence                                  # noqa: E402
import terrain                                     # noqa: E402

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

# ---- plain voice ---------------------------------------------------------
#
# A walk may declare contract.voice = "plain", and then it is held to the
# stricter set below. The walks written before the rule existed do not declare
# it and are not touched, which is deliberate: the rule is for what comes next.
#
# What the rule is for. The prose had a house accent, and it was mine rather
# than anybody's: balanced antithesis, the knowing aside, an abstract noun
# doing work a verb should do, and a short portentous sentence to land a
# paragraph. It reads like an essay about a town. A guide standing beside you
# says the thing and stops. Same for the questions: a clue does not need a
# flourish, it needs to be answerable.
VOICES = ("standard", "plain")

PLAIN_LOOK_WORDS_MAX = 60
PLAIN_LOOK_WORDS_NOTE = 45
PLAIN_AFTER_WORDS_MAX = 100
PLAIN_AFTER_WORDS_NOTE = 80
PLAIN_SENTENCE_WORDS = 25
PLAIN_ASK_WORDS = 25
PLAIN_HINT_WORDS = 25
PLAIN_DIRECTIONS_WORDS = 60

# Tics. Each one is a way of sounding like an essay rather than a person, and
# every one of them is quotable from a walk already published.
FLOURISHES = [
    # "That is the giveaway, and it is also the point."
    # "this is the" is left alone: "This is the stop for a drink" introduces
    # something in front of you, which is the opposite of the tic. "That is"
    # and "which is" point BACK at what you just said, which is the tic.
    (r"\b(?:and )?(?:that|which) is (?:also )?(?:the|why|what|where|how)\b"
     r"(?! (?:walk|last stop|one|two|three|four|five|six|seven|eight|nine"
     r"|ten|eleven|twelve)\b)",
     "a knowing aside. Say the thing and stop"),
    (r"\bthe (?:giveaway|irony|joke|trick|catch|whole point|real point)\b",
     "an essay flourish"),
    # "what solving it looked like", "is what a bastide looks like"
    (r"\bwhat .{0,30}? look(?:ed|s) like\b", "an abstract noun doing a verb's job"),
    # "not X, it is Y" / "rather than working for one"
    (r"\b(?:rather|other) than \w+ing\b", "balanced antithesis; pick one side"),
    (r"\bnot (?:just|only|merely|simply) \w+", "the not-just-but construction"),
    (r"\bis less \w+ than\b", "balanced antithesis; pick one side"),
    # hedges stacked on a claim
    (r"\b(?:almost certainly|arguably|effectively|essentially|fundamentally"
     r"|ultimately|notably|crucially|precisely|genuinely|indeed|moreover"
     r"|remarkably|curiously|tellingly|strikingly|in many ways|in a sense"
     r"|of sorts|something of a|in practice|worth noting"
     r"|it is worth (?:noting|remembering|saying|adding))\b",
     "a hedge or an intensifier; cut it"),
    # essay nouns
    (r"\b(?:testament|tapestry|backdrop|narrative|essence|hallmark|microcosm"
     r"|embodiment|juxtaposition|interplay|nexus)\b", "an essay noun"),
    (r"\b(?:speaks to|stands as|serves as|bears witness|no accident|a reminder that)\b",
     "an essay verb"),
]
FLOURISHES = [(re.compile(pat, re.I), why) for pat, why in FLOURISHES]

# Long words with short ones sitting right next to them.
WORDY = {
    "utilise": "use", "utilize": "use", "commence": "start", "purchase": "buy",
    "numerous": "many", "additional": "more", "approximately": "about",
    "subsequently": "then", "prior to": "before", "in order to": "to",
    "due to the fact that": "because", "a number of": "some",
    "at this point in time": "now", "in the event that": "if",
    "the majority of": "most", "possess": "have", "reside": "live",
    "construct": "build", "demonstrate": "show", "obtain": "get",
    "sufficient": "enough", "attempt": "try", "assist": "help",
    "regarding": "about", "concerning": "about", "whilst": "while",
    "amongst": "among", "endeavour": "try", "facilitate": "help",
}

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
# Below this many reachable nodes, a stop is on an island of its own rather than
# on the network. A park path drawn but never joined to a street does this.
ISLAND_NODES = 200
TURN_CLAIMS = re.compile(r"\b(turn|take the|first|second|third)\s+"
                         r"(left|right|turning)", re.I)

# The authored distances on a leg should add up to what the router says it is.
DIST_TOLERANCE_FRAC = 0.25
DIST_TOLERANCE_M = 25.0

# ---- the two ways a leg may be written -----------------------------------
#
# Which one a leg is allowed to use is not the author's taste. confidence.py
# scores the leg against the map and against other routing engines, and a leg
# that does not earn turn-by-turn cannot have it. The reason is a walker's
# complaint that stop 4's directions were not quite right, together with the
# observation that Google is not right there either. Where the map itself is
# thin, the only honest thing to write is a heading and a landmark.
#
# Rough is not a lesser mode. It is what somebody who knows the town actually
# says, and it cannot be wrong the way a turn sequence can be wrong, because it
# does not claim the thing that turns out to be false.
DIRECTIONS_MODES = ("turn_by_turn", "rough")
# Rough directions describe a heading, not a route, so both the distance and the
# bearing are held to looser limits than a turn sequence is.
ROUGH_DIST_TOLERANCE_FRAC = 0.40
ROUGH_COMPASS_TOLERANCE_DEG = 80

# Written once, here, rather than by each author in their own words. It has to
# say the same thing every time: you have not gone wrong, and here is what to
# aim at. Rewriting it per stop is how a caveat turns into an apology.
#
# But it has to say the TRUE thing. There are two reasons a leg goes rough and
# they are not the same reason. Noble Val's warrens really are unsigned lanes
# older than the map. Castres is an ordinary signed town centre where three or
# four routes are the same length, and pasting the warren line onto it would be
# a lie about the place. So the caveat follows the cause.
ROUGH_CAVEATS = {
    "warren": ("The lanes here are older than the map and most carry no sign, "
               "so if you come out somewhere else you have not gone wrong."),
    "choices": ("There is more than one way through here and they are all about "
                "the same length, so if you come out somewhere else you have "
                "not gone wrong."),
}
# The wording that shipped before the two causes were told apart. Walks written
# under the old rule keep it, so archiving a walk means archiving its text too.
ROUGH_LANES = ROUGH_CAVEATS["warren"]

# ---- hills ---------------------------------------------------------------
#
# Climbing towards where you are going is not a complaint. Climbing the same
# metres twice is. reclimb is ascent minus the net gain, so a walk that only
# ever climbs towards its end scores zero however steep it is. The brief for a
# town on a hilltop was "make sure you aren't sending us up and down more than
# necessary", and this is the number that answers it.
RECLIMB_NOTE_M = 20.0
RECLIMB_MAX_M = 50.0

WORD_NUMBERS = {
    "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "a hundred": 100, "one hundred": 100, "two hundred": 200,
    "three hundred": 300, "four hundred": 400, "five hundred": 500,
    # Six to nine were missing, so "six hundred and fifty metres" matched only
    # the "fifty metres" on the end and a 650 m leg read as 50 m.
    "six hundred": 600, "seven hundred": 700, "eight hundred": 800,
    "nine hundred": 900,
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
    m = re.search(r"\b((?:a|one|two|three|four|five|six|seven|eight|nine)"
                  r"\s+hundred(?:\s+and\s+\w+)?"
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
    for m in re.finditer(r"\b((?:a|one|two|three|four|five|six|seven|eight|nine)\s+hundred"
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
        # A French street name can carry a word BEFORE the prefix: Grand Rue
        # Raymond VII, Grand Rue de la Barbacane, Petite Rue. Looking only
        # forwards from "Rue" made every mention of the main street in Cordes
        # read as an invented street and failed the whole build. So the mention
        # starts at the preceding capitalised word when there is one, and
        # resolve_street tries the longer form first.
        start = i
        if i and toks[i - 1][0][:1].isupper():
            # Only refuse when a sentence ends BETWEEN the two words. Looking at
            # what came before the earlier word instead meant a street name
            # opening a sentence — "About sixty metres. Grand Rue Raymond VII
            # runs straight into a gateway" — lost its first word and was
            # reported as invented.
            gap = text[toks[i - 1][1] + len(toks[i - 1][0]):pos]
            if not any(c in gap for c in ".!?:;"):
                start = i - 1
        found.append((toks[start][1], [t for t, _ in toks[start:start + 7]]))
    return found


def resolve_street(town, tokens):
    """The longest form of a mention that the map actually knows.

    Tries dropping a leading word too, so a mention that picked up the previous
    capitalised word by mistake ("Halle Grand Rue Raymond VII") still resolves,
    and one that genuinely needs it ("Grand Rue Raymond VII") resolves to the
    longer name because that is tried first.
    """
    for drop in (0, 1):
        for n in range(len(tokens), drop + 1, -1):
            name = " ".join(tokens[drop:n])
            got = _known(town, name)
            if got:
                return got
    return None


def _known(town, name):
    if town.has_street(name):
        # The map's spelling, not the author's: "Rue Amelie Galup" has to come
        # back as "Rue Amélie Galup" or nothing downstream will match.
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
    """Words that identify a stop well enough to set off from it.

    Accents folded on both sides. Without that, a stop whose id is "edit" and
    whose street is Rue Chambre de l'Édit failed to match its own name, because
    "édit" does not contain the substring "edit". The street resolver has folded
    since Noble Val; this had not caught up.
    """
    blob = f"{stop.get('title','')} {stop.get('where','')} {stop.get('id','')}"
    blob = streets.fold(blob).replace("-", " ")
    return {w for w in re.findall(r"[a-z]{4,}", blob) if w not in GENERIC_WORDS}


def names_its_start(directions, prev):
    """Does the opening sentence name the place you are setting off from?"""
    first = streets.fold(re.split(r"(?<=[.?!])\s+", directions.strip())[0])
    return any(w in first for w in naming_words(prev))


# ---- a question has to rest on something real -----------------------------
#
# "A mathematician is remembered on this square. What was his name?" shipped on
# the strength of an OSM node tagged, in full, historic=memorial. That is a dot
# on a map. It does not say statue, plaque or stone, it does not say what is
# written on it, and the walker could not find it.
#
# A thing OSM merely records the existence of is fine to walk to and fine to
# talk about. It is not enough to promise somebody they can read an answer off
# it. For that the map has to say what kind of thing it is, or what it says.
VAGUE_WITHOUT_DETAIL = {
    "historic": {"memorial", "monument", "plaque", "tomb", "boundary_stone"},
    "tourism": {"artwork"},
    "man_made": {"plaque"},
}
DETAIL_TAGS = ("memorial", "artwork_type", "inscription", "description",
               "material", "subject", "subject:wikidata", "wikidata",
               "wikipedia", "image", "height")
# How close a stop has to be to a place for the question to be resting on it.
RESTS_ON_M = 12.0


# A plaque 29 m back from the square, inside a block of jewellers, is a fine
# thing to mention and a bad thing to build a question on.
REACHABLE_M = 20.0


def out_of_reach(town, stop):
    """A small findable thing a question hangs off, that you cannot get near.

    Only small things. A cathedral sits 21 m off the walkable way because it is
    a cathedral, and you stand at its door, which is on the street. A plaque
    29 m back from a square is a different problem entirely.
    """
    if town is None or not stop.get("question"):
        return None
    got = town.place_near(stop["lat"], stop["lon"], RESTS_ON_M)
    if not got:
        return None
    place, _ = got
    tags = place.get("tags") or {}
    if not any(tags.get(k) in v for k, v in VAGUE_WITHOUT_DETAIL.items()):
        return None
    off = town.off_network_m(place["lat"], place["lon"])
    return (place, off) if off > REACHABLE_M else None


def rests_on_a_dot(town, stop):
    """The place this question hangs off, when the map barely knows it exists."""
    if town is None or not stop.get("question"):
        return None
    got = town.place_near(stop["lat"], stop["lon"], RESTS_ON_M)
    if not got:
        return None
    place, _ = got
    tags = place.get("tags") or {}
    vague = any(tags.get(k) in v for k, v in VAGUE_WITHOUT_DETAIL.items())
    if not vague:
        return None
    if any(k in tags for k in DETAIL_TAGS):
        return None
    return place


# ---- saying it twice -----------------------------------------------------
#
# Every other check in this file reads one field at a time. The walker does not.
# One stop is one card, and the card is the title, then how to walk there, then
# what to look at, then the question, one under the other. Fields written
# separately, each made to stand on its own, come out as:
#
#   Read the sign at the corner. This street is named after a courtroom.
#   The court sat in Castres for most of a century.
#   This street is named after a courtroom. Read the sign. What was it called?
#
# Nothing caught that, because nothing had ever compared two fields.
REPEAT_ERROR_WORDS = 4     # four words the same, twice on one card
REPEAT_NOTE_WORDS = 3
# A run of nothing but function words is not a repeated phrase, it is English.
# "like this one" turning up twice tells you nothing; "at the corner" does.
FUNCTION_WORDS = {
    "a", "an", "and", "as", "at", "be", "but", "by", "for", "from", "here",
    "in", "into", "is", "it", "its", "like", "of", "on", "one", "or", "out",
    "over", "so", "than", "that", "the", "then", "there", "they", "this",
    "to", "up", "was", "were", "with", "you", "your", "not", "no", "if",
    "have", "has", "had", "do", "does", "did", "are", "will", "would",
    "he", "she", "his", "her", "him", "we", "us", "them", "who", "what",
    "which", "when", "all", "any", "some", "more", "most", "very", "can",
    "could", "should", "may", "might", "must", "been", "being", "just",
    "only", "even", "also", "still",
}


def _words(text):
    return [m.group(0) for m in re.finditer(r"[\w'\u2019]+", text or "")]


def known_names(town):
    """Every street and place name the map knows, folded.

    Needed because the exemption cannot be "it looks like a proper noun". A stop
    title is Title Case, so every run of words in it looks like a proper noun,
    and "A Street Named After a Court" sailed through a check that was supposed
    to catch exactly that title. Only a real name off the map is exempt.
    """
    if town is None:
        return set()
    out = {streets.fold(w["name"]) for w in town.streets if w["name"]}
    out |= {streets.fold(p["name"]) for p in town.places if p.get("name")}
    return out


def repeated_across(pieces, names=(), longest=9):
    """Phrases said twice on one card, longest first.

    `pieces` is [(name, text), ...] in the order the walker reads them. Street
    and place names are exempt: a street has to be called the same thing every
    time it is mentioned.
    """
    seen = {}
    for field, text in pieces:
        toks = _words(text)
        for n in range(REPEAT_NOTE_WORDS, longest + 1):
            for i in range(len(toks) - n + 1):
                run = toks[i:i + n]
                key = " ".join(streets.fold(w) for w in run)
                if all(w in FUNCTION_WORDS for w in key.split()):
                    continue
                if any(key in name for name in names):
                    continue
                seen.setdefault(key, {}).setdefault(field, " ".join(run))
    hits = [(len(k.split()), k, v) for k, v in seen.items() if len(v) > 1]
    hits.sort(reverse=True)
    out, covered = [], []
    for n, key, where in hits:
        if any(key in bigger for bigger in covered):
            continue
        covered.append(key)
        out.append((n, list(where.values())[0], sorted(where)))
    return out


def plain_faults(where, text):
    """Every tic and every long word in one piece of prose.

    Reported one line each, with what to do instead, because "this is not plain
    enough" is not actionable and a walker never sees the difference between a
    rule and a scolding.
    """
    out = []
    if not text:
        return out
    for pattern, why in FLOURISHES:
        m = pattern.search(text)
        if m:
            out.append(f"{where}: {m.group(0).strip()!r} is {why}")
    low = text.lower()
    for long_word, short in WORDY.items():
        if re.search(rf"\b{re.escape(long_word)}\b", low):
            out.append(f"{where}: {long_word!r}; say {short!r}")
    return out


def human_list(items):
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} or {items[-1]}"


def rough_cause(score):
    """Why this leg cannot be given as turns: a warren, or a choice of routes.

    No score means no opinion, and no opinion keeps the wording the walk already
    shipped with. Walks written before the two causes were told apart must not
    have their text changed by a later rule.
    """
    if score is None:
        return "warren"
    return "warren" if (score.get("unnamed_frac") or 0) > confidence.UNNAMED_MAX \
        else "choices"


def rough_directions(stop, cause="warren"):
    """The shipped text for a rough leg: heading, streets, caveat, landmark."""
    caveat = ROUGH_CAVEATS.get(cause, ROUGH_LANES)
    out = [(stop.get("directions") or "").strip()]
    named = stop.get("directions_streets") or []
    if named:
        out.append(f"You may come out on {human_list(named)}. {caveat}")
    else:
        out.append(caveat)
    target = (stop.get("directions_target") or "").strip().rstrip(".")
    if target:
        out.append(f"What you are looking for is {target}.")
    return "\n\n".join(out)


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

    names = known_names(streets.load(tour["id"]))
    voice = c.get("voice", "standard")
    if voice not in VOICES:
        errors.append(f"contract.voice must be one of {list(VOICES)}, not {voice!r}")
        voice = "standard"
    plain = voice == "plain"
    if not plain:
        notes.append("this walk does not declare contract.voice = \"plain\". The "
                     "walks written before that rule existed are left alone, but "
                     "anything new should declare it")

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
                mode = s.get("directions_mode", "turn_by_turn")
                if mode not in DIRECTIONS_MODES:
                    errors.append(f"{where}: directions_mode must be one of "
                                  f"{list(DIRECTIONS_MODES)}, not {mode!r}")
                    mode = "turn_by_turn"
                if mode == "rough":
                    # A heading, not a route. Left and right belong to a turn
                    # sequence, and a turn sequence is exactly what this leg
                    # has been judged unable to support.
                    if not compass_positions(d):
                        errors.append(f"{where}: rough directions must give a "
                                      f"compass heading, not a turn")
                    if TURN_CLAIMS.search(d):
                        errors.append(f"{where}: rough directions must not count "
                                      f"turnings; a turning you cannot name "
                                      f"cannot be counted")
                    if not (s.get("directions_target") or "").strip():
                        errors.append(f"{where}: rough directions need a "
                                      f"directions_target, the thing you are "
                                      f"walking towards")
                    if not (s.get("directions_streets") or []):
                        notes.append(f"{where}: rough directions with no "
                                     f"directions_streets; naming the streets you "
                                     f"may come out on is most of the value")
                else:
                    for field in ("directions_target", "directions_streets"):
                        if s.get(field):
                            errors.append(f"{where}: {field} belongs to rough "
                                          f"directions; this leg is turn_by_turn")
                if len(d.split()) < (14 if mode == "rough" else 25):
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
        look_max = PLAIN_LOOK_WORDS_MAX if plain else LOOK_WORDS_MAX
        look_note = PLAIN_LOOK_WORDS_NOTE if plain else LOOK_WORDS_NOTE
        after_max = PLAIN_AFTER_WORDS_MAX if plain else AFTER_WORDS_MAX
        after_note = PLAIN_AFTER_WORDS_NOTE if plain else AFTER_WORDS_NOTE
        n_look, n_after = len(look.split()), len(after.split())
        if n_look > look_max:
            errors.append(f"{where}: {n_look} words of look, max {look_max}")
        elif n_look > look_note:
            notes.append(f"{where}: {n_look} words of look, aim under {look_note}")
        if n_after > after_max:
            errors.append(f"{where}: {n_after} words of explainer, max "
                          f"{after_max}. A guide is brief")
        elif n_after > after_note:
            notes.append(f"{where}: {n_after} words of explainer, aim under "
                         f"{after_note}")
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
                n = len(sentence.split())
                if plain and n > PLAIN_SENTENCE_WORDS:
                    errors.append(f"{where} {field}: a sentence runs to {n} words, "
                                  f"max {PLAIN_SENTENCE_WORDS}. Break it in two")
                elif n > LONG_SENTENCE_WORDS:
                    notes.append(f"{where} {field}: a sentence runs to {n} words")
            if "—" in text:
                notes.append(f"{where} {field}: contains a long dash")

        # Everything a walker reads, the clues included. A question does not
        # get to be florid because it is a question.
        if plain:
            pieces = [("look", look), ("after", after),
                      ("directions", s.get("directions") or ""),
                      ("nudge", (s.get("nudge") or {}).get("prompt") or "")]
            if q:
                pieces += [("question", q.get("ask") or ""),
                           ("hint", q.get("hint") or "")]
            for field, text in pieces:
                errors += plain_faults(f"{where} {field}", text)
            if q:
                for field, cap in (("ask", PLAIN_ASK_WORDS),
                                   ("hint", PLAIN_HINT_WORDS)):
                    n = len((q.get(field) or "").split())
                    if n > cap:
                        errors.append(f"{where} question {field}: {n} words, "
                                      f"max {cap}")
            n = len((s.get("directions") or "").split())
            if n > PLAIN_DIRECTIONS_WORDS:
                errors.append(f"{where}: {n} words of directions, max "
                              f"{PLAIN_DIRECTIONS_WORDS}")

            # One stop is one card, and the walker reads these one under the
            # other. Written separately, each made to stand on its own, they
            # repeat each other word for word.
            card = [("title", s.get("title") or ""),
                    ("directions", s.get("directions") or ""),
                    ("look", look), ("nudge", (s.get("nudge") or {}).get("prompt") or ""),
                    ("ask", (q or {}).get("ask") or ""),
                    ("hint", (q or {}).get("hint") or ""),
                    ("after", after)]
            for n_words, phrase, fields in repeated_across(card, names):
                line = (f"{where}: {phrase!r} is said in both the "
                        f"{' and the '.join(fields)}")
                if n_words >= REPEAT_ERROR_WORDS:
                    errors.append(line + ". Say it once")
                else:
                    notes.append(line)
        if re.search(r"\d", s.get("after", "")) and not s.get("after_spoken"):
            notes.append(f"{where}: digits in the explainer but no spoken form")

    for field in ("outro",):
        text = tour.get(field) or ""
        for phrase in SUMMING_UP:
            if phrase in text.lower():
                errors.append(f"{field}: {phrase!r} is summing up; cut it")
    if plain:
        intro = tour.get("intro") or {}
        for field, text in (("outro", tour.get("outro") or ""),
                            ("intro lead", intro.get("lead") or ""),
                            ("intro body", intro.get("body") or ""),
                            ("intro start", intro.get("start") or ""),
                            ("tagline", tour.get("tagline") or "")):
            errors += plain_faults(field, text)
        for t in tour.get("topics", []):
            errors += plain_faults(f"topic {t['id']}", t.get("blurb") or "")
        header = [("name", tour.get("name") or ""),
                  ("tagline", tour.get("tagline") or ""),
                  ("intro lead", intro.get("lead") or ""),
                  ("intro body", intro.get("body") or ""),
                  ("intro start", intro.get("start") or "")]
        for n_words, phrase, fields in repeated_across(header, names):
            line = (f"the opening says {phrase!r} in both the "
                    f"{' and the '.join(fields)}")
            if n_words >= REPEAT_ERROR_WORDS:
                errors.append(line + ". Say it once")
            else:
                notes.append(line)

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
               f"{s.get('directions_target','') or ''} "
               f"{s.get('look','')} {s.get('after','')}" for s in stops])
        for _, mention in street_mentions(prose):
            if resolve_street(town, mention) is None:
                errors.append(f"no street called {' '.join(mention[:4])!r} in "
                              f"{tour.get('city', 'this town')}; the map says "
                              f"otherwise")
        for s_ in stops:
            here = f"stop {stops.index(s_) + 1} ({s_['id']})"
            far = out_of_reach(town, s_)
            if far:
                errors.append(
                    f"{here}: the question rests on {far[0]['name']!r}, which is "
                    f"{far[1]:.0f} m off the nearest walkable way. Ask about "
                    f"something a walker can stand in front of")
            dot = rests_on_a_dot(town, s_)
            if dot:
                errors.append(
                    f"{here}: the question rests on {dot['name']!r}, which the "
                    f"map records as {dot['tags']} and nothing else. That is a "
                    f"dot on a map, not something you can promise a walker they "
                    f"will find. Ask about something the map describes")

        scores = confidence.score_tour(tour, town)
        # Where the engines disagree about a leg, the streets on THEIR route are
        # the ones a walker may actually come out on. A rough leg is allowed to
        # name those as well as ours, which is the whole point of the mode.
        engine_lines = confidence.load_answers(tour["id"]) or {}
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
                size = town.component_size(s["lat"], s["lon"])
                if size < ISLAND_NODES:
                    errors.append(
                        f"{where}: sits on an isolated fragment of the walkable "
                        f"network, {size} nodes wide. The map never joins it to "
                        f"anything, so no route can reach it. Move the stop a few "
                        f"metres onto a street")
                else:
                    errors.append(f"{where}: no walking route from the stop "
                                  f"before it")
                continue
            mode = s.get("directions_mode", "turn_by_turn")
            said = sum(all_authored_metres(s.get("directions") or ""))
            if said:
                frac = (ROUGH_DIST_TOLERANCE_FRAC if mode == "rough"
                        else DIST_TOLERANCE_FRAC)
                slack = max(DIST_TOLERANCE_M, r["metres"] * frac)
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

            # Whether this leg may be given as a sequence of turns at all is
            # decided by the map and by other routing engines, not by taste.
            verdict = scores.get(s["id"])
            if verdict and verdict["verdict"] == "rough" and mode != "rough":
                errors.append(
                    f"{where}: written as turn-by-turn, but this leg does not "
                    f"support it. " + " Also: ".join(verdict["reasons"])
                    + ". Write it as rough directions instead: a heading, a "
                    f"rough distance, the streets you may come out on, and what "
                    f"to look for.")
            if verdict and verdict["verdict"] == "turn_by_turn" and mode == "rough":
                notes.append(f"{where}: written rough, though the map supports "
                             f"turn-by-turn here")
            for why in (verdict or {}).get("notes", []):
                notes.append(f"{where}: {why}")

            # Streets you may come out on still have to be streets, and still
            # have to be on this leg, or on a route another engine would take.
            # Rough does not mean unchecked.
            plausible = set(heading) | standing
            for ans in (engine_lines.get((stops[i - 1]["id"], s["id"]))
                        or {}).get("answers", []):
                if ans.get("line"):
                    plausible |= town.names_near_line(ans["line"])
            for name in (s.get("directions_streets") or []):
                got = resolve_street(town, name.split())
                if got is None:
                    errors.append(f"{where}: directions_streets names {name!r}, "
                                  f"which is not a street in "
                                  f"{tour.get('city', 'this town')}")
                elif got not in plausible:
                    errors.append(f"{where}: directions_streets names {got!r}, "
                                  f"which is not on the way from the stop before it")
                elif got != name:
                    # This list is printed to the walker as it is written, so it
                    # has to carry the town's own spelling. "Rue Amelie Galup"
                    # resolves fine and then goes out on the page without its
                    # accent, next to street signs that have one.
                    errors.append(f"{where}: directions_streets says {name!r}; "
                                  f"the map spells it {got!r}")

            # In rough directions the streets belong in directions_streets, where
            # the caveat frames them honestly. Naming one in the prose promises
            # the walker they will be on it, which is the promise this mode
            # exists to stop making. The origin is the exception: you have to say
            # where you are setting off from.
            if mode == "rough":
                origin = {n for n, _ in town.named_here(
                    stops[i - 1]["lat"], stops[i - 1]["lon"], STANDING_ON_M)}
                for _, name in named:
                    if name not in origin:
                        errors.append(
                            f"{where}: rough directions name {name!r} in the "
                            f"prose; put it in directions_streets instead, so it "
                            f"reads as a street you may meet rather than one you "
                            f"are promised")

            # Named in the order you meet them. Endpoints are exempt: the street
            # you are standing on and the one you are heading for can be said at
            # any point, and usually are said first.
            routed_order = [x["name"] for x in legs if x["name"]]
            deduped = []
            for name in routed_order:
                if not deduped or deduped[-1] != name:
                    deduped.append(name)
            claimed = ([n for _, n in named if n in heading]
                       if mode != "rough" else [])
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
                tol = (ROUGH_COMPASS_TOLERANCE_DEG if mode == "rough"
                       else COMPASS_TOLERANCE_DEG)
                if name and name in heading:
                    if angle_off(deg, heading[name][1]) > tol:
                        errors.append(
                            f"{where}: says {name} runs {word}, but on this leg "
                            f"it runs {streets.compass_word(heading[name][1])}")
                elif angle_off(deg, geo.bearing_deg(
                        stops[i - 1]["lat"], stops[i - 1]["lon"],
                        s["lat"], s["lon"])) > tol:
                    errors.append(f"{where}: says {word}, but the leg goes "
                                  f"{streets.compass_word(geo.bearing_deg(stops[i-1]['lat'], stops[i-1]['lon'], s['lat'], s['lon']))}")

    # ---- hills, when the height of the ground is known ---------------------
    ground = terrain.load(tour["id"])
    if ground is None:
        notes.append("no height data for this town; run the Fetch map data "
                     "workflow with what: elevation, so the walk can be checked "
                     "for climbing the same metres twice")
    elif town is not None:
        _, whole = terrain.walk_profile(tour, town, ground)
        if whole["start"] is not None:
            notes.append(
                f"the walk runs {whole['start']:.0f} m to {whole['end']:.0f} m, "
                f"climbing {whole['ascent']:.0f} m and dropping "
                f"{whole['descent']:.0f} m")
            if whole["reclimb"] > RECLIMB_MAX_M:
                errors.append(
                    f"the walk climbs {whole['reclimb']:.0f} m it had already "
                    f"climbed once. Reorder the stops so the walking goes one "
                    f"way up or one way down")
            elif whole["reclimb"] > RECLIMB_NOTE_M:
                notes.append(f"{whole['reclimb']:.0f} m of the climbing is "
                             f"ground given away and taken back")

    # Titles sit next to each other in the walker's head even though they are
    # never on screen together. "The Fountain on the Square" followed by "A
    # Memorial on the Square" reads as one place, not two.
    if plain:
        for n_words, phrase, which in repeated_across(
                [(s["id"], s.get("title") or "") for s in stops], names):
            notes.append(f"the titles of {' and '.join(which)} both say "
                         f"{phrase!r}")

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
    # Walks written before the two causes were told apart keep the wording they
    # shipped with. Anything declaring voice: plain gets the true one.
    plain = (tour.get("contract") or {}).get("voice") == "plain"
    scores = confidence.score_tour(tour) if plain else {}
    stops = []
    for s in tour["stops"]:
        stops.append({
            "id": s["id"], "topic": s["topic"], "title": s["title"],
            "where": s["where"], "lat": s["lat"], "lon": s["lon"],
            "directions": (rough_directions(s, rough_cause(scores.get(s["id"])))
                           if s.get("directions_mode") == "rough"
                           else s.get("directions")),
            "directions_mode": s.get("directions_mode", "turn_by_turn"),
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


def rough_survived(shipped_stop, source_stop):
    """Every part of a rough leg made it into the artefact, unedited.

    A rough leg is assembled from parts, so re-running the assembler inside the
    verifier would prove nothing. What is checked instead is that all of the
    source survived and that the standard caveat is present and unaltered.
    Those are the things a bad bake would lose.
    """
    shipped = shipped_stop.get("directions") or ""
    out = []
    if not any(c in shipped for c in ROUGH_CAVEATS.values()):
        out.append(f"{shipped_stop['id']}: the shipped directions carry no caveat")
    wanted = ([source_stop.get("directions") or "",
               (source_stop.get("directions_target") or "").strip().rstrip(".")]
              + list(source_stop.get("directions_streets") or []))
    out += [f"{shipped_stop['id']}: the shipped directions have lost {part[:40]!r}"
            for part in wanted if part and part not in shipped]
    return out


def verify(artefact, source):
    """Re-derive the artefact from the source file and complain about drift."""
    problems = []
    src = {s["id"]: s for s in source["stops"]}
    if [s["id"] for s in artefact["stops"]] != [s["id"] for s in source["stops"]]:
        problems.append("stop order does not match the source")
        return problems
    for s in artefact["stops"]:
        o = src[s["id"]]
        fields = ["title", "where", "look", "after", "look_spoken",
                  "after_spoken", "lat", "lon", "topic",
                  "gate", "question", "nudge"]
        if o.get("directions_mode") == "rough":
            problems += rough_survived(s, o)
        else:
            fields.append("directions")
            if s.get("directions_mode") != "turn_by_turn":
                problems.append(f"{s['id']}: directions_mode does not match "
                                f"the source")
        for field in fields:
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
