#!/usr/bin/env python3
"""Sort a crawl into what needs reading and what does not.

    python3 pub-quiz/verify/triage.py <run> <evidence_dir>

A pub goes forward for reading only if one of its fetched pages mentions a quiz
with a Tuesday within a few hundred characters of it. This is deliberately
loose: it is there to spare readers two thousand pubs with no quiz at all, not
to decide anything. Deciding is the readers' job, and then the build's.

Writes <evidence_dir>/_triage.json:
    read      entries to read: id, pub name from the crawl, OSM ids, pages
    hubs      listing and quiz-host pages, kept whole, for finding more pubs
    counts    how many fell where
"""
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUIZ = re.compile(r"quiz|trivia", re.I)
TUES = re.compile(r"\btues?(day)?s?\b", re.I)
NEAR = 450


def near(text):
    for m in QUIZ.finditer(text):
        if TUES.search(text[max(0, m.start() - NEAR): m.end() + NEAR]):
            return True
    return False


def main(run, ev_dir):
    d = ROOT / "data" / "fetched" / run
    pages = {}
    for p in sorted(d.glob("pages*.json.gz")):
        pages.update(json.loads(gzip.decompress(p.read_bytes())))
    crawl = {e["id"]: e for e in json.loads((d / "crawl.json").read_text())["pages"]} if (d / "crawl.json").exists() else {}
    read, hubs = [], []
    counts = {"entries": len(pages), "no_text": 0, "no_quiz": 0, "quiz_not_tuesday": 0, "to_read": 0, "blocked": 0}
    for cid, plist in pages.items():
        e = crawl.get(cid, {})
        if e.get("keep") == "all":
            hubs.append(cid)
            continue
        texts = [(p.get("text") or "") + "\n" + "\n".join(f.get("text", "") for f in p.get("frames", [])) for p in plist]
        if any(p.get("status") == "blocked" for p in plist):
            counts["blocked"] += 1
        if not any(p.get("chars") or p.get("text") for p in plist):
            counts["no_text"] += 1
        elif not any(p.get("has_quiz") for p in plist):
            counts["no_quiz"] += 1
        elif not any(near(t) for t in texts):
            counts["quiz_not_tuesday"] += 1
        else:
            counts["to_read"] += 1
            read.append({"id": cid, "crawl_name": e.get("name"), "osm": e.get("osm", []),
                         "urls": [p["url"] for p in plist if p.get("has_quiz")]})
    Path(ev_dir, "_triage.json").write_text(json.dumps({"read": read, "hubs": hubs, "counts": counts}, indent=1))
    print(json.dumps(counts))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
