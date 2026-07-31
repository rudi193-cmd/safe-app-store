// Uniform Sweat Tracker: log a mild entry and a catastrophic entry, then
// check the summary correctly picks worst/best by score, not by order.

export async function run(browser, baseUrl) {
  const results = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    await page.goto(`${baseUrl}/games/uniform-sweat-tracker/index.html`, { waitUntil: 'load' });

    await page.fill('#event', 'Week 1 vs. Eastview');
    await page.fill('#temp', '68');
    await page.fill('#score', '2');
    await page.dispatchEvent('#score', 'input');
    await page.click('.submit-button');
    await page.waitForTimeout(100);

    await page.fill('#event', 'Homecoming vs. Central');
    await page.fill('#temp', '96');
    await page.fill('#complaint', 'The wool remembers nothing but pain.');
    await page.fill('#score', '10');
    await page.dispatchEvent('#score', 'input');
    await page.click('.submit-button');
    await page.waitForTimeout(100);

    const entryCount = await page.locator('.entry').count();

    results.push({
      name: 'both logged entries appear in the list',
      pass: entryCount === 2,
      error: entryCount === 2 ? undefined : `entry count was ${entryCount}`,
    });

    // Read structurally (which .summary-item's .value sits under which
    // .label) rather than checking substring presence anywhere in the
    // summary card — a plain "does this text appear somewhere" check cannot
    // tell a correctly-labeled pair from a swapped one, since both event
    // names are present in the DOM either way.
    const summaryPairs = await page.$$eval('.summary-item', (items) =>
      items.map((el) => ({
        label: el.querySelector('.label')?.textContent ?? '',
        value: el.querySelector('.value')?.textContent ?? '',
      }))
    );
    const worstValue = summaryPairs.find((p) => p.label === 'Worst day')?.value;
    const bestValue = summaryPairs.find((p) => p.label === 'Best day')?.value;
    const avgValue = summaryPairs.find((p) => p.label === 'Average suffering')?.value;

    results.push({
      name: 'worst day shows the highest-suffering entry',
      pass: worstValue === 'Homecoming vs. Central',
      error: worstValue === 'Homecoming vs. Central' ? undefined : `worst day slot read "${worstValue}"`,
    });

    results.push({
      name: 'best day shows the lowest-suffering entry',
      pass: bestValue === 'Week 1 vs. Eastview',
      error: bestValue === 'Week 1 vs. Eastview' ? undefined : `best day slot read "${bestValue}"`,
    });

    results.push({
      name: 'average suffering is computed correctly',
      pass: avgValue === '6.0 / 10',
      error: avgValue === '6.0 / 10' ? undefined : `average slot read "${avgValue}"`,
    });
  } catch (err) {
    results.push({ name: '<sweat-tracker suite did not complete>', pass: false, error: err.message });
  } finally {
    await context.close();
  }

  if (pageErrors.length) {
    results.push({ name: 'sweat-tracker: no uncaught page errors', pass: false, error: pageErrors.join('\n') });
  }
  return results;
}
