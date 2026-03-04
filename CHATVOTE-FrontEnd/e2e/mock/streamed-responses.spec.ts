import { test, expect } from '@playwright/test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Streamed Responses', () => {

  test('Submitting a question shows streamed response chunks', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'What is your education policy?');
    // Wait for response content to appear (mock sends "Response chunk 0. Response chunk 1. Response chunk 2. ")
    await expect(page.getByText('Response chunk')).toBeVisible({ timeout: 30000 });
  });

  test('Multiple party responses complete with quick replies', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'What is your education policy?');
    // Verify streaming response appears (at least one party started responding)
    await expect(page.getByText('Response chunk').first()).toBeVisible({ timeout: 30000 });
    // Quick replies appear only after ALL parties finish responding,
    // proving multiple party responses were generated and completed
    await waitForResponseComplete(page);
  });
});
