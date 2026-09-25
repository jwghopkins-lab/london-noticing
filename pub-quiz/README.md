# London Tuesday Quizzes

A map of weekly pub quizzes in London on Tuesday nights, with a start-time
filter. Each pin opens the page on the pub's (or its quiz host's) own website
that states the quiz, with the words it says quoted.

This folder is separate from the walks. Nothing in it reads or writes the
walks' content, data, pipeline or published site, and the walks' build does not
look in here. Its one file outside this folder is its own workflow,
`.github/workflows/pub-quiz-fetch.yml`.

## The one rule

**A quiz is only on the map if a first-hand page says so, and the build can
prove it.** First-hand means the pub's own website, the pub company's page for
that pub, or the quiz company's own venue list. Listings sites, articles,
reviews and search results are used to find pubs, never to confirm them.

Every quiz carries a quote copied from that page. `build/build.py` re-reads the
text the runner fetched and refuses to build if a quote is not there word for
word, does not say Tuesday, or does not contain the start time claimed.

Weekly only. Fortnightly, monthly, "first Tuesday", "returning soon" and single
dated events are left off. So is anything outside the Greater London boundary.

## How a quiz gets on

1. **Crawl.** A GitHub runner renders every London pub website in
   OpenStreetMap (2,358 sites) in Chromium, follows up to four what's-on or quiz
   links from each, and keeps the text of any page that mentions a quiz. It also
   fetches the quiz companies' venue lists, pub-company sitemaps, and the pub
   sites that listings sites link to.
2. **Triage.** `verify/triage.py` passes on only pubs with a quiz mentioned
   near a Tuesday. `verify/listings.py` cuts quiz-company lists into one file
   per venue.
3. **Two readers.** `verify/readers.workflow.js` runs a first reader, who
   decides and copies the exact quote, then a second reader, who tries to refute
   it. Both only see the fetched text. Their verdicts are in `data/verdicts/`.
4. **Accept.** `verify/accept.py` keeps a quiz only if the first reader
   confirmed it, the second failed to refute it and read the same start time,
   and the build's evidence check passes. Every rejection is in
   `data/status.json` with its reason.
5. **Place.** `verify/locate.py` puts each quiz on its pub's OpenStreetMap
   point. A shared pub-company website never counts as proof of which pub; a
   name must match; a pub whose name several London pubs share needs a
   postcode. Duplicates merge; clashing times drop both.
6. **Build.** `build/build.py` checks every quote again and writes
   `dist/london-tuesday-quizzes.html`, one self-contained file.

## Layout

    fetch/request.json         what the runner should fetch next (changing it runs the job)
    fetch/fetch_pages.mjs      renders pages in Chromium, keeps text that mentions a quiz
    fetch/make_crawl.py        request + every OSM pub website + sitemaps -> crawl list
    fetch/osm_pubs.py          London's pubs and bars, from Overpass
    fetch/osm_basemap.py       the vector basemap
    fetch/osm_boundary.py      the Greater London outline
    fetch/geocode.py           postcode -> position, via postcodes.io
    data/fetched/<run>/        each run's crawl list, pages and postcodes
    data/osm/                  pubs, basemap (and the slim copy the page carries), boundary
    data/verdicts/             both readers' verdicts, per run
    data/quizzes.json          the confirmed quizzes, with quotes and positions
    data/status.json           counts, and why each candidate was left off
    verify/                    evidence, triage, listings, readers, accept, locate
    build/                     the page template, the build, the basemap slimmer
    dist/london-tuesday-quizzes.html   the built page, published as an artifact

## Why a runner fetches everything

The sandbox this is built in cannot reach pub websites, postcodes.io or any map
server, and web search is capped per session. A GitHub runner can reach them all.

The artifact host will not load map tiles, so the basemap (Thames, parks, main
roads, stations, neighbourhood names) ships inside the page as OpenStreetMap
vectors. For street-level detail each pub has a Directions link.

## Updating it

Run it again with a new run name, so every quiz is re-read from its page today:

1. `fetch/request.json`: `{"run": "r<N>", "shards": 12, "crawl_osm_pubs": true,
   "osm": false, "pages": [...]}`. Put in the pages list: every confirmed quiz's
   `source_url` (to catch quizzes that stopped), the quiz companies' lists, and
   any new leads. Push, and wait for the runner's commit.
2. `python3 verify/evidence.py r<N> <dir>`, `python3 verify/triage.py r<N> <dir>`,
   `python3 verify/listings.py r<N> <dir>`.
3. Run `verify/readers.workflow.js` over the ids in `<dir>/_triage.json` and
   `_listings.json`, and save each result under `data/verdicts/`.
4. `python3 verify/accept.py r<N> <verdicts> ...` (only the new run's verdicts,
   so nothing is carried forward unread), `python3 verify/locate.py`,
   `python3 build/build.py`.
5. Republish `dist/london-tuesday-quizzes.html` to the same artifact URL.

Map data © OpenStreetMap contributors, ODbL.
