"""Shared Overpass helper for the pub quiz fetchers. Runs on a GitHub runner."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
# Greater London and a little over: south, west, north, east.
BOX = "51.28,-0.52,51.70,0.34"
UA = "london-noticing pub quiz map (github.com/jwghopkins-lab)"


def fetch(q, attempts=3, timeout=300):
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(attempts):
        for url in ENDPOINTS:
            t0 = time.time()
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
                print(f"  {url}: {len(data.get('elements', []))} elements in {time.time() - t0:.0f}s", flush=True)
                return data
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                    json.JSONDecodeError, ConnectionError) as err:
                last = f"{url}: {type(err).__name__}: {err}"
                print(f"  {last} after {time.time() - t0:.0f}s", flush=True)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass would not answer. Last error: {last}")


def r5(x):
    return round(x, 5)
