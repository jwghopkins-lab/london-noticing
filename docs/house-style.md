# House style

Every rule here came from something the user cut, reworded or complained about
while the first Gdansk walk was being tested. They are written down so the
second walk starts where the first one finished rather than relearning them.

Rules marked **[checked]** are enforced by `pipeline/build_tour.py` and fail the
build. The rest are on whoever is writing.

## Voice

1. Plain English. Write like a well-read friend who lives here. Short
   sentences, one idea each.
2. No long dashes stacking clauses. **[checked]**
3. No summing-up. Do not restate what you just said, and do not tell the reader
   what to take away from it. Cut "That is the last thing worth taking away",
   "Now the part worth knowing", "and that is the point". **[checked]**
4. No filler that only exists to sound knowing: "so squint", "washed up here",
   "the thing that eventually did X". Say what it was.
5. Nothing condescending about a place or the people in it. A city was not
   "flat, wet and made of clay"; it had no building stone. A port did not
   "charge everybody"; it took a cut of what passed. Men in a treadwheel were
   not "like hamsters".
6. Say "destroyed", not "killed", about a city.
7. Do not tell the walker to do something that sounds like homework for later.
   "Start counting" reads as a task. Cut it.

## Structure

8. One stage is: one block of text that walks you there, says what to look at
   and asks the question. Then one thing to do. Then one block that explains
   the answer. Then a button.
9. The walk ends on the tour's own last line. No sign-off restating the
   distance and the stop count. **[checked]**
10. A stop title must not contain its own answer. "The Golden House" gave away
    "gold", so it became "Number 41, Long Market". **[checked]**
11. The question text must not contain its own answer either. **[checked]**

## Directions

12. Every stop after the first says how to walk there: street names, turnings,
    and a distance. **[checked]**
13. Say the distance once. The authored line owns it. The player must never
    bolt a computed heading on top, because that number is a straight line
    times a detour factor and it disagrees. It once printed "about 152 metres"
    directly above a hand-measured "about a hundred and twenty metres".
    **[checked: `directions_style`]**
14. Round distances. Nearest 5 m below 100, nearest 10 m below 500, nearest
    50 m above that. "About 296 metres" is weirdly exact. **[checked]**
15. No walking time for anything under 100 metres. A 23 metre stroll does not
    take "a minute or two". **[checked]**

## Answers

16. Every answer listed as correct must actually be accepted, in every form a
    phone keyboard produces. Checked by `pipeline/check_answers.cjs` against
    the shipped page, because a rejected "two" reached a published build.
17. Accept the plural, the singular, the Polish, the digit and the word, and
    one typo. Numbers must work spelled out; nobody types a digit.
18. A "not sure, tell me" button on every question, available from the start.
19. Every location gate carries a pass button. A walk that dead ends because a
    phone could not get a fix is worse than one somebody skipped a check on.

## Location gates

25. The reach of a gate is its radius plus 15 metres, whatever the phone claims
    about its own accuracy. Subtracting the full reported accuracy turned a
    50 m gate into a 50 + accuracy gate, and it opened from more than 50 metres
    away, round a corner, on a different street. **[checked: geo and the player
    are compared]**
26. A fix worse than 75 metres opens nothing. It is not a near miss, it is no
    information, and saying "warm" about it is a lie. **[checked]**
27. Take the best fix of several seconds, not the first one. Phones hand over a
    coarse network fix first and a good satellite fix a few seconds later.
28. Size the radius to the thing. A bridge is not a doorway.

## Voice, again: this is a guide, not a treasure hunt

33. No riddle furniture in what you say at a stop. "Somewhere in here is a
    painting. Go and find it" is the puzzle project this player was copied out
    of, where withholding the answer WAS the product. Here the product is
    showing somebody a thing, so say "there is a painting of that story on the
    wall". Banned outright: somewhere in here, see if you can, can you spot,
    your task, hidden in plain sight, go and find it, look carefully and, the
    trick is, clue, riddle, puzzle. **[checked]**
34. The explainer is brief. It is read standing up, often in the sun, and 180
    words is ninety seconds of being talked at. Maximum 130 words and four
    paragraphs; aim under 110. **[checked]**
35. What to look at is shorter still. Maximum 80 words, aim under 60.
    **[checked]**
36. Lead with the answer, then the story. "Night. It is by Fauconnier, and he
    painted the whole scene after dark." Not a paragraph of throat-clearing
    first.

## Directions

29. Every stop records where its coordinate came from: surveyed, published or
    estimated. **[checked]**
30. A compass bearing in the directions must agree with the bearing between the
    two coordinates. If it does not, one of them is stale. **[checked]**
31. The first sentence must NAME the place you are setting off from. "Leave the
    square on the far side from the bridge" has an origin in it and names
    nothing: which square, and which side is the bridge on when you cannot see
    it? **[checked]**
32. Be wary of a compass bearing into an estimated coordinate. Both can be
    wrong the same way, and then nothing can catch it. **[checked as a note]**

### Checked against the real map

The town's street network is fetched from OpenStreetMap by the Fetch map data
workflow and committed to `data/osm/<tour>.json`. It runs on a GitHub runner
because this sandbox cannot reach any OSM host. The bounding box comes from the
tour's own contract, so this works for any town anywhere with no extra
configuration.

37. Every street the directions name must exist in the extract. An invented
    street fails the build. **[checked]**
38. The distances written into a leg must add up to what the router says that
    leg is, along the actual streets, within 25 per cent. **[checked]**
39. Every stop must be within 60 m of somewhere a person can walk.
    **[checked]**
40. Take coordinates from the extract, not from memory. The seven Noble Val
    stops were out by up to 100 m when placed by eye, which the tightened gates
    would have failed on.

### If you are going to give street directions they have to be right

41. A compass word next to a street name is a claim about THAT street, and it
    is checked against the street's heading on that leg. "Take Rue du Pont des
    Vierges south east out of the square" shipped; that street runs north east,
    and the south east came off a different segment entirely. **[checked]**
42. A street named in a leg must be one you actually walk on, or one you are
    standing on at either end. **[checked]**
43. Turn-by-turn only where the route earns it: every stretch named, and four
    turns or fewer. Two of Noble Val's six legs are medieval warrens, six and
    seven turns with a fifth to a quarter of the walking down lanes with no
    name on them. No turn sequence written for those can be followed.
    **[checked]**
44. On a leg that does not earn it, say what to head for and let them
    reorientate on arrival: name the target, give the routed distance and the
    overall bearing, and say what they will see when they get there. Do not
    name more than the street you leave and the one you arrive at.
    **[checked]**

## Facts

20. Do not write a question about a physical detail you have not verified. If
    the count is wrong the stop is unanswerable. Where a detail could not be
    confirmed, ask about something else, or make it a location gate instead.
21. Prefer a question whose answer is also readable from a name, a sign or the
    shape of the thing, so a walker who cannot see the detail is not stuck.

## Audio, later

22. Short sentences, one idea each. Nothing that only works on a screen.
    **[checked]**
23. A separate `_spoken` field wherever the written and spoken forms differ,
    which in practice means anywhere with digits or a date. **[checked]**
24. Stop ids are stable and never regenerated. A renamed stop is a broken
    recording.
