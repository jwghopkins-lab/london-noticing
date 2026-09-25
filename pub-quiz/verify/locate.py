#!/usr/bin/env python3
"""Give every confirmed quiz a position on the map.

    python3 pub-quiz/verify/locate.py

Prefers the pub's own point in OpenStreetMap, which is usually on the building.
A pub counts as matched when an OSM pub or bar within MAX_M of the quiz's
postcode has much the same name, or links to the same website. Otherwise the
postcode's centre is used; a London postcode covers a handful of addresses, so
that is rarely more than a street's width out. A quiz with neither is not
placed, and the build will refuse it.
"""
import difflib
import glob
import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MAX_M = 350


def norm(s):
    s = (s or "").lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|ye olde|ye) ", "", s.strip())
    s = re.sub(r"\b(pub|bar|tavern|inn|pub and kitchen|and kitchen|freehouse|free house|london)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def domain(u):
    try:
        h = urlparse(u if "://" in u else "https://" + u).hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


SHARED = {"fullers.co.uk", "youngs.co.uk", "greeneking.co.uk", "greeneking-pubs.co.uk", "nicholsonspubs.co.uk",
          "taylor-walker.co.uk", "antic-london.com", "craftbeerco.com", "facebook.com", "instagram.com",
          "stonegatepubs.com", "shepherdneame.co.uk", "thebigfatquiz.com", "designmynight.com", "linktr.ee"}


def metres(a, b):
    dy = (a[0] - b[0]) * 111320
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians(51.5))
    return math.hypot(dx, dy)


def postcodes():
    out = {}
    for p in sorted(glob.glob(str(DATA / "fetched" / "*" / "postcodes.json"))):
        for k, v in json.loads(Path(p).read_text()).items():
            if v:
                out[k.replace(" ", "").upper()] = v
    return out


def main():
    quizzes = json.loads((DATA / "quizzes.json").read_text())
    pubs = json.loads((DATA / "osm" / "pubs.json").read_text())
    pcs = postcodes()
    placed = {"osm": 0, "postcode": 0, "none": 0}
    for q in quizzes:
        pc = pcs.get((q.get("postcode") or "").replace(" ", "").upper())
        centre = (pc["lat"], pc["lon"]) if pc else None
        qd = domain(q.get("website", ""))
        qn = norm(q["name"])
        best = None
        for p in pubs:
            pos = (p["lat"], p["lon"])
            d = metres(centre, pos) if centre else None
            if d is not None and d > MAX_M:
                continue
            sim = max(difflib.SequenceMatcher(None, qn, norm(p.get(k))).ratio()
                      for k in ("name", "alt_name", "old_name") if p.get(k)) if p.get("name") else 0
            pd = domain(p.get("website") or p.get("contact:website") or p.get("url") or "")
            same_site = bool(qd and pd and qd == pd and qd not in SHARED)
            if not (sim >= 0.82 or same_site):
                continue
            if d is None and not same_site:
                continue  # without a postcode, only a shared website is proof enough
            score = sim + (0.5 if same_site else 0) - (d or 0) / 2000
            if not best or score > best[0]:
                best = (score, p, d)
        if best:
            _, p, d = best
            q.update(lat=p["lat"], lon=p["lon"], location_source="osm", osm=p["osm"])
            if d is not None:
                q["osm_to_postcode_m"] = round(d)
            placed["osm"] += 1
        elif centre:
            q.update(lat=round(centre[0], 5), lon=round(centre[1], 5), location_source="postcode")
            q.pop("osm", None)
            placed["postcode"] += 1
        else:
            for k in ("lat", "lon", "location_source", "osm"):
                q.pop(k, None)
            placed["none"] += 1
            print(f"cannot place {q['id']}: no usable postcode and no OSM match")
    (DATA / "quizzes.json").write_text(json.dumps(quizzes, indent=1, ensure_ascii=False))
    print(f"placed from OSM {placed['osm']}, from postcode {placed['postcode']}, not placed {placed['none']}")


if __name__ == "__main__":
    main()
