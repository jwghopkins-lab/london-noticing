#!/usr/bin/env python3
"""Look up every postcode in pub-quiz/fetch/request.json on postcodes.io.

Runs on a GitHub runner (the sandbox cannot reach postcodes.io). A postcode
unit in London covers a handful of addresses, so its centroid is usually within
a few dozen metres of the door; the build prefers the pub's own OSM point when
one matches and falls back to this.

Writes pub-quiz/data/fetched/<run>/postcodes.json
"""
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
req = json.loads((HERE / "request.json").read_text())
out_dir = HERE.parent / "data" / "fetched" / req["run"]
out_dir.mkdir(parents=True, exist_ok=True)

codes = sorted({p.strip().upper() for p in req.get("postcodes", []) if p.strip()})
result = {}
for i in range(0, len(codes), 100):
    body = json.dumps({"postcodes": codes[i:i + 100]}).encode()
    r = urllib.request.Request("https://api.postcodes.io/postcodes", data=body,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as resp:
        for item in json.loads(resp.read())["result"]:
            q, res = item["query"], item["result"]
            result[q] = None if res is None else {
                "postcode": res["postcode"], "lat": res["latitude"], "lon": res["longitude"],
                "district": res.get("admin_district"), "ward": res.get("admin_ward"),
            }

# A postcode that has since been retired still says where the pub was.
for q in [k for k, v in result.items() if v is None]:
    try:
        u = "https://api.postcodes.io/terminated_postcodes/" + urllib.request.quote(q)
        with urllib.request.urlopen(u, timeout=30) as resp:
            res = json.loads(resp.read())["result"]
            result[q] = {"postcode": res["postcode"], "lat": res["latitude"],
                         "lon": res["longitude"], "terminated": True}
    except Exception:
        pass

(out_dir / "postcodes.json").write_text(json.dumps(result, indent=1))
print(f"{len(codes)} postcodes, {sum(v is None for v in result.values())} not found")
