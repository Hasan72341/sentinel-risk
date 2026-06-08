import { test, expect } from '@playwright/test';

// This test uses the real local API and bundled SEC cache, with no route mocking.
test('public filings case loads from dashboard and exports source evidence', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: /Start with reported financials/ }).click();
  await expect(page.getByRole('heading', { name: 'Public Filings Credit Review', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'COCA COLA CO', exact: true })).toBeVisible();
  await expect(page.getByText('47,061', { exact: true })).toBeVisible();
  await page.screenshot({ path: '../docs/evidence/public-filings.png', fullPage: true });
  await page.getByLabel('Issuer', { exact: true }).selectOption('PEP');
  await expect(page.getByRole('heading', { name: 'PepsiCo, Inc.', exact: true })).toBeVisible();
  await expect(page.getByText('91,854', { exact: true })).toBeVisible();
  await page.getByLabel('Issuer', { exact: true }).selectOption('KDP');
  await expect(page.getByText('15,351', { exact: true })).toBeVisible();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export evidence pack' }).click();
  const archive = await downloaded;
  expect(archive.suggestedFilename()).toBe('public-filings-credit-case.zip');
  await expect(page.getByRole('status').filter({ hasText: 'Credit case downloaded.' })).toBeVisible();
});
