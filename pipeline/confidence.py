#!/usr/bin/env python3
"""Decide whether a leg can honestly be given as turn-by-turn directions.

This is the answer to a real complaint: the directions for stop 4 of the Noble
Val walk were not quite right, and neither, as the walker pointed out, was
Google. That is the whole insight. In a medieval warren the map itself is thin —
lanes with no name in the data and no sign on the wall — and no amount of care
in the writing fixes that. What fixes it is knowing which legs are like that and
saying something different on those legs.

So every leg gets scored, and the score decides the mode:

    turn_by_turn   take this street, then that one, and it is this far
    rough          head this way, this far, you may come out on one of these
                   streets, and here is what you are looking for

Rough is not a failure. It is what a person actually says when they know a place
and know the lanes are a muddle. It cannot be wrong in the way a turn sequence
can be wrong, because it does not claim the thing that turns out to be false.

Five signals, any one of which can send a leg to rough:

  agreement   Do independent routing engines walk it the same way? Their answers
              are fetched by fetch_routes.py and committed. Disagreement means
              the map does not state the route plainly.
  margin      Is there a second way round of much the same length? This one
              needs no second engine and is the most useful of the five. Where
              two routes are within a quarter of each other a walker will take
              either, so directions that assume one of them are a coin toss.
              Except on a spine — see below. That question only bites when the
              directions are a sequence of turnings to be counted off.
  unnamed     How much of the walking is down lanes the map has no name for. You
              cannot tell somebody to take a street that has no name, and you
              cannot tell them to count turnings past lanes they cannot see.
              Counted between named streets only: a short nameless stretch at
              either end is the approach to the door, not a decision.
  turns       A person holding a phone in the sun follows about four.
  snap        How far each end of the leg is from anywhere you can walk. A stop
              floating off the network means the route to it is a guess.

Absence of evidence is not evidence. A leg the engines disagree about is a
reason to drop to rough; a leg no engine could be asked about — the fetch has
never run, or both of them timed out — is a note telling somebody to go and ask,
not a verdict. Otherwise a flaky afternoon on a volunteer-run server would
silently rewrite a walk.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402
import streets                                     # noqa: E402

BASE = Path(__file__).resolve().parent.parent
ROUTES_DIR = BASE / "data" / "routes"

# Two routes count as the same route when four fifths of each lies within
# twenty metres of the other. Twenty is chosen from the street width these
# walks happen on: it forgives which side of a lane the engine drew, and does
# not forgive a different lane.
AGREE_TOL_M = 20.0
AGREE_OVERLAP = 0.80
AGREE_LENGTH = 1.25
# ...and the gap has to be worth arguing about. Across a 30 m square, 28 m
# against 35 m is a 1.25 ratio and means nothing at all.
AGREE_LENGTH_M = 20.0
SAMPLE_M = 8.0

MARGIN_MIN = 1.25          # the next way round must be a quarter longer
UNNAMED_MAX = 0.10         # a tenth of the walking may be down nameless lanes
TURNS_MAX = 4
SNAP_MAX_M = 25.0
LANDMARK_M = 25.0          # something OSM names, close enough to walk towards
ALTERNATIVE_SHARE = 0.60   # above this the "other" route is the same route
SHORT_LEG_M = 8.0          # stretches below this are joins, not turns
# One named street carrying this much of a leg makes the leg a spine: the
# instruction is "walk up that street", and there is nothing to get wrong.
SPINE_SHARE = 0.55
# An unnamed stretch at either end of a leg is the approach: the yard you step
# out of, the path across the green to the door. Up to this length it is not a
# choice a walker has to make, so it is not counted against the leg. Past it,
# it is a stretch of walking like any other.
APPROACH_M = 60.0

MODES = ("turn_by_turn", "rough")


# ---- geometry ------------------------------------------------------------

def resample(line, step_m=SAMPLE_M):
    """Points every step_m along a polyline, so overlap is measured by length.

    Without this, a route drawn with many nodes at one end and few at the other
    would be judged mostly on its crowded end.
    """
    if not line:
        return []
    out = [tuple(line[0])]
    carry = 0.0
    for a, b in zip(line, line[1:]):
        d = geo.haversine_m(a[0], a[1], b[0], b[1])
        if d == 0:
            continue
        travelled = carry
        while travelled + step_m <= d:
            travelled += step_m
            f = travelled / d
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        carry = travelled - d
    out.append(tuple(line[-1]))
    return out


def covered(line_a, line_b, tol=AGREE_TOL_M):
    """Fraction of line_a that lies within tol of line_b."""
    pts = resample(line_a)
    if not pts:
        return 0.0
    near = sum(1 for p in pts if geo.point_to_line_m(p, line_b) <= tol)
    return near / len(pts)


def agreement(ours, theirs, tol=AGREE_TOL_M):
    """How far two engines agree about one leg.

    Overlap is taken both ways and the worse one kept. One way alone is not
    enough: a short route that runs along part of a long one is fully covered by
    it while describing a different walk.
    """
    a_len = sum(geo.haversine_m(a[0], a[1], b[0], b[1])
                for a, b in zip(ours, ours[1:]))
    b_len = sum(geo.haversine_m(a[0], a[1], b[0], b[1])
                for a, b in zip(theirs, theirs[1:]))
    ratio = (max(a_len, b_len) / min(a_len, b_len)) if min(a_len, b_len) > 0 else 999.0
    return {
        "overlap": round(min(covered(ours, theirs, tol),
                             covered(theirs, ours, tol)), 3),
        "length_ratio": round(ratio, 3),
        "their_metres": round(b_len, 1),
    }


def strip_approach(legs):
    """Drop a short nameless stretch from either end of a leg.

    Almost every unnamed stretch on the Borough walk turned out to be the first
    or the last one: the yard the stop stands in, the pavement from the road to
    the pub door, the path over the green. None of those is a lane a walker has
    to pick out from other lanes, which is the thing the unnamed signal exists
    to catch. Counting them sent three legs to rough directions for the crime of
    having a doorstep.
    """
    out = list(legs)
    while out and not out[0]["name"] and not out[0].get("obvious") \
            and out[0]["metres"] <= APPROACH_M:
        out.pop(0)
    while out and not out[-1]["name"] and not out[-1].get("obvious") \
            and out[-1]["metres"] <= APPROACH_M:
        out.pop()
    return out


# ---- the score -----------------------------------------------------------

# A stop moved by more than this is a different stop, and an answer fetched for
# where it used to be says nothing about where it is now.
STALE_M = 10.0


def load_answers(tour_id):
    """The committed second opinions, keyed by (from, to). None if never fetched.

    The endpoints each answer was fetched for are kept alongside it, so a stop
    that has since moved can be spotted. Without that, moving a stop by fifty
    metres leaves the old answers in place, agreeing with a route nobody walks.
    """
    path = ROUTES_DIR / f"{tour_id}.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {(leg["from"], leg["to"]): leg for leg in doc["legs"]}


def fresh_answers(leg, a, b):
    """This leg's answers, if they were fetched for these two points."""
    if leg is None:
        return []
    for stored, now in ((leg.get("from_at"), a), (leg.get("to_at"), b)):
        if not stored or geo.haversine_m(stored[0], stored[1], now[0], now[1]) > STALE_M:
            return None
    return leg["answers"]


