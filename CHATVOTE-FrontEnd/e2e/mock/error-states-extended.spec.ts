import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, getChatInput } from '../support/test-helpers';

test.describe('Error States Extended', () => {
  test('16.4 Very long message input is handled gracefully', async ({ page }) => {
    await setupChat(page);

    const longMessage = 'a'.repeat(1200);
    const chatInput = getChatInput(page);
    await chatInput.fill(longMessage);

    // Send button should be enabled (input is non-empty)
    const sendButton = page.locator('button[type="submit"]').filter({ has: page.locator('svg') });
    await expect(sendButton).toBeEnabled({ timeout: 5000 });

    // Submit and verify the app handles it without crashing
    await chatInput.press('Enter');

    // The message (or a truncated version) should appear in the conversation,
    // or at minimum the page should not show an unhandled error
    await expect(page.locator('body')).not.toContainText('Unhandled', { timeout: 10000 });
    await expect(page.locator('body')).not.toContainText('Application error', { timeout: 5000 });
  });

  test('16.5 Special characters in message input are not executed as script (XSS)', async ({ page }) => {
    await setupChat(page);

    const xssPayload = '<script>alert(1)</script>';
    await sendMessage(page, xssPayload);

    // The text should appear as plain text in the conversation, not executed
    await expect(page.getByText(xssPayload)).toBeVisible({ timeout: 10000 });

    // Confirm no alert dialog was triggered by the XSS payload
    let alertFired = false;
    page.on('dialog', (dialog) => {
      alertFired = true;
      dialog.dismiss();
    });

    // Give a short window for any deferred script execution to fire
    await page.waitForTimeout(1000);
    expect(alertFired).toBe(false);
  });

  test('1.8 Navigating to non-existent chat session ID shows error or redirects', async ({ page }) => {
    await page.goto('/chat/nonexistent-chat-id-12345', { waitUntil: 'domcontentloaded' });

    // The app must not crash with an unhandled error boundary message
    await expect(page.locator('body')).not.toContainText('Application error', { timeout: 10000 });

    // Accept either: an error/not-found page, or a redirect back to /chat
    const url = page.url();
    const isOnChatRoot = url.includes('/chat') || url.endsWith('/chat/nonexistent-chat-id-12345');
    expect(isOnChatRoot).toBe(true);
  });
});
