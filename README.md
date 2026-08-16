# london-noticing

A gamified walking tour of central London. No puzzle, no team, no login, no secrets.

You open a web page, pick 3 topics from a list of 5, and get an 18-stop walking
route: 6 stops per chosen topic. The point is to make you look at something you
have walked past a hundred times and see it differently.

5 topics choose 3 gives exactly 10 combinations, so the 10 routes map one-to-one
onto the possible choices. Route lookup is a table, not an algorithm.

## Status

Research only. No product code yet. See `research/topic-proposals.md`.

## Rules of the build

- The route lookup is authoritative. It fixes which 18 stops and their order.
  Nothing scores or reorders them.
- Route artefacts are self-contained. The phone on the walk may have no signal.
- Verification is separate from generation. A generator that grades itself
  grades itself generously.
- Roughly 4 stops per route are location-gated. The rest are not.
- Every piece of text is written to be spoken aloud. Short sentences, one idea
  each, nothing that only works on a screen. Stop ids stay stable so audio can
  be attached later.

## Lineage

Player UI and content pipeline copied once from the Fedora project, then
diverged. Route-baking posture borrowed from the Trivium tour-kit extract.
No shared code, no shared database, no imports from either at runtime.
