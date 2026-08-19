const { test, expect } = require('@playwright/test');

test('renders exactly 29 constellation stars', async ({ page }) => {
  await page.goto('/');
  const stars = page.locator('.star');
  await expect(stars).toHaveCount(29);
});

test('each constellation has a label on the map', async ({ page }) => {
  await page.goto('/');
  const labels = page.locator('.constellation-label');
  await expect(labels).toHaveCount(7);

  const names = await labels.allTextContents();
  expect(names).toContain('The Willow');
  expect(names).toContain('The Almanac');
  expect(names).toContain('The Sovereign');
  expect(names).toContain('The Scholar');
  expect(names).toContain('The Seeker');
  expect(names).toContain('The Scribe');
  expect(names).toContain('The Outlier');
});

test('oracle button produces a visible reading', async ({ page }) => {
  await page.goto('/');
  const reading = page.locator('#reading');
  await expect(reading).not.toHaveClass(/visible/);

  await page.click('#oracle-btn');
  await expect(reading).toHaveClass(/visible/, { timeout: 2000 });
  await expect(page.locator('#reading-title')).not.toBeEmpty();
  await expect(page.locator('#reading-body')).not.toBeEmpty();
});

test('clicking oracle again cycles to a different reading', async ({ page }) => {
  await page.goto('/');
  await page.click('#oracle-btn');
  await expect(page.locator('#reading')).toHaveClass(/visible/, { timeout: 5000 });
  const first = await page.locator('#reading-title').textContent();

  await page.click('#oracle-btn');
  await page.waitForTimeout(500);
  await expect(page.locator('#reading')).toHaveClass(/visible/, { timeout: 5000 });
  const second = await page.locator('#reading-title').textContent();

  expect(second).not.toEqual(first);
});

test('personality profile renders 8 stat bars', async ({ page }) => {
  await page.goto('/');
  const stats = page.locator('.stat');
  await expect(stats).toHaveCount(8);
});

test('legend shows all 7 constellation names', async ({ page }) => {
  await page.goto('/');
  const items = page.locator('.legend-item');
  await expect(items).toHaveCount(7);
});

test('tooltip appears on star hover', async ({ page }) => {
  await page.goto('/');
  const tooltip = page.locator('#tooltip');
  await expect(tooltip).not.toHaveClass(/visible/);

  const firstStar = page.locator('.star').first();
  await firstStar.hover();
  await expect(tooltip).toHaveClass(/visible/);
  await expect(page.locator('.tooltip-name')).not.toBeEmpty();
});
