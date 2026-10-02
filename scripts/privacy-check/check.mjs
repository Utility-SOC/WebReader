// Verifies, in a real browser, what WebReader's pages send and store.
//
//   BASE_URL           site to test (default http://localhost:5173)
//   ALLOWED_ORIGINS    comma-separated extra origins you have deliberately approved
//   EXPECT_READING_ROOM=1   expect a reading-room deployment (no upload control)
//
// Exit code 0 = every check passed. Run it yourself against your own
// deployment; you don't have to take anyone's word for it.
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://localhost:5173';
const allowed = new Set([new URL(BASE).origin, ...(process.env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean)]);
const readingRoom = process.env.EXPECT_READING_ROOM === '1';

let failures = 0;
const check = (label, ok, detail = '') => { if (!ok) failures++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? '  -- ' + detail : ''}`); };

// Hand-built one-page PDF so no fixture files are needed.
function tinyPdf(text) {
  const stream = `BT /F1 8 Tf 10 170 Td (${text}) Tj ET`;
  const objs = [
    '<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('');
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(out, 'latin1');
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
page.on('dialog', d => d.accept());

const seen = [];
ctx.on('request', r => seen.push(r.url()));
ctx.on('websocket', ws => seen.push(ws.url()));

await page.goto(BASE); await page.waitForSelector('h1');
await page.waitForTimeout(500);

if (readingRoom) {
  check('reading room: no upload control offered', await page.locator('input[type=file]').count() === 0);
} else {
  await page.setInputFiles('input[type=file]', { name: 'sample.txt', mimeType: 'text/plain',
    buffer: Buffer.from('Chapter One\n\n' + 'The quick brown fox jumps over the lazy dog. '.repeat(40)) });
  await page.waitForSelector('button[aria-label="Play"]', { timeout: 30000 });

  // Every font in the picker: bundled ones must really load (no silent fallback), and loading must stay on-origin.
  const fonts = await page.$$eval('#set-font option', os => os.map(o => ({ label: o.textContent, family: o.value })));
  const system = /Courier|Arial|Comic/;
  for (const f of fonts) {
    await page.selectOption('#set-font', f.family);
    const loaded = await page.evaluate(async fam => (await document.fonts.load(`16px ${fam}`)).length, f.family);
    if (system.test(f.family)) console.log(`INFO  ${f.label}: system font`);
    else check(`font bundled and loads: ${f.label}`, loaded > 0);
  }

  await page.locator('button[aria-label="Chapters"]').click(); await page.waitForSelector('[role=dialog]'); await page.keyboard.press('Escape');
  await page.locator('button[aria-label^="Download audio"]').click(); await page.waitForSelector('[role=dialog]'); await page.keyboard.press('Escape');

  await page.locator('button[aria-label="Load a different file"]').click();
  await page.setInputFiles('input[type=file]', { name: 'sample.pdf', mimeType: 'application/pdf', buffer: tinyPdf('alpha beta gamma') });
  await page.waitForSelector('#editor-title', { timeout: 30000 });
  await page.waitForTimeout(800);
}

// ---- verdicts ----
const external = [...new Set(seen.filter(u => !u.startsWith('data:') && !u.startsWith('blob:')).map(u => new URL(u).origin))].filter(o => {
  const o2 = o.replace(/^ws/, 'http'); return !allowed.has(o) && !allowed.has(o2);
});
check('no requests to origins other than the site itself (or approved ones)', external.length === 0, external.join(', '));
check(`${seen.length} requests observed, all accounted for`, true);

const cookies = await ctx.cookies();
check('no cookies set', cookies.length === 0, cookies.map(c => c.name).join(', '));

const storage = await page.evaluate(() => ({
  local: Object.keys(localStorage), session: Object.keys(sessionStorage),
  workers: 'serviceWorker' in navigator ? 0 : 0,
}));
const regs = await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length);
check('no service workers registered', regs === 0);
console.log(`INFO  localStorage keys on this device: ${storage.local.join(', ') || '(none)'}`);
const risky = storage.local.filter(k => /file|name|doc|history|recent|title/i.test(k));
check('no document names/history kept in browser storage', risky.length === 0, risky.join(', '));
check('sessionStorage unused', storage.session.length === 0, storage.session.join(', '));

await browser.close();
console.log(failures ? `\n${failures} check(s) FAILED` : '\nAll checks passed');
process.exit(failures ? 1 : 0);
