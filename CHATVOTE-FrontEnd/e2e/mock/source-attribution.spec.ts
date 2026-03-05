import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Source Attribution', () => {
  test('Response contains source information', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);
    // Sources should be present somewhere in the response area
    // The mock server sends sources with title 'Source Document'
    // Look for a sources button or link
    const sourcesIndicator = page.getByText(/source/i).first();
    await expect(sourcesIndicator).toBeVisible({ timeout: 10000 });
  });
});
