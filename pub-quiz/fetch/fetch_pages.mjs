// Fetch every page named in pub-quiz/fetch/request.json in a real browser and
// keep the words on it, so a quiz can be checked against what the pub itself
// says rather than what a listings site remembers.
//
// Runs on a GitHub runner: the authoring sandbox cannot reach pub websites.
// Many pub sites draw their what's-on list with JavaScript, so a plain HTTP
// get would see an empty page; this renders each one in Chromium first.
//
// For each entry it fetches the URLs given, then follows up to `follow`
// same-site links whose address or label looks like a what's-on, events or
// quiz page, one level deep. That is how a pub's homepage leads to the page
// that actually lists its quiz.
//
// The request can be split across runners: SHARD and SHARDS pick every
// SHARDS-th entry starting at SHARD. A page's text is kept only if it mentions
// a quiz (unless the entry says keep: "all"), which keeps a crawl of a few
// thousand pub sites small enough to commit.
//
// Writes pub-quiz/data/fetched/<run>/pages-<shard>.json.gz

import { chromium } from 'playwright'
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
// make_crawl.py writes crawl.json (the request plus every pub website); without
// it, the request's own pages are the whole list.
const req = JSON.parse(readFileSync(join(HERE, existsSync(join(HERE, 'crawl.json')) ? 'crawl.json' : 'request.json'), 'utf8'))
const SHARD = Number(process.env.SHARD || 0)
const SHARDS = Number(process.env.SHARDS || 1)
const OUT = join(HERE, '..', 'data', 'fetched', req.run)
const CONCURRENCY = Number(process.env.CONCURRENCY || 6)
const TEXT_CAP = 60000
const LINK_RE = /what.?s.?on|event|quiz|entertainment|weekly|calendar|diary|trivia|tuesday|happenings|live-music|whats/i
const SKIP_HOST = /(^|\.)(facebook|instagram|twitter|x|tiktok|linktr|youtube|google|goo|bit|tripadvisor|opentable|resy|sevenrooms|designmynight|ubereats|deliveroo|just-eat)\.[a-z.]+$/i
const QUIZ = /quiz|trivia/i

const entries = req.pages.filter((_, i) => i % SHARDS === SHARD)
const browser = await chromium.launch({ args: ['--disable-blink-features=AutomationControlled'] })
const results = {}
let done = 0

async function grab(url, keep, followRe) {
  const rec = { url, fetched_at: new Date().toISOString() }
  let host
  try { host = new URL(url).hostname } catch { rec.error = 'bad url'; return rec }
  if (keep !== 'all' && SKIP_HOST.test(host)) { rec.error = 'skipped: social or booking site'; return rec }
  const ctx = await browser.newContext({
    locale: 'en-GB',
    timezoneId: 'Europe/London',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 1600 },
  })
  await ctx.route('**/*', r => ['image', 'media', 'font'].includes(r.request().resourceType()) ? r.abort() : r.continue())
  await ctx.addInitScript(() => { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) })
  const page = await ctx.newPage()
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 })
    rec.status = resp ? resp.status() : null
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
    // A bot check ("Just a moment...") sometimes clears itself if given time.
    for (let i = 0; i < 8 && /just a moment|attention required|checking your browser/i.test(await page.title().catch(() => '')); i++) await page.waitForTimeout(2000)
    rec.status = /just a moment|attention required/i.test(await page.title().catch(() => '')) ? 'blocked' : rec.status
    // Cookie walls and age gates hide the page on some pub sites.
    const gate = page.getByRole('button', { name: /^(accept( all)?( cookies)?|allow all( cookies)?|i agree|agree|got it|ok|yes|i am (over )?18|enter( site)?)\b/i }).first()
    if (await gate.isVisible({ timeout: 500 }).catch(() => false)) { await gate.click({ timeout: 2000 }).catch(() => {}); await page.waitForTimeout(800) }
    await page.waitForTimeout(1200)
    rec.final_url = page.url()
    rec.title = (await page.title()).slice(0, 200)
    const text = (await page.evaluate(() => document.body ? document.body.innerText : '')).replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n')
    const frames = []
    for (const f of page.frames()) {
      if (f === page.mainFrame() || !f.url() || f.url().startsWith('about:')) continue
      const t = await f.evaluate(() => document.body ? document.body.innerText : '').catch(() => '')
      if (t && t.trim()) frames.push({ url: f.url(), text: t.replace(/[ \t]+/g, ' ').slice(0, 20000) })
    }
    rec.chars = text.length
    rec.has_quiz = QUIZ.test(text) || frames.some(f => QUIZ.test(f.text))
    if (keep === 'all' || rec.has_quiz) {
      rec.text = text.slice(0, TEXT_CAP)
      if (frames.length) rec.frames = frames
      rec.ld_json = (await page.$$eval('script[type="application/ld+json"]', ns => ns.map(n => n.textContent))).map(s => s.slice(0, 6000)).slice(0, 4)
    }
    const fhost = new URL(rec.final_url).hostname
    const links = await page.$$eval('a[href]', as => as.map(a => ({ href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 100) })))
    rec._follow = links
      .filter(l => { try { return new URL(l.href).hostname === fhost } catch { return false } })
      .filter(l => followRe ? followRe.test(l.href) : (LINK_RE.test(l.href) || LINK_RE.test(l.text)))
      .map(l => l.href.split('#')[0])
    if (keep === 'all') rec.links_out = links.filter(l => { try { const h = new URL(l.href).hostname; return h !== fhost && /^https?:/.test(l.href) } catch { return false } }).slice(0, 800)
  } catch (e) {
    rec.error = String(e).split('\n')[0].slice(0, 300)
  } finally {
    await ctx.close().catch(() => {})
  }
  return rec
}

async function doEntry(c) {
  const followRe = c.follow_re ? new RegExp(c.follow_re, 'i') : null
  const seen = new Set()
  const pages = []
  for (const u of c.urls) {
    if (!u || seen.has(u)) continue
    seen.add(u)
    pages.push(await grab(u, c.keep, followRe))
  }
  const follow = c.follow ?? 4
  if (follow > 0) {
    const extra = [...new Set(pages.flatMap(p => p._follow || []))]
      .filter(u => !seen.has(u) && !/\.(pdf|jpg|png|jpeg|gif|webp|ics)(\?|$)/i.test(u))
      .sort((a, b) => (QUIZ.test(b) - QUIZ.test(a)))
      .slice(0, follow)
    for (const u of extra) { seen.add(u); const p = await grab(u, c.follow_keep || 'quiz', null); p.followed = true; pages.push(p) }
  }
  for (const p of pages) delete p._follow
  results[c.id] = pages
  done++
  if (done % 25 === 0 || entries.length < 50) console.log(`${done}/${entries.length} ${c.id}: ${pages.filter(p => p.has_quiz).length}/${pages.length} pages mention a quiz`)
}

const queue = [...entries]
await Promise.all(Array.from({ length: CONCURRENCY }, async () => {
  while (queue.length) await doEntry(queue.shift())
}))
await browser.close()

mkdirSync(OUT, { recursive: true })
writeFileSync(join(OUT, `pages-${SHARD}.json.gz`), gzipSync(JSON.stringify(results)))
const n = Object.values(results).flat()
console.log(`shard ${SHARD}/${SHARDS} done: ${entries.length} entries, ${n.length} pages, ${n.filter(p => p.error).length} errors, ${n.filter(p => p.has_quiz).length} mention a quiz`)
