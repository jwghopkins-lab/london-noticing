# London Tuesday Quizzes

A map of pub quizzes in London on Tuesday nights, with a start-time filter.
Each pub on it links to the page on its own website that states the quiz.

This folder is separate from the walks. Nothing in it reads or writes the
walks' content, data, pipeline or published site, and the walks' build does not
look in here.

## The one rule

**A quiz is only on the map if a first-hand page says so, and the build can
prove it.** First-hand means the pub's own website, the pub company's page for
that pub, or the quiz host's own venue list. Listings sites, articles, reviews
and search snippets are used to find pubs, never to confirm them.

Each quiz carries a quote copied from that page. `build/build.py` re-reads the
page text the runner fetched and refuses to build if any quote is not there word
for word, does not say Tuesday, or does not contain the start time claimed.

Weekly only. A quiz that runs fortnightly, monthly or "most Tuesdays" is left
off, because a map that sends you on the wrong week is worse than no map.

## Layout

    fetch/request.json        what the runner should fetch next
    fetch/fetch_pages.mjs     renders each page in Chromium, keeps its text
    fetch/geocode.py          postcode -> position, via postcodes.io
    fetch/osm_london.py       London's pubs and the vector basemap, via Overpass
    data/fetched/<run>/       what came back from each run
    data/osm/                 pubs.json and basemap.json
    data/candidates.json      every pub the search found, confirmed or not
    data/quizzes.json         the confirmed quizzes, with their quotes
    data/status.json          counts, and why each candidate was left off
    verify/evidence.py        one short evidence file per candidate
    verify/locate.py          picks each pub's position
    build/page.html           the page
    build/build.py            checks the evidence and builds the page
    dist/london-tuesday-quizzes.html   the built page, published as an artifact

## Why a runner fetches everything

The sandbox this is built in cannot reach pub websites, postcodes.io or any
map server. A GitHub runner can. Changing `fetch/request.json` on this branch
runs `.github/workflows/pub-quiz-fetch.yml`, which fetches what the request lists
and commits the results under `data/`.

The artifact host will not load map tiles, so the basemap (Thames, parks, main
roads, stations, neighbourhood names) is drawn from OpenStreetMap vectors
shipped inside the page. For street-level detail, each pub has a Directions
link.

## Updating it

1. Search for new candidates, and add them to `data/candidates.json`.
2. Put every candidate's pages (the confirmed ones too, to catch quizzes that
   have stopped) in `fetch/request.json` under a new `run` name, push, and wait
   for the runner's commit.
3. `python3 verify/evidence.py <run> <dir>`, then check each candidate against
   its evidence file: two independent readers, and it goes on only if both
   agree on Tuesday, weekly and the start time.
4. `python3 verify/locate.py`, then `python3 build/build.py`.
5. Republish `dist/london-tuesday-quizzes.html` to the same artifact URL.

Map data © OpenStreetMap contributors, ODbL.
