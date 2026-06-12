import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;

test('custom provider settings survive save and reload without subscription UI', async ({ page }) => {
  let saved: { api_key: string; api_endpoint: string; model: string } | null = null;
  await page.route('**/api/v1/analysis/history**', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/ai/configure', async route => {
    if (route.request().method() === 'POST') {
      saved = route.request().postDataJSON();
      await route.fulfill({ json: { status: 'configured', model: saved?.model } });
    } else {
      await route.fulfill({ json: saved
        ? { configured: true, model: saved.model, endpoint: saved.api_endpoint }
        : { configured: false, model: '', endpoint: '' } });
    }
  });
  await page.goto('/#/settings');
  await expect(page.locator('header')).toContainText(`v${version}`);
  await expect(page.getByRole('main').getByText(version, { exact: true })).toBeVisible();
  await expect(page.getByText(/Free Tier|Manage your subscription|Get one here/i)).toHaveCount(0);
  await expect(page.getByText('Local rule-based analysis', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save provider settings' })).toBeDisabled();
  await expect(page.getByLabel('Model ID', { exact: true })).toHaveValue('');

  await page.getByLabel('Provider', { exact: true }).selectOption('custom');
  const endpoint = 'http://127.0.0.1:9123/v1';
  await page.getByLabel('API base URL').fill(endpoint);
  await page.getByLabel('Model ID', { exact: true }).fill('test-model-id');
  await page.getByLabel('API key', { exact: true }).fill('test-key-for-config-regression');
  await page.getByRole('button', { name: 'Save provider settings' }).click();
  await expect(page.getByText('Provider settings saved', { exact: true })).toBeVisible();
  await expect(page.getByLabel('API key', { exact: true })).toHaveValue('');
  expect(saved).toEqual({ api_key: 'test-key-for-config-regression', api_endpoint: endpoint, model: 'test-model-id' });

  await page.reload();
  await expect(page.getByText('Provider configured', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Provider', { exact: true })).toHaveValue('custom');
  await expect(page.getByLabel('API base URL')).toHaveValue(endpoint);
  await expect(page.getByLabel('Model ID', { exact: true })).toHaveValue('test-model-id');
  await expect(page.getByLabel('API key', { exact: true })).toHaveValue('');
});

test('API failure is reported as unavailable, not an offline operating mode', async ({ page }) => {
  await page.route('**/api/v1/health', route => route.fulfill({ status: 503, json: {} }));
  await page.route('**/api/v1/ai/configure', route => route.fulfill({ status: 503, json: {} }));
  await page.goto('/#/settings');
  await expect(page.locator('header')).toContainText('API unavailable');
  await expect(page.getByRole('alert').filter({ hasText: 'Provider settings unavailable' })).toBeVisible();
  await expect(page.getByText('Offline Mode', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Local rule-based analysis', { exact: true })).toHaveCount(0);
});
