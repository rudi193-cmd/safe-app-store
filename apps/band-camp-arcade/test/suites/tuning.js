// Tuning Note Purgatory: start, run for a bit, stop, and check the run got
// timed and the personal best actually persisted.

export async function run(browser, baseUrl) {
  const results = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    await page.goto(`${baseUrl}/games/tuning-note-purgatory/index.html`, { waitUntil: 'load' });

    await page.click('#mainButton');
    await page.waitForTimeout(600);
    await page.click('#mainButton');
    await page.waitForTimeout(150);

    const lastTime = await page.textContent('#lastTime');
    const bestTime = await page.textContent('#bestTime');
    const buttonText = await page.textContent('#mainButton');

    results.push({
      name: 'stopping ends the run and re-labels the button Start',
      pass: buttonText === 'Start',
      error: buttonText === 'Start' ? undefined : `button read "${buttonText}"`,
    });

    results.push({
      name: 'a run records a non-zero elapsed time',
      pass: lastTime !== '0:00.0' && lastTime !== '--',
      error: lastTime === '0:00.0' || lastTime === '--' ? `lastTime was "${lastTime}"` : undefined,
    });

    results.push({
      name: 'personal best updates after a run',
      pass: bestTime === lastTime && bestTime !== '--',
      error: bestTime === lastTime ? undefined : `bestTime "${bestTime}" != lastTime "${lastTime}"`,
    });
  } catch (err) {
    results.push({ name: '<tuning suite did not complete>', pass: false, error: err.message });
  } finally {
    await context.close();
  }

  if (pageErrors.length) {
    results.push({ name: 'tuning: no uncaught page errors', pass: false, error: pageErrors.join('\n') });
  }
  return results;
}
