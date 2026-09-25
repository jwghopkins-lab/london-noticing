#!/usr/bin/env python3
"""Merge the two readers' verdicts into the list of confirmed quizzes.

    python3 pub-quiz/verify/accept.py <run> <verdicts.json> [<run> <verdicts.json> ...]

A quiz is accepted only when the first reader confirmed it, the second reader
failed to refute it and read the same start time, and the build's own evidence
check passes on it: the quote is on the fetched page word for word and carries
Tuesday and the start time. Everything else is recorded in status.json with the
reason, so the next update can see what was tried.

Writes pub-quiz/data/quizzes.json (without positions: run locate.py next)
       pub-quiz/data/status.json
"""
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build", ROOT / "build" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def main(pairs):
    accepted, rejected = [], []
    for run, path in pairs:
        crawl_p = ROOT / "data" / "fetched" / run / "crawl.json"
        crawl = {e["id"]: e for e in json.loads(crawl_p.read_text())["pages"]} if crawl_p.exists() else {}
        for batch in json.loads(Path(path).read_text()):
            challenged = {c["id"]: c for c in (batch.get("challenge") or [])}
            for r in batch["read"]:
                cid = r["id"]
                if r["verdict"] != "confirmed":
                    rejected.append({"candidate_id": cid, "run": run, "reason": r["verdict"], "why": r.get("why", "")})
                    continue
                c = challenged.get(cid)
                if batch.get("challenge") is None or c is None:
                    rejected.append({"candidate_id": cid, "run": run, "reason": "not_challenged", "why": "second reader did not report"})
                    continue
                if c["refuted"]:
                    rejected.append({"candidate_id": cid, "run": run, "reason": "refuted", "why": "; ".join(c["problems"])})
                    continue
                if c.get("start_seen") and c["start_seen"] != r.get("start"):
                    rejected.append({"candidate_id": cid, "run": run, "reason": "start_disagrees",
                                     "why": f"first reader {r.get('start')}, second {c['start_seen']}"})
                    continue
                e = crawl.get(cid, {})
                q = {
                    "id": slug(r.get("pub_name")) + "-" + slug((r.get("postcode") or cid)[-8:]),
                    "name": r.get("pub_name") or e.get("name"),
                    "address": r.get("address", ""),
                    "postcode": (r.get("postcode") or "").upper().strip(),
                    "start": r.get("start"),
                    "website": e.get("urls", [r.get("source_url")])[0],
                    "source_url": r.get("source_url"),
                    "source_kind": r.get("source_kind"),
                    "quote": r.get("quote"),
                    "extra_quotes": r.get("extra_quotes") or [],
                    "freq_note": r.get("freq_note", ""),
                    "host": r.get("host", ""),
                    "checked": date.today().isoformat(),
                    "evidence_run": run,
                    "candidate_id": cid,
                    "osm_ids": e.get("osm", []),
                    "area": "-",
                    "lat": 51.5, "lon": -0.1,  # placeholders so check() can run; locate.py sets the real ones
                }
                errs = [x for x in build.check(q) if not x.startswith("position")]
                if errs:
                    rejected.append({"candidate_id": cid, "run": run, "reason": "evidence_check", "why": "; ".join(errs)})
                    continue
                for k in ("area", "lat", "lon"):
                    q.pop(k)
                accepted.append(q)

    # One pub found twice (a seed and its OSM website, say) is kept once.
    seen, unique = {}, []
    for q in accepted:
        key = tuple(q["osm_ids"]) or (build.squash(q["name"]), q["postcode"].replace(" ", ""))
        if key in seen:
            continue
        seen[key] = q
        unique.append(q)
    ids = {}
    for q in unique:
        n = ids.get(q["id"], 0)
        ids[q["id"]] = n + 1
        if n:
            q["id"] += f"-{n + 1}"

    (ROOT / "data" / "quizzes.json").write_text(json.dumps(unique, indent=1, ensure_ascii=False))
    reasons = {}
    for r in rejected:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    status = {"checked": date.today().isoformat(), "confirmed": len(unique), "rejected_by_reason": reasons,
              # Pubs whose own page mentions a Tuesday quiz that was still left off.
              "unconfirmed_count": sum(v for k, v in reasons.items() if k in (
                  "not_weekly", "no_start_time", "ended_or_stale", "unclear", "refuted", "start_disagrees", "evidence_check")),
              "rejected": rejected}
    (ROOT / "data" / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"accepted {len(unique)} ({len(accepted) - len(unique)} duplicates dropped); rejected {json.dumps(reasons)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(list(zip(a[::2], a[1::2])))
