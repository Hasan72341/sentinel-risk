import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';

// The fixtures are the backend's own demo responses, so these tests fail when a
// page reads keys the API does not return.
const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name: string) => readFileSync(join(here, 'fixtures', `${name}-demo.json`), 'utf8');

async function mockJson(page: Page, pattern: string, body: string | object) {
  await page.route(pattern, (route) => route.fulfill({
    contentType: 'application/json',
    body: typeof body === 'string' ? body : JSON.stringify(body),
  }));
}

const demoPages = [
  {
    slug: 'stochastic-calculus',
    tabs: ['GBM / Itô', 'Heston', 'Greeks', 'Barrier', 'Jump-Diffusion'],
    shows: ['Simulated Paths'],
  },
  {
    slug: 'network-analysis',
    tabs: ['Correlation Network', 'MST', 'Contagion', 'Systemic Risk'],
    shows: ['Network Analysis Demo'],
  },
  {
    slug: 'advanced-optimization',
    tabs: ['SOCP Portfolio', 'Robust Optimization', 'HRP', 'Pareto Frontier'],
    shows: ['Expected Return'],
  },
  {
    slug: 'causal-inference',
    tabs: ['Granger Causality', 'Impulse Response', 'Transfer Entropy', 'Mutual Information', 'Causal Discovery'],
    shows: ['Causal Structure Recovery'],
  },
];

for (const demo of demoPages) {
  test(`${demo.slug} renders every tab from the real demo response`, async ({ page }) => {
    await mockJson(page, `**/api/v1/${demo.slug}/demo`, fixture(demo.slug));
    await page.goto(`/#/${demo.slug}`);
    const main = page.getByRole('main');
    for (const text of demo.shows) await expect(main.getByText(text).first()).toBeVisible();

    for (const tab of demo.tabs) {
      await main.getByRole('button', { name: tab, exact: true }).click();
      // No empty-state message and no metric card left without a value.
      await expect(main.getByText(/^No .* available$/)).toHaveCount(0);
      await expect(main.locator('p', { hasText: /^—$/ })).toHaveCount(0);
    }
    await main.getByRole('button', { name: demo.tabs[0], exact: true }).click();
    await expect(main.locator('svg.recharts-surface, table').first()).toBeVisible();
  });
}

test('factor analysis renders the demo response', async ({ page }) => {
  await mockJson(page, '**/api/v1/factor-analysis/demo', fixture('factor-analysis'));
  await page.goto('/#/factor-analysis');
  await page.getByRole('main').getByRole('button', { name: 'Analyse sample factors', exact: true }).click();
  await expect(page.getByRole('main').locator('svg.recharts-surface').first()).toBeVisible();
});

test('history lists analyses from the flat snake_case API response', async ({ page }) => {
  await mockJson(page, '**/api/v1/analysis/history**', [{
    analysis_id: 'a1b2c3d4', company_name: 'Lotus Harbor Trading', period: 'FY 2025',
    file_name: 'lotus.csv', created_at: '2026-09-01T10:00:00',
    summary: { profitability: 80, liquidity: 70, leverage: 60, efficiency: 50 },
  }]);
  await page.goto('/#/history');
  await expect(page.getByText('Lotus Harbor Trading').first()).toBeVisible();
  await expect(page.getByText('(sample)')).toHaveCount(0);
});

test('reports show the public study when there are no saved analyses', async ({ page }) => {
  await mockJson(page, '**/api/v1/analysis/history**', []);
  await page.goto('/#/reports');
  await expect(page.getByRole('heading', { name: 'No saved statement analyses' })).toBeVisible();
  await expect(page.getByText('Acme Corporation (sample)')).toHaveCount(0);
  await expect(page.getByRole('link', { name: /Open filings and export/ })).toHaveAttribute('href', '#/public-filings');
});

test('preferences use backend field names without an activation form', async ({ page }) => {
  await mockJson(page, '**/api/v1/analysis/history**', []);
  let saved: Record<string, unknown> | null = null;
  await page.route('**/api/v1/settings/preferences', async (route) => {
    if (route.request().method() === 'PUT') {
      saved = route.request().postDataJSON();
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(saved) });
    } else {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ default_language: 'en', chart_theme: 'light', decimal_places: 3, auto_save: true }),
      });
    }
  });

  await page.goto('/#/settings');
  await expect(page.getByText(/Free Tier|Manage your subscription|License activated/i)).toHaveCount(0);
  await page.getByRole('button', { name: 'Save preferences', exact: true }).click();
  await expect(page.getByText('Preferences saved')).toBeVisible();
  expect(saved).toEqual({ default_language: 'en', chart_theme: 'light', decimal_places: 3, auto_save: true });
});
