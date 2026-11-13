import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--no-sandbox'],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
let browserErrors = 0;
page.on('pageerror', (error) => console.error('PAGE ERROR:', error.message));
page.on('console', (message) => { if (message.type() === 'error') { browserErrors++; console.error('BROWSER:', message.text()); } });
await page.goto('http://127.0.0.1:4173/', { waitUntil: 'networkidle' });
await page.screenshot({ path: 'smoke-home.png', fullPage: true });
await page.getByRole('button', { name: /Use included sample/ }).click();
await page.locator('#configuration').waitFor({ state: 'visible', timeout: 30000 });
await page.locator('#sampleFps').selectOption('2');
console.log('Sample loaded:', await page.locator('#videoDetails').textContent());
await page.getByRole('button', { name: /Analyze video/ }).click();
await page.locator('#results').waitFor({ state: 'visible', timeout: 600000 });
console.log('Result:', {
  crossings: await page.locator('#crossingCount').textContent(),
  stops: await page.locator('#stopCount').textContent(),
  frames: await page.locator('#frameCount').textContent(),
  status: await page.locator('#statusMessage').textContent(),
});
assert.equal(await page.locator('#crossingCount').textContent(), '2');
assert.equal(await page.locator('#frameCount').textContent(), '61');
const download = await Promise.all([
  page.waitForEvent('download'),
  page.locator('#exportCsv').click(),
]).then(([file]) => file);
const csv = await (await import('node:fs/promises')).readFile(await download.path(), 'utf8');
assert.match(csv, /crossing/);
assert.match(csv, /top_to_bottom/);
const jsonDownload = await Promise.all([
  page.waitForEvent('download'),
  page.locator('#exportJson').click(),
]).then(([file]) => file);
const run = JSON.parse(await (await import('node:fs/promises')).readFile(await jsonDownload.path(), 'utf8'));
assert.equal(run.records.length, 61);
assert.deepEqual(run.events.map((event) => event.vehicle_class), ['car', 'car']);
await page.locator('#eventRows button').first().click();
await page.locator('#addLabel').click();
await page.locator('#metrics').getByText(/1 matched/).waitFor();
assert.match(await page.locator('#metrics').textContent(), /1 matched/);
await page.screenshot({ path: 'smoke-results.png', fullPage: true });
await page.reload({ waitUntil: 'networkidle' });
await page.locator('.open-run').first().click();
await page.locator('#crossingCount').getByText('2').waitFor();
assert.equal(await page.locator('#crossingCount').textContent(), '2');
assert.equal(await page.locator('.manual-label').count(), 1);
console.log('Reloaded saved run: 2 crossings, 1 manual label; CSV export checked.');
assert.equal(browserErrors, 0);
await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: 'smoke-mobile.png', fullPage: true });
console.log('Mobile viewport horizontal overflow:', await page.evaluate(() => document.documentElement.scrollWidth > innerWidth));
await page.getByRole('button', { name: /Try stop demo/ }).click();
await page.locator('#configuration').waitFor({ state: 'visible' });
await page.locator('#sampleFps').selectOption('2');
assert.equal(await page.locator('#confidence').inputValue(), '10');
await page.getByRole('button', { name: /Analyze video/ }).click();
await page.waitForFunction(() => document.querySelector('#statusMessage')?.textContent?.startsWith('Complete.'));
const stopJsonDownload = await Promise.all([page.waitForEvent('download'), page.locator('#exportJson').click()]).then(([file]) => file);
const stopRun = JSON.parse(await (await import('node:fs/promises')).readFile(await stopJsonDownload.path(), 'utf8'));
assert.equal(stopRun.events.filter((event) => event.type === 'stop').length, 1);
await page.screenshot({ path: 'smoke-stop-demo.png', fullPage: true });
assert.equal(await page.locator('#stopCount').textContent(), '1');
console.log('Synthetic stop demo: 1 visible stop event.');
await browser.close();
