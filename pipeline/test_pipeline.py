#!/usr/bin/env python3
"""Unit tests for the parts that fail quietly.

The smoke test drives the page and proves the walk works. These tests cover the
two things a browser cannot show you: whether the geometry is right, and
whether the independent checker would actually catch a bad artefact. A checker
that never fails is not a checker.

    python3 -m unittest discover -s pipeline -p 'test_*.py' -v
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combos                                      # noqa: E402
import geo                                         # noqa: E402
import verify_bakes                                # noqa: E402
import build_tour                                  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
CONTENT = BASE / "content"


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


class TestGeo(unittest.TestCase):
    # St Paul's to the Monument, a distance easy to check against a map.
    STPAULS = (51.5138, -0.0984)
    MONUMENT = (51.5102, -0.0860)

    def test_haversine_is_about_right(self):
        d = geo.haversine_m(*self.STPAULS, *self.MONUMENT)
        self.assertTrue(900 < d < 1100, f"got {d:.0f} m")

    def test_zero_distance(self):
        self.assertAlmostEqual(geo.haversine_m(51.5, -0.1, 51.5, -0.1), 0.0, places=6)

    def test_gate_subtracts_some_accuracy_but_not_all(self):
        # 70 m out, 60 m of claimed error, 50 m radius. The old rule allowed the
        # full 60 and opened. The allowance is capped at 25, so 70 - 25 > 50.
        self.assertFalse(geo.gate_passes(70, 60, 50))
        # Inside the radius outright is always in.
        self.assertTrue(geo.gate_passes(45, 60, 50))
        # And a confident phone gets no help it does not need.
        self.assertFalse(geo.gate_passes(90, 5, 50))

    def test_a_hopeless_fix_opens_nothing(self):
        """This is the one that matters. A phone that does not know where it is
        must not be able to vouch for you, even standing on the spot."""
        self.assertFalse(geo.gate_passes(400, 5000, 60))
        self.assertFalse(geo.gate_passes(200, 5000, 60))
        self.assertFalse(geo.gate_passes(5, 200, 60))

    def test_gate_cannot_open_much_beyond_its_radius(self):
        """Whatever the phone claims, the reach is radius + 15 m and no more."""
        for acc in (0, 10, 40, 74):
            self.assertFalse(geo.gate_passes(50 + 15 + 1, acc, 50),
                             f"opened at 66 m with accuracy {acc}")

    def test_the_player_agrees_with_geo_about_the_gate(self):
        """The gate rule exists twice, in Python here and in JavaScript in the
        page that actually runs on the walk. Two implementations of one rule is
        how a tightened gate ships tightened in the tests and loose on a phone,
        so the numbers are read out of the shipped page and compared."""
        page = (Path(__file__).resolve().parent.parent
                / "app" / "index.html").read_text(encoding="utf-8")
        for name, want in (("ACC_ALLOWANCE_M", geo.ACC_ALLOWANCE_M),
                           ("ACC_USELESS_M", geo.ACC_USELESS_M)):
            m = re.search(rf"const {name} = (\d+);", page)
            self.assertIsNotNone(m, f"{name} not found in the player")
            self.assertEqual(int(m.group(1)), int(want),
                             f"{name} is {m.group(1)} in the player, {want} in geo")
        self.assertIn("if (acc > ACC_USELESS_M) return false;", page,
                      "the player no longer refuses a hopeless fix")

    def test_gate_opens_when_standing_there(self):
        self.assertTrue(geo.gate_passes(10, 20, 70))
        self.assertTrue(geo.gate_passes(30, 30, 30))

    def test_long_leg_is_flagged(self):
        points = [("a", 51.5138, -0.0984), ("b", 51.5300, -0.0984)]   # ~1.8 km
        result = geo.check(points)
        self.assertTrue(any("minutes" in p for p in result["problems"]),
                        result["problems"])

    def test_short_walk_is_not_flagged(self):
        points = [("a", 51.5138, -0.0984), ("b", 51.5150, -0.0950)]   # ~280 m
        self.assertEqual(geo.check(points)["problems"], [])

    def test_doubling_back_is_flagged(self):
        # Out east, then straight back west past the start.
        points = [("a", 51.515, -0.100), ("b", 51.515, -0.095), ("c", 51.515, -0.101)]
        result = geo.check(points)
        self.assertEqual(result["reversals"], 1)

    def test_turning_a_corner_is_not_a_reversal(self):
        """An L-shaped turn round a block is how walking works."""
        points = [("a", 51.515, -0.100), ("b", 51.515, -0.096), ("c", 51.518, -0.096)]
        self.assertEqual(geo.check(points)["reversals"], 0)

    def test_two_stops_at_the_same_place(self):
        points = [("a", 51.515, -0.100), ("b", 51.51501, -0.100)]
        self.assertTrue(any("same place" in p for p in geo.check(points)["problems"]))

    def test_a_stop_twice_in_one_route(self):
        points = [("a", 51.515, -0.100), ("b", 51.516, -0.097), ("a", 51.515, -0.100)]
        self.assertTrue(any("more than once" in p for p in geo.check(points)["problems"]))


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


class TestDirectionChecks(unittest.TestCase):
    """The checks that read the map, tested without needing the map."""

    def test_an_ordinary_word_is_not_a_street(self):
        """'the two rivers made the place. The Aveyron carried the trade' was
        read as a street called Place, and failed the build."""
        text = "The two rivers made the place. The Aveyron carried the trade."
        self.assertEqual(build_tour.street_mentions(text), [])

    def test_a_real_street_is_picked_up(self):
        got = build_tour.street_mentions("Walk up Rue du Pont de l'Aveyron.")
        self.assertTrue(got, "missed a street name")
        self.assertEqual(got[0][1][:2], ["Rue", "du"])

    def test_every_distance_on_a_leg_is_counted(self):
        """A leg described in parts has to add up, so all of them are read."""
        text = ("about fifty metres. It runs on. Keep going another seventy "
                "metres or so.")
        self.assertEqual(sorted(build_tour.all_authored_metres(text)), [50, 70])

    def test_spelled_out_distances_count_too(self):
        self.assertEqual(build_tour.all_authored_metres(
            "about a hundred and seventy metres"), [170])

    def test_a_compound_bearing_is_read_once(self):
        """'west' sits inside 'north west'. Reading both made the compound look
        like two claims, one of them 45 degrees out."""
        got = build_tour.compass_positions("cross to the north west corner")
        self.assertEqual([d for _, d, _ in got], [315])

    def test_a_bearing_next_to_a_street_belongs_to_that_street(self):
        text = "take Rue du Pont des Vierges south east out of the square"
        mentions = build_tour.street_mentions(text)
        pos = build_tour.compass_positions(text)[0][0]
        att = build_tour.attached_street(text, pos, mentions)
        self.assertIsNotNone(att, "the bearing was read as being about the leg")
        self.assertEqual(att[1][:2], ["Rue", "du"])

    def test_a_bearing_in_the_next_sentence_is_about_the_leg(self):
        text = "Head for Place du Bessarel. About two hundred metres, north west."
        mentions = build_tour.street_mentions(text)
        pos = [p for p, _, _ in build_tour.compass_positions(text)][0]
        self.assertIsNone(build_tour.attached_street(text, pos, mentions))

    def test_turn_claims_do_not_fire_on_ordinary_words(self):
        self.assertIsNone(build_tour.TURN_CLAIMS.search("do not count turnings"))
        self.assertIsNone(build_tour.TURN_CLAIMS.search("it turns north"))
        self.assertIsNotNone(build_tour.TURN_CLAIMS.search("turn right onto X"))
        self.assertIsNotNone(build_tour.TURN_CLAIMS.search("take the first left"))

    def test_riddle_talk_is_named(self):
        self.assertIn("go and find it", build_tour.RIDDLE_PHRASES)
        self.assertIn("somewhere in here", build_tour.RIDDLE_PHRASES)


if __name__ == "__main__":
    unittest.main()
