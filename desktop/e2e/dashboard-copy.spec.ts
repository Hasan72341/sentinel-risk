import { test, expect } from '@playwright/test';

test('saved history stays truthful when empty, unavailable or deletion fails', async ({ page }) => {
  let historyMode: 'empty' | 'unavailable' | 'saved' = 'empty';
  const savedAnalysis = {
    analysis_id: 'saved-statement',
    company_name: 'Uploaded statement',
    period: 'FY 2024',
    file_name: 'statement.csv',
    created_at: '2026-10-04T09:00:00Z',
    summary: {},
  };
  await page.route('**/analysis/history?*', async route => {
    await route.fulfill({
      status: historyMode === 'unavailable' ? 503 : 200,
      contentType: 'application/json',
      body: JSON.stringify(historyMode === 'saved' ? [savedAnalysis] : []),
    });
  });
  await page.route('**/analysis/saved-statement', async route => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
    } else {
      await route.continue();
    }
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'No analyses yet', exact: true })).toBeVisible();
  await expect(page.getByText(/Acme|Globex|Pinnacle/)).toHaveCount(0);
  await expect(page.getByRole('link', { name: /Start with reported financials/ })).toContainText('FY2022–2024');

  await page.goto('/#/reports');
  await expect(page.getByRole('heading', { name: 'No saved statement analyses', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /Open filings and export/ })).toHaveAttribute('href', '#/public-filings');
  await expect(page.getByRole('button', { name: /as PDF|as XLSX/ })).toHaveCount(0);

  historyMode = 'unavailable';
  await page.goto('/#/history');
  await expect(page.getByRole('alert').filter({ hasText: 'Saved analyses could not be loaded' })).toBeVisible();
  await expect(page.getByText(/Acme|Globex|Pinnacle/)).toHaveCount(0);

  historyMode = 'saved';
  await page.getByRole('button', { name: 'Retry history', exact: true }).click();
  await expect(page.getByRole('link', { name: /Uploaded statement/ })).toBeVisible();
  await page.getByRole('button', { name: 'Delete Uploaded statement', exact: true }).click();
  await expect(page.getByText('Analysis could not be deleted. It remains in your history.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /Uploaded statement/ })).toBeVisible();
});
