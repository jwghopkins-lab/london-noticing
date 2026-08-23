#!/usr/bin/env python3
"""Unit tests for the archived London topic-picker walk.

These came out of pipeline/test_pipeline.py when London was archived. They are
kept, and kept runnable, because the walk may be dug out again and a resurrected
route with no tests around it is worse than no route.

    python3 -m unittest discover -s archive/london -p 'test_*.py' -v

Run archive/london/bake.py first: the verifier tests tamper with a real
artefact, so they need one on disk.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pipeline"))
import combos                                      # noqa: E402
import verify_bakes                                # noqa: E402

BASE = Path(__file__).resolve().parent.parent.parent
CONTENT = Path(__file__).resolve().parent


def content():
    return (json.loads((CONTENT / "topics.json").read_text(encoding="utf-8")),
            json.loads((CONTENT / "stops.json").read_text(encoding="utf-8")),
            json.loads((CONTENT / "routes.json").read_text(encoding="utf-8")))


class TestCombos(unittest.TestCase):
    IDS = ["roman", "fire", "rivers", "marks", "fleet"]

    def test_key_is_order_independent(self):
        self.assertEqual(combos.combo_key(["fire", "rivers", "fleet"]),
                         combos.combo_key(["rivers", "fleet", "fire"]))

    def test_five_choose_three_is_ten(self):
        rows = combos.all_combos(self.IDS, 3)
        self.assertEqual(len(rows), 10)
        self.assertEqual(len({k for k, _ in rows}), 10)

    def test_every_pick_lands_on_a_route(self):
        """The point of the whole design: no algorithm, just a lookup."""
        keys = {k for k, _ in combos.all_combos(self.IDS, 3)}
        _, _, routes = content()
        self.assertEqual(keys, set(routes["routes"]))


class TestVerifier(unittest.TestCase):
    """Tamper with a good artefact and check the verifier notices.

    These are the tests that matter. bake.py calls verify() on every artefact
    before writing it, so if the verifier is blind then nothing is being checked
    at all and we would not know.
    """

    def setUp(self):
        self.topics, self.stops, self.routes = content()
        path = BASE / "out" / "fire-fleet-rivers.json"
        if not path.exists():
            self.skipTest("run bake.py first")
        self.good = json.loads(path.read_text(encoding="utf-8"))

    def verify(self, artefact):
        return verify_bakes.verify(artefact, self.topics, self.stops, self.routes)

    def test_the_good_one_passes(self):
        self.assertEqual(self.verify(self.good), [])

    def test_reordered_stops_are_caught(self):
        """The route lookup is authoritative. Reordering must not slip through."""
        bad = copy.deepcopy(self.good)
        bad["stops"].reverse()
        self.assertTrue(any("order" in p for p in self.verify(bad)))

    def test_edited_prose_is_caught(self):
        # Append rather than search and replace. An earlier version of this test
        # swapped a specific word, and when the route order changed that word was
        # no longer in stop zero, so the edit did nothing and the test passed by
        # tampering with nothing at all.
        bad = copy.deepcopy(self.good)
        bad["stops"][0]["after"] += " And another thing."
        self.assertTrue(any("does not match the content" in p for p in self.verify(bad)))

    def test_edited_prose_is_caught_on_every_stop(self):
        for i in range(len(self.good["stops"])):
            bad = copy.deepcopy(self.good)
            bad["stops"][i]["look"] += " Extra."
            self.assertTrue(self.verify(bad),
                            f"tampering with stop {i} went unnoticed")

    def test_moved_coordinate_is_caught(self):
        bad = copy.deepcopy(self.good)
        bad["stops"][0]["lat"] = 51.9
        self.assertTrue(self.verify(bad))

    def test_stale_distance_is_caught(self):
        """The walk summary must be derived from the coordinates, not asserted."""
        bad = copy.deepcopy(self.good)
        bad["walk"]["total_walk_m"] = 42.0
        self.assertTrue(any("walk distance" in p for p in self.verify(bad)))

    def test_wrong_gate_count_is_caught(self):
        bad = copy.deepcopy(self.good)
        bad["gated_stops"] = 99
        self.assertTrue(any("gated" in p for p in self.verify(bad)))

    def test_missing_text_is_caught(self):
        """A stop with no prose is not self-contained, whatever else is right."""
        bad = copy.deepcopy(self.good)
        bad["stops"][1]["look"] = ""
        self.assertTrue(any("self-contained" in p for p in self.verify(bad)))

    def test_mismatched_combo_key_is_caught(self):
        bad = copy.deepcopy(self.good)
        bad["combo_key"] = "fleet-rivers-fire"        # unsorted
        self.assertTrue(any("does not match" in p for p in self.verify(bad)))

    def test_a_smuggled_in_stop_is_caught(self):
        """A stop from a topic this combination did not choose."""
        bad = copy.deepcopy(self.good)
        bad["stops"][0]["topic"] = "roman"
        self.assertTrue(self.verify(bad))


class TestBakedArtefacts(unittest.TestCase):
    def setUp(self):
        self.out = BASE / "out"
        if not (self.out / "manifest.json").exists():
            self.skipTest("run bake.py first")

    def test_every_combination_has_an_artefact(self):
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["combos"]), 10)
        for c in manifest["combos"]:
            self.assertIn(c["status"], ("ok", "draft"), c)

    def test_artefacts_are_self_contained(self):
        """Nothing on the walk may need a second request to be readable."""
        for path in self.out.glob("*.json"):
            if path.name == "manifest.json":
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for stop in doc["stops"]:
                for field in ("id", "title", "where", "look", "after", "lat", "lon"):
                    self.assertTrue(stop.get(field) not in (None, ""),
                                    f"{path.name}: {stop.get('id')} missing {field}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
