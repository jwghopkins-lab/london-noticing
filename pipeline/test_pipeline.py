#!/usr/bin/env python3
"""Unit tests for the parts that fail quietly.

The smoke test drives the page and proves the walk works. These tests cover the
things a browser cannot show you: whether the geometry is right, whether a gate
opens where it should, and whether the checks that read the map would actually
catch bad directions. A checker that never fails is not a checker.

    python3 -m unittest discover -s pipeline -p 'test_*.py' -v

The London topic-picker tests used to live here too. London is archived, so
they moved with it, to archive/london/test_london.py.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo                                         # noqa: E402
import streets                                     # noqa: E402
import confidence                                  # noqa: E402
import terrain                                     # noqa: E402
import build_tour                                  # noqa: E402

BASE = Path(__file__).resolve().parent.parent


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

    def test_standing_on_a_street_is_not_being_near_one(self):
        """45 m reached three streets over in a town of four-metre alleys, and
        made 'that street is not on your way' exempt almost everything."""
        self.assertLessEqual(build_tour.STANDING_ON_M, 30)

    def test_riddle_talk_is_named(self):
        self.assertIn("go and find it", build_tour.RIDDLE_PHRASES)
        self.assertIn("somewhere in here", build_tour.RIDDLE_PHRASES)


if __name__ == "__main__":
    unittest.main()


# A town small enough to reason about by hand. One straight street running east,
# one running north off its far end, and a nameless alley cutting the corner, so
# there are two ways from the bottom left to the top right.
#
#   C (0.002, 0.002)
#   |
#   |  North Street
#   |
#   B (0.000, 0.002)
#   |
#   |  East Street
#   |
#   A (0.000, 0.000)
#
TOY = {
    "streets": [
        {"name": "East Street", "kind": "residential",
         "line": [[0.0, 0.0], [0.0, 0.002]]},
        {"name": "North Street", "kind": "residential",
         "line": [[0.0, 0.002], [0.002, 0.002]]},
    ],
    "places": [], "water": [],
}


def toy(extra_streets=()):
    doc = {"streets": list(TOY["streets"]) + list(extra_streets),
           "places": [], "water": []}
    return streets.Town(doc)


class TestRoutingFromWhereYouStand(unittest.TestCase):
    """The bridge bug: routing from the nearest NODE loses whole stretches."""

    def test_a_stop_in_the_middle_of_a_long_way_is_not_moved_to_its_end(self):
        town = toy()
        # Halfway along East Street, which is drawn with a node at each end.
        mid = (0.0, 0.001)
        node, node_d = town.snap(*mid)
        self.assertGreater(node_d, 100, "the nearest drawn node is far away")
        self.assertAlmostEqual(town.off_network_m(*mid), 0.0, places=3,
                               msg="but the walker is standing on the street")
        r = town.route(mid, (0.002, 0.002))
        # Half of East Street plus all of North Street, not just North Street.
        self.assertGreater(r["metres"], 300, r["metres"])

    def test_both_ends_on_one_stretch_do_not_go_round_by_the_junctions(self):
        town = toy()
        r = town.route((0.0, 0.0005), (0.0, 0.0015))
        self.assertLess(r["metres"], 150, r["metres"])

    def test_a_bridge_is_not_an_anonymous_lane(self):
        """Nameless in the data, unmissable on the ground."""
        plain = toy([{"name": None, "kind": "primary",
                      "line": [[-0.001, 0.0], [0.0, 0.0]]}])
        bridge = toy([{"name": None, "kind": "primary", "obvious": "bridge",
                       "line": [[-0.001, 0.0], [0.0, 0.0]]}])
        start, end = (-0.0005, 0.0), (0.0, 0.002)
        got_plain = confidence.score_leg(plain, start, end, [])
        got_bridge = confidence.score_leg(bridge, start, end, [])
        self.assertGreater(got_plain["unnamed_frac"], 0.1)
        self.assertEqual(got_bridge["unnamed_frac"], 0.0)


class TestConfidence(unittest.TestCase):
    def test_only_one_way_round_is_the_easiest_leg_not_the_hardest(self):
        """margin 1.0 once meant 'no alternative exists', the best possible case,
        and was scored as the worst."""
        got = confidence.score_leg(toy(), (0.0, 0.0), (0.002, 0.002), [])
        self.assertTrue(got["only_way"])
        self.assertIsNone(got["margin"])
        self.assertFalse([r for r in got["reasons"] if "toss-up" in r])

    def test_two_ways_round_of_the_same_length_are_a_toss_up(self):
        """A second street parallel to the first makes the route a coin flip."""
        town = toy([{"name": "Back Lane", "kind": "residential",
                     "line": [[0.0, 0.0], [0.002, 0.0], [0.002, 0.002]]}])
        got = confidence.score_leg(town, (0.0, 0.0), (0.002, 0.002), [])
        self.assertTrue([r for r in got["reasons"] if "toss-up" in r], got)

    def test_a_disagreeing_engine_sends_a_leg_to_rough(self):
        town = toy()
        # A route down a different street entirely.
        theirs = {"engine": "invented", "line": [[0.0, 0.0], [0.002, 0.0],
                                                 [0.002, 0.002]]}
        got = confidence.score_leg(town, (0.0, 0.0), (0.002, 0.002), [theirs])
        self.assertEqual(got["verdict"], "rough")
        self.assertTrue([r for r in got["reasons"] if "differently" in r], got)

    def test_an_agreeing_engine_leaves_the_leg_alone(self):
        town = toy()
        theirs = {"engine": "agreeable",
                  "line": [[0.0, 0.0], [0.0, 0.002], [0.002, 0.002]]}
        got = confidence.score_leg(town, (0.0, 0.0), (0.002, 0.002), [theirs])
        self.assertEqual(got["verdict"], "turn_by_turn", got["reasons"])

    def test_an_engine_that_could_not_be_reached_is_a_note_not_a_verdict(self):
        """A bad afternoon on a free server must not rewrite a walk."""
        town = toy()
        got = confidence.score_leg(town, (0.0, 0.0), (0.002, 0.002),
                                   [{"engine": "down", "error": "timeout"}])
        self.assertEqual(got["reasons"], [])
        self.assertTrue(got["notes"])

    def test_never_fetched_is_also_only_a_note(self):
        got = confidence.score_leg(toy(), (0.0, 0.0), (0.002, 0.002), None)
        self.assertEqual(got["reasons"], [])
        self.assertTrue([n for n in got["notes"] if "second opinion" in n])

    def test_a_few_metres_apart_on_a_short_leg_is_not_a_disagreement(self):
        """28 m against 35 m is a 1.25 ratio and means nothing."""
        town = toy()
        short = confidence.agreement([(0.0, 0.0), (0.0, 0.0003)],
                                     [(0.0, 0.0), (0.0, 0.0002)])
        self.assertGreater(short["length_ratio"], confidence.AGREE_LENGTH)
        self.assertLess(abs(short["their_metres"] - 33), confidence.AGREE_LENGTH_M)
        got = confidence.score_leg(
            town, (0.0, 0.0), (0.0, 0.0003),
            [{"engine": "close enough", "line": [[0.0, 0.0], [0.0, 0.0002]]}])
        self.assertEqual(got["verdict"], "turn_by_turn", got["reasons"])


class TestRoughDirections(unittest.TestCase):
    def test_the_shipped_text_carries_all_four_parts(self):
        got = build_tour.rough_directions({
            "directions": "From the bridge, head north. About fifty metres.",
            "directions_streets": ["Rue A", "Rue B"],
            "directions_target": "a tall stone tower",
        })
        self.assertIn("From the bridge", got)
        self.assertIn("Rue A or Rue B", got)
        self.assertIn(build_tour.ROUGH_LANES, got)
        self.assertIn("What you are looking for is a tall stone tower.", got)

    def test_one_street_is_not_listed_as_if_there_were_two(self):
        got = build_tour.rough_directions({
            "directions": "x", "directions_streets": ["Rue A"],
            "directions_target": "y"})
        self.assertIn("You may come out on Rue A.", got)

    def test_the_verifier_notices_a_lost_part(self):
        source = {"id": "b", "directions_mode": "rough",
                  "directions": "From the bridge, head north.",
                  "directions_streets": ["Rue A"],
                  "directions_target": "a tall stone tower"}
        good = {"id": "b", "directions": build_tour.rough_directions(source)}
        self.assertEqual(build_tour.rough_survived(good, source), [])
        for lost in (build_tour.ROUGH_LANES, "Rue A", "a tall stone tower",
                     "From the bridge, head north."):
            bad = {"id": "b", "directions": good["directions"].replace(lost, "")}
            self.assertTrue(build_tour.rough_survived(bad, source),
                            f"losing {lost!r} went unnoticed")


class TestTerrain(unittest.TestCase):
    def test_climbing_towards_where_you_are_going_is_not_wasted(self):
        got = terrain.summarise([100, 110, 120, 130])
        self.assertEqual(got["ascent"], 30)
        self.assertEqual(got["reclimb"], 0)

    def test_climbing_the_same_metres_twice_is(self):
        # Up thirty, down thirty, up thirty again: ends where a straight climb
        # would have, having done the work twice.
        got = terrain.summarise([100, 130, 100, 130])
        self.assertEqual(got["ascent"], 60)
        self.assertEqual(got["reclimb"], 30)

    def test_a_walk_that_ends_lower_wasted_all_of_its_climbing(self):
        got = terrain.summarise([100, 120, 90])
        self.assertEqual(got["reclimb"], 20)

    def test_jitter_is_not_a_hill(self):
        """A metre of DEM noise every sample must not accumulate."""
        noisy = [100 + (1 if i % 2 else 0) for i in range(200)]
        self.assertEqual(terrain.summarise(noisy)["ascent"], 0)

    def test_a_real_step_is_still_seen_through_the_jitter(self):
        got = terrain.summarise([100, 101, 100, 101, 140, 139, 140])
        self.assertGreater(got["ascent"], 35)

    def test_no_heights_is_not_a_flat_walk(self):
        got = terrain.summarise([])
        self.assertIsNone(got["start"])
        self.assertEqual(got["ascent"], 0)

    def test_a_height_lookup_far_from_any_sample_says_so(self):
        ground = terrain.Terrain({"dataset": "test",
                                  "points": [[44.0, 1.0, 250.0]]})
        self.assertEqual(ground.height(44.0, 1.0), 250.0)
        self.assertIsNone(ground.height(44.02, 1.02))


class TestStreetNamesWithAWordInFront(unittest.TestCase):
    """Grand Rue Raymond VII. The prefix is not the first word.

    Looking only forwards from "Rue" made every mention of the main street in
    Cordes read as an invented street, and failed the whole build six times over.
    """
    class FakeTown:
        NAMES = {"grand rue raymond vii": "Grand Rue Raymond VII",
                 "rue obscure": "Rue Obscure",
                 "place de la halle": "Place de la Halle"}

        def has_street(self, name):
            return name.lower() in self.NAMES

        def canonical(self, name):
            return self.NAMES.get(name.lower())

    def resolve(self, text):
        town = self.FakeTown()
        return [build_tour.resolve_street(town, toks)
                for _, toks in build_tour.street_mentions(text)]

    def test_the_leading_word_is_picked_up(self):
        self.assertEqual(
            self.resolve("Follow Grand Rue Raymond VII, which runs west."),
            ["Grand Rue Raymond VII"])

    def test_a_street_opening_a_sentence_keeps_its_first_word(self):
        """The exact text that failed: a full stop before, not between."""
        self.assertEqual(
            self.resolve("About sixty metres. Grand Rue Raymond VII runs to the gate."),
            ["Grand Rue Raymond VII"])

    def test_a_sentence_ending_between_the_two_words_still_splits_them(self):
        self.assertEqual(
            self.resolve("You reach the Halle. Rue Obscure joins here."),
            ["Rue Obscure"])

    def test_a_capitalised_word_in_front_that_is_not_part_of_the_name(self):
        """Dropping the leading word is tried too, so this still resolves."""
        self.assertEqual(self.resolve("Cross Place de la Halle to the corner."),
                         ["Place de la Halle"])

    def test_an_invented_street_is_still_invented(self):
        self.assertEqual(self.resolve("Take Grand Rue de la Lune west."), [None])


class TestPlainVoice(unittest.TestCase):
    """Every example here is quotable from a walk that was published."""

    def faults(self, text):
        return [f.split(": ", 1)[1] for f in build_tour.plain_faults("x", text)]

    def test_the_knowing_aside(self):
        self.assertTrue(self.faults("That is the third living this hill has made."))
        self.assertTrue(self.faults("That is where a town kept its fairs."))
        self.assertTrue(self.faults("The carving gives it away, and that is the point."))

    def test_pointing_at_something_in_front_of_you_is_not_the_aside(self):
        """'This is' introduces; 'that is' points back. Only one is the tic."""
        self.assertEqual(self.faults("This is the stop for a drink."), [])
        self.assertEqual(self.faults("This is the oldest house on the street."), [])

    def test_the_walk_may_still_end_on_its_own_last_line(self):
        self.assertEqual(self.faults("That is the walk."), [])
        self.assertEqual(self.faults("That is the seven."), [])

    def test_an_abstract_noun_doing_a_verbs_job(self):
        self.assertTrue(self.faults("The well is what solving it looked like."))

    def test_balanced_antithesis(self):
        self.assertTrue(self.faults("people who hunted for a living rather than working"))
        self.assertTrue(self.faults("It is not just a house, it is a statement."))

    def test_hedges_and_intensifiers(self):
        for tic in ("almost certainly", "arguably", "essentially", "crucially",
                    "in many ways", "it is worth noting"):
            self.assertTrue(self.faults(f"The house was {tic} a merchant's."), tic)

    def test_essay_nouns(self):
        self.assertTrue(self.faults("The street is a testament to the trade."))
        self.assertTrue(self.faults("The carvings speak to a wider tapestry."))

    def test_long_words_get_the_short_one_offered(self):
        got = build_tour.plain_faults("x", "Prior to the fair they would utilise the hall.")
        self.assertTrue(any("'before'" in f for f in got), got)
        self.assertTrue(any("'use'" in f for f in got), got)

    def test_ordinary_plain_english_passes(self):
        for line in ("The roof is held up on pillars and open on every side.",
                     "Stand under the arch and look back up the street.",
                     "There is a well beside it. It goes down through the rock.",
                     "The lane is worth two steps.",
                     "Ormeaux. Elms.",
                     "Take the second turning and stop at the blue door."):
            self.assertEqual(self.faults(line), [], line)


class TestVoiceIsOptIn(unittest.TestCase):
    """The walks written before the rule existed must be left exactly alone."""

    def test_the_old_walks_do_not_declare_plain(self):
        for path in sorted(BASE.glob("content/*/*.json")):
            tour = json.loads(path.read_text(encoding="utf-8"))
            voice = (tour.get("contract") or {}).get("voice", "standard")
            self.assertIn(voice, build_tour.VOICES, path.name)

    def test_plain_caps_are_tighter_than_the_old_ones(self):
        self.assertLess(build_tour.PLAIN_LOOK_WORDS_MAX, build_tour.LOOK_WORDS_MAX)
        self.assertLess(build_tour.PLAIN_AFTER_WORDS_MAX, build_tour.AFTER_WORDS_MAX)
        self.assertLess(build_tour.PLAIN_SENTENCE_WORDS, build_tour.LONG_SENTENCE_WORDS)


class TestNamingTheOrigin(unittest.TestCase):
    """The first sentence has to name the stop you are setting off from."""

    EDIT = {"id": "edit", "title": "A Street Named After a Court",
            "where": "the narrow street off Place de la République"}

    def test_an_accented_name_still_matches_its_own_id(self):
        """'edit' is not a substring of 'edit' with an acute on the e."""
        self.assertTrue(build_tour.names_its_start(
            "From Rue Chambre de l'\u00c9dit, walk back to the corner.", self.EDIT))

    def test_a_stop_that_is_not_named_is_caught(self):
        self.assertFalse(build_tour.names_its_start(
            "Leave the square on the far side and keep going.", self.EDIT))

    def test_a_generic_word_does_not_count_as_naming_anything(self):
        """'Leave the square' names nothing: which square, and which side?"""
        self.assertNotIn("square", build_tour.naming_words(self.EDIT))
        self.assertNotIn("street", build_tour.naming_words(self.EDIT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
