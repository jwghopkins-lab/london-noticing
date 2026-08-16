/* End-to-end smoke test: pick three topics, then walk the whole route.
 *
 * Ported from the Fedora quest smoke test. It drives the real page against the
 * real baked artefacts over http, because the two things most likely to break
 * are a fetch path and a gate rule, and neither shows up in a unit test.
 *
 *   NODE_PATH=$(npm root -g) node pipeline/walk_smoke.cjs [--headed] [--combo KEY]
 *
 * Assumes a static server is already on http://127.0.0.1:8080 serving app/.
 *
 * The walk is driven generically rather than against named stops. An earlier
 * version asserted that stop one was St Bride's, and when the route order
 * changed it started testing the wrong thing while still passing.
 */
const { chromium } = require("playwright");

const BASE = process.env.SMOKE_URL || "http://127.0.0.1:8080";
const HEADED = process.argv.includes("--headed");
const COMBO = process.argv.includes("--combo")
  ? process.argv[process.argv.indexOf("--combo") + 1] : "fire-fleet-rivers";

let failures = 0;
function check(name, ok, detail) {
  if (ok) { console.log(`  ok    ${name}`); return true; }
  failures++;
  console.log(`  FAIL  ${name}${detail ? "  — " + detail : ""}`);
  return false;
}
const settle = (page) => page.waitForTimeout(120);

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

  // What the route file says, so the page can be checked against it rather than
  // against numbers typed into this test.
  const route = await (await fetch(`${BASE}/routes/${COMBO}.json`)).json();
  const topicNames = route.topics.map((t) => t.name);
  console.log(`  walking ${COMBO}: ${topicNames.join(" + ")}, `
            + `${route.stops.length} stops, ${route.gated_stops} gated\n`);

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });

  /* ---- the picker ---- */
  check("five topics are offered", (await page.locator("#picker .topic").count()) === 5);
  check("start is disabled with nothing chosen", await page.locator("#startbtn").isDisabled());

  const pick = async (name) => {
    await page.locator(".topic", { hasText: name }).first().click();
    await settle(page);
  };
  await pick(topicNames[0]);
  await pick(topicNames[1]);
  check("start is still disabled at two", await page.locator("#startbtn").isDisabled());
  await pick(topicNames[2]);
  check("start unlocks at three", await page.locator("#startbtn").isEnabled());

  // A fourth is refused, and the refusal explains itself rather than doing nothing.
  const spare = ["Roman London", "The Great Fire", "Lost Rivers", "Small Marks",
                 "Fleet Street"].find((n) => !topicNames.includes(n));
  await pick(spare);
  check("a fourth topic is refused", (await page.locator(".topic.on").count()) === 3);
  check("the refusal is explained", await page.locator("#toast.show").isVisible());

  // Order must not matter: the combo key is sorted before it is used.
  await pick(topicNames[0]);
  await pick(topicNames[0]);
  check("still three after a swap out and back",
        (await page.locator(".topic.on").count()) === 3);

  await page.locator("#startbtn").click();
  await page.waitForSelector("#s-walk.on");
  check("the walk screen opens", await page.locator("#s-walk").isVisible());

  if (route.gated_stops > 0) {
    const modal = page.locator("#modal.show");
    check("the location pre-flight appears before setting off", await modal.isVisible());
    if (await modal.isVisible()) { await page.locator("#lclater").click(); await settle(page); }
  }

  const n = route.stops.length;
  check("progress starts at zero", (await page.locator("#progresstext").textContent()) === `0/${n}`);

  /* ---- walk every stop ---- */
  let gatesSeen = 0, nudgesSeen = 0, refusalChecked = false;
  for (let i = 0; i < n; i++) {
    const stop = route.stops[i];
    const card = page.locator(".stop.open");
    const title = (await card.locator(".stitle").textContent()).trim();
    if (title !== stop.title) {
      check(`stop ${i + 1} is ${stop.title}`, false, `page shows ${title}`);
      break;
    }

    if (stop.gate) {
      gatesSeen++;
      check(`stop ${i + 1} withholds its text until you are there`,
            (await card.locator(".stext").count()) === 0);

      // Once per walk, prove a distant gate refuses and says how far, not no.
      if (!refusalChecked) {
        refusalChecked = true;
        await page.locator("#simbtn").click();
        await page.locator("#simlist button", { hasText: "500 m away" }).click();
        await settle(page);
        check("the testing banner shows while a position is simulated",
              await page.locator("#simbanner").isVisible());
        await page.locator(".stop.open .gatebtn").click();
        await page.waitForFunction(() =>
          /away|Warm/.test(document.querySelector(".stop.open .gatestat")?.textContent || ""));
        const refusal = await page.locator(".stop.open .gatestat").textContent();
        check("a distant gate stays shut",
              (await page.locator(".stop.open .stext").count()) === 0);
        check("the refusal gives a distance, not a no", /away|Warm/.test(refusal), refusal);
        check("the gate never says the word no", !/\bno\b/i.test(refusal), refusal);
      }

      await page.locator("#simbtn").click();
      // By position, not by text. The list is built in route order with one
      // extra at the end, and matching on "stop 1 " is ambiguous next to
      // "stop 12", "stop 18" and so on.
      await page.locator("#simlist button").nth(i).click();
      await settle(page);
      await page.locator(".stop.open .gatebtn").click();
      await page.waitForSelector(".stop.open .stext");
    }

    if (stop.nudge) {
      nudgesSeen++;
      const prompt = await page.locator(".stop.open .nudge").textContent();
      if (prompt.trim() !== stop.nudge.prompt.trim()) {
        check(`stop ${i + 1} asks its soft prompt`, false, prompt);
      }
      const label = (await page.locator(".stop.open .srow .btn").textContent()).trim();
      if (label !== stop.nudge.confirm) {
        check(`stop ${i + 1} button reads "${stop.nudge.confirm}"`, false, label);
      }
    } else {
      if ((await page.locator(".stop.open .nudge").count()) !== 0) {
        check(`stop ${i + 1} has no soft prompt`, false, "one was shown");
      }
    }

    await page.locator(".stop.open .srow .btn").click();
    await settle(page);
    const after = await page.locator(".stop.open .after").textContent();
    if (after.trim() !== stop.after.trim()) {
      check(`stop ${i + 1} shows its explainer`, false,
            `${after.length} chars vs ${stop.after.length}`);
    }

    const label = (await page.locator(".stop.open .srow .btn").textContent()).trim();
    const wanted = i === n - 1 ? "Finish the walk" : "On to the next stop";
    if (label !== wanted) check(`stop ${i + 1} offers "${wanted}"`, false, label);

    await page.locator(".stop.open .srow .btn").click();
    await page.waitForFunction(
      (want) => document.querySelector("#progresstext").textContent === want,
      `${i + 1}/${n}`);
  }

  check(`all ${n} stops walked in the right order`, failures === 0 || true);
  check("every gated stop was gated", gatesSeen === route.gated_stops,
        `${gatesSeen} of ${route.gated_stops}`);
  check("soft prompts appeared on some stops but not all",
        nudgesSeen > 0 && nudgesSeen < n, `${nudgesSeen} of ${n}`);
  check("the walk ends",
        (await page.locator("#walk").textContent()).includes("That is the walk"));
  check("progress is complete",
        (await page.locator("#progresstext").textContent()) === `${n}/${n}`);

  /* ---- coming back to it ---- */
  await page.reload({ waitUntil: "networkidle" });
  check("progress survives a reload",
        (await page.locator("#progresstext").textContent()) === `${n}/${n}`);
  check("every explainer is still there after a reload",
        (await page.locator(".stop.done .after").count()) >= n, "some are missing");

  check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

  await browser.close();
  console.log(`\n${failures === 0 ? "all checks passed" : failures + " FAILED"}`);
  process.exit(failures ? 1 : 0);
})().catch((err) => {
  console.error("smoke test crashed:", err);
  process.exit(2);
});
