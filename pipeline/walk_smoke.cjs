/* End-to-end smoke test: pick three topics, walk the route, exercise every
 * stop type and both sides of the location gate.
 *
 * Ported from the Fedora quest smoke test. It drives the real page against the
 * real baked artefacts over http, because the two things most likely to break
 * are a fetch path and a gate rule, and neither shows up in a unit test.
 *
 *   NODE_PATH=$(npm root -g) node pipeline/walk_smoke.cjs [--headed]
 *
 * Assumes a static server is already on http://127.0.0.1:8080 serving app/.
 */
const { chromium } = require("playwright");

const BASE = process.env.SMOKE_URL || "http://127.0.0.1:8080";
const HEADED = process.argv.includes("--headed");

let failures = 0;
function check(name, ok, detail) {
  if (ok) { console.log(`  ok    ${name}`); return true; }
  failures++;
  console.log(`  FAIL  ${name}${detail ? "  — " + detail : ""}`);
  return false;
}

// The word reveal is deliberately slow, so every assertion about text waits for
// it rather than racing it.
async function settled(page) {
  await page.waitForTimeout(150);
}

(async () => {
  const browser = await chromium.launch({ headless: !HEADED });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: "reduce",          // skip the reveal animation, not the logic
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await page.goto(BASE, { waitUntil: "networkidle" });

  /* ---- the picker ---- */
  const topics = page.locator("#picker .topic");
  check("five topics are offered", (await topics.count()) === 5,
        `saw ${await topics.count()}`);
  check("start is disabled with nothing chosen",
        await page.locator("#startbtn").isDisabled());

  const pick = async (name) => {
    await page.locator(".topic", { hasText: name }).first().click();
    await settled(page);
  };
  await pick("The Great Fire");
  await pick("Fleet Street");
  check("start is still disabled at two", await page.locator("#startbtn").isDisabled());
  await pick("Lost Rivers");
  check("start unlocks at three", await page.locator("#startbtn").isEnabled());

  // Four is refused, and the refusal explains itself rather than doing nothing.
  await pick("Roman London");
  check("a fourth topic is refused", (await page.locator(".topic.on").count()) === 3,
        `${await page.locator(".topic.on").count()} selected`);
  check("the refusal is explained", await page.locator("#toast.show").isVisible());

  // Order must not matter: the combo key is sorted before it is used.
  await pick("The Great Fire");                 // deselect
  await pick("The Great Fire");                 // reselect, now last
  check("still three after a swap out and back",
        (await page.locator(".topic.on").count()) === 3);

  await page.locator("#startbtn").click();
  await page.waitForSelector("#s-walk.on");
  check("the walk screen opens", await page.locator("#s-walk").isVisible());

  // The location pre-flight fires because this route has a gated stop.
  const preflight = page.locator("#modal.show");
  if (await preflight.isVisible()) {
    check("the location pre-flight appears before setting off", true);
    await page.locator("#lclater").click();
    await settled(page);
  } else {
    check("the location pre-flight appears before setting off", false, "no modal");
  }

  check("progress starts at zero of three",
        (await page.locator("#progresstext").textContent()) === "0/3");

  /* ---- stop 1: a plain stop ---- */
  let card = page.locator(".stop.open");
  check("stop 1 is St Bride's",
        (await card.locator(".stitle").textContent()).includes("St Bride"));
  check("stop 1 is not gated", (await card.locator(".gatebtn").count()) === 0);
  check("stop 1 has no soft prompt", (await card.locator(".nudge").count()) === 0);
  await card.locator(".srow .btn").click();
  await settled(page);
  check("the explainer arrives on stop 1",
        (await page.locator(".stop.open .after").textContent()).includes("wedding cake"));
  await page.locator(".stop.open .srow .btn").click();
  await page.waitForFunction(() =>
    document.querySelector("#progresstext").textContent === "1/3");

  /* ---- stop 2: a soft prompt ---- */
  card = page.locator(".stop.open");
  check("stop 2 is the clock",
        (await card.locator(".stitle").textContent()).includes("clock"));
  check("stop 2 asks whether you have found it",
        (await card.locator(".nudge").textContent()).includes("Have you found"));
  check("the button carries the confirm wording",
        (await card.locator(".srow .btn").textContent()).trim() === "Found them");
  await card.locator(".srow .btn").click();
  await settled(page);
  check("the explainer arrives on stop 2",
        (await page.locator(".stop.open .after").textContent()).includes("minute hand"));
  check("the finished stop above is still readable",
        (await page.locator(".stop.done .after").first().textContent()).length > 50);
  await page.locator(".stop.open .srow .btn").click();
  await page.waitForFunction(() =>
    document.querySelector("#progresstext").textContent === "2/3");

  /* ---- stop 3: the location gate ---- */
  card = page.locator(".stop.open");
  check("stop 3 is gated", (await card.locator(".gatebtn").count()) === 1);
  check("the gate withholds the text until you are there",
        (await card.locator(".stext").count()) === 0);

  // Stand well away. The gate must refuse, and must say warm or cold, never no.
  await page.locator("#simbtn").click();
  await page.locator("#simlist button", { hasText: "500 m away" }).click();
  await settled(page);
  check("the testing banner is visible while simulating",
        await page.locator("#simbanner").isVisible());
  await page.locator(".stop.open .gatebtn").click();
  await page.waitForFunction(() =>
    (document.querySelector(".stop.open .gatestat") || {}).textContent
      ?.match(/away|Warm/));
  const refusal = await page.locator(".stop.open .gatestat").textContent();
  check("a distant gate refuses", (await page.locator(".stop.open .stext").count()) === 0);
  check("the refusal gives a distance, not a no", /away|Warm/.test(refusal), refusal);
  check("the gate never says the word no", !/\bno\b/i.test(refusal), refusal);

  // Now stand on the spot.
  await page.locator("#simbtn").click();
  await page.locator("#simlist button", { hasText: "Stand at stop 3" }).click();
  await settled(page);
  await page.locator(".stop.open .gatebtn").click();
  await page.waitForSelector(".stop.open .stext");
  check("standing there opens the stop",
        (await page.locator(".stop.open .stext").textContent()).includes("bridge"));

  await page.locator(".stop.open .srow .btn").click();
  await settled(page);
  check("the explainer arrives on stop 3",
        (await page.locator(".stop.open .after").textContent()).includes("Fleet"));
  check("the last stop offers to finish",
        (await page.locator(".stop.open .srow .btn").textContent()).includes("Finish"));
  await page.locator(".stop.open .srow .btn").click();
  await page.waitForFunction(() =>
    document.querySelector("#progresstext").textContent === "3/3");
  check("the walk ends", (await page.locator("#walk").textContent()).includes("That is the walk"));

  /* ---- coming back to it ---- */
  await page.reload({ waitUntil: "networkidle" });
  check("progress survives a reload",
        (await page.locator("#progresstext").textContent()) === "3/3");
  const afters = await page.locator(".stop.done .after").count();
  check("every explainer is still there after a reload", afters >= 3, `${afters} of 3`);

  check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

  await browser.close();
  console.log(`\n${failures === 0 ? "all checks passed" : failures + " FAILED"}`);
  process.exit(failures ? 1 : 0);
})().catch((err) => {
  console.error("smoke test crashed:", err);
  process.exit(2);
});
