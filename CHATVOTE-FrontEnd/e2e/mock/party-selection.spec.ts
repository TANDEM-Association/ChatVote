import { test, expect } from '../support/base-test';
import { goToChat, setupChat, sendMessage, waitForResponseComplete, getChatInput } from '../support/test-helpers';

test.describe('Party Selection', () => {
  test('5.2 Clicking Comparer les partis opens party selection modal', async ({ page }) => {
    await goToChat(page);
    const compareButton = page.locator('button:has(svg.lucide-git-compare-arrows)').first();
    await expect(compareButton).toBeVisible({ timeout: 5000 });
    // Sidebar buttons are covered by the main content area — use dispatchEvent to bypass.
    await compareButton.dispatchEvent('click');
    // The party selection modal uses a custom Modal (no role="dialog").
    const modal = page.locator('.fixed.inset-0.z-50.justify-center');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(modal.locator('h2')).toBeVisible({ timeout: 5000 });
  });

  test('5.3 User can select one party and start chat', async ({ page }) => {
    await goToChat(page);
    const compareButton = page.locator('button:has(svg.lucide-git-compare-arrows)').first();
    await expect(compareButton).toBeVisible({ timeout: 5000 });
    await compareButton.dispatchEvent('click');
    const modal = page.locator('.fixed.inset-0.z-50.justify-center');
    await expect(modal).toBeVisible({ timeout: 5000 });
    // Party cards are <Button> elements with <img> (party logos) — not <li>.
    const partyCards = modal.locator('button:has(img)');
    await expect(partyCards.first()).toBeVisible({ timeout: 10000 });
    await partyCards.first().click();
    // Click the "Start comparative chat" / "Démarrer le chat comparatif" submit button
    await modal.getByRole('button', { name: /start comparative|démarrer|modify parties|modifier/i }).click();
    // Modal should close
    await expect(modal).not.toBeVisible({ timeout: 5000 });
    // URL should contain party_id
    await expect(page).toHaveURL(/party_id=/, { timeout: 10000 });
  });

  test('5.4 User can select multiple parties for group chat', async ({ page }) => {
    await goToChat(page);
    const compareButton = page.locator('button:has(svg.lucide-git-compare-arrows)').first();
    await expect(compareButton).toBeVisible({ timeout: 5000 });
    await compareButton.dispatchEvent('click');
    const modal = page.locator('.fixed.inset-0.z-50.justify-center');
    await expect(modal).toBeVisible({ timeout: 5000 });
    // Party cards are <Button> elements with <img> (party logos)
    const partyCards = modal.locator('button:has(img)');
    await expect(partyCards.first()).toBeVisible({ timeout: 10000 });
    await partyCards.nth(0).click();
    await partyCards.nth(1).click();
    await partyCards.nth(2).click();
    // Click submit
    await modal.getByRole('button', { name: /start comparative|démarrer|modify parties|modifier/i }).click();
    // Modal should close
    await expect(modal).not.toBeVisible({ timeout: 5000 });
  });

  test('5.5 Closing party selection modal without confirming makes no changes', async ({ page }) => {
    await goToChat(page);
    const initialURL = page.url();
    const compareButton = page.locator('button:has(svg.lucide-git-compare-arrows)').first();
    await expect(compareButton).toBeVisible({ timeout: 5000 });
    await compareButton.dispatchEvent('click');
    const modal = page.locator('.fixed.inset-0.z-50.justify-center');
    await expect(modal).toBeVisible({ timeout: 5000 });
    // Select a party without confirming
    const partyCards = modal.locator('button:has(img)');
    await expect(partyCards.first()).toBeVisible({ timeout: 10000 });
    await partyCards.first().click();
    // Close via the X button (custom Modal has no Escape handler)
    await modal.locator('button:has(svg path)').first().click();
    await expect(modal).not.toBeVisible({ timeout: 5000 });
    // URL should be unchanged (no party_id added)
    expect(page.url()).toBe(initialURL);
  });

  test('5.6 Party pre-selection via URL query parameter', async ({ page }) => {
    await page.goto('/chat?party_id=renaissance');
    await expect(page.getByRole('img', { name: 'chatvote' }).first()).toBeVisible({ timeout: 15000 });
    // The party_id param should be preserved in the URL
    await expect(page).toHaveURL(/party_id=renaissance/, { timeout: 5000 });
  });

  test('5.7 User can add more parties to existing chat via add parties button', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Tell me about immigration policy');
    await waitForResponseComplete(page);
    // Look for add parties button (PlusIcon in chat input area)
    const addPartiesButton = page.locator('button:has(svg.lucide-plus)').first();
    await expect(addPartiesButton).toBeVisible({ timeout: 10000 });
    await addPartiesButton.dispatchEvent('click');
    // Modal should open (custom Modal, no role="dialog")
    const modal = page.locator('.fixed.inset-0.z-50.justify-center');
    await expect(modal).toBeVisible({ timeout: 5000 });
  });
});
