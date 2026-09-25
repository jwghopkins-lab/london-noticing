// Fetch every page named in pub-quiz/fetch/request.json in a real browser and
// keep the words on it, so a quiz can be checked against what the pub itself
// says rather than what a listings site remembers.
//
// Runs on a GitHub runner: the authoring sandbox cannot reach pub websites.
// Many pub sites draw their what's-on list with JavaScript, so a plain HTTP
// get would see an empty page; this renders each one in Chromium first.
//
// For each candidate it fetches the URLs it was given, then follows up to
// FOLLOW same-site links whose address or label looks like a what's-on,
// events or quiz page, one level deep.
//
// Writes pub-quiz/data/fetched/<run>/pages.json.gz

import { chromium } from 'playwright'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const req = JSON.parse(readFileSync(join(HERE, 'request.json'), 'utf8'))
const OUT = join(HERE, '..', 'data', 'fetched', req.run)
const FOLLOW = 5
const CONCURRENCY = 8
const TEXT_CAP = 60000
const LINK_RE = /what.?s.?on|event|quiz|entertainment|weekly|calendar|diary|live|trivia|tuesday/i

const browser = await chromium.launch()
const results = {}

async function grab(url) {
  const ctx = await browser.newContext({
    locale: 'en-GB',
    timezoneId: 'Europe/London',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 1600 },
  })
  const page = await ctx.newPage()
  const rec = { url, fetched_at: new Date().toISOString() }
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 })
    rec.status = resp ? resp.status() : null
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})
    // Cookie walls and age gates hide the page on some pub sites.
    for (const label of [/^accept( all)?( cookies)?$/i, /^allow all/i, /^agree/i, /^i agree/i, /^got it/i, /^ok$/i, /^yes/i, /^i am (over )?18/i, /^enter/i]) {
      const b = page.getByRole('button', { name: label }).first()
      if (await b.isVisible({ timeout: 300 }).catch(() => false)) { await b.click({ timeout: 2000 }).catch(() => {}); await page.waitForTimeout(800) }
    }
    await page.waitForTimeout(1500)
    rec.final_url = page.url()
    rec.title = await page.title()
    rec.text = (await page.evaluate(() => document.body ? document.body.innerText : '')).replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').slice(0, TEXT_CAP)
    rec.frames = []
    for (const f of page.frames()) {
      if (f === page.mainFrame() || !f.url() || f.url().startsWith('about:')) continue
      const t = await f.evaluate(() => document.body ? document.body.innerText : '').catch(() => '')
      if (t && t.trim()) rec.frames.push({ url: f.url(), text: t.replace(/[ \t]+/g, ' ').slice(0, 20000) })
    }
    rec.ld_json = (await page.$$eval('script[type="application/ld+json"]', ns => ns.map(n => n.textContent))).map(s => s.slice(0, 8000)).slice(0, 6)
    const host = new URL(rec.final_url).host
    rec.links = (await page.$$eval('a[href]', as => as.map(a => ({ href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80) }))))
      .filter(l => { try { return new URL(l.href).host === host } catch { return false } })
      .filter(l => LINK_RE.test(l.href) || LINK_RE.test(l.text))
      .map(l => l.href.split('#')[0])
  } catch (e) {
    rec.error = String(e).slice(0, 300)
  } finally {
    await ctx.close().catch(() => {})
  }
  return rec
}

async function doCandidate(c) {
  const seen = new Set()
  const pages = []
  for (const u of c.urls) {
    if (seen.has(u)) continue
    seen.add(u)
    pages.push(await grab(u))
  }
  if (c.follow !== false) {
    const extra = [...new Set(pages.flatMap(p => p.links || []))].filter(u => !seen.has(u)).slice(0, FOLLOW)
    for (const u of extra) { seen.add(u); const p = await grab(u); p.followed = true; pages.push(p) }
  }
  for (const p of pages) delete p.links
  results[c.id] = pages
  const ok = pages.filter(p => p.text && p.text.length > 200).length
  console.log(`${c.id}: ${ok}/${pages.length} pages with text`)
}

const queue = [...req.pages]
await Promise.all(Array.from({ length: CONCURRENCY }, async () => {
  while (queue.length) await doCandidate(queue.shift())
}))
await browser.close()

mkdirSync(OUT, { recursive: true })
writeFileSync(join(OUT, 'pages.json.gz'), gzipSync(JSON.stringify(results)))
const n = Object.values(results).flat()
console.log(`done: ${n.length} pages, ${n.filter(p => p.error).length} errors, ${n.filter(p => (p.text || '').length > 200).length} with text`)
