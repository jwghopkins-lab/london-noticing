#!/usr/bin/env python3
"""Turn a fetch run into one short evidence file per candidate, for reading.

    python3 pub-quiz/verify/evidence.py <run> <out_dir>

A pub's page can be 60,000 characters of menus and cookie notices. What a
checker needs is every passage that mentions a quiz, every line that looks like
an address, and enough of the page's framing (title, final address, any dates)
to tell a live page from a stale one. Short pages are kept whole.
"""
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUIZ = re.compile(r"quiz|trivia", re.I)
POSTCODE = re.compile(r"\b(?:EC|WC|[NESW]|NW|SE|SW|[A-Z]{1,2})\d[A-Z\d]?\s*\d[A-Z]{2}\b")
YEAR = re.compile(r"\b20(1\d|2\d)\b")
WINDOW = 700
WHOLE = 5000


def windows(text, rx, width):
    spans = []
    for m in rx.finditer(text):
        a, b = max(0, m.start() - width), min(len(text), m.end() + width)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    return [text[a:b] for a, b in spans]


def main(run, out_dir):
    pages = {}
    for p in sorted((ROOT / "data" / "fetched" / run).glob("pages*.json.gz")):
        pages.update(json.loads(gzip.decompress(p.read_bytes())))
    crawl_p = ROOT / "data" / "fetched" / run / "crawl.json"
    crawl = {e["id"]: e for e in json.loads(crawl_p.read_text())["pages"]} if crawl_p.exists() else {}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for cid, plist in pages.items():
        e = crawl.get(cid, {})
        parts = [f"CANDIDATE {cid}: crawled as the website of "
                 f"{e.get('name') or 'an unnamed entry'}" + (f" (OpenStreetMap {', '.join(e['osm'])})" if e.get("osm") else "")]
        quiz_hits = 0
        for p in plist:
            text = p.get("text") or ""
            frames = "\n".join(f"[frame {f['url']}]\n{f['text']}" for f in p.get("frames", []))
            full = text + ("\n" + frames if frames else "")
            head = [f"=== PAGE {p.get('url')}",
                    f"final url: {p.get('final_url')}", f"http status: {p.get('status')}",
                    f"title: {p.get('title')}", f"fetched: {p.get('fetched_at')}",
                    f"followed from another page: {bool(p.get('followed'))}"]
            if p.get("error"):
                head.append(f"ERROR: {p['error']}")
            years = sorted(set(m.group(0) for m in YEAR.finditer(full)))
            head.append(f"years mentioned on page: {', '.join(years) or 'none'}")
            codes = sorted(set(m.group(0) for m in POSTCODE.finditer(full)))[:8]
            head.append(f"postcode-like strings: {', '.join(codes) or 'none'}")
            hits = windows(full, QUIZ, WINDOW)
            quiz_hits += len(hits)
            if len(full) <= WHOLE:
                body = ["--- whole page text ---", full]
            elif hits:
                body = [f"--- {len(hits)} passage(s) mentioning quiz/trivia ---"] + [f"[...]{h}[...]" for h in hits]
            else:
                body = ["--- no mention of quiz or trivia on this page ---"]
            addr = [l.strip() for l in full.splitlines() if POSTCODE.search(l)][:4]
            if addr and len(full) > WHOLE:
                body += ["--- lines with a postcode ---"] + addr
            parts.append("\n".join(head + body))
        (out / f"{cid}.txt").write_text("\n\n".join(parts))
        summary[cid] = {"pages": len(plist), "quiz_passages": quiz_hits,
                        "with_text": sum(1 for p in plist if len(p.get("text") or "") > 200)}
    (out / "_summary.json").write_text(json.dumps(summary, indent=1))
    n = len(summary)
    print(f"{n} candidates; {sum(1 for v in summary.values() if v['quiz_passages'])} have a page mentioning a quiz; "
          f"{sum(1 for v in summary.values() if not v['with_text'])} got no text at all")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
