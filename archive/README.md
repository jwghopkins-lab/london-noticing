# Archived walks

Frozen, not deleted. Nothing in here is built, checked or tested by the normal
pipeline any more, and none of it will pick up later changes to the player.

**Every published page stays up.** The builds under `app/` and `dist/` are
committed, self-contained files, so the workflow carries them through to the
site without rebuilding them. Archiving stops maintenance; it does not break
anybody's link.

| Walk | Archived | URL still live |
|---|---|---|
| The Amber Mile, Gdansk | Aug 2026 | `/gdansk/` |
| The Gunpowder Mile, Gdansk | Aug 2026 | `/gunpowder-mile/` |
| London Noticing (topic picker, 10 routes) | Aug 2026 | `/` and `/download/london-noticing.html` |
| Two White Eagles, Saint-Antonin-Noble-Val | Sep 2026 | `/noble-val/` |
| Built in One Go, Cordes-sur-Ciel | Sep 2026 | `/cordes/` |
| Half the Town, Castres | Sep 2026 | `/castres/` |

## gdansk/

Two walk JSONs. `build_tour.py` globs `content/*/*.json`, so moving them here
was the whole job. To bring one back, move it to `content/<town>/` and build. It
will be held to whatever the house style requires by then, which is the point of
taking it out rather than leaving it in.

## france/

Three walks in the Tarn, written Aug and Sep 2026: Saint-Antonin-Noble-Val,
Cordes-sur-Ciel and Castres. Same job as `gdansk/` — the JSONs moved out of
`content/`, which is the whole of it, because `build_tour.py` globs
`content/*/*.json`.

Their map extracts, routing second opinions and elevation are still under
`data/`, so any of them can be brought back by moving one file and rebuilding,
with no fetching. It would then be held to whatever the house style requires by
then, which is the point.

They are where a good deal of the checker came from: the street name with a word
before its prefix, the two causes for a leg the map cannot describe, the clue
that said the same thing twice, the plaque the extract threw the evidence away
for. Those tests and rules keep their worked examples, because the example is
the reasoning.

## london/

London was not one walk but a different machine: five topics, pick any three,
ten pre-authored routes, a baker, an independent verifier and a seed-SQL
emitter. All of it is here, content and code together, with its own tests.

It still runs from where it sits:

```
python3 archive/london/validate_content.py
python3 archive/london/bake.py --include-drafts
python3 archive/london/verify_bakes.py
python3 archive/london/build_standalone.py
python3 -m unittest discover -s archive/london -p 'test_*.py'
```

That was checked on the day it was archived, and it reproduced the committed
artefacts byte for byte. `walk_smoke.cjs` needs a server on the app directory
(`python3 -m http.server 8080 --directory app`).

It still borrows `pipeline/geo.py` for distances and gates, so the live gate
rule and the archived one cannot drift apart.

## What these are worth keeping for

Every rule in `docs/house-style.md` came off one of these walks. The walks are
superseded; the rules are not.
