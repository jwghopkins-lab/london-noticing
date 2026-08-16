#!/usr/bin/env python3
"""Fold the whole walk into one HTML file.

The served build fetches its topics and its route artefacts as separate static
files, which is right for a website. This build inlines all of them into the
page, so the result is a single file that works with no server, no connection
and no second request. Hand it to somebody on a phone and it runs.

It is the same page. Nothing is forked. index.html looks for
window.NOTICING_BUNDLE and falls back to fetching when it is not there, so the
served build and the standalone build run identical code.

    python3 pipeline/build_standalone.py [--out dist/london-noticing.html]
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
APP = BASE / "app"
MARKER = "<script>\n\"use strict\";"


def main():
    args = sys.argv[1:]
    out = (Path(args[args.index("--out") + 1]) if "--out" in args
           else BASE / "dist" / "london-noticing.html")

    page = (APP / "index.html").read_text(encoding="utf-8")
    topics = json.loads((APP / "topics.json").read_text(encoding="utf-8"))
    routes = {}
    for path in sorted((APP / "routes").glob("*.json")):
        if path.name == "manifest.json":
            continue
        routes[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    if not routes:
        print("no baked routes in app/routes — run bake.py first")
        return 1

    bundle = {"topics": topics["topics"], "routes": routes}
    # </script> inside JSON would close the tag early and break the page.
    payload = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    inject = (f'<script>window.NOTICING_BUNDLE = {payload};</script>\n' + MARKER)

    if MARKER not in page:
        print("could not find the script block to inject before")
        return 1
    page = page.replace(MARKER, inject, 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    kb = out.stat().st_size / 1024
    stops = sum(len(r["stops"]) for r in routes.values())
    print(f"{out} written: {len(routes)} routes, {stops} stop cards, {kb:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
