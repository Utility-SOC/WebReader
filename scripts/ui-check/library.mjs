// Browser check of the library UI against a running WebReader with the demo data loaded (scripts/demo-seed.sh).
// Covers: axe (WCAG 2.2 AA + best practice) in light/dark, keyboard-only search, paging + focus, labelling of
// software-inferred titles, provenance, privacy (no cookies / stored searches / third-party requests), 320px reflow.
//   BASE=http://localhost:5173 ./scripts/ui-check.sh
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
const BASE = process.env.BASE || 'http://localhost:5173';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const seen = []; ctx.on('request', r => seen.push(r.url()));
const TAGS = ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice'];
let fails = 0;
const ok = (l, v, d = '') => { if (!v) fails++; console.log(`${v ? 'PASS' : 'FAIL'}  ${l}${d ? '  -- ' + d : ''}`); };
const scan = async (name) => {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  ok(`axe ${name}`, r.violations.length === 0, r.violations.map(v => `${v.id}(${v.nodes.length}) ${v.nodes[0].target.join(' ')}`).join('; '));
};
const theme = async (dark) => {
  const isDark = await page.locator('button[aria-label="Switch to light theme"]').count() > 0;
  if (isDark !== dark) await page.locator(dark ? 'button[aria-label="Switch to dark theme"]' : 'button[aria-label="Switch to light theme"]').click();
  await page.waitForTimeout(600);
};
const results = () => page.locator('ol[aria-label="Search results"] > li');

await page.goto(BASE); await page.waitForSelector('h1');
ok('Library nav appears when the library has documents', await page.locator('nav[aria-label="Main"] button:has-text("Library")').waitFor({ timeout: 8000 }).then(() => true).catch(() => false));
await page.locator('nav[aria-label="Main"] button:has-text("Library")').click();
await page.waitForSelector('#library-title');
await results().first().waitFor();
ok('first page shows 20 results', await results().count() === 20, `${await results().count()}`);
ok('status announces the total', (await page.locator('#library-title ~ p[role=status], section[aria-labelledby=library-title] [role=status]').first().innerText()).includes('36'));
for (const dark of [true, false]) {
  await theme(dark);
  await scan(`library (${dark ? 'dark' : 'light'}), browsing`);
}
await theme(true);

// ---- keyboard-only: type a query, submit with Enter, read the status, open a result
await page.locator('#lib-q').focus();
await page.keyboard.type('zoning'); await page.keyboard.press('Enter');
await page.waitForFunction(() => document.querySelector('#library-title').parentElement.querySelector('[role=status]')?.textContent.includes('found for'));
ok('search result count is announced with the query', (await page.locator('section[aria-labelledby=library-title] [role=status]').first().innerText()).includes('zoning'));
ok('one result for "zoning"', await results().count() === 1);
ok('match highlighting uses <mark> (no raw markers on screen)', await page.locator('mark').count() > 0 && !(await page.locator('ol').innerText()).includes('⟦'));
await scan('library with a search');

// ---- filters
await page.locator('#lib-q').fill(''); await page.keyboard.press('Enter');
await page.selectOption('#lib-agency', 'Parks and Recreation');
await page.waitForFunction(() => document.querySelector('#library-title').parentElement.querySelector('[role=status]')?.textContent.startsWith('10 documents'));
ok('agency filter narrows to 10', await results().count() === 10);
await page.locator('button:has-text("Clear search and filters")').click();
await page.waitForFunction(() => document.querySelector('#library-title').parentElement.querySelector('[role=status]')?.textContent.startsWith('36 documents'));

// ---- paging + focus
await page.locator('button:has-text("Next page")').click();
await page.waitForFunction(() => document.querySelector('nav[aria-label="Results pages"]')?.textContent.includes('Page 2 of 2'));
ok('page 2 has the remaining 16', await results().count() === 16);
ok('focus moves to the results heading after paging', await page.evaluate(() => document.activeElement?.textContent === 'Results'));
await page.locator('button:has-text("Previous page")').click();
await page.waitForFunction(() => document.querySelector('nav[aria-label="Results pages"]')?.textContent.includes('Page 1 of 2'));

// ---- machine-generated labelling
await page.locator('#lib-q').fill('snow'); await page.keyboard.press('Enter');
await page.waitForFunction(() => document.querySelector('#library-title').parentElement.querySelector('[role=status]')?.textContent.includes('found for'));
ok('a title inferred by software is labelled in words', await page.locator('text=Title inferred by software').count() === 1);

// ---- open a document in the reader, with provenance
await page.locator('#lib-q').fill('zoning'); await page.keyboard.press('Enter');
await page.waitForFunction(() => document.querySelector('#library-title').parentElement.querySelector('[role=status]')?.textContent.includes('found for'));
await results().first().locator('button').focus(); await page.keyboard.press('Enter');
await page.waitForSelector('button[aria-label="Play"]', { timeout: 15000 });
ok('document opens in the reader', await page.locator('#about-title').innerText() === 'Planning Commission Minutes - March');
await page.locator('summary:has-text("About this document")').click();
const rows = await page.locator('table tbody tr').allInnerTexts();
ok('provenance is shown for each detail', rows.some(r => r.includes('Title') && r.includes('From the document')) && rows.some(r => r.includes('Agency') && r.includes('Set by the site administrator')), rows.length + ' rows');
for (const dark of [true, false]) { await theme(dark); await scan(`reader with About panel (${dark ? 'dark' : 'light'})`); }
await theme(true);
await page.locator('button:has-text("Back to search results")').click();
await page.waitForSelector('#library-title');
ok('back to results works', await page.locator('#lib-q').count() === 1);

// ---- privacy: nothing about the search is stored or sent anywhere else
const cookies = await ctx.cookies();
ok('no cookies', cookies.length === 0);
const keys = await page.evaluate(() => Object.keys(localStorage).concat(Object.keys(sessionStorage)));
ok('no search terms or document names in browser storage', !keys.some(k => /search|query|recent|history|doc|title/i.test(k)), keys.join(','));
const store = await page.evaluate(() => JSON.stringify(localStorage));
ok('stored preferences do not contain the query', !store.includes('zoning'));
const origin = new URL(BASE).origin;
const ext = [...new Set(seen.filter(u => !u.startsWith('data:') && !u.startsWith('blob:')).map(u => new URL(u).origin))].filter(o => o !== origin && o.replace(/^ws/, 'http') !== origin);
ok('no requests to any other origin', ext.length === 0, ext.join(', '));

// ---- reflow at 320px
const ctx2 = await b.newContext({ viewport: { width: 320, height: 640 } });
const p2 = await ctx2.newPage(); await p2.goto(BASE + '/#/library'); await p2.waitForSelector('#library-title'); await p2.locator('ol[aria-label="Search results"] > li').first().waitFor();
const over = await p2.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
ok('library reflows at 320px with no horizontal scroll', over <= 1, `overflow ${over}px`);
await b.close();
console.log(fails ? `\n${fails} FAILED` : '\nAll library UI checks passed');
process.exit(fails ? 1 : 0);
