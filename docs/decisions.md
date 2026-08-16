# Decisions

## 16 Aug 2026 — POC launch

**Repo.** New private repo `london-noticing` under jwghopkins-lab, created by the
user because the session's GitHub App cannot create repositories (403). Develop on
`claude/tour-directions-poc-ngqx8h`.

**Hosting.** Static first: one HTML page plus ten self-contained route JSON
artefacts, served as static files. No backend for the POC. The content pipeline
also emits seed SQL, so a Supabase backend can be added later without rewriting
the builder. Consequence: the builder has two emitters over one content model, and
the JSON emitter is the one the player reads.

**Location gates.** Gate logic ships as built, including the haversine pass rule
and the warm/cold feedback. A development position simulator lets a tester assert
a position without being in London. The simulator must be visibly a development
tool and must not weaken the real pass rule.

**First POC scope.** Vertical slice, three stops. Enough to prove the text reveal,
one location gate through the simulator, and one soft "have you found it yet"
prompt. The three stops should cover all three stop types rather than three of a
kind.

## Open

- Which five topics. Blocks all content.
- `make_editable.py` and `make_review.py` from the Fedora session scratchpad. Not
  committed to Fedora, so they have to come from the user.
