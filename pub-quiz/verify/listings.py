#!/usr/bin/env python3
"""Split quiz-company and pub-company listing pages into one evidence file per venue.

    python3 pub-quiz/verify/listings.py <run> <evidence_dir>

A quiz company's own list of the pubs it runs quizzes at is a first-hand
source, and so is a pub company's what's-on page for one of its pubs. But a
reader checks one pub at a time, so a list of twenty venues becomes twenty
files, each with the page's own heading for context and, verbatim, any entry
on the same page that is marked as not weekly (so a reader can see how the
page marks one).

Listings sites (TriviaNearMe, QuizAdvisor, DesignMyNight and the like) are not
first-hand and are not split here: they are only used to find pubs.

Ids are "<hub entry>~<n>", which the build resolves back to the hub's pages.
Appends the new ids to <evidence_dir>/_listings.json.
"""
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TUES = re.compile(r"\btues?(day)?s?\b", re.I)
QUIZ = re.compile(r"quiz|trivia", re.I)

# Hubs whose own pages are first-hand: whose it is, and how its list is laid out.
FIRST_HAND = {
    "hub-bigfatquiz": ("the Big Fat Quiz Company's own list of the pubs where it runs quizzes",
                       re.compile(r"(?=^(?:Fortnightly · )?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) · )", re.M)),
    "hub-compleatquiz": ("Compleat Quiz's own list of the pubs where it runs quizzes",
                         re.compile(r"\nvenue\n")),
    "hub-compleatquiz-all": ("Compleat Quiz's own list of the pubs where it runs quizzes",
                             re.compile(r"\nvenue\n")),
    "hub-questionone": ("Question One's own venue pages and venue list (Question One runs the quizzes)",
                        re.compile(r"(?=^(?:PUB QUIZ – )?[^\n]+\n(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) \d\d:\d\d$)", re.M)),
    "hub-urbanpubs-whatson": ("Urban Pubs & Bars' own what's-on pages for its pubs", None),
}
NOT_WEEKLY = re.compile(r"fortnight|every other|monthly|of the month|of every month|returning soon|returns \d|coming soon|starts \d", re.I)


def main(run, ev_dir):
    d = ROOT / "data" / "fetched" / run
    pages = {}
    for p in sorted(d.glob("pages*.json.gz")):
        pages.update(json.loads(gzip.decompress(p.read_bytes())))
    ev = Path(ev_dir)
    made = []
    for hub, (whose, splitter) in FIRST_HAND.items():
        n = 0
        for page in pages.get(hub, []):
            text = page.get("text") or ""
            if not (QUIZ.search(text) and TUES.search(text)):
                continue
            head = [f"=== PAGE {page['url']}", f"final url: {page.get('final_url')}", f"http status: {page.get('status')}",
                    f"title: {page.get('title')}", f"fetched: {page.get('fetched_at')}",
                    f"about this page: {whose}"]
            blocks = [b.strip() for b in splitter.split(text)] if splitter else [text]
            intro = blocks[0][:600] if splitter else ""
            marked = [b[:160] for b in blocks[1:] if NOT_WEEKLY.search(b[:200])] if splitter else []
            for b in (blocks[1:] if splitter and len(blocks) > 1 else blocks):
                if not (TUES.search(b[:120]) if splitter else TUES.search(b)):
                    continue
                n += 1
                cid = f"{hub}~{n}"
                parts = [f"CANDIDATE {cid}: one venue's entry from {whose}. The pub is the one named in the entry below."]
                parts += head
                if intro:
                    parts += ["--- the page's own heading ---", intro]
                if marked:
                    parts += ["--- other entries on the same page that the page marks as not weekly or not yet running (for context) ---"] + marked
                parts += ["--- this venue's entry ---" if splitter else "--- whole page text ---", b]
                (ev / f"{cid}.txt").write_text("\n".join(parts))
                made.append(cid)
    (ev / "_listings.json").write_text(json.dumps(made, indent=1))
    print(f"{len(made)} venue entries from first-hand listings: " +
          ", ".join(f"{h} {sum(1 for m in made if m.startswith(h + '~'))}" for h in FIRST_HAND))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
