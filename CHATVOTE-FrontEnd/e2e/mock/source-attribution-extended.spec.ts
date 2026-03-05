import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Source Attribution Extended', () => {
  // FIXME: Mock server only sends sources for selected parties. Without party
  // selection the sources loop is skipped. Needs party selection before message send.
  test.fixme('Clicking Sources button shows source document details', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // The Sources button is rendered by SourcesButton component with text from tCommon("sources") = "Sources"
    const sourcesButton = page.getByRole('button', { name: /sources/i }).first();
    await expect(sourcesButton).toBeVisible({ timeout: 10000 });
    await sourcesButton.click();

    // The modal opens and shows the sources panel heading and source content_preview
    // Mock source has content: 'Relevant source content for testing.'
    await expect(page.getByText('Relevant source content for testing.')).toBeVisible({ timeout: 5000 });
  });

  test('Copy button copies response text', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // CopyButton is a ghost icon-only button with a sr-only "Copy" span.
    // It switches from Copy icon to Check icon after clicking.
    const copyButton = page.locator('button .lucide-copy').first();
    await expect(copyButton).toBeVisible({ timeout: 10000 });
    await copyButton.click();

    // After clicking, the Copy icon is replaced by the Check icon (visual confirmation)
    const checkIcon = page.locator('button .lucide-check').first();
    await expect(checkIcon).toBeVisible({ timeout: 5000 });
  });
});
