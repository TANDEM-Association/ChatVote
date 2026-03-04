import { test, expect } from '@playwright/test';
import { setupChat, goToChat, getChatInput } from '../support/test-helpers';

test.describe('Chat Input and Message Submission', () => {
  test('Chat input is disabled before municipality selection', async ({ page }) => {
    await goToChat(page);
    await expect(getChatInput(page)).toBeDisabled();
  });

  test('Chat input becomes enabled after municipality selection', async ({ page }) => {
    await setupChat(page);
    await expect(getChatInput(page)).toBeEnabled();
  });

  test('Pressing Enter submits the message', async ({ page }) => {
    await setupChat(page);
    const chatInput = getChatInput(page);
    await chatInput.fill('Test question');
    await chatInput.press('Enter');
    // The user message should appear in the chat
    await expect(page.getByText('Test question')).toBeVisible({ timeout: 10000 });
  });

  test('Empty input does not submit', async ({ page }) => {
    await setupChat(page);
    const chatInput = getChatInput(page);
    await chatInput.press('Enter');
    // URL should NOT have chat_id
    await expect(page).not.toHaveURL(/chat_id=/);
  });
});
