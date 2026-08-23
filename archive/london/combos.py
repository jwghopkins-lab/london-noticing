#!/usr/bin/env python3
"""The ten combinations of three topics from five.

Ported from the TRIVIUM tour-kit extract. Almost all of this is obvious. The
one part worth having is combo_key: the ids are SORTED before joining, so that
a walker who taps Fire then Rivers and a walker who taps Rivers then Fire land
on the same key, the same artefact and the same cache entry.

    python3 pipeline/combos.py
"""
from itertools import combinations
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent.parent.parent
PICK = 3


def combo_key(topic_ids):
    """The canonical name for a set of chosen topics. Order-independent."""
    return "-".join(sorted(topic_ids))


def all_combos(topic_ids, pick=PICK):
    """Every combination, as (key, ids). Deterministic order."""
    return [(combo_key(c), list(c)) for c in combinations(sorted(topic_ids), pick)]


def load_topics():
    doc = json.loads((BASE / "content" / "topics.json").read_text(encoding="utf-8"))
    return doc["topics"]


def main():
    topics = load_topics()
    names = {t["id"]: t["name"] for t in topics}
    rows = all_combos([t["id"] for t in topics])
    print(f"{len(topics)} topics, pick {PICK} -> {len(rows)} combinations\n")
    for key, ids in rows:
        print(f"  {key:<22} {' + '.join(names[i] for i in ids)}")


if __name__ == "__main__":
    main()
