import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Quick Reply Suggestions', () => {
  test('Quick replies appear after response completes', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);
    await expect(page.getByRole('button', { name: /what about education/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: /tell me about healthcare/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: /economic policies/i })).toBeVisible({ timeout: 10000 });
  });

  test('Clicking a quick reply sends it as a new message', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);
    await page.getByRole('button', { name: /what about education/i }).click();
    // Should trigger another response cycle
    await expect(page.getByText('Response chunk').first()).toBeVisible({ timeout: 30000 });
  });
});
