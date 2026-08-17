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
