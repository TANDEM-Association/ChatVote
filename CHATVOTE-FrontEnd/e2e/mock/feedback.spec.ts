import { test, expect } from '@playwright/test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Feedback Buttons', () => {
  test('Like and dislike buttons appear on completed assistant message', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // ThumbsUp and ThumbsDown are icon-only ghost buttons rendered inside message actions.
    // There will be one per party response. We only need the first to be visible.
    const thumbsUpButton = page.locator('button .lucide-thumbs-up').first();
    const thumbsDownButton = page.locator('button .lucide-thumbs-down').first();

    await expect(thumbsUpButton).toBeVisible({ timeout: 10000 });
    await expect(thumbsDownButton).toBeVisible({ timeout: 10000 });
  });

  test('Clicking like button marks message as liked', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // Click the first thumbs-up button
    const thumbsUpButton = page.locator('button .lucide-thumbs-up').first();
    await expect(thumbsUpButton).toBeVisible({ timeout: 10000 });
    await thumbsUpButton.click();

    // After clicking like, the ThumbsUp icon gets fill-foreground/30 class (active/filled state)
    const likedIcon = page.locator('button .lucide-thumbs-up.fill-foreground\\/30').first();
    await expect(likedIcon).toBeVisible({ timeout: 5000 });
  });

  test('Clicking dislike button opens feedback input', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // Click the first thumbs-down button to open the feedback modal
    const thumbsDownButton = page.locator('button .lucide-thumbs-down').first();
    await expect(thumbsDownButton).toBeVisible({ timeout: 10000 });
    await thumbsDownButton.click();

    // The Modal contains a Textarea with the feedback placeholder
    const feedbackTextarea = page.getByPlaceholder(/feedback/i);
    await expect(feedbackTextarea).toBeVisible({ timeout: 5000 });
  });
});
