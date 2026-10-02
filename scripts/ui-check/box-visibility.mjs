// Is the text under a PDF-editor selection box still readable, in every browser and display configuration?
//
// Draws a box over real text (the way a person would, with the mouse) in Chromium, Firefox and WebKit under: light/dark,
// forced-colors (Windows / Linux high-contrast), hiDPI, a browser that can't parse modern colour functions, an
// "outline only" setting, and WORST CASES where the fill is forced fully opaque (an extension, a theme, a driver bug).
// It measures the darkest pixel inside the box: near 0 means the text shows through.
//   BASE=http://localhost:5173 ./scripts/ui-check.sh box
// Exits non-zero if any combination hides the text.
import { chromium, firefox, webkit } from 'playwright';
const BASE = process.env.BASE || 'http://localhost:5173';
// A one-page PDF with a few lines of 12pt text, built by hand.
function pdfWithLines(lines) {
  const stream = 'BT /F1 20 Tf 72 700 Td (' + lines[0] + ') Tj ET\n' + lines.slice(1).map((l, i) => `BT /F1 12 Tf 72 ${640 - i * 18} Td (${l}) Tj ET`).join('\n');
  const objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('');
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(out, 'latin1');
}
const PDF = pdfWithLines(['Residential Lease Agreement', 'This lease is made between the landlord and the tenant named below.',
  'The tenant agrees to pay rent on the first day of each month.', 'The premises shall be used only as a private dwelling.',
  'Pets are not permitted without prior written consent.']);

const only = (process.env.ONLY || '').split(',').filter(Boolean);
const browsers = { chromium, firefox, webkit };
const configs = [
  { name: 'default',                  opts: {} },
  { name: 'dark scheme',              opts: { colorScheme: 'dark' } },
  { name: 'light scheme',             opts: { colorScheme: 'light' } },
  { name: 'forced-colors (dark)',     opts: { forcedColors: 'active', colorScheme: 'dark' } },
  { name: 'forced-colors (light)',    opts: { forcedColors: 'active', colorScheme: 'light' } },
  { name: 'hiDPI x2',                 opts: { deviceScaleFactor: 2 } },
  { name: 'no color-mix/oklch (old)', opts: {}, stripModernColor: true },
  // worst case: whatever the cause, the fill ends up fully OPAQUE (extension, theme, driver...)
  { name: 'WORST CASE: opaque fill', opts: {}, injectCss: 'div.absolute.border-2:not(.border-dashed):not(.wr-box), .wr-box-fill { background-color: rgb(205, 220, 255) !important; }' },
  { name: 'worst case + forced-colors', opts: { forcedColors: 'active' }, injectCss: 'div.absolute.border-2:not(.border-dashed):not(.wr-box), .wr-box-fill { background-color: rgb(205, 220, 255) !important; }' },
  { name: 'Outline toggle on', opts: {}, clickOutline: true },
];
const rows = [];
for (const [bname, bt] of Object.entries(browsers)) {
  if (only.length && !only.includes(bname)) continue;
  let browser; try { browser = await bt.launch(); } catch (e) { console.log(bname, 'cannot launch:', String(e).split('\n')[0]); continue; }
  for (const cfg of configs) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, ...cfg.opts });
    const page = await ctx.newPage(); page.on('dialog', d => d.accept());
    if (cfg.stripModernColor) {
      // what a browser that doesn't understand these functions effectively does: drops the declarations
      await page.route(/\.css(\?.*)?$|\/src\/.*\.css|\/@vite|tailwind/, async route => {
        try { const r = await route.fetch(); let t = await r.text(); t = t.replaceAll('color-mix(', 'color-mixx(').replaceAll('oklch(', 'oklchx(').replaceAll('oklab(', 'oklabx('); await route.fulfill({ response: r, body: t }); } catch { await route.continue(); }
      });
    }
    let res = { browser: bname, config: cfg.name };
    try {
      await page.goto(BASE); await page.waitForSelector('h1');
      await page.setInputFiles('input[type=file]', { name: 'sample.pdf', mimeType: 'application/pdf', buffer: PDF });
      await page.waitForSelector('#editor-title', { timeout: 30000 }); await page.waitForTimeout(1500);
      await page.waitForFunction(() => { const i = document.querySelector('img'); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 20000 });
      if (cfg.injectCss) await page.addStyleTag({ content: cfg.injectCss });
      if (cfg.clickOutline) await page.locator('button:has-text("Tint")').click();
      const img = await page.locator('img').first().boundingBox();
      const x0 = img.x + img.width * 0.10, y0 = img.y + img.height * 0.17, x1 = img.x + img.width * 0.80, y1 = img.y + img.height * 0.31;
      await page.mouse.move(x0, y0); await page.mouse.down(); await page.mouse.move(x1, y1, { steps: 8 }); await page.mouse.up();
      await page.waitForTimeout(500);
      const buf = await page.screenshot();
      res = { ...res, ...(await page.evaluate(async (b64) => {
        const box = [...document.querySelectorAll('div.absolute.border-2')].find(e => !e.className.includes('border-dashed'));
        if (!box) return { error: 'no box found' };
        const r = box.getBoundingClientRect(); const cs = getComputedStyle(box);
        const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob());
        const c = document.createElement('canvas'); c.width = bmp.width; c.height = bmp.height; const g = c.getContext('2d'); g.drawImage(bmp, 0, 0);
        const k = bmp.width / window.innerWidth;                       // device pixels per CSS pixel
        const inset = 8, sx = Math.round((r.left + inset) * k), sy = Math.round((r.top + inset) * k), sw = Math.round((r.width - 2 * inset) * k), sh = Math.round((r.height - 2 * inset) * k);
        const d = g.getImageData(sx, sy, sw, sh).data; let min = 255, sum = [0, 0, 0], n = 0;
        for (let i = 0; i < d.length; i += 4) { const l = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; if (l < min) min = l; sum[0] += d[i]; sum[1] += d[i + 1]; sum[2] += d[i + 2]; n++; }
        return { bg: cs.backgroundColor, blend: cs.mixBlendMode, minLum: Math.round(min), meanRGB: sum.map(v => Math.round(v / n)).join(','), forced: matchMedia('(forced-colors: active)').matches };
      }, buf.toString('base64'))) };
      if (process.env.SHOT) await page.screenshot({ path: `shot-${bname}-${cfg.name.replace(/[^a-z0-9]+/gi, '_')}.png`, clip: { x: 0, y: 100, width: 1280, height: 700 } });
    } catch (e) { res.error = String(e).split('\n')[0].slice(0, 90); }
    rows.push(res); await ctx.close();
  }
  await browser.close();
}
const pad = (s, n) => String(s ?? '').padEnd(n);
let bad = 0;
console.log(pad('browser', 9) + pad('config', 26) + pad('text visible under box?', 25) + pad('min lum', 8) + pad('box background (computed)', 46) + 'forced');
for (const r of rows) {
  const visible = r.error ? 'ERROR ' + r.error : (r.minLum < 110 ? 'yes' : 'NO - HIDDEN');
  console.log(pad(r.browser, 9) + pad(r.config, 26) + pad(visible, 25) + pad(r.minLum, 8) + pad(r.bg, 46) + (r.forced ?? ''));
}
bad = rows.filter(r => r.error || !(r.minLum < 110)).length;
console.log(bad ? `\n${bad} combination(s) HIDE the text` : `\nAll ${rows.length} combinations keep the text readable`);
process.exit(bad ? 1 : 0);
