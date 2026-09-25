#!/usr/bin/env python3
"""Build the London Tuesday quiz map into one self-contained HTML file.

    python3 pub-quiz/build/build.py

Reads   pub-quiz/data/quizzes.json      the confirmed quizzes
        pub-quiz/data/osm/basemap.json  the vector basemap
        pub-quiz/data/fetched/<run>/    the pages each quiz was confirmed on
Writes  pub-quiz/dist/london-tuesday-quizzes.html

The build refuses to ship a quiz it cannot re-check. Every quiz must carry a
quote, and that quote must appear word for word in the text the runner fetched
from the quiz's source page, and it must name Tuesday, and the start time it
claims must be in it. A quiz typed in by hand, or remembered from a listings
site, has no fetched page behind it and fails.
"""
import gzip
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "dist" / "london-tuesday-quizzes.html"
LONDON = (51.28, 51.70, -0.52, 0.34)
SOURCE_KINDS = {"pub", "company", "host"}


def squash(s):
    """Compare text the way a reader would: case, spacing and quote marks aside."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def time_forms(hhmm):
    """Every way a page might write a start time, e.g. 19:30 -> 7.30pm, 7:30 pm, 19:30."""
    h, m = map(int, hhmm.split(":"))
    h12 = (h + 11) % 12 + 1
    forms = {f"{h:02d}:{m:02d}", f"{h}:{m:02d}", f"{h:02d}.{m:02d}", f"{h}.{m:02d}", f"{h:02d}{m:02d}"}
    for sep in (":", "."):
        mm = f"{sep}{m:02d}" if m else ""
        for suf in ("pm", " pm", "p.m.", " p.m."):
            forms.add(f"{h12}{mm}{suf}")
        if m == 0:
            forms.add(f"{h12}{sep}00pm")
            forms.add(f"{h12}{sep}00 pm")
    if m:
        forms.update({f"{h12}:{m:02d}", f"{h12}.{m:02d}"})
    if m == 30:
        forms.add(f"half {h12}")
        forms.add(f"half past {h12}")
    return forms


def load_pages(run, cache={}):
    """A run's pages, merged across the shards it was fetched in."""
    if run not in cache:
        files = sorted((DATA / "fetched" / run).glob("pages*.json.gz"))
        merged = {}
        for p in files:
            merged.update(json.loads(gzip.decompress(p.read_bytes())))
        cache[run] = merged if files else None
    return cache[run]


def evidence_text(q):
    pages = load_pages(q["evidence_run"])
    if pages is None:
        return None
    texts = []
    # A listing page's venues are checked one by one as "<entry>~<n>"; a pub
    # site reached from a listing is an entry of its own, "<entry>~ext<n>".
    cid = q["candidate_id"]
    for page in pages.get(cid, pages.get(cid.split("~")[0], [])):
        if q["source_url"] in (page.get("url"), page.get("final_url")):
            texts.append(page.get("text") or "")
            texts.extend(f.get("text", "") for f in page.get("frames", []))
    return squash("\n".join(texts)) if texts else None


def check(q):
    errs = []
    for f in ("id", "name", "area", "start", "lat", "lon", "website", "source_url",
              "source_kind", "quote", "checked", "evidence_run", "candidate_id"):
        if q.get(f) in (None, ""):
            errs.append(f"missing {f}")
    if errs:
        return errs
    if not re.fullmatch(r"(1[5-9]|2[0-3]):[0-5]\d", q["start"]):
        errs.append(f"start {q['start']!r} is not an evening HH:MM")
    if not (LONDON[0] <= q["lat"] <= LONDON[1] and LONDON[2] <= q["lon"] <= LONDON[3]):
        errs.append("position is outside London")
    for f in ("website", "source_url"):
        if not q[f].startswith(("https://", "http://")):
            errs.append(f"{f} is not a web address")
    if q["source_kind"] not in SOURCE_KINDS:
        errs.append(f"source_kind must be one of {sorted(SOURCE_KINDS)}")
    text = evidence_text(q)
    if text is None:
        errs.append(f"no fetched page for {q['source_url']} in run {q['evidence_run']}")
        return errs
    quotes = [q["quote"]] + q.get("extra_quotes", [])
    for s in quotes:
        if squash(s) not in text:
            errs.append(f"quote not found word for word on the fetched page: {s!r}")
    joined = squash(" ".join(quotes))
    if not re.search(r"\btues?(day)?s?\b", joined):
        errs.append("the quoted words do not say Tuesday")
    if not any(f in joined for f in time_forms(q["start"])):
        errs.append(f"the quoted words do not give the start time {q['start']}")
    return errs


def main():
    quizzes = json.loads((DATA / "quizzes.json").read_text())
    failed = 0
    ids = set()
    for q in quizzes:
        errs = check(q)
        if q.get("id") in ids:
            errs.append("duplicate id")
        ids.add(q.get("id"))
        if errs:
            failed += 1
            print(f"FAIL {q.get('id')}: " + "; ".join(errs))
    if failed:
        sys.exit(f"{failed} of {len(quizzes)} quizzes failed the evidence check; nothing built")

    public = [{k: q[k] for k in ("id", "name", "area", "address", "postcode", "start", "lat", "lon",
                                 "website", "source_url", "source_kind", "quote", "extra_quotes", "checked", "host",
                                 "freq_note", "location_source") if q.get(k) not in (None, "")}
              for q in quizzes]
    status_p = DATA / "status.json"
    status = json.loads(status_p.read_text()) if status_p.exists() else {}
    crawled = set()
    for c in (DATA / "fetched").glob("*/crawl.json"):
        crawled |= {e["id"] for e in json.loads(c.read_text())["pages"] if e["id"].startswith("osm-")}
    meta = {"checked": max(q["checked"] for q in quizzes),
            "crawled": len(crawled),
            "read": status.get("read_count", 0),
            "no_time": status.get("rejected_by_reason", {}).get("no_start_time", 0),
            "built": date.today().isoformat()}
    basemap = json.loads((DATA / "osm" / "basemap-slim.json").read_text())

    def js(o):
        return json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    page = (ROOT / "build" / "page.html").read_text()
    page = page.replace("__LEAFLET_CSS__", (ROOT / "build" / "vendor" / "leaflet-1.9.4.css").read_text())
    page = page.replace("__QUIZZES__", js(public)).replace("__BASEMAP__", js(basemap)).replace("__META__", js(meta))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    print(f"built {OUT.relative_to(ROOT.parent)}: {len(public)} quizzes, {OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
