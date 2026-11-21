// Print an HTML file to a Letter-size PDF with the pre-installed Chromium. Usage: node print_pdf.js in.html out.pdf
const { chromium } = require('playwright');
(async () => {
  const [inp, out, m = '0.5in,0.6in'] = process.argv.slice(2);
  const [tb, lr] = m.split(',');
  const b = await chromium.launch({ args: ['--no-proxy-server'] });
  const p = await b.newPage();
  await p.goto('file://' + inp, { waitUntil: 'domcontentloaded' });
  await p.pdf({ path: out, format: 'Letter', printBackground: true,
                margin: { top: tb, bottom: tb, left: lr, right: lr } });
  await b.close();
})();
