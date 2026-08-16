# london-noticing

A gamified walking tour of central London. No puzzle, no team, no login, no
secrets.

You open a web page, pick 3 topics from a list of 5, and get an 18-stop walking
route: 6 stops per chosen topic. The point is to make you look at something you
have walked past a hundred times and see it differently. Not "I solved it".
"Oh, look at that."

Five topics choose three is exactly ten combinations, so the ten routes map
one-to-one onto the possible picks. Route lookup is a table, not an algorithm.

## Status

Vertical slice. Three stops of one route, covering all three stop types: a
plain stop, a soft-prompt stop, and a location-gated stop. The picker is wired
to all ten combinations; nine of them have no stops written yet.

Screenshots in `docs/shots/`.

## Running it

    python3 pipeline/validate_content.py      # content contracts
    python3 pipeline/bake.py --include-drafts # content -> route artefacts
    python3 pipeline/verify_bakes.py          # independent re-check of the artefacts
    python3 -m unittest discover -s pipeline -p 'test_*.py'

    npx http-server app -p 8080               # then open http://127.0.0.1:8080
    NODE_PATH=$(npm root -g) node pipeline/walk_smoke.cjs

The page must be served over http. Opened straight off the disk it cannot fetch
its own route files, and it will say so rather than looking broken.

## Layout

    content/topics.json   the five topics
    content/stops.json    the stop library: text, coordinates, gates, prompts
    content/routes.json   THE ROUTE LOOKUP. Authoritative.
    pipeline/             combos, geography, the bake harness, the checker, tests
    app/                  the page, plus baked artefacts, deployed as static files
    sql/seed.sql          generated; the backend path, not used by the POC
    docs/decisions.md     what was decided and why

## Rules of the build

**The route lookup is authoritative.** It fixes which 18 stops a combination
gets and the order they are walked in. Nothing scores, ranks or reorders them.
An earlier design scored six stops per topic and then looked up an authored
order, and every route failed its checks because the scoring picked a different
six from the one the order was written for.

**Artefacts are self-contained.** The phone on the walk may have no signal, so
each route file carries every word, coordinate and prompt it needs. Once a route
has loaded it is kept on the phone.

**Verification is separate from generation.** `verify_bakes.py` imports nothing
from `bake.py` and re-derives everything from the content files, including a
second implementation of the distance formula. A generator that grades itself
grades itself generously.

**Roughly four stops per route are gated.** A walk that is nothing but check-ins
is a chore. The gate never says no: it reports warm or cold, because a phone in
a courtyard can be a hundred metres out, and refusing somebody who is standing
right there is worse than having no gate at all.

**Everything is written to be spoken.** Short sentences, one idea each, nothing
that only works on a screen, and a separate `*_spoken` field wherever dates and
numbers need saying differently. Stop ids are stable forever so audio can be
attached to them later. The audio itself is not built.

## Lineage

The player UI, the location gate and its permission pre-flight, the word-by-word
reveal and the card arrival animation were copied once from the Fedora project
and then diverged. Its team codes, login, deny-all row level security, lives,
guess limits, leaderboard and collect mode were all stripped: that product had
answers to hide and this one has nothing to hide at all.

The bake harness posture came from the Trivium tour-kit extract. Its topic
picker and its scoring were not reused, because with five fixed topics and a
user who picks three there is no rotation problem and nothing to rank.

No shared code, no shared database, no imports from either at runtime.
