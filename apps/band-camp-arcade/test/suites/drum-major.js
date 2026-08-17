// Drum Major Says: start a run, read back the calls the game actually dealt
// (mirrored to #board[data-sequence] as real state), repeat them, and check
// that a clean repeat grows the sequence by one — and that a wrong call ends
// the run with the streak recorded.

async function readSequence(page) {
  const raw = await page.getAttribute('#board', 'data-sequence');
  return raw ? raw.split(',').map(Number) : [];
}

async function repeat(page, seq) {
  for (const cmd of seq) {
    // eslint-disable-next-line no-await-in-loop
    await page.click(`.pad[data-cmd="${cmd}"]`);
  }
}

export async function run(browser, baseUrl) {
  const results = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    await page.goto(`${baseUrl}/games/drum-major-says/index.html`, { waitUntil: 'load' });

    // Round 1: Start deals a single opening call, then hands the floor over.
    await page.click('#mainButton');
    await page.waitForSelector('#board[data-phase="input"]', { timeout: 5000 });
    const round1 = await readSequence(page);

    results.push({
      name: 'starting deals a one-call opening sequence',
      pass: round1.length === 1,
      error: round1.length === 1 ? undefined : `opening sequence was length ${round1.length}`,
    });

    // Repeat round 1 correctly. A cleared round bumps the streak (synchronously)
    // then replays a longer sequence — so wait for the streak, then the replay.
    await repeat(page, round1);
    await page.waitForFunction(() => document.getElementById('streak').textContent === '1', null, { timeout: 5000 });
    await page.waitForSelector('#board[data-phase="input"]', { timeout: 5000 });
    const round2 = await readSequence(page);
    const streakAfter = await page.textContent('#streak');

    results.push({
      name: 'a full correct repeat grows the sequence to the next round',
      pass: round2.length === 2 && streakAfter === '1',
      error:
        round2.length === 2 && streakAfter === '1'
          ? undefined
          : `after clearing round 1: sequence length ${round2.length}, streak "${streakAfter}"`,
    });

    // Now break formation on purpose: click any call that isn't the next one.
    const wrong = [0, 1, 2, 3].find((c) => c !== round2[0]);
    await page.click(`.pad[data-cmd="${wrong}"]`);
    await page.waitForSelector('#board[data-phase="over"]', { timeout: 5000 });
    const best = await page.evaluate(() => localStorage.getItem('drum-major-best-streak'));

    results.push({
      name: 'a wrong call ends the run and records the best streak',
      pass: Number(best) >= 1,
      error: Number(best) >= 1 ? undefined : `best streak in storage was "${best}"`,
    });
  } catch (err) {
    results.push({ name: '<drum-major suite did not complete>', pass: false, error: err.message });
  } finally {
    await context.close();
  }

  if (pageErrors.length) {
    results.push({ name: 'drum-major: no uncaught page errors', pass: false, error: pageErrors.join('\n') });
  }
  return results;
}
