// Sectional Bingo: mark a full top row and check BINGO actually triggers.

export async function run(browser, baseUrl) {
  const results = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    await page.goto(`${baseUrl}/games/sectional-bingo/index.html`, { waitUntil: 'load' });

    const squareCount = await page.locator('.square').count();
    results.push({
      name: 'a card renders 25 squares with a marked free space',
      pass: squareCount === 25,
      error: squareCount === 25 ? undefined : `square count was ${squareCount}`,
    });

    for (let i = 0; i <= 4; i++) {
      await page.locator(`.square[data-index="${i}"]`).click();
    }
    await page.waitForTimeout(150);

    const banner = await page.textContent('#banner');
    results.push({
      name: 'marking a full row triggers BINGO',
      pass: banner === 'BINGO!',
      error: banner === 'BINGO!' ? undefined : `banner read "${banner}"`,
    });

    // unmark one square in that row; the banner should clear
    await page.locator('.square[data-index="0"]').click();
    await page.waitForTimeout(100);
    const bannerAfterUnmark = await page.textContent('#banner');
    results.push({
      name: 'unmarking a square in the winning row clears the banner',
      pass: bannerAfterUnmark === '',
      error: bannerAfterUnmark === '' ? undefined : `banner read "${bannerAfterUnmark}"`,
    });
  } catch (err) {
    results.push({ name: '<bingo suite did not complete>', pass: false, error: err.message });
  } finally {
    await context.close();
  }

  if (pageErrors.length) {
    results.push({ name: 'bingo: no uncaught page errors', pass: false, error: pageErrors.join('\n') });
  }
  return results;
}
