---
name: tour-authoring
description: Build a walking tour for a town from scratch — pick the insights, place the stops from real map data, write directions the map can actually support, and get it through the checks. Use when asked to make a walk, a tour or a trail for any place, or to fix directions on an existing one.
---

# Authoring a walk

A walk is seven or so stops, each one a thing worth standing in front of, joined
by directions that are true. Everything hard about it is in that last clause.

The rules live in `docs/house-style.md`. This is the order to do things in.
Where the two disagree, the house style wins: it is the one the build enforces.

## The one idea to hold on to

**Nothing goes in a walk because it sounded right. It goes in because something
checked it.** Coordinates come from the map extract, not from memory. Distances
come from routing along the streets, not from a straight line times a fudge
factor. Compass bearings are compared against the street they are attached to.
And whether a leg may be given as a sequence of turns at all is decided by a
score, not by how confident the sentence feels.

Every check in `pipeline/build_tour.py` exists because something shipped without
it and a walker found it. The comments say which. Do not remove one to get a
build through.

## 0. Before writing a word: get the map

Create `content/<town>/<walk-id>.json` with `id`, `name`, `city`, `topics`, and
a `contract` block:

```json
"contract": {"n_stops": 7, "topic_split": [3, 2, 2], "question_stops": 4,
             "location_gates": 3, "bbox": [44.145, 44.158, 1.748, 1.765]}
```

`bbox` is `[lat_lo, lat_hi, lon_lo, lon_hi]` round the walkable area. Everything
downstream keys off it, so a walk in any town anywhere needs no other setup.

Then run the **Fetch map data** workflow (`.github/workflows/osm.yml`). It runs
on a GitHub runner because this sandbox cannot reach any map host, and commits
what it gets. Pull before writing.

A brand new town has no content file yet, and cannot have one, because the stops
come out of the extract. So pass the box straight to the workflow instead:

    tour: cordes-sur-ciel
    what: both
    bbox: 44.0580,44.0710,1.9430,1.9640
    city: Cordes-sur-Ciel

`what: both` fetches the streets and the height of the ground. The route second
opinions are skipped, because there are no stops yet to route between; come back
for those at step 3. Write the same box into the tour's `contract.bbox` so a
later refetch reproduces the same extract.

Explore it before choosing anything:

```
python3 pipeline/streets.py --tour <walk-id> --find "Maison Romane"
python3 pipeline/streets.py --tour <walk-id> --near 44.1504 1.7551
```

The extract knows every street name, and every shop, church, bridge and
fountain OSM has a name for. It is a better guide to what is actually there
than any amount of recall, and it will contradict you. Let it.

## 1. Fifteen insights, then seven

Gather far more than you need — about fifteen — then pick on four tests:

- **Interesting**: it changes how the place looks once you know it.
- **Coherent**: the seven together tell one story, not seven.
- **Findable**: at least three stops need a real answer a walker can read off
  the thing itself. Not a fact you would have to already know.
- **Standable**: at least three want a location gate, so the walk knows you got
  there. A gate and a question can share a stop.

Verify the physical detail before you write a question about it. A miscounted
carving makes the stop unanswerable and there is no recovering from it on the
day. Where a detail cannot be confirmed, ask something else or make it a gate.

## 2. Place the stops, and settle the order on the profile

Take every coordinate from `--find` or `--near`, never by eye, and record
`"coord_source": "osm"`.

In a hill town, decide the ORDER before writing a word of prose:

```
python3 pipeline/terrain.py --tour <walk-id>
```

What matters is not ascent but **reclimb** — ascent minus the net gain — the
metres you gained, gave away and gained again. Cordes runs 277 m up over a
283 m summit and down to 251 m: nine metres of ascent, nine of reclimb, and
every leg but one is a single named stretch of one street. Six candidate orders
were scored before one was written. Reordering seven stops is free; rewriting
seven legs is not.

Over 20 m of reclimb is a note. Over 50 m fails the build.

## 2b. Coordinates

When the Noble Val stops were placed by eye they were out by up to a hundred
metres, and the tightened gates would have refused three walkers standing in
exactly the right place.

Also make sure the walk does not double back and no leg is long enough to be
boring. `python3 pipeline/build_tour.py` reports both.

A short walk is not a failure. Cordes is 381 m because the upper town is 250 m
long. Padding it would have meant descending the hill and climbing back up.

## 3. Ask the other engines

Now that the stops exist, run the same workflow with `what: routes`. It asks
OSRM and Valhalla to walk each leg and commits their answers to
`data/routes/<walk-id>.json`. Then:

```
python3 pipeline/confidence.py --tour <walk-id>
```

