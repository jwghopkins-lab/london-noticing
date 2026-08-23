# london-noticing

Self-contained walking tours. You open a web page and get a walk: a handful of
stops, each one a thing worth standing in front of, with directions between them
that are true. No login, no signal needed, no team, no secrets.

The point is to make somebody look at a thing they have walked past and see it
differently. Not "I solved it". "Oh, look at that."

## Where the rules are

Two files, and they are the actual product now — the walks are what falls out of
them.

    docs/house-style.md                    56 numbered rules. The ones marked
                                           [checked] fail the build.
    .claude/skills/tour-authoring/SKILL.md the method: what order to do things in
                                           when building a walk for a new town.

Every rule came off a real complaint from somebody on a real walk. The comments
in `pipeline/build_tour.py` say which rule each check enforces and what shipped
without it.

## Live walks

| Walk | Where | Built from |
|---|---|---|
| Two White Eagles | `/noble-val/` | `content/saint-antonin/two-white-eagles.json` |

Archived, links still live: two Gdansk walks at `/gdansk/` and
`/gunpowder-mile/`, and the London topic picker at `/`. See `archive/README.md`.

## Running it

    python3 pipeline/build_tour.py                   # the contract and the map
    node pipeline/check_answers.cjs                  # every answer round-trips
    python3 -m unittest discover -s pipeline -p 'test_*.py'
    NODE_PATH=$(npm root -g) node pipeline/tour_smoke.cjs   # the walk, end to end

    python3 pipeline/confidence.py --tour <id>       # can this leg be given as turns?
    python3 pipeline/streets.py --tour <id> --find "Maison Romane"
    python3 pipeline/streets.py --tour <id> --near 44.1504 1.7551

Map data is fetched by the **Fetch map data** workflow, on a GitHub runner,
because this sandbox cannot reach any map host. It commits the results, so the
build and the author work from the same files offline for ever.

## Layout

    content/<town>/<walk>.json  a walk: stops, text, coordinates, gates, answers
    data/osm/<walk>.json        the street graph and named places, from Overpass
    data/routes/<walk>.json     what OSRM and Valhalla make of each leg
    pipeline/                   the builder, the checks, the router, the tests
    app/                        the player, plus the built pages
    dist/                       single-file builds, for handing to a phone
    docs/house-style.md         the rules
    docs/decisions.md           what was decided and why
    archive/                    frozen walks, still published, no longer built

## Rules of the build

**The map decides, not the author.** Coordinates come out of the OSM extract.
Distances come from routing along the streets. A compass bearing next to a
street name is checked against that street's heading on that leg. And whether a
leg may be written as a sequence of turns at all is a score, not a judgement:
`pipeline/confidence.py` weighs what two independent routing engines make of it,
whether there is a second way round of much the same length, how much of the
walking is down nameless lanes, how many turns there are, and how far the ends
sit off the network. A leg that fails is written as a heading and a landmark
instead, and the build refuses to ship it any other way.

**Artefacts are self-contained.** The phone on the walk may have no signal, so
each walk file carries every word, coordinate and prompt it needs.

**Verification is separate from generation.** The checker re-derives everything
from the source, with its own implementation of the distance formula. A
generator that grades itself grades itself generously.

**Every check is proved by breaking it.** A check nobody has ever seen fire is a
check that does not work. Two were found silently doing nothing that way.

**A gate cannot be talked out of it.** The ones that are gated on position have
no bypass in the shipped page. But the gate never says no, only warm or cold,
because a phone in a courtyard can be a hundred metres out, and it refuses any
fix worse than 75 m outright rather than pretending to know.

**Testing a gate from somewhere else** uses an approach simulator that simulates
walking rather than arriving. It is off unless asked for, by `?testing=1` in the
address or five taps on the wordmark, and it is never written to storage, so it
cannot follow you onto the street.

**Everything is written to be spoken.** Short sentences, one idea each, nothing
that only works on a screen, and a separate `*_spoken` field wherever dates and
numbers need saying differently. Stop ids are stable for ever so audio can be
attached later. The audio itself is not built.

## Lineage

The player UI, the location gate and its permission pre-flight, the word-by-word
reveal and the card arrival animation were copied once from the Fedora project
and then diverged. Its team codes, login, deny-all row level security, lives,
guess limits, leaderboard and collect mode were all stripped: that product had
answers to hide and this one has nothing to hide at all.

The bake harness posture came from the Trivium tour-kit extract. Its topic
picker and its scoring were not reused.

No shared code, no shared database, no imports from either at runtime.
