#!/usr/bin/env python3
"""Build the crawl list: the request's own pages, plus every London pub's website.

    python3 pub-quiz/fetch/make_crawl.py

Reads  pub-quiz/fetch/request.json   (pages, and crawl_osm_pubs: true/false)
       pub-quiz/data/osm/pubs.json
Writes pub-quiz/fetch/crawl.json     the entries fetch_pages.mjs works through

A website shared by many pubs (a pub company's homepage) says nothing about any
one of them, so an address used by more than one pub is crawled once and only
if it has a path, and a bare company domain is skipped.
"""
import gzip
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
req = json.loads((HERE / "request.json").read_text())
entries = list(req.get("pages", []))
seen = {u for e in entries for u in e["urls"]}

SOCIAL = ("facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "linktr.ee",
          "youtube.com", "tripadvisor", "google.", "goo.gl", "bit.ly")

if req.get("crawl_osm_pubs"):
    pubs = json.loads((HERE.parent / "data" / "osm" / "pubs.json").read_text())
    by_url = defaultdict(list)
    for p in pubs:
        u = (p.get("website") or p.get("contact:website") or p.get("url") or "").split(";")[0].strip()
        if not u:
            continue
        if "://" not in u:
            u = "https://" + u
        try:
            parsed = urlparse(u)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        if not host or any(s in host for s in SOCIAL):
            continue
        by_url[u.rstrip("/")].append(p)
    added = 0
    for u, ps in sorted(by_url.items()):
        path = urlparse(u).path.strip("/")
        if len(ps) > 1 and not path:
            continue  # a company homepage shared by several pubs
        if u in seen or u + "/" in seen:
            continue
        p = ps[0]
        entries.append({"id": "osm-" + p["osm"].replace("/", "-"), "urls": [u], "follow": 4,
                        "osm": [x["osm"] for x in ps], "name": p.get("name")})
        seen.add(u)
        added += 1
    print(f"{added} pub websites from OpenStreetMap")

def sitemap_urls(url, depth=0):
    """Every page URL in a sitemap, following sitemap indexes two levels down."""
    try:
        r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; london-noticing pub quiz map)"})
        with urllib.request.urlopen(r, timeout=40) as resp:
            body = resp.read()
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body.decode("utf-8", "replace"))
    except Exception as err:
        print(f"  sitemap {url}: {type(err).__name__}: {err}")
        return []
    out = []
    for loc in locs:
        if depth < 2 and re.search(r"sitemap[^/]*\.xml(\.gz)?$", loc, re.I):
            out += sitemap_urls(loc, depth + 1)
        else:
            out.append(loc)
    return out


# A pub company's sitemap lists every pub page it has, including pubs whose
# OpenStreetMap entry carries no website. "match" picks the London pub pages.
for sm in req.get("sitemaps", []):
    urls = sorted({u.rstrip("/") for u in sitemap_urls(sm["url"]) if re.search(sm["match"], u, re.I)})
    added = 0
    for u in urls:
        if u in seen or u + "/" in seen:
            continue
        entries.append({"id": f"{sm['prefix']}-{re.sub(r'[^a-z0-9]+', '-', u.split('://')[1].lower()).strip('-')[-60:]}",
                        "urls": [u], "follow": sm.get("follow", 4)})
        seen.add(u)
        added += 1
    print(f"{added} pages from {sm['url']} ({len(urls)} matched)")

(HERE / "crawl.json").write_text(json.dumps({"run": req["run"], "pages": entries}, indent=0))
print(f"{len(entries)} entries in the crawl")
