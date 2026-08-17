/* End-to-end test for the Gdansk walk, against the single file build.
 *
 *   NODE_PATH=$(npm root -g) node pipeline/amber_smoke.cjs [--headed]
 *
 * The walk is one stage per stop. A stage is a single block of text carrying,
 * in order: what the last answer meant, how to walk here, what to look at, and
 * the question. Then one thing to do. So most of what this checks is that the
 * right things are in the right block, in the right order, and only once.
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const FILE = "file://" + path.resolve(__dirname, "..", "dist", "amber-mile.html");
const TOUR = JSON.parse(fs.readFileSync(
  path.resolve(__dirname, "..", "out", "gdansk", "amber-mile.json"), "utf8"));

let failures = 0;
function check(name, ok, detail) {
  if (ok) { console.log(`  ok    ${name}`); return true; }
  failures++;
  console.log(`  FAIL  ${name}${detail ? "  — " + detail : ""}`);
  return false;
}
const settle = (p) => p.waitForTimeout(140);
const squash = (t) => t.replace(/\s+/g, " ").trim();

(async () => {
  const browser = await chromium.launch({ headless: !process.argv.includes("--headed") });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  // Everything is inlined, so block the network: this has to work with no signal.
  await page.route("**/*", (r) => r.request().url().startsWith("file:")
    ? r.continue() : r.abort());

  const n = TOUR.stops.length;
  console.log(`  ${TOUR.name}: ${n} stops, ${TOUR.question_stops} questions, `
            + `${TOUR.gated_stops} location gates, `
            + `${(TOUR.walk.total_walk_m / 1000).toFixed(2)} km\n`);

  await page.goto(FILE + "?testing=1");
  await page.waitForSelector("#startbtn");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector("#startbtn");

  check("no topic picker on a fixed tour", !(await page.locator("#picker").isVisible()));
  check("the intro says where to start",
        (await page.locator(".intro").textContent()).includes("Upland Gate"));

  await page.locator("#startbtn").click();
  await page.waitForSelector("#s-walk.on");
  if (await page.locator("#modal.show").isVisible()) await page.locator("#lclater").click();
  await settle(page);
  check("progress starts at zero",
        (await page.locator("#progresstext").textContent()) === `0/${n}`);

  let asked = 0, gated = 0, passUsed = 0, toldAt = -1;
  for (let i = 0; i < n; i++) {
    const stop = TOUR.stops[i];
    const prev = i > 0 ? TOUR.stops[i - 1] : null;
    const card = page.locator(".stop.open");
    const title = squash(await card.locator(".stitle").textContent());
    if (title !== stop.title) {
      check(`stage ${i + 1} is ${stop.title}`, false, `page shows ${title}`);
      break;
    }

    // Before answering there is exactly one block: the way there.
    check(`stage ${i + 1} shows one block before you answer`,
          (await card.locator(".stext").count()) === 1);
    const text = squash(await card.locator(".stext").textContent());
    check(`stage ${i + 1} does not give the pay-off away early`,
          !text.includes(squash(stop.after).slice(0, 40)));

    if (prev) {
      // Turn-by-turn directions already say which way and how far. A computed
      // heading on top of them repeated the distance and disagreed with it:
      // 152 metres straight-line-times-detour above a hand-measured 120.
      check(`stage ${i + 1} states its distance once`,
            text.startsWith(squash(stop.directions).slice(0, 30)), text.slice(0, 50));
      const metres = (text.match(/\b\d+\s*metres\b/g) || []);
      check(`stage ${i + 1} has no computed distance bolted on`,
            metres.length === 0, metres.join(", "));
      const dirAt = text.indexOf(squash(stop.directions).slice(0, 40));
      const lookAt = text.indexOf(squash(stop.look).slice(0, 40));
      check(`stage ${i + 1} starts by saying how to walk here`, dirAt === 0 || dirAt > 0);
      check(`stage ${i + 1} puts the directions before what to look at`,
            lookAt > dirAt, `${dirAt} then ${lookAt}`);
    }
    check(`stage ${i + 1} says what to look at`,
          text.includes(squash(stop.look).slice(0, 40)));

    if (stop.question) {
      asked++;
      const ask = squash(stop.question.ask);
      check(`stage ${i + 1} ends with the question`, text.endsWith(ask), text.slice(-45));
      check(`stage ${i + 1} does not ask the same thing twice`,
            text.indexOf(ask) === text.lastIndexOf(ask));
      check(`stage ${i + 1} has an answer box and no pass button`,
            (await card.locator(".qrow input").count()) === 1
            && (await card.locator(".gateskip").count()) === 0);
      check(`stage ${i + 1} offers a tell-me from the start`,
            (await card.locator(".qgiveup").count()) === 1);

      if (asked === 1) {
        await card.locator(".qrow input").fill("banana");
        await card.locator(".qrow .btn").click();
        await page.waitForTimeout(220);
        check("a wrong answer does not move you on",
              (await page.locator("#progresstext").textContent()) === `${i}/${n}`);
        await page.locator(".stop.open .qrow input").fill("banana");
        await page.locator(".stop.open .qrow .btn").click();
        await page.waitForTimeout(260);
        check("the hint arrives after two wrong answers",
              (await page.locator(".stop.open .qhint").count()) === 1);
      }

      // Prefer a word over a digit. Nobody types a digit, and the digit is what
      // hid a rejected "two" in a published build.
      const use = stop.question.answers.find((a) => /[a-z]/i.test(a))
                  || stop.question.answers[0];
      const told = (toldAt < 0 && asked === 2);
      if (told) {
        toldAt = i;                                 // once per walk, ask to be told
        await page.locator(".stop.open .qgiveup").click();
      } else {
        await page.locator(".stop.open .qrow input").fill(use);
        await page.locator(".stop.open .qrow .btn").click();
      }
      await page.waitForTimeout(300);
      check(`stage ${i + 1} stays put until you press on`,
            (await page.locator("#progresstext").textContent()) === `${i}/${n}`);
      const both = await page.locator(".stop.open .stext").allTextContents();
      check(`stage ${i + 1} then adds the pay-off as a second block`,
            both.length === 2 && squash(both[1]).includes(squash(stop.after).slice(0, 40)),
            `${both.length} blocks`);
      if (told) {
        check("being told says what the answer was",
              squash(both[1]).startsWith(`The answer was ${use}`), squash(both[1]).slice(0, 40));
      }
    } else if (stop.gate) {
      gated++;
      check(`stage ${i + 1} has a location check and a pass button`,
            (await card.locator(".gatebtn").count()) === 1
            && (await card.locator(".gateskip").count()) === 1);
      check(`stage ${i + 1} has no answer box`,
            (await card.locator(".qrow input").count()) === 0);

      if (passUsed === 0) {
        passUsed++;
        await card.locator(".gateskip").click();    // what the pass button is for
        await page.waitForTimeout(300);
        check("the pass button opens the pay-off without moving you on",
              (await page.locator("#progresstext").textContent()) === `${i}/${n}`
              && (await page.locator(".stop.open .stext").count()) === 2);
      } else {
        await card.locator('.devrow [data-act="start"]').click();
        await settle(page);
        await page.locator(".stop.open .gatebtn").click();
        await page.waitForTimeout(280);
        check(`stage ${i + 1} stays shut from 500 m away`,
              (await page.locator(".stop.open .stext").count()) === 1);
        // Check between every action rather than only at the top. The gate opens
        // the moment a stride lands inside the radius, and the controls vanish
        // with it, so a blind click on the next line times out.
        let strides = 0;
        while (strides < 12) {
          if ((await page.locator(".stop.open .stext").count()) === 2) break;
          if (!(await page.locator('.stop.open .devrow [data-act="step"]').count())) break;
          strides++;
          await page.locator('.stop.open .devrow [data-act="step"]').click();
          await settle(page);
          if (!(await page.locator(".stop.open .gatebtn").count())) break;
          await page.locator(".stop.open .gatebtn").click();
          await page.waitForTimeout(260);
        }
        check(`stage ${i + 1} took a real approach to open`, strides >= 3, `${strides} strides`);
      }
    }

    // The pay-off is read where it was earned, and a button moves you on.
    const nextLabel = (await page.locator(".stop.open .srow .btn").textContent()).trim();
    const wantLabel = i === n - 1 ? "Finish the walk" : `On to stop ${i + 2}`;
    check(`stage ${i + 1} offers "${wantLabel}"`, nextLabel === wantLabel, nextLabel);
    await page.locator(".stop.open .srow .btn").click();
    await page.waitForFunction(
      (want) => document.querySelector("#progresstext").textContent === want,
      `${i + 1}/${n}`);
  }

  check("seven stops asked a question", asked === 7, `${asked}`);
  check("three stops were location gated", gated === 3, `${gated}`);
  check("every stage is one card",
        (await page.locator("#walk .stop").count()) === n + 1,
        `${await page.locator("#walk .stop").count()}`);
  // The last card is the tour's own outro and nothing else. It used to be
  // followed by a line restating the distance and the stop count, which is the
  // one moment nobody needs the numbers back.
  const ending = squash(await page.locator("#walk .stop").last().textContent());
  check("the walk ends on its own last line", ending === squash(TOUR.outro), ending.slice(-60));

  await page.reload();
  await page.waitForSelector("#s-walk.on");
  check("progress survives a reload",
        (await page.locator("#progresstext").textContent()) === `${n}/${n}`);
  check("and the whole story is still there",
        (await page.locator("#walk .stop").count()) === n + 1);
  check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

  /* ---- the reveal has to be followable ----
     Everything above runs with reduced motion so it is not racing an animation.
     This part turns motion on. The directions once shipped with no animation at
     all, and the page scrolled past them, so the one thing you have to read was
     the easiest thing to miss. */
  {
    const live = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const lp = await live.newPage();
    await lp.route("**/*", (r) => r.request().url().startsWith("file:")
      ? r.continue() : r.abort());
    await lp.goto(FILE);
    await lp.evaluate(() => localStorage.clear());
    await lp.reload();
    await lp.waitForSelector("#startbtn");
    await lp.locator("#startbtn").click();
    await lp.waitForSelector("#s-walk.on");
    if (await lp.locator("#modal.show").isVisible()) await lp.locator("#lclater").click();
    await lp.waitForTimeout(2800);

    const r = await lp.evaluate(() => {
      const card = document.querySelector(".stop.open");
      return { words: card.querySelectorAll(".stext .w").length,
               shown: card.querySelectorAll(".stext .w.on").length,
               tip: !!card.querySelector(".skiptip"),
               top: card.getBoundingClientRect().top };
    });
    check("the first block reveals a word at a time", r.words > 20, `${r.words} words`);
    check("and is still going after a moment",
          r.shown > 0 && r.shown < r.words, `${r.shown}/${r.words}`);
    check("and says you can tap to see it all", r.tip);
    check("and is on screen while it does it",
          r.top > -20 && r.top < 700, `top ${Math.round(r.top)}`);

    await lp.locator(".stitle").first().click();
    await lp.waitForTimeout(250);
    const after = await lp.evaluate(() => {
      const card = document.querySelector(".stop.open");
      return { pending: card.querySelectorAll(".stext .w").length,
               tip: !!card.querySelector(".skiptip") };
    });
    check("tapping finishes it at once", after.pending === 0, `${after.pending} left`);
    check("and the tip goes away", !after.tip);
    await live.close();
  }

  await browser.close();
  console.log(`\n${failures === 0 ? "all checks passed" : failures + " FAILED"}`);
  process.exit(failures ? 1 : 0);
})().catch((err) => { console.error("smoke test crashed:", err); process.exit(2); });
