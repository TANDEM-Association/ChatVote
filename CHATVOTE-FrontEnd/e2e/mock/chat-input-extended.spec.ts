import { test, expect } from '@playwright/test';
import { setupChat, sendMessage, getChatInput } from '../support/test-helpers';

test.describe('Chat Input Extended', () => {
  test('4.4 Clicking the send button submits the message', async ({ page }) => {
    await setupChat(page);
    const chatInput = getChatInput(page);
    await chatInput.fill('Tell me about healthcare');

    // The submit button contains the ArrowUp lucide icon
    const sendButton = page.locator('button[type="submit"]').filter({ has: page.locator('svg') });
    await sendButton.click();

    await expect(page.getByText('Tell me about healthcare')).toBeVisible({ timeout: 10000 });
  });

  test('4.6 Whitespace-only input does not submit', async ({ page }) => {
    await setupChat(page);
    const chatInput = getChatInput(page);
    await chatInput.fill('   ');
    await chatInput.press('Enter');

    // URL should NOT have chat_id query param (no session was started)
    await expect(page).not.toHaveURL(/chat_id=/, { timeout: 5000 });
  });

  test('4.7 Send button is disabled when input is empty, enabled when input has text', async ({ page }) => {
    await setupChat(page);

    const sendButton = page.locator('button[type="submit"]').filter({ has: page.locator('svg') });

    // Empty input — button must be disabled
    await expect(sendButton).toBeDisabled({ timeout: 5000 });

    // Type a character — button must become enabled
    const chatInput = getChatInput(page);
    await chatInput.type('a');
    await expect(sendButton).toBeEnabled({ timeout: 5000 });
  });

  test.describe('Streaming state', () => {
    test.use({ viewport: { width: 1280, height: 720 } });

    // Serial to avoid race conditions with the loading state window
    test('4.8 Chat input is disabled while response is streaming', async ({ page }) => {
      await setupChat(page);
      await sendMessage(page, 'What is your housing policy?');

      // Immediately after sending, the store sets loading.newMessage = true,
      // which disables both the input and the send button.
      // We poll for up to 5 s to catch the loading window before it clears.
      const chatInput = getChatInput(page);
      await expect(chatInput).toBeDisabled({ timeout: 5000 });
    });
  });

  test('4.9 AI disclaimer text is visible below chat input', async ({ page }) => {
    await setupChat(page);
    await expect(
      page.getByText(/chatvote peut faire des erreurs|chatvote can make mistakes/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test('4.10 Learn more button next to disclaimer is clickable and opens info panel', async ({ page }) => {
    await setupChat(page);

    // The disclaimer has a "learn more" button: EN "Learn more here." / FR "En savoir plus ici."
    const learnMoreButton = page.locator('button').filter({
      hasText: /en savoir plus|learn more/i,
    });
    await expect(learnMoreButton).toBeVisible({ timeout: 10000 });
    await learnMoreButton.click();

    // Clicking opens a custom Modal (no role="dialog") with AI disclaimer details.
    // EN title: "AI Notice" / FR title: "Avertissement IA"
    await expect(
      page.getByRole('heading', { name: /AI Notice|Avertissement IA/i })
    ).toBeVisible({ timeout: 5000 });
  });
});