That prints, per leg, `OK` or `ROUGH` and why. **Read it before writing any
directions.** It tells you which legs you are allowed to describe as turns.

## 4. Write each leg in the mode you were given

**turn_by_turn** — name the streets in the order you walk them, say which way
each runs, give one rounded distance for the whole leg, and start by naming
where you are setting off from.

> From Place du Bessarel, walk east along the square to the far end and pick up
> Rue du Pont des Vierges, which runs north east.

**rough** — a heading and a landmark. Five parts, in the JSON:

```json
"directions_mode": "rough",
"directions": "From Place du Bessarel, head east. About a hundred and fifty metres, all of it in narrow lanes.",
"directions_streets": ["Rue du Pont des Vierges", "Rue Amélie Galup", "Rue du Cluzel"],
"directions_target": "a street sign for Rue Guilhem Peyre"
```

The builder assembles the shipped text and adds the standard caveat. Do not
write your own version of it.

Rough is not the booby prize. It is what somebody who knows the town says, and
it cannot be wrong in the way a turn sequence can be wrong, because it does not
claim the thing that turns out to be false.

## 5. Write the stop

One block that walks you there, says what to look at and asks. Then one thing to
do. Then one block explaining the answer.

Brief. It is read standing up, often in the sun. 80 words for what to look at,
130 for the explainer, and aim well under both. Lead with the answer, then the
story.

No riddle furniture. This is a tour guide, not a treasure hunt — "there is a
painting of that story on the wall", never "somewhere in here is a painting, go
and find it". The player was copied out of a puzzle project where withholding
the answer *was* the product; here the product is showing somebody a thing.

No summing up. Say it once and stop.

## 6. Answers and gates

List every form a phone keyboard produces: plural, singular, the local language,
the digit **and** the word. Nobody types a digit. `pipeline/check_answers.cjs`
checks the whole matrix against the shipped matcher, including one-character
typos, and it exists because a published build once rejected the word "two" at a
stop whose answer was two.

Size each gate radius to the thing. A bridge is not a doorway. Every gate carries
a pass button: a walk that dead-ends because a phone could not get a fix is worse
than one somebody skipped a check on.

## 7. Build until it is quiet

```
python3 pipeline/build_tour.py                     # the contract and the map
node pipeline/check_answers.cjs                    # every answer round-trips
NODE_PATH=$(npm root -g) node pipeline/tour_smoke.cjs   # the walk, end to end
python3 -m unittest discover -s pipeline -p 'test_*.py'
```

Errors stop the build; notes are advice. Push to the branch and the Pages
workflow serves it at `/<served_at>/`.

## When a check fires

| It says | What is actually wrong |
|---|---|
| *does not support turn-by-turn* | The map cannot carry a turn sequence here. Rewrite as rough; do not argue with the score. |
| *says X runs south east, but on this leg it runs north east* | A bearing welded onto the wrong street. This is the exact bug that started all of it. |
| *names X, which is not on the way* | You sent somebody down a street this leg never touches. |
| *names X out of order* | Right streets, wrong sequence. |
| *the directions add up to N m but the streets route in M* | One of the two is stale — usually the prose, occasionally the coordinate. |
| *never say where you are setting off from* | The first sentence has an origin phrase but names nothing. "Leave the square on the far side from the bridge" is not an origin. |
| *no street called X* | You invented it, or spelled it the way it sounds. |
| *the map spells it Y* | Accents. The sign has them. |
| *N m from the nearest walkable way* | The coordinate is in a field, or in the wrong place entirely. |
| *climbs N m it had already climbed once* | Reorder the stops. Do not rewrite the prose first. |

## Things that were got wrong, so you do not have to

- A stop placed by eye, then a compass bearing written to match the guess. Both
  wrong the same way, so nothing could catch it, and a walker was sent east to
  somewhere north west. Hence `coord_source` and the bearing check.
- A gate that opened from fifty metres away round a corner, because the phone's
  own claimed accuracy was subtracted in full. A phone that says it is unsure
  should not thereby be trusted further.
- Routing from the nearest drawn node, which quietly deleted forty metres of
  bridge from the first leg.
- "Most of the shops along here are brocante" — written because it felt true.
  The map knows three antique shops in that town and none of them is on that
  street. It is on the next one, and it is now named on the stop it belongs to.
- Two Overpass fetches thrown away and reported as success, because `git add`
  on three directories fails entirely when one of them does not exist yet.
- A street name with a word before the prefix. `Grand Rue Raymond VII` is the
  main street of Cordes and the checker called it invented, six times, until the
  mention was allowed to start one word earlier.
