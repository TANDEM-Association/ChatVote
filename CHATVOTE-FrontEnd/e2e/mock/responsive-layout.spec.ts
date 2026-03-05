import { test, expect } from '../support/base-test';
import { goToChat } from '../support/test-helpers';

test.describe('Responsive Layout', () => {
  test('Mobile viewport hides sidebar', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await goToChat(page);
    // On mobile, the sidebar trigger button in the header is visible (block md:hidden)
    await expect(page.getByRole('button', { name: /toggle sidebar/i }).first()).toBeVisible();
  });

  test('Desktop viewport shows sidebar', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await goToChat(page);
    await expect(page.getByRole('link', { name: /legal notice|mentions légales/i })).toBeVisible({ timeout: 5000 });
  });
});
