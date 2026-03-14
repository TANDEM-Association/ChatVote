import { test, expect } from '../support/base-test';

const MOCK_TOPIC_STATS = {
  total_chunks: 450,
  classified_chunks: 380,
  unclassified_chunks: 70,
  themes: [
    {
      theme: 'environnement',
      count: 85,
      percentage: 18.9,
      by_party: { 'Les Écologistes': 30, 'Place Publique': 25, Renaissance: 15, LFI: 15 },
      by_source: { election_manifesto: 50, candidate_website_programme: 35 },
      by_fiabilite: { '1': 10, '2': 60, '3': 15 },
      sub_themes: [
        { name: 'biodiversité', count: 30, by_party: { 'Les Écologistes': 15 } },
        { name: 'énergie renouvelable', count: 25, by_party: { 'Place Publique': 10 } },
        { name: 'pollution', count: 20, by_party: { Renaissance: 5 } },
      ],
    },
    {
      theme: 'économie',
      count: 65,
      percentage: 14.4,
      by_party: { Renaissance: 35, LFI: 20, RN: 10 },
      by_source: { election_manifesto: 40, candidate_website_programme: 25 },
      by_fiabilite: { '1': 5, '2': 50, '3': 10 },
      sub_themes: [
        { name: 'emploi', count: 40, by_party: { Renaissance: 20 } },
        { name: 'fiscalité', count: 25, by_party: { LFI: 10 } },
      ],
    },
    {
      theme: 'sécurité',
      count: 45,
      percentage: 10.0,
      by_party: { RN: 25, Renaissance: 15, LR: 5 },
      by_source: { election_manifesto: 30, candidate_website_programme: 15 },
      by_fiabilite: { '2': 35, '3': 10 },
      sub_themes: [
        { name: 'police', count: 25, by_party: { RN: 15 } },
        { name: 'justice', count: 20, by_party: { LR: 5 } },
      ],
    },
  ],
  collections: {
    all_parties_dev: { total: 200, classified: 170 },
    candidates_websites_dev: { total: 250, classified: 210 },
  },
};

test.describe('Topic Insights Page', () => {
  test.beforeEach(async ({ page, expectedErrors }) => {
    // HMR websocket errors are expected in test environment
    expectedErrors.push(/webpack-hmr/);

    // Intercept the backend API calls with mock data
    await page.route('**/api/experiment/topics', (route) =>
      route.fulfill({ json: MOCK_TOPIC_STATS }),
    );
  });

  test('page loads and shows header', async ({ page }) => {
    await page.goto('/experiment/topics');
    await expect(page.getByRole('heading', { name: 'Topic Insights' })).toBeVisible();
    await expect(page.getByText('Knowledge Base Themes')).toBeVisible();
  });

  test('shows summary stat cards', async ({ page }) => {
    await page.goto('/experiment/topics');
    await expect(page.getByText('450')).toBeVisible(); // Total Chunks
    await expect(page.getByText('380')).toBeVisible(); // Classified
    await expect(page.getByText('70', { exact: true })).toBeVisible();  // Unclassified
  });

  test('shows collection breakdown', async ({ page }) => {
    await page.goto('/experiment/topics');
    await expect(page.getByText('all_parties_dev')).toBeVisible();
    await expect(page.getByText('candidates_websites_dev')).toBeVisible();
    await expect(page.getByText('170/200')).toBeVisible();
    await expect(page.getByText('210/250')).toBeVisible();
  });

  test('shows distribution bar chart with themes', async ({ page }) => {
    await page.goto('/experiment/topics');
    await expect(page.getByRole('heading', { name: 'Distribution' })).toBeVisible();
    await expect(page.getByText('environnement').first()).toBeVisible();
    await expect(page.getByText('économie').first()).toBeVisible();
    await expect(page.getByText('sécurité').first()).toBeVisible();
  });

  test('theme cards are expandable', async ({ page }) => {
    await page.goto('/experiment/topics');

    // Theme details section should exist
    await expect(page.getByText('Theme Details')).toBeVisible();

    // Click first theme card to expand it
    const firstCard = page.locator('button', { hasText: 'environnement' }).first();
    await firstCard.click();

    // After expanding, party breakdown should be visible
    await expect(page.getByText('Party Distribution')).toBeVisible();
    await expect(page.getByText('Les Écologistes').first()).toBeVisible();

    // Sub-themes should be visible
    await expect(page.getByText('Sub-themes')).toBeVisible();
    await expect(page.getByText('biodiversité')).toBeVisible();
  });

  test('shows unclassified chunks section', async ({ page }) => {
    await page.goto('/experiment/topics');
    await expect(page.getByText('Unclassified Chunks')).toBeVisible();
    await expect(page.getByText(/70 chunks.*have no theme assigned/)).toBeVisible();
  });

});

test.describe('Experiment Playground → Topic Insights Navigation', () => {
  test.beforeEach(async ({ page, expectedErrors }) => {
    expectedErrors.push(/webpack-hmr/);

    // Mock the schema endpoint so experiment playground loads
    await page.route('**/api/experiment/schema', (route) =>
      route.fulfill({
        json: {
          themes: ['environnement', 'économie'],
          fiabilite_levels: { '1': 'GOVERNMENT', '2': 'OFFICIAL' },
          namespaces: ['renaissance'],
          nuances_politiques: [],
          collections: ['parties', 'candidates'],
        },
      }),
    );
  });

  test('experiment playground has link to Topic Insights', async ({ page }) => {
    await page.goto('/experiment');
    const link = page.getByRole('link', { name: 'Topic Insights' });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', '/experiment/topics');
  });
});
