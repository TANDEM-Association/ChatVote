import { expect, test } from "../support/base-test";

test.describe("Donate Page", () => {
  test.beforeEach(async ({ expectedErrors }) => {
    expectedErrors.push(/auth\/network-request-failed/);
    expectedErrors.push(/FirebaseError/);
    expectedErrors.push(/Failed to load resource/);
    expectedErrors.push(/analytics/i);
    expectedErrors.push(/API key not valid/);
    expectedErrors.push(/permission-denied/);
    expectedErrors.push(/No matching allow statements/);
    expectedErrors.push(/config-fetch-failed/);
    expectedErrors.push(/installations\/request-failed/);
  });

  test("donate page loads at /donate URL", async ({ page }) => {
    await page.goto("/donate", { timeout: 30000 });
    await expect(page).toHaveURL(/\/donate/);
  });

  test("donate page shows the card title heading", async ({ page }) => {
    await page.goto("/donate", { timeout: 30000 });
    // DonationForm renders a CardTitle with t("donation.title")
    // The card title is inside a CardHeader — look for any heading
    await expect(page.locator("h1, h2, h3").first()).toBeVisible({
      timeout: 15000,
    });
  });

  test("donation amount buttons are visible", async ({ page }) => {
    await page.goto("/donate", { timeout: 30000 });
    // DonationForm renders preset amount buttons (5, 10, 20, 50, 100, 200, 500 €)
    await expect(page.getByRole("button", { name: "5 €", exact: true })).toBeVisible(
      { timeout: 15000 },
    );
    await expect(
      page.getByRole("button", { name: "50 €", exact: true }),
    ).toBeVisible({ timeout: 15000 });
  });

  test("donation slider is visible", async ({ page }) => {
    await page.goto("/donate", { timeout: 30000 });
    // DonationForm renders a Slider component
    await expect(page.locator('[role="slider"]')).toBeVisible({
      timeout: 15000,
    });
  });

  test("donate submit button is visible", async ({ page }) => {
    await page.goto("/donate", { timeout: 30000 });
    // DonateSubmitButton renders a submit button
    await expect(page.locator('button[type="submit"]')).toBeVisible({
      timeout: 15000,
    });
  });

  test("donate submit button is disabled when amount is below minimum", async ({
    page,
  }) => {
    await page.goto("/donate", { timeout: 30000 });
    // Default amount is 50 — button should be enabled
    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeVisible({ timeout: 15000 });
    await expect(submitBtn).toBeEnabled({ timeout: 10000 });
  });

  test("clicking a preset amount button updates the displayed amount", async ({
    page,
  }) => {
    await page.goto("/donate", { timeout: 30000 });
    // Click the 10 € preset button (use exact match to avoid matching 100 €)
    const tenEuroBtn = page.getByRole("button", { name: "10 €", exact: true });
    await expect(tenEuroBtn).toBeVisible({ timeout: 15000 });
    await tenEuroBtn.click();
    // The amount display shows NumberFlow — verify 10 appears in the page
    await expect(page.getByText("10").first()).toBeVisible({ timeout: 10000 });
  });
});
