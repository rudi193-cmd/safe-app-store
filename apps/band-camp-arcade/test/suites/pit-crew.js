// Pit Crew Simulator: start level 1 (one instrument), drag it onto its
// target, let the count run out, and check the level cleared and scored.

export async function run(browser, baseUrl) {
  const results = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    await page.goto(`${baseUrl}/games/pit-crew-simulator/index.html`, { waitUntil: 'load' });

    await page.click('#mainButton');
    await page.waitForTimeout(150);

    const { instCenter, targetCenter } = await page.evaluate(() => {
      const inst = document.querySelector('.instrument');
      const target = document.querySelector('.target');
      const iRect = inst.getBoundingClientRect();
      const tRect = target.getBoundingClientRect();
      return {
        instCenter: { x: iRect.left + iRect.width / 2, y: iRect.top + iRect.height / 2 },
        targetCenter: { x: tRect.left + tRect.width / 2, y: tRect.top + tRect.height / 2 },
      };
    });

    await page.mouse.move(instCenter.x, instCenter.y);
    await page.mouse.down();
    await page.mouse.move(targetCenter.x, targetCenter.y, { steps: 10 });
    await page.mouse.up();

    // level 1: 8 counts at 620ms each ~= 5s, plus resolveLevel's 900ms delay
    await page.waitForTimeout(6200);

    const banner = await page.textContent('#banner');
    const score = await page.textContent('#scoreNum');
    const buttonAfterClear = await page.textContent('#mainButton');

    results.push({
      name: 'dragging onto the target clears the level',
      pass: banner === 'SET! Nice.',
      error: banner === 'SET! Nice.' ? undefined : `banner read "${banner}"`,
    });

    results.push({
      name: 'clearing a level increases the score',
      pass: score === '100',
      error: score === '100' ? undefined : `score read "${score}"`,
    });

    // #levelNum only updates when buildLevel() runs again, i.e. on the next
    // "Next level" click — it does not update just because the internal
    // `level` counter incremented.
    results.push({
      name: 'a clean clear offers a next level',
      pass: buttonAfterClear === 'Next level',
      error: buttonAfterClear === 'Next level' ? undefined : `button read "${buttonAfterClear}"`,
    });

    await page.click('#mainButton');
    await page.waitForTimeout(150);
    const level = await page.textContent('#levelNum');
    const instrumentCount = await page.locator('.instrument').count();

    results.push({
      name: 'starting the next level builds two instruments',
      pass: level === '2' && instrumentCount === 2,
      error: level === '2' && instrumentCount === 2 ? undefined : `level "${level}", ${instrumentCount} instruments`,
    });
  } catch (err) {
    results.push({ name: '<pit-crew suite did not complete>', pass: false, error: err.message });
  } finally {
    await context.close();
  }

  if (pageErrors.length) {
    results.push({ name: 'pit-crew: no uncaught page errors', pass: false, error: pageErrors.join('\n') });
  }
  return results;
}
