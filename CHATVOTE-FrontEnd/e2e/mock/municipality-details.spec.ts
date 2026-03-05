import { test, expect } from '../support/base-test';
import { goToChat, selectMunicipality, getChatInput } from '../support/test-helpers';

test.describe('Municipality Details', () => {
  test('3.1 Municipality search input is visible on empty chat page', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByPlaceholder(/commune|municipality/i).first()).toBeVisible({ timeout: 10000 });
    await expect(getChatInput(page)).toBeDisabled({ timeout: 5000 });
  });

  test('3.2 Typing in municipality input shows autocomplete suggestions', async ({ page }) => {
    await goToChat(page);
    const municipalityInput = page.getByPlaceholder(/commune|municipality/i).first();
    await expect(municipalityInput).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await municipalityInput.pressSequentially('Paris', { delay: 80 });
    // Autocomplete dropdown should show list items
    const firstResult = page.locator('li').filter({ hasText: 'Paris' }).first();
    await expect(firstResult).toBeVisible({ timeout: 10000 });
  });

  test('3.5 Municipality selection persists when navigating back', async ({ page }) => {
    await goToChat(page);
    await selectMunicipality(page, 'Paris');
    // URL should contain municipality_code after selection
    await expect(page).toHaveURL(/municipality_code=/, { timeout: 5000 });
    // Navigate away then back
    await page.goto('/guide');
    await page.goBack();
    // municipality_code should still be in the URL
    await expect(page).toHaveURL(/municipality_code=/, { timeout: 10000 });
  });

  test('3.6 Typing non-existent municipality shows no results', async ({ page }) => {
    await goToChat(page);
    const municipalityInput = page.getByPlaceholder(/commune|municipality/i).first();
    await expect(municipalityInput).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await municipalityInput.pressSequentially('xyznonexistent999', { delay: 50 });
    // Wait for any potential async fetch to settle
    await page.waitForTimeout(2000);
    // No autocomplete list items should be visible
    await expect(page.locator('li').filter({ hasText: 'xyznonexistent999' }).first()).not.toBeVisible({ timeout: 5000 });
    // Chat input should remain disabled
    await expect(getChatInput(page)).toBeDisabled({ timeout: 5000 });
  });
});
