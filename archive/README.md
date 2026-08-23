# Archived walks

Frozen, not deleted. Content in here is out of the build: `build_tour.py` globs
`content/*/*.json`, so nothing under `archive/` is checked, baked or tested any
more, and these walks will not pick up later changes to the player.

**The published pages stay up.** `app/gdansk/index.html` and
`app/gunpowder-mile/index.html` are committed, self-contained builds, so the
links already handed out keep working exactly as they were on the day they were
archived. Archiving stops maintenance; it does not break anybody's link.

| Walk | Archived | URL still live |
|---|---|---|
| The Amber Mile, Gdansk | Aug 2026 | `/gdansk/` |
| The Gunpowder Mile, Gdansk | Aug 2026 | `/gunpowder-mile/` |

To bring one back, move its JSON to `content/<town>/` and run
`python3 pipeline/build_tour.py`. It will be held to whatever the house style
requires by then, which is the point of taking it out rather than leaving it in.

## What these two are worth keeping for

Every rule in `docs/house-style.md` came off one of these walks or off Noble
Val. The walks themselves are superseded; the rules are not.
