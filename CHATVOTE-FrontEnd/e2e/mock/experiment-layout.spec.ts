import { expect, test } from "../support/base-test";

test.describe("Experiment Pages Layout", () => {
  test.beforeEach(async ({ page, expectedErrors }) => {
    expectedErrors.push(/analytics/i);
    expectedErrors.push(/API key not valid/);
    expectedErrors.push(/permission-denied/);
    expectedErrors.push(/No matching allow statements/);

    // Mock client-side fetches (experiment schema, topics)
    await page.route("**/api/experiment/schema", (route) =>
      route.fulfill({
        json: {
          themes: ["environnement", "économie"],
          fiabilite_levels: { "1": "GOVERNMENT", "2": "OFFICIAL" },
          namespaces: ["renaissance"],
          nuances_politiques: [],
          collections: ["parties", "candidates"],
        },
      }),
    );
    await page.route("**/api/experiment/topics", (route) =>
      route.fulfill({
        json: {
          total_chunks: 0,
          classified_chunks: 0,
          unclassified_chunks: 0,
          themes: [],
          collections: {},
        },
      }),
    );
    await page.route("**/api/experiment/bertopic", (route) =>
      route.fulfill({
        json: {
          status: "success",
          total_messages: 0,
          num_topics: 0,
          topics: [],
        },
      }),
    );
  });

  test("experiment main page has sidebar and heading", async ({ page }) => {
    await page.goto("/experiment", { timeout: 30000 });
    await expect(page.getByRole("heading", { name: "Experiment" })).toBeVisible(
      { timeout: 15000 },
    );
    // Icon sidebar chat link
    await expect(page.locator('a[href="/chat"]').first()).toBeVisible();
  });

  test("experiment main page has back arrow to /chat", async ({ page }) => {
    await page.goto("/experiment", { timeout: 30000 });
    await expect(page.getByRole("heading", { name: "Experiment" })).toBeVisible(
      { timeout: 15000 },
    );
    await expect(page.locator('a[href="/chat"]').first()).toBeVisible();
  });

  test("topics page has sidebar", async ({ page }) => {
    await page.goto("/experiment/topics", { timeout: 30000 });
    await expect(
      page.getByRole("heading", { name: "Topic Insights" }).first(),
    ).toBeVisible({ timeout: 15000 });
    // Sidebar chat link should be visible
    await expect(page.locator('a[href="/chat"]').first()).toBeVisible();
  });
});
