import { expect, test } from "../support/base-test";

test.describe("Static Information Pages", () => {
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

  test.describe("Privacy Policy page", () => {
    test("loads and shows the main heading", async ({ page }) => {
      await page.goto("/privacy-policy", { timeout: 30000 });
      await expect(page).toHaveURL(/\/privacy-policy/);
      await expect(
        page.getByRole("heading", { name: /politique de confidentialité/i }),
      ).toBeVisible({ timeout: 15000 });
    });

    test("shows the legal basis section heading", async ({ page }) => {
      await page.goto("/privacy-policy", { timeout: 30000 });
      await expect(
        page.getByRole("heading", { name: /Bases juridiques applicables/i }),
      ).toBeVisible({ timeout: 15000 });
    });

    test("shows the data subject rights section", async ({ page }) => {
      await page.goto("/privacy-policy", { timeout: 30000 });
      await expect(
        page.getByRole("heading", { name: /Droits des personnes concernées/i }),
      ).toBeVisible({ timeout: 15000 });
    });

    test("shows contact email", async ({ page }) => {
      await page.goto("/privacy-policy", { timeout: 30000 });
      await expect(page.getByText(/contact@chatvote\.org/i)).toBeVisible({
        timeout: 15000,
      });
    });
  });

  test.describe("Legal Notice page", () => {
    test("loads and shows the main heading", async ({ page }) => {
      await page.goto("/legal-notice", { timeout: 30000 });
      await expect(page).toHaveURL(/\/legal-notice/);
      await expect(
        page.getByRole("heading", { name: /mentions légales/i }),
      ).toBeVisible({ timeout: 15000 });
    });

    test("shows organization name TANDEM", async ({ page }) => {
      await page.goto("/legal-notice", { timeout: 30000 });
      await expect(page.getByText(/TANDEM/)).toBeVisible({ timeout: 15000 });
    });

    test("shows contact section", async ({ page }) => {
      await page.goto("/legal-notice", { timeout: 30000 });
      await expect(page.getByText(/contact@chatvote\.org/i)).toBeVisible({
        timeout: 15000,
      });
    });
  });

  test.describe("Guide page", () => {
    test("loads at /guide URL", async ({ page }) => {
      await page.goto("/guide", { timeout: 30000 });
      await expect(page).toHaveURL(/\/guide/);
    });

    test("shows a heading", async ({ page }) => {
      await page.goto("/guide", { timeout: 30000 });
      // GuideTitle renders an h1 with the translated guide.title key
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 15000 });
    });

    test("shows page content", async ({ page }) => {
      await page.goto("/guide", { timeout: 30000 });
      // The HowTo component renders below the title — page should have body content
      await expect(page.locator("main, article, section").first()).toBeVisible({
        timeout: 15000,
      });
    });
  });

  test.describe("Navigation to static pages", () => {
    test("navigating to /guide shows the guide page", async ({ page }) => {
      await page.goto("/guide", { timeout: 30000 });
      await expect(page).toHaveURL(/\/guide/);
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 15000 });
    });

    test("navigating to /privacy-policy shows the privacy page", async ({
      page,
    }) => {
      await page.goto("/privacy-policy", { timeout: 30000 });
      await expect(page).toHaveURL(/\/privacy-policy/);
      await expect(
        page.getByRole("heading", { name: /politique de confidentialité/i }),
      ).toBeVisible({ timeout: 15000 });
    });

    test("navigating to /legal-notice shows the legal notice page", async ({
      page,
    }) => {
      await page.goto("/legal-notice", { timeout: 30000 });
      await expect(page).toHaveURL(/\/legal-notice/);
      await expect(
        page.getByRole("heading", { name: /mentions légales/i }),
      ).toBeVisible({ timeout: 15000 });
    });
  });
});
