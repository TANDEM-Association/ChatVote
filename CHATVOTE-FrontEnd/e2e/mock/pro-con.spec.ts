import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Pro/Con Position Evaluation', () => {
  // Pro/con feature is disabled (showProConButton = false in chat-single-message-actions.tsx)
  test.fixme('Evaluate position button appears on assistant messages', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // ChatProConButton renders with text "Evaluate position" for non-assistant party messages.
    // The mock sends party_ids ['renaissance', 'la-france-insoumise'], both non-ASSISTANT_ID,
    // so each party message will show this button.
    const evaluateButton = page.getByRole('button', { name: /evaluate position/i }).first();
    await expect(evaluateButton).toBeVisible({ timeout: 10000 });
  });

  test.fixme('Clicking evaluate position triggers pro/con streaming', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // Click the first "Evaluate position" button
    const evaluateButton = page.getByRole('button', { name: /evaluate position/i }).first();
    await expect(evaluateButton).toBeVisible({ timeout: 10000 });
    await evaluateButton.click();

    // The mock server responds with pro_con_perspective_complete containing
    // "Pro: Good policy. Con: High cost." — the expandable panel shows this content.
    await expect(page.getByText('Pro: Good policy. Con: High cost.')).toBeVisible({ timeout: 15000 });
  });
});
