import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Error States and Edge Cases', () => {
  test('Disclaimer is visible at bottom', async ({ page }) => {
    await setupChat(page);
    await expect(page.getByText(/chatvote can make mistakes|chatvote peut faire des erreurs/i)).toBeVisible();
  });

  test('Learn more button is clickable', async ({ page }) => {
    await setupChat(page);
    const learnMore = page.getByRole('button', { name: /learn more here|en savoir plus/i });
    await expect(learnMore).toBeVisible();
  });
});
