export const meta = {
  name: 'pub-quiz-verify',
  description: 'Two independent readers check each crawled pub page for a weekly Tuesday quiz and its start time',
  phases: [
    { title: 'Read', detail: 'first reader extracts verdict, start time and exact quote' },
    { title: 'Challenge', detail: 'second reader tries to refute every confirmation' },
  ],
}

const RULES = `Today is Friday 25 September 2026. You are checking whether London pubs run a pub quiz EVERY Tuesday, and at what time it starts. The evidence is text fetched from websites by a browser; each evidence file starts with "CANDIDATE <id>: crawled as the website of <pub name>", then one "=== PAGE <url>" block per fetched page (with its title, final url, fetch date, years mentioned, postcode-like strings), then the passages that mention a quiz, or the whole page if it is short.

Read files with the Read tool. Do not use the web: judge only from the evidence file.

A quiz is CONFIRMED only when ALL of these hold:
1. It is on a first-hand page: the pub's own website, the pub company's page for that specific pub, or the quiz company's own listing for that venue. Not a listings/review/news site.
2. It is at the pub named on the CANDIDATE line, or at a single clearly identified pub if the page is a quiz company or pub-group page. If a group site lists quizzes at several of its pubs, the one at THIS pub must be clearly identifiable.
3. It happens EVERY Tuesday (weekly). "Every Tuesday", "Tuesdays", "Tuesday nights", or a weekly what's-on schedule with Tuesday: Quiz all count. So does a dated listing showing the quiz on consecutive upcoming Tuesdays. "First Tuesday of the month", "every other Tuesday", "fortnightly", "monthly", a single one-off date, or "selected Tuesdays" are NOT weekly.
4. A start time for the quiz is given (e.g. 8pm, 7.30pm, 19:30, "7pm for a 7:30 start" means 19:30). If only a doors/booking time is given that is not clearly the quiz start, it is not confirmed.
5. Nothing suggests it has stopped: no "quiz is on a break/paused/returning in ...", no evidence that the only listings are old dated events (e.g. only 2023 or 2024 dates). A page with no dates at all is fine.

QUOTE RULES (a machine checks these, so be exact): "quote" must be copied character for character from the evidence text as one contiguous span (keep the page's capitals, punctuation and spacing; it may start and end mid-line, but must not join text from different lines unless they are adjacent in the file). Keep it under 220 characters. Together, quote plus any extra_quotes must contain the word Tuesday (or Tue/Tues/Tuesdays) AND the start time written as on the page. Prefer a single quote that has both. extra_quotes are for when the day and time are in different places on the same page (e.g. a heading "TUESDAY QUIZ" and a line "starts 8pm"); both must come from the SAME PAGE block as source_url.

source_url must be the exact url from the "=== PAGE <url>" line of the page the quote is on (the first url on that line, not the final url).
source_kind: "pub" (pub's own site), "company" (pub group's page for this pub), "host" (quiz company's listing).
start: 24-hour HH:MM.
address/postcode: as printed on the page if present, else empty. Do not guess.
pub_name: as the pub styles itself.
LISTING ENTRIES: some files are one venue's entry cut from a quiz company's or pub company's own list (the CANDIDATE line says so). There, the pub is the one named in the entry, and the page is first-hand. An entry that gives a weekday and a time as a regular slot (e.g. "Tuesday · 8pm", or "Day: Tuesday" with "Time: 19:30") counts as weekly only if the same page visibly marks its non-weekly entries as such (the file shows any it found, for context) and this entry carries no such mark. If the page usually writes the frequency on each entry (e.g. "Every Tuesday") and this entry has none, the verdict is unclear. "Returning soon", "Coming soon" or a start date means ended_or_stale. For such an entry the quote should hold the day/time line and the venue name, copied exactly; it may run across the adjacent lines of the entry. Venues outside London (e.g. Oxford, Windsor, Epsom) are not_this_pub.`

const READ = {
  type: 'object',
  properties: {
    results: { type: 'array', items: {
      type: 'object',
      properties: {
        id: { type: 'string' },
        verdict: { type: 'string', enum: ['confirmed', 'not_tuesday', 'not_weekly', 'no_start_time', 'ended_or_stale', 'not_this_pub', 'not_first_hand', 'no_quiz', 'unclear'] },
        pub_name: { type: 'string' },
        address: { type: 'string' },
        postcode: { type: 'string' },
        start: { type: 'string' },
        source_url: { type: 'string' },
        source_kind: { type: 'string', enum: ['pub', 'company', 'host', 'other', ''] },
        quote: { type: 'string' },
        extra_quotes: { type: 'array', items: { type: 'string' } },
        freq_note: { type: 'string', description: 'short phrase like "Every Tuesday"' },
        host: { type: 'string', description: 'quizmaster or quiz company if the page names one' },
        why: { type: 'string' },
      },
      required: ['id', 'verdict', 'why'],
    } },
  },
  required: ['results'],
}

const CHALLENGE = {
  type: 'object',
  properties: {
    results: { type: 'array', items: {
      type: 'object',
      properties: {
        id: { type: 'string' },
        refuted: { type: 'boolean' },
        problems: { type: 'array', items: { type: 'string' } },
        start_seen: { type: 'string', description: 'the quiz start time you read, HH:MM, or empty' },
      },
      required: ['id', 'refuted', 'problems'],
    } },
  },
  required: ['results'],
}

const batches = args.batches.map(b => b.map(id => ({ id, path: args.dir + '/' + id + '.txt' })))
log(`${batches.length} batches, ${batches.flat().length} candidates`)

const out = await pipeline(
  batches,
  (b, _, i) => agent(`${RULES}

Check each of these candidates. Read every evidence file listed, fully. Return one result per id.

${b.map(c => `- id ${c.id}: ${c.path}`).join('\n')}`, { label: `read:${i + 1}`, phase: 'Read', schema: READ }),
  (r, b, i) => {
    if (!r) return null
    const conf = r.results.filter(x => x.verdict === 'confirmed')
    if (!conf.length) return { read: r.results, challenge: [] }
    const pathOf = Object.fromEntries(b.map(c => [c.id, c.path]))
    return agent(`${RULES}

You are the SECOND reader, and your job is to try to REFUTE each claim below. Another reader said each of these pubs runs a quiz every Tuesday at the stated time. Open the evidence file and check, independently and sceptically:
(a) the quote appears in the evidence exactly as given, on the page named by source_url;
(b) it is a quiz, at THIS pub (the one on the CANDIDATE line, or the single venue a quiz-company page is about);
(c) it is weekly on Tuesdays, not monthly, fortnightly, occasional or a one-off;
(d) the stated start time is the QUIZ's start time on Tuesdays (not another event's, not another day's, not a doors time when a later start is given);
(e) nothing suggests it has stopped or that the listing is old;
(f) the page is first-hand (the pub's own site, its pub company's page for it, or the quiz company's own listing).
Set refuted=true if ANY of these fails or you cannot tell. Only set refuted=false if the evidence clearly supports every point. Report the start time you read yourself in start_seen.

${conf.map(x => `- id ${x.id} (${pathOf[x.id]}): "${x.pub_name}", Tuesday ${x.start}, source_url ${x.source_url}, quote: ${JSON.stringify(x.quote)}${(x.extra_quotes || []).length ? ', extra_quotes: ' + JSON.stringify(x.extra_quotes) : ''}`).join('\n')}`,
      { label: `challenge:${i + 1}`, phase: 'Challenge', schema: CHALLENGE })
      .then(c => ({ read: r.results, challenge: c ? c.results : null }))
  },
)
return out.filter(Boolean)
