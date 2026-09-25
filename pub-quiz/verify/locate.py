#!/usr/bin/env python3
"""Give every confirmed quiz a position on the map, and merge any pub found twice.

    python3 pub-quiz/verify/locate.py

Positions come from the pub's own point in OpenStreetMap, which is usually on
the building, found in this order:

1. The quiz was found by crawling a pub's own website: that pub.
2. An OSM pub of much the same name near the postcode the quiz's page gives.
3. With no postcode position: a pub of much the same name whose OSM address
   has the same postcode, or the only one of that name in the postcode's
   district, or the only one of that name in London.
4. Failing all that, the postcode's own centre.

A website only counts as proof of identity when it belongs to one pub: a pub
company's domain is shared by dozens, and matching on it once put three
different quizzes on three wrong pubs. Name similarity is always required.

A quiz with no position is left off. So is one whose page gives a postcode more
than 600 m from the pub it was crawled for.

The same pub confirmed twice (say on its own site and on its quiz host's list)
is kept once, preferring the pub's own page as the source. If two first-hand
pages disagree on the start time, the pub is left off.
"""
import difflib
import glob
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MAX_M = 350
SOURCE_RANK = {"pub": 0, "company": 1, "host": 2}


def norm(s):
    s = (s or "").lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|ye olde|ye) ", "", s.strip())
    s = re.sub(r"\b(pub|bar|tavern|inn|pub and kitchen|and kitchen|freehouse|free house|london|pub and rooms)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def url_key(u):
    try:
        p = urlparse(u if "://" in u else "https://" + u)
    except ValueError:
        return "", ""
    h = (p.hostname or "").lower()
    return (h[4:] if h.startswith("www.") else h), p.path.rstrip("/").lower()


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(51.5)))


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0


def site(p):
    return (p.get("website") or p.get("contact:website") or p.get("url") or "").split(";")[0].strip()


def postcodes():
    out = {}
    for p in sorted(glob.glob(str(DATA / "fetched" / "*" / "postcodes.json"))):
        for k, v in json.loads(Path(p).read_text()).items():
            if v:
                out[k.replace(" ", "").upper()] = v
    return out


def district(pc):
    m = re.match(r"([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}$", (pc or "").upper().strip())
    return m.group(1) if m else None


