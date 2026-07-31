// GE Score Roast: check score-band classification and that regenerate
// actually varies the output rather than repeating one fixed line.

export async function run(browser, baseUrl) {
  const results = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    await page.goto(`${baseUrl}/games/ge-score-roast/index.html`, { waitUntil: 'load' });

    await page.click('#roastBtn');
    await page.waitForTimeout(100);
    const noScoreText = await page.textContent('#outputCard');
    results.push({
      name: 'roasting with no score shows the validation placeholder',
      pass: noScoreText.includes('numeric score'),
      error: noScoreText.includes('numeric score') ? undefined : `output read "${noScoreText}"`,
    });

    await page.fill('#scoreInput', '22');
    await page.click('#roastBtn');
    await page.waitForTimeout(100);
    const brutalLabel = await page.textContent('.band-label');
    results.push({
      name: 'a low score classifies as Brutal',
      pass: brutalLabel === 'Brutal',
      error: brutalLabel === 'Brutal' ? undefined : `band label read "${brutalLabel}"`,
    });

    await page.fill('#scoreInput', '91');
    await page.click('#roastBtn');
    await page.waitForTimeout(100);
    const highLabel = await page.textContent('.band-label');
    results.push({
      name: 'a high score classifies as Suspiciously Glowing',
      pass: highLabel === 'Suspiciously Glowing',
      error: highLabel === 'Suspiciously Glowing' ? undefined : `band label read "${highLabel}"`,
    });

    // Each persona/band pool only has 2 lines, so with fewer clicks a fair
    // coin can land on the same line every time. 14 clicks keeps the false-
    // negative rate (both lines exist, but the sequence is never split)
    // below 1 in 8000, which is what stopping at 6 clicks previously missed.
    const lines = new Set();
    for (let i = 0; i < 14; i++) {
      await page.click('#regenBtn');
      await page.waitForTimeout(60);
      lines.add(await page.textContent('.roast-line'));
    }
    results.push({
      name: 'regenerate produces more than one distinct line',
      pass: lines.size > 1,
      error: lines.size > 1 ? undefined : `only ever saw: ${[...lines].join(' | ')}`,
    });
  } catch (err) {
    results.push({ name: '<ge-score-roast suite did not complete>', pass: false, error: err.message });
  } finally {
    await context.close();
  }

  if (pageErrors.length) {
    results.push({ name: 'ge-score-roast: no uncaught page errors', pass: false, error: pageErrors.join('\n') });
  }
  return results;
}
