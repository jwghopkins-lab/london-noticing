/* Every accepted answer must actually be accepted.
 *
 *   NODE_PATH=$(npm root -g) node pipeline/check_answers.cjs
 *
 * This exists because of a bug that reached a published build. The answer
 * normaliser strips filler words before comparing, and the filler list had
 * "two" and "pair" in it, added so that "a pair of unicorns" would match
 * "unicorns". The Crane's answer IS two. Typing "two" normalised to an empty
 * string and was marked wrong, and the hint pointed straight back at the word
 * that could not work. The only answer that got through was the digit.
 *
 * The end-to-end test did not catch it because it submits answers[0], which
 * happened to be "2". So this checks the whole matrix instead: every listed
 * answer, on every question, plus a set of answers that must NOT pass, so that
 * a matcher which simply says yes to everything fails too.
 *
 * It lifts the two functions out of the shipped page rather than reimplementing
 * them, so there is nothing to drift.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const page = fs.readFileSync(path.join(ROOT, "app", "index.html"), "utf8");
const src = page.match(/function normalise[\s\S]*?\n}\n[\s\S]*?function answerAccepted[\s\S]*?\n}/);
if (!src) {
  console.error("could not find normalise/answerAccepted in app/index.html");
  process.exit(2);
}
eval(src[0]);                                        // eslint-disable-line no-eval

// Things nobody should be let through with, whatever the question.
const MUST_FAIL = ["", "   ", "dunno", "no idea", "asdf", "banana", "skip", "1234567"];

let failures = 0;
function fail(msg) { failures++; console.log(`  FAIL  ${msg}`); }

// Every walk that has been built, not a named list. A walk that
// nobody remembered to add here would be a second walk nobody checked.
const dir = path.join(ROOT, "out", "walks");
const tours = (fs.existsSync(dir) ? fs.readdirSync(dir) : [])
  .filter((f) => f.endsWith(".json")).sort()
  .map((f) => [f.replace(/\.json$/, ""), path.join(dir, f)]);
if (!tours.length) { console.error("no built tours in out/walks"); process.exit(2); }

for (const [name, file] of tours) {
  if (!fs.existsSync(file)) { console.log(`  skip  ${name} (not built)`); continue; }
  const tour = JSON.parse(fs.readFileSync(file, "utf8"));
  let questions = 0, variants = 0;

  for (const stop of tour.stops) {
    if (!stop.question) continue;
    questions++;
    const accepted = stop.question.answers;

    for (const a of accepted) {
      variants++;
      if (!answerAccepted(a, accepted)) {
        fail(`${stop.id}: the listed answer "${a}" is rejected by the matcher `
           + `(normalises to "${normalise(a)}")`);
      }
      // Capitals and a trailing full stop are what a phone keyboard produces.
      for (const typed of [a.toUpperCase(), a[0].toUpperCase() + a.slice(1), a + ".", ` ${a} `]) {
        if (!answerAccepted(typed, accepted)) {
          fail(`${stop.id}: "${typed}" is rejected but "${a}" is accepted`);
        }
      }
    }

    for (const bad of MUST_FAIL) {
      if (answerAccepted(bad, accepted)) {
        fail(`${stop.id}: junk answer "${bad}" is accepted`);
      }
    }

    // Diacritics must not matter. Polish crossed L does not decompose under
    // NFD, so it has to be mapped by hand; without that "cegla" with the stroke
    // came out as "ceg a" and was rejected while the plain form worked.
    for (const a of accepted) {
      const stripped = a.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\u0142/g, "l");
      if (stripped !== a && !answerAccepted(stripped, accepted)) {
        fail(`${stop.id}: "${a}" is accepted but "${stripped}" without accents is not`);
      }
    }

    // One slip on a phone keyboard should not stop the walk. Only checked on
    // answers long enough for a single edit to be unambiguous.
    //
    // Typed from the answer as WRITTEN, not as normalised. Building the typo out
    // of the normalised form makes a liar of the test: "darkness" normalises to
    // "darknes" because the plural strip eats the last s, so a substitution on
    // top of that is two edits from what a person would actually type, and the
    // test failed on words nobody would ever enter.
    for (const a of accepted) {
      const w = String(a).toLowerCase().trim();
      if (w.length < 6 || w.includes(" ")) continue;
      const typos = [w.slice(0, -1), w + w.slice(-1), w.slice(0, 2) + w.slice(3),
                     w.slice(0, 2) + "x" + w.slice(3),
                     // two letters swapped, which is the commonest of all
                     w.slice(0, 2) + w[3] + w[2] + w.slice(4)];
      for (const t of typos) {
        if (!answerAccepted(t, accepted)) {
          fail(`${stop.id}: one-character typo "${t}" of "${a}" is rejected`);
        }
      }
    }

    // A number written as a word must work wherever a digit does, and the
    // other way round. This is the exact shape of the bug.
    const WORDS = { "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
                    "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten" };
    for (const [digit, word] of Object.entries(WORDS)) {
      const hasDigit = accepted.some((a) => String(a).trim() === digit);
      const hasWord = accepted.some((a) => String(a).trim().toLowerCase() === word);
      if (hasDigit && !hasWord) {
        fail(`${stop.id}: accepts "${digit}" but not "${word}"; add it`);
      }
      if (hasWord && !answerAccepted(word, accepted)) {
        fail(`${stop.id}: lists "${word}" but the matcher rejects it`);
      }
      if (hasDigit && !answerAccepted(word, accepted)) {
        fail(`${stop.id}: nobody types a digit; "${word}" must be accepted`);
      }
    }
  }
  // Being generous must not tip over into saying yes to anything. Every other
  // question's own answer has to be rejected here.
  const qs = tour.stops.filter((s) => s.question);
  for (const stop of qs) {
    for (const other of qs) {
      if (other.id === stop.id) continue;
      const theirs = other.question.answers.find((a) => /[a-z]/i.test(a));
      if (theirs && answerAccepted(theirs, stop.question.answers)) {
        fail(`${stop.id}: accepts "${theirs}", which is ${other.id}'s answer`);
      }
    }
  }

  console.log(`  ${name}: ${questions} questions, ${variants} listed answers checked, `
            + `${qs.length * (qs.length - 1)} cross-stop rejections checked`);
}

console.log(`\n${failures === 0 ? "every answer round-trips" : failures + " FAILED"}`);
process.exit(failures ? 1 : 0);
