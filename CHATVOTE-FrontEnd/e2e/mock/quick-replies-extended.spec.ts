import { test, expect } from '@playwright/test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

test.describe('Quick Reply Suggestions Extended', () => {
  test('Quick reply buttons are scrollable horizontally on narrow viewport', async ({ page }) => {
    // Set a narrow mobile viewport before navigating
    await page.setViewportSize({ width: 375, height: 812 });

    await setupChat(page);
    await sendMessage(page, 'Education policy?');
    await waitForResponseComplete(page);

    // The quick replies container in chat-input.tsx has class "overflow-x-auto"
    // and renders buttons as children. On a narrow viewport the container should
    // allow horizontal scrolling without causing vertical overflow.
    const quickRepliesContainer = page.locator('div.overflow-x-auto').filter({
      has: page.getByRole('button', { name: /what about education/i }),
    });

    await expect(quickRepliesContainer).toBeVisible({ timeout: 10000 });

    // Verify the container allows horizontal scroll: scrollWidth >= clientWidth
    const isHorizontallyScrollable = await quickRepliesContainer.evaluate((el) => {
      return el.scrollWidth >= el.clientWidth;
    });
    expect(isHorizontallyScrollable).toBe(true);

    // Verify no vertical overflow is caused by the quick replies row
    const hasNoVerticalOverflow = await quickRepliesContainer.evaluate((el) => {
      return el.scrollHeight <= el.clientHeight + 2; // 2px tolerance for rounding
    });
    expect(hasNoVerticalOverflow).toBe(true);
  });
});
