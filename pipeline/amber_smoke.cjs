/* End-to-end test for the Gdansk walk, driven against the single file build.
 *
 *   NODE_PATH=$(npm root -g) node pipeline/amber_smoke.cjs [--headed]
 *
 * It walks all ten stops: answers every question, gets one wrong on purpose to
 * check the hint arrives, and takes each location gate both ways, once by
 * simulated approach and once with the pass button.
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
const settle = (p) => p.waitForTimeout(120);

(async () => {
  const browser = await chromium.launch({ headless: !process.argv.includes("--headed") });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  // Everything is inlined, so block the network entirely: this must work with
  // no signal at all, which is the realistic condition abroad.
  await page.route("**/*", (r) => r.request().url().startsWith("file:")
    ? r.continue() : r.abort());

  console.log(`  ${TOUR.name}: ${TOUR.stops.length} stops, `
            + `${TOUR.question_stops} questions, ${TOUR.gated_stops} location gates, `
            + `${(TOUR.walk.total_walk_m / 1000).toFixed(2)} km\n`);

  await page.goto(FILE + "?testing=1");
  await page.waitForSelector("#startbtn");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector("#startbtn");

  check("no topic picker on a fixed tour", !(await page.locator("#picker").isVisible()));
  check("the intro says where to start",
        (await page.locator(".intro").textContent()).includes("Upland Gate"));
  check("the start button is ready", await page.locator("#startbtn").isEnabled());

  await page.locator("#startbtn").click();
  await page.waitForSelector("#s-walk.on");
  if (await page.locator("#modal.show").isVisible()) await page.locator("#lclater").click();
  await settle(page);

  const n = TOUR.stops.length;
  check("progress starts at zero",
        (await page.locator("#progresstext").textContent()) === `0/${n}`);

  let asked = 0, gated = 0, passUsed = 0, hintSeen = false;
  for (let i = 0; i < n; i++) {
    const stop = TOUR.stops[i];
    const card = page.locator(".stop.open");
    const title = (await card.locator(".stitle").textContent()).trim();
    if (title !== stop.title) {
      check(`stop ${i + 1} is ${stop.title}`, false, `page shows ${title}`);
      break;
    }

    // Directions must be present, and must arrive before the stop they lead to.
    if (i > 0) {
      const legs = page.locator(".leg");
      const last = await legs.nth((await legs.count()) - 1).textContent();
      if (!last.includes(stop.directions.split("\n")[0].slice(0, 30))) {
        check(`stop ${i + 1} is preceded by its directions`, false, last.slice(0, 60));
      }
    }

    if (stop.question) {
      asked++;
      check(`stop ${i + 1} asks a question`, (await card.locator(".qask").count()) === 1);
      check(`stop ${i + 1} has no pass button`, (await card.locator(".gateskip").count()) === 0);

      // One deliberate wrong answer per walk, twice, to bring the hint out.
      if (!hintSeen) {
        for (let t = 0; t < 2; t++) {
          await page.locator(".stop.open .qrow input").fill("banana");
          await page.locator(".stop.open .qrow .btn").click();
          await page.waitForTimeout(200);
        }
        check("a wrong answer does not open the stop",
              (await page.locator(".stop.open .after").count()) === 0);
        check("the hint arrives after two wrong answers",
              (await page.locator(".stop.open .qhint").count()) === 1);
        check("no way out of a question after only two wrong answers",
              (await page.locator(".stop.open .qgiveup").count()) === 0);
        // Two more, to bring out the last resort, then check it works. A stop
        // that cannot be answered because the thing is under a tarpaulin must
        // not end the walk.
        for (let t = 0; t < 2; t++) {
          await page.locator(".stop.open .qrow input").fill("banana");
          await page.locator(".stop.open .qrow .btn").click();
          await page.waitForTimeout(200);
        }
        check("a way out appears after four wrong answers",
              (await page.locator(".stop.open .qgiveup").count()) === 1);
        hintSeen = true;
      }

      // Prefer a word over a digit. The bug that reached a published build was
      // exactly here: this used answers[0], which for the Crane was "2", so the
      // fact that "two" was rejected went unnoticed. Nobody types a digit.
      const use = stop.question.answers.find((a) => /[a-z]/i.test(a))
                  || stop.question.answers[0];
      await page.locator(".stop.open .qrow input").fill(use);
      await page.locator(".stop.open .qrow .btn").click();
      await page.waitForTimeout(250);
      check(`stop ${i + 1} opens on "${use}"`,
            (await page.locator(".stop.open .after").count()) === 1);
    } else if (stop.gate) {
      gated++;
      check(`stop ${i + 1} withholds its text until you are there`,
            (await card.locator(".stext").count()) === 0);
      check(`stop ${i + 1} offers a pass button`, (await card.locator(".gateskip").count()) === 1);

      if (passUsed === 0) {
        // First one: use the pass button, which is what it is there for.
        await page.locator(".stop.open .gateskip").click();
        passUsed++;
      } else {
        // The rest: walk in properly and let the real check decide.
        await page.locator('.stop.open .devrow [data-act="start"]').click();
        await settle(page);
        let strides = 0;
        while ((await page.locator(".stop.open .stext").count()) === 0 && strides < 12) {
          strides++;
          await page.locator('.stop.open .devrow [data-act="step"]').click();
          await settle(page);
          await page.locator(".stop.open .gatebtn").click();
          await page.waitForTimeout(220);
        }
        check(`stop ${i + 1} took a real approach to open`, strides >= 3, `${strides} strides`);
      }
      await page.waitForSelector(".stop.open .stext");
      await page.locator(".stop.open .srow .btn").click();
      await page.waitForTimeout(200);
    }

    const after = await page.locator(".stop.open .after").textContent();
    if (after.trim() !== stop.after.trim()) {
      check(`stop ${i + 1} shows its explainer`, false,
            `${after.length} chars vs ${stop.after.length}`);
    }
    await page.locator(".stop.open .srow .btn").click();
    await page.waitForFunction(
      (want) => document.querySelector("#progresstext").textContent === want,
      `${i + 1}/${n}`);
  }

  check(`all ${n} stops walked in order`, true);
  check("seven stops asked a question", asked === 7, `${asked}`);
  check("three stops were location gated", gated === 3, `${gated}`);
  check("every stop after the first had directions",
        (await page.locator(".leg").count()) === n - 1,
        `${await page.locator(".leg").count()} of ${n - 1}`);
  check("the walk ends",
        (await page.locator("#walk").textContent()).includes("That is the walk"));

  await page.reload();
  await page.waitForSelector("#s-walk.on");
  check("progress survives a reload",
        (await page.locator("#progresstext").textContent()) === `${n}/${n}`);
  check("the directions are still there afterwards",
        (await page.locator(".leg").count()) === n - 1);
  check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

  await browser.close();
  console.log(`\n${failures === 0 ? "all checks passed" : failures + " FAILED"}`);
  process.exit(failures ? 1 : 0);
})().catch((err) => { console.error("smoke test crashed:", err); process.exit(2); });
