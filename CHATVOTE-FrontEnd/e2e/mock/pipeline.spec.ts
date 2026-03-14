import { test, expect } from '../support/base-test';
import type { Page } from '@playwright/test';

const SECRET = 'test-secret';
const ADMIN_URL = `/admin/dashboard/${SECRET}`;

// Flat NodesMap — PipelineTab does `const data: NodesMap = await res.json()`
const STATUS_MOCK = {
  population: {
    node_id: 'population',
    label: 'population',
    enabled: true,
    status: 'success',
    last_run_at: '2026-03-14T00:00:00Z',
    last_duration_s: 12.5,
    last_error: null,
    counts: { communes: 500 },
    settings: { top_n_communes: 500 },
    checkpoints: {},
  },
  candidatures: {
    node_id: 'candidatures',
    label: 'candidatures',
    enabled: true,
    status: 'idle',
    last_run_at: null,
    last_duration_s: null,
    last_error: null,
    counts: {},
    settings: {},
    checkpoints: {},
  },
  seed: {
    node_id: 'seed',
    label: 'seed',
    enabled: true,
    status: 'error',
    last_run_at: '2026-03-13T23:00:00Z',
    last_duration_s: 45.2,
    last_error: 'Firestore quota exceeded',
    counts: { candidates: 1200, parties: 16 },
    settings: {},
    checkpoints: {},
  },
  scraper: {
    node_id: 'scraper',
    label: 'scraper',
    enabled: true,
    status: 'running',
    last_run_at: '2026-03-14T00:30:00Z',
    last_duration_s: null,
    last_error: null,
    counts: { scraped: 150, total: 500 },
    settings: { backend: 'playwright' },
    checkpoints: {},
  },
  indexer: {
    node_id: 'indexer',
    label: 'indexer',
    enabled: false,
    status: 'idle',
    last_run_at: null,
    last_duration_s: null,
    last_error: null,
    counts: {},
    settings: {},
    checkpoints: {},
  },
};

/**
 * Mock admin APIs via addInitScript — patches window.fetch before any scripts
 * run. This is necessary because page.route() doesn't reliably intercept
 * cross-origin requests from dynamically imported Next.js modules (the admin
 * page lazy-loads PipelineTab via next/dynamic with ssr:false).
 */