def score_leg(town, a, b, answers=None):
    """Score one leg. `answers` is the list this leg's engines returned.

    None means no second opinion has ever been fetched for this tour, which is
    reported and scored around. An empty list means the fetch ran and every
    engine failed on this leg, which is a reason to be less sure, not more.
    """
    out = {"verdict": "rough", "reasons": [], "notes": [], "engines": [],
           "metres": None, "turns": None, "unnamed_frac": None,
           "margin": None, "only_way": False, "snap_m": None,
           "spine": None, "spine_share": None, "approach_m": 0.0}

    # A stop off the walkable network is only a problem when there is nothing
    # there to aim at. The church stop sits 41 m off the graph because it is
    # inside the church, and "the church is on the square" is a perfectly good
    # last instruction. A stop 41 m off the graph in the middle of nowhere is
    # not the same thing at all.
    snaps = []
    for pt in (a, b):
        d = town.off_network_m(*pt)
        if d > SNAP_MAX_M and town.place_near(*pt, LANDMARK_M):
            d = 0.0
        snaps.append(d)
    out["snap_m"] = round(max(snaps), 1)

    r = town.route(a, b)
    if r is None:
        out["reasons"].append("no walking route between these two stops")
        return out
    out["metres"] = round(r["metres"], 1)

    legs = [x for x in r["legs"] if x["metres"] >= SHORT_LEG_M]
    inner = strip_approach(legs)
    out["approach_m"] = round(
        sum(x["metres"] for x in legs) - sum(x["metres"] for x in inner), 1)
    unnamed = sum(x["metres"] for x in inner
                  if not x["name"] and not x.get("obvious"))
    out["turns"] = max(0, len(legs) - 1)
    out["unnamed_frac"] = round(unnamed / r["metres"], 3) if r["metres"] else 0.0

    # The spine: the one named street the leg mostly runs along, if there is
    # one. This is what makes the margin signal safe to ignore. Told to walk up
    # Borough High Street you cannot end up on Tennis Street by mistake — you
    # are on a street with its name written on it, and the other way round is
    # not a way of getting this wrong, only a different walk somebody could
    # have taken. The signal was written for a warren, where the instruction is
    # "second on the left" and a second way round makes the count meaningless.
    # Grouped by folded name, because OSM carries the riverside path as both
    # "The Queen's Walk" and "The Queens Walk" and they are one street. Kept
    # apart, neither half reached the share and the leg had no spine.
    by_name = {}
    for x in r["legs"]:
        if x["name"]:
            key = streets.fold(x["name"]).replace("'", "").replace("\u2019", "")
            spellings, along = by_name.get(key, ({}, 0.0))
            spellings[x["name"]] = spellings.get(x["name"], 0.0) + x["metres"]
            by_name[key] = (spellings, along + x["metres"])
    if by_name and r["metres"]:
        spellings, along = max(by_name.values(), key=lambda v: v[1])
        out["spine_share"] = round(along / r["metres"], 3)
        if out["spine_share"] >= SPINE_SHARE:
            out["spine"] = max(spellings.items(), key=lambda kv: kv[1])[0]

    # The second-best way round, found by making the best one expensive.
    #
    # The penalty steers the search but cannot invent a street. Where there is
    # genuinely only one way through, the second search is forced back down the
    # same edges and returns the same length — which reads as margin 1.0, the
    # worst possible score, for the most certain situation there is. So the
    # second route only counts as an alternative when it is actually a
    # different route. Anything else means there is one way round, and one way
    # round is the easiest leg to describe, not the hardest.
    mine = town.path_edges(r["path"])
    other = town.route(a, b, avoid=mine)
    if other and r["metres"] > 0:
        theirs = town.path_edges(other["path"])
        shared = len(theirs & mine) / len(theirs) if theirs else 1.0
        if shared <= ALTERNATIVE_SHARE:
            out["margin"] = round(other["metres"] / r["metres"], 3)
        else:
            out["only_way"] = True

    if out["snap_m"] > SNAP_MAX_M:
        out["reasons"].append(
            f"a stop sits {out['snap_m']:.0f} m off the walkable network, so the "
            f"route to it is partly guesswork")
    if out["unnamed_frac"] > UNNAMED_MAX:
        out["reasons"].append(
            f"{out['unnamed_frac'] * 100:.0f}% of the walking is down lanes the "
            f"map has no name for")
    if out["turns"] > TURNS_MAX:
        out["reasons"].append(
            f"{out['turns']} turns, more than anybody follows off a phone")
    if (out["margin"] is not None and out["margin"] < MARGIN_MIN
            and not out["spine"]):
        out["reasons"].append(
            f"there is another way round only {(out['margin'] - 1) * 100:.0f}% "
            f"longer, so which streets you end up on is close to a toss-up")
    elif out["margin"] is not None and out["margin"] < MARGIN_MIN:
        out["notes"].append(
            f"there is another way round only {(out['margin'] - 1) * 100:.0f}% "
            f"longer, but {out['spine']} carries "
            f"{out['spine_share'] * 100:.0f}% of this leg, so naming it is "
            f"enough")

    ours = [(p[0], p[1]) for p in r["path"]]
    if answers is None:
        out["notes"].append(
            "no second opinion on file; run the Fetch route second opinions "
            "workflow")
    else:
        agreed = 0
        for ans in answers:
            if ans.get("error") or not ans.get("line"):
                out["engines"].append({"engine": ans.get("engine", "?"),
                                       "error": ans.get("error", "no geometry")})
                continue
            cmp = agreement(ours, [tuple(p) for p in ans["line"]])
            cmp["engine"] = ans["engine"]
            gap = abs(cmp["their_metres"] - r["metres"])
            ok = (cmp["overlap"] >= AGREE_OVERLAP
                  and (cmp["length_ratio"] <= AGREE_LENGTH
                       or gap <= AGREE_LENGTH_M))
            cmp["agrees"] = ok
            out["engines"].append(cmp)
            agreed += 1 if ok else 0
            if not ok:
                out["reasons"].append(
                    f"{ans['engine']} walks this leg differently: "
                    f"{cmp['overlap'] * 100:.0f}% of the two routes coincide and "
                    f"it makes the leg {cmp['their_metres']:.0f} m against our "
                    f"{r['metres']:.0f} m")
        if not agreed and not out["reasons"]:
            # Every engine failed to answer. That is a bad afternoon on a free
            # server, not a fact about the streets.
            out["notes"].append("no independent engine could be reached for "
                                "this leg, so nothing confirms the route")

    if not out["reasons"]:
        out["verdict"] = "turn_by_turn"
    return out