def inside(lat, lon, rings):
    """Even-odd point in polygon over all rings ([lat, lon] pairs), so holes work."""
    hit = False
    for ring in rings:
        for (y1, x1), (y2, x2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def main():
    quizzes = json.loads((DATA / "quizzes.json").read_text())
    pubs = json.loads((DATA / "osm" / "pubs.json").read_text())
    by_osm = {p["osm"]: p for p in pubs}
    for p in pubs:
        p["_n"] = norm(p.get("name"))
    domain_use = Counter(url_key(site(p))[0] for p in pubs if site(p))
    pcs = postcodes()
    base = json.loads((DATA / "osm" / "basemap.json").read_text())
    places = [p for p in base.get("places", []) if p["p"] in ("suburb", "neighbourhood", "quarter", "town")]

    def area(lat, lon):
        return min(places, key=lambda p: metres((lat, lon), (p["lat"], p["lon"])) * (0.8 if p["p"] == "suburb" else 1))["n"]

    def own_site(q, p):
        """Same website, and one that belongs to a single pub (or the exact same page)."""
        qd, qp = url_key(q.get("website", ""))
        pd, pp = url_key(site(p))
        if not qd or qd != pd:
            return False
        return domain_use[qd] <= 1 or bool(qp and qp == pp)

    lp = DATA / "osm" / "london.json"
    london = json.loads(lp.read_text())["rings"] if lp.exists() else None
    if not london:
        print("warning: no Greater London boundary yet (data/osm/london.json); nothing is filtered by it")
    placed, keep = Counter(), []
    for q in quizzes:
        qn = norm(q["name"])
        pc = pcs.get((q.get("postcode") or "").replace(" ", "").upper())
        centre = (pc["lat"], pc["lon"]) if pc else None
        pick, how = None, None

        own = next((by_osm[o] for o in q.get("osm_ids", []) if o in by_osm), None)
        if own:
            if centre and metres(centre, (own["lat"], own["lon"])) > 600:
                print(f"left off {q['id']}: its page's postcode is "
                      f"{metres(centre, (own['lat'], own['lon'])):.0f} m from the pub it was crawled for")
                continue
            pick, how = own, "crawled"
        elif centre:
            near = [(sim(qn, p["_n"]) + (0.3 if own_site(q, p) else 0) - metres(centre, (p["lat"], p["lon"])) / 2000, p)
                    for p in pubs if metres(centre, (p["lat"], p["lon"])) <= MAX_M
                    and (sim(qn, p["_n"]) >= 0.82 or (own_site(q, p) and sim(qn, p["_n"]) >= 0.5))]
            if near:
                pick, how = max(near, key=lambda x: x[0])[1], "name near postcode"
        else:
            named = [p for p in pubs if sim(qn, p["_n"]) >= 0.85]
            pc_q = (q.get("postcode") or "").replace(" ", "").upper()
            same_pc = [p for p in named if pc_q and (p.get("addr:postcode") or "").replace(" ", "").upper() == pc_q]
            same_d = [p for p in named if district(q.get("postcode")) and district(p.get("addr:postcode")) == district(q.get("postcode"))]
            exact = [p for p in pubs if sim(qn, p["_n"]) >= 0.92]
            sites = [p for p in named if own_site(q, p)]
            for cands, label in ((same_pc, "name and postcode"), (same_d, "name in district"), (sites, "own website"),
                                 (exact if len(qn) >= 8 else [], "unique name")):
                if len(cands) == 1:
                    pick, how = cands[0], label
                    break

        if pick:
            q.update(lat=pick["lat"], lon=pick["lon"], location_source="osm", osm=pick["osm"],
                     located_by=how, area=area(pick["lat"], pick["lon"]))
            if centre:
                q["osm_to_postcode_m"] = round(metres(centre, (pick["lat"], pick["lon"])))
            if not q.get("postcode") and pick.get("addr:postcode"):
                q["postcode"] = pick["addr:postcode"].upper()
            if not q.get("address"):
                street = " ".join(x for x in (pick.get("addr:housenumber"), pick.get("addr:street")) if x)
                if street:
                    q["address"] = ", ".join(x for x in (street, pick.get("addr:postcode")) if x)
                    q["address_source"] = "osm"
            # The homepage link goes to the pub itself, not to a listing.
            s = site(pick)
            if q.get("source_kind") != "pub" and s and domain_use[url_key(s)[0]] <= 1:
                q["website"] = s if "://" in s else "https://" + s
            placed["osm"] += 1
        elif centre:
            q.update(lat=round(centre[0], 5), lon=round(centre[1], 5), location_source="postcode",
                     located_by="postcode centre", area=area(*centre))
            placed["postcode"] += 1
        else:
            placed["none"] += 1
            print(f"left off {q['id']}: no postcode position, and no OSM pub it can only be")
            continue
        if london and not inside(q["lat"], q["lon"], london):
            placed["outside"] += 1
            print(f"left off {q['id']}: {q['name']} is outside Greater London")
            continue
        keep.append(q)

    def key(q):
        return q.get("osm") or (round(q["lat"], 4), round(q["lon"], 4))

    # One building can carry two names (Bertie's Bar is in the Prince of Wales),
    # so pins within 40 m with the same start time are one quiz.
    for i, q in enumerate(keep):
        for r in keep[:i]:
            if q["start"] == r["start"] and metres((q["lat"], q["lon"]), (r["lat"], r["lon"])) <= 40:
                q["osm"] = r.get("osm") or q.get("osm")
                q["lat"], q["lon"] = r["lat"], r["lon"]
                break
    groups = {}
    for q in keep:
        groups.setdefault(key(q), []).append(q)
    merged, clashes = [], 0
    for k, qs in groups.items():
        if len({q["start"] for q in qs}) > 1:
            clashes += 1
            print(f"left off {qs[0]['name']}: first-hand pages disagree on the start time: " +
                  ", ".join(f"{q['start']} on {q['source_url']}" for q in qs))
            continue
        merged.append(min(qs, key=lambda q: SOURCE_RANK.get(q["source_kind"], 9)))

    (DATA / "quizzes.json").write_text(json.dumps(merged, indent=1, ensure_ascii=False))
    print(f"placed {placed['osm']} on their OSM pub, {placed['postcode']} on a postcode centre, {placed['none']} not placed; "
          f"{len(keep) - len(merged) - sum(len(g) for g in groups.values() if len({q['start'] for q in g}) > 1)} duplicates merged, "
          f"{clashes} left off for clashing times; {len(merged)} on the map")


if __name__ == "__main__":
    main()
