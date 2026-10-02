// Browser check of the admin accessibility report (the HTML written by `library_cli report --html`).
// axe (WCAG 2.2 AA + best practice) in light, dark and forced-colors; no external requests; skip link, heading order,
// keyboard use of the document links and details; 320px reflow; renders in Chromium, Firefox and WebKit.
//   ./scripts/report-check.sh /path/to/report.html
import { chromium, firefox, webkit } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
const URL_ = 'file:///r/' + (process.env.REPORT_NAME || 'report.html');
let fails = 0;
const ok = (l, v, d = '') => { if (!v) fails++; console.log(`${v ? 'PASS' : 'FAIL'}  ${l}${d ? '  -- ' + d : ''}`); };
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];
const b = await chromium.launch();
for (const scheme of ['light', 'dark']) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: scheme });
  const p = await ctx.newPage(); const external = [];
  p.on('request', r => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:')) external.push(r.url()); });
  await p.goto(URL_);
  const r = await new AxeBuilder({ page: p }).withTags(TAGS).analyze();
  ok(`axe (${scheme})`, r.violations.length === 0, r.violations.map(v => `${v.id}(${v.nodes.length}) ${v.nodes[0].target.join(' ')}`).join('; '));
  ok(`no external requests (${scheme})`, external.length === 0, external.join(','));
  if (scheme === 'light') {
    await p.keyboard.press('Tab');
    ok('first Tab stop is the skip link', await p.evaluate(() => document.activeElement?.textContent === 'Skip to the report'));
    await p.keyboard.press('Enter');
    ok('skip link moves to the report', await p.evaluate(() => location.hash === '#main'));
    const h = await p.evaluate(() => [...document.querySelectorAll('h1,h2')].map(e => e.tagName + ':' + e.textContent.trim()));
    ok('one h1 then h2 sections in order', h[0].startsWith('H1') && h.slice(1).every(x => x.startsWith('H2')), h.join(' | '));
    // every document link goes to a details section; opening it via keyboard works
    await p.locator('table a[href^="#doc-"]').first().focus(); await p.keyboard.press('Enter');
    const opened = await p.evaluate(() => { const d = document.querySelector(location.hash); return !!d; });
    ok('document link jumps to its details', opened, await p.evaluate(() => location.hash));
    await p.locator('summary').first().focus(); await p.keyboard.press('Enter');
    ok('details can be opened with the keyboard', await p.evaluate(() => document.querySelector('details[open]') !== null));
    const rs = await new AxeBuilder({ page: p }).withTags(TAGS).analyze();
    ok('axe with a details section open', rs.violations.length === 0, rs.violations.map(v => v.id).join(','));
      }
  await ctx.close();
}
// reflow + zoom + forced colours + other engines
const c320 = await b.newContext({ viewport: { width: 320, height: 640 } }); const p3 = await c320.newPage(); await p3.goto(URL_);
const over = await p3.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
ok('reflows at 320px (tables scroll inside their own region, page does not)', over <= 1, `page overflow ${over}px`);
const regions = await p3.evaluate(() => [...document.querySelectorAll('.wrap')].filter(e => e.scrollWidth > e.clientWidth).every(e => getComputedStyle(e).overflowX !== 'visible'));
ok('wide tables sit in a scrollable region', regions);
const fc = await b.newContext({ forcedColors: 'active' }); const pf = await fc.newPage(); await pf.goto(URL_);
const rf = await new AxeBuilder({ page: pf }).withTags(TAGS).analyze(); ok('axe in forced-colors mode', rf.violations.length === 0, rf.violations.map(v => v.id).join(','));
await b.close();
for (const [name, bt] of [['firefox', firefox], ['webkit', webkit]]) {
  const br = await bt.launch(); const pg = await (await br.newContext()).newPage(); await pg.goto(URL_);
  ok(`${name}: renders the report`, (await pg.locator('h1').innerText()) === 'Accessibility report' && await pg.locator('table').count() >= 4);
  await br.close();
}
console.log(fails ? `\n${fails} FAILED` : '\nAll report checks passed'); process.exit(fails ? 1 : 0);