def score_tour(tour, town=None):
    """Every leg of a tour, in walking order. Keyed by the arriving stop's id."""
    town = town or streets.load(tour["id"])
    if town is None:
        return {}
    answers = load_answers(tour["id"])
    out = {}
    stops = tour["stops"]
    for before, after in zip(stops, stops[1:]):
        a = (before["lat"], before["lon"])
        b = (after["lat"], after["lon"])
        stale = False
        if answers is None:
            got = None
        else:
            got = fresh_answers(answers.get((before["id"], after["id"])), a, b)
            if got is None:
                # Fetched for somewhere else. No answer, not a wrong answer.
                got, stale = [], True
        out[after["id"]] = score_leg(town, a, b, got)
        if stale:
            out[after["id"]]["notes"].append(
                "the second opinion on file was fetched for a different "
                "coordinate; this stop has moved since. Re-run the routes fetch")
    return out


def main():
    args = sys.argv[1:]
    which = args[args.index("--tour") + 1] if "--tour" in args else "all"
    for path in sorted(BASE.glob("content/*/*.json")):
        tour = json.loads(path.read_text(encoding="utf-8"))
        if which not in ("all", tour["id"]):
            continue
        town = streets.load(tour["id"])
        if town is None:
            print(f"{tour['id']}: no map extract")
            continue
        print(f"\n{tour['name']} ({tour['id']})")
        for stop_id, s in score_tour(tour, town).items():
            mark = "OK  " if s["verdict"] == "turn_by_turn" else "ROUGH"
            print(f"  {mark} {stop_id:<16} {s['metres']:.0f} m  "
                  f"{s['turns']} turns  {s['unnamed_frac'] * 100:.0f}% unnamed  "
                  f"margin {s['margin']}  "
                  f"spine {s['spine'] or '-'}")
            for why in s["reasons"]:
                print(f"        - {why}")
            for why in s["notes"]:
                print(f"        ? {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