async function mockAdminApis(page: Page, statusData: Record<string, unknown> = STATUS_MOCK) {
  const statusJson = JSON.stringify(statusData);
  await page.addInitScript((mockData) => {
    const originalFetch = window.fetch;
    // Store action log on window so tests can query it
    (window as any).__adminMockLog = [] as string[];
    window.fetch = async function patchedFetch(input: RequestInfo | URL, init?: RequestInit) {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const method = init?.method ?? 'GET';

      if (url.includes('/api/v1/admin/data-sources/status') && method === 'GET') {
        return new Response(mockData, { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/v1/admin/maintenance')) {
        return new Response(JSON.stringify({ enabled: false }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/v1/admin/data-sources/k8s-status')) {
        return new Response(JSON.stringify({ available: false }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/v1/admin/data-sources/config/')) {
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/v1/admin/data-sources/run-all')) {
        (window as any).__adminMockLog.push('run-all');
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/v1/admin/data-sources/run/')) {
        const nodeId = url.split('/').pop();
        (window as any).__adminMockLog.push(`run:${nodeId}`);
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.includes('/api/v1/admin/data-sources/stop/')) {
        const nodeId = url.split('/').pop();
        (window as any).__adminMockLog.push(`stop:${nodeId}`);
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return originalFetch.call(window, input, init);
    };
  }, statusJson);
}

/** Mock admin APIs to return 403 (unauthorized) */
async function mockAdminApisUnauthorized(page: Page) {
  await page.addInitScript(() => {
    const originalFetch = window.fetch;
    window.fetch = async function patchedFetch(input: RequestInfo | URL, init?: RequestInit) {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/admin/data-sources/status')) {
        return new Response('Forbidden', { status: 403 });
      }
      if (url.includes('/api/v1/admin/maintenance')) {
        return new Response('Forbidden', { status: 403 });
      }
      return originalFetch.call(window, input, init);
    };
  });
}

test.describe('Admin Dashboard Pipeline Tab (mocked)', () => {
  test.beforeEach(async ({ expectedErrors }) => {
    expectedErrors.push(/webpack-hmr/);
    expectedErrors.push(/auth\/network-request-failed/);
    expectedErrors.push(/FirebaseError/);
    expectedErrors.push(/Failed to load resource/);
    expectedErrors.push(/analytics/i);
    expectedErrors.push(/API key not valid/);
    expectedErrors.push(/permission-denied/);
    expectedErrors.push(/No matching allow statements/);
  });

  test('dashboard loads and shows all 8 tab buttons', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });

    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Coverage' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Charts' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Chat Sessions' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Multi Query' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Data Consistency' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Crawler' })).toBeVisible();
  });

  test('unauthorized access shows error', async ({ page }) => {
    await mockAdminApisUnauthorized(page);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(page.getByText('Unauthorized')).toBeVisible({ timeout: 10000 });
  });

  test('pipeline tab shows all pipeline node names', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });

    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // Node labels rendered in h3 elements inside NodeCard
    await expect(page.getByText(/population/i).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/candidatures/i).first()).toBeVisible();
    await expect(page.getByText(/seed/i).first()).toBeVisible();
    await expect(page.getByText(/scraper/i).first()).toBeVisible();
    await expect(page.getByText(/indexer/i).first()).toBeVisible();
  });

  test('success node (population) shows emerald status dot', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // statusDot uses bg-emerald-500 for success
    const populationCard = page.locator('[data-node-id="population"]');
    await expect(populationCard.locator('[class*="bg-emerald-500"]').first()).toBeVisible({ timeout: 15000 });
  });

  test('error node (seed) shows red status dot', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // statusDot uses bg-red-500/100 for error
    const seedCard = page.locator('[data-node-id="seed"]');
    await expect(seedCard.locator('[class*="bg-red-500"]').first()).toBeVisible({ timeout: 15000 });
  });

  test('running node (scraper) shows amber pulsing status dot', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // statusDot uses animate-pulse bg-amber-400 for running
    const scraperCard = page.locator('[data-node-id="scraper"]');
    await expect(scraperCard.locator('[class*="animate-pulse"]').first()).toBeVisible({ timeout: 15000 });
  });

  test('idle node (candidatures) shows neutral status dot', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // Idle nodes use bg-muted-foreground — no pulse, no emerald, no red
    const candidaturesCard = page.locator('[data-node-id="candidatures"]');
    await expect(candidaturesCard).toBeVisible({ timeout: 15000 });
    await expect(candidaturesCard.locator('[class*="animate-pulse"]')).not.toBeVisible();
  });

  test('error node (seed) shows error message text', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    await expect(page.getByText('Firestore quota exceeded')).toBeVisible({ timeout: 15000 });
  });

  test('run button triggers node execution POST request', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // candidatures is idle+enabled → shows Run button
    const candidaturesCard = page.locator('[data-node-id="candidatures"]');
    await expect(candidaturesCard).toBeVisible({ timeout: 15000 });
    const runBtn = candidaturesCard.getByRole('button', { name: 'Run' });
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await runBtn.click();

    // Check the mock log for the run action
    await expect.poll(
      () => page.evaluate(() => (window as any).__adminMockLog),
      { timeout: 5000 },
    ).toContainEqual('run:candidatures');
  });

  test('stop button triggers node stop POST request', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // scraper is running → shows Stop button
    const scraperCard = page.locator('[data-node-id="scraper"]');
    await expect(scraperCard).toBeVisible({ timeout: 15000 });
    const stopBtn = scraperCard.getByRole('button', { name: 'Stop' });
    await expect(stopBtn).toBeVisible({ timeout: 10000 });
    await stopBtn.click();

    await expect.poll(
      () => page.evaluate(() => (window as any).__adminMockLog),
      { timeout: 5000 },
    ).toContainEqual('stop:scraper');
  });

  test('Run All button triggers full pipeline POST request', async ({ page }) => {
    // Use a STATUS_MOCK without any running nodes — when anyRunning is true,
    // the toolbar shows "Stop All" instead of "Run All Enabled"
    const noRunningMock = {
      ...STATUS_MOCK,
      scraper: { ...STATUS_MOCK.scraper, status: 'success', last_duration_s: 30.0 },
    };
    await mockAdminApis(page, noRunningMock);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    await expect(page.getByText(/population/i).first()).toBeVisible({ timeout: 15000 });

    // "Run All Enabled" button in the pipeline toolbar (visible when no node is running)
    const runAllBtn = page.getByRole('button', { name: 'Run All Enabled' });
    await expect(runAllBtn).toBeVisible({ timeout: 10000 });
    await runAllBtn.click();

    await expect.poll(
      () => page.evaluate(() => (window as any).__adminMockLog),
      { timeout: 5000 },
    ).toContainEqual('run-all');
  });

  test('node counts display correctly', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    await expect(page.getByText(/population/i).first()).toBeVisible({ timeout: 15000 });

    // Population node has communes: 500
    await expect(page.getByText('500').first()).toBeVisible({ timeout: 10000 });

    // Seed node has candidates: 1200
    await expect(page.getByText('1200').first()).toBeVisible({ timeout: 10000 });
  });

  test('disabled node (indexer) has Run button disabled', async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(`${ADMIN_URL}?tab=pipeline`, { timeout: 30000 });
    await expect(page.getByRole('heading', { name: 'Admin Dashboard' })).toBeVisible({ timeout: 15000 });

    // Disabled nodes have Run button with disabled={!node.enabled}
    const indexerCard = page.locator('[data-node-id="indexer"]');
    await expect(indexerCard).toBeVisible({ timeout: 15000 });
    const runBtn = indexerCard.getByRole('button', { name: 'Run' });
    await expect(runBtn).toBeDisabled({ timeout: 10000 });
  });
});
