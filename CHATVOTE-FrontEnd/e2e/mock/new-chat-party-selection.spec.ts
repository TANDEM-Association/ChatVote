import { test, expect } from '@playwright/test';
import { goToChat, setupChat } from '../support/test-helpers';

test.describe('New Chat and Party Selection', () => {
  test('Municipality selection changes URL and displays municipality name', async ({ page }) => {
    await goToChat(page);
    const municipalityInput = page.getByPlaceholder(/commune|municipality/i).first();
    await expect(municipalityInput).toBeVisible({ timeout: 10000 });
    // Wait briefly for /api/municipalities to load before typing
    await page.waitForTimeout(1000);
    await municipalityInput.pressSequentially('Lyon', { delay: 80 });
    // Use filter to target the municipality autocomplete result, not sidebar listitems
    const firstResult = page.locator('li').filter({ hasText: 'Lyon' }).first().locator('button');
    await expect(firstResult).toBeVisible({ timeout: 10000 });
    await firstResult.click();
    // URL should contain municipality_code after selection
    await expect(page).toHaveURL(/municipality_code=/, { timeout: 5000 });
    // Municipality name should be displayed (MunicipalitySearch shows "{nom}, {postalCode}")
    await expect(page.getByText(/Lyon, 690/).first()).toBeVisible({ timeout: 5000 });
  });

  test('Comparer les partis button is visible', async ({ page }) => {
    await goToChat(page);
    // Desktop sidebar has icon-only button; mobile/expanded sidebar has labelled button.
    // Check for the GitCompareArrows icon button in either form.
    const iconButton = page.locator('button:has(svg.lucide-git-compare-arrows)').first();
    await expect(iconButton).toBeVisible({ timeout: 5000 });
  });
});
