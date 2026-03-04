import { test, expect } from '@playwright/test';
import { goToChat, setupChat } from '../support/test-helpers';

test.describe('Responsive Layout Extended', () => {
  test('14.2 Sidebar toggle button is visible on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await goToChat(page);

    // On mobile the header renders a sidebar trigger button (block md:hidden)
    const toggleButton = page.getByRole('button', { name: /toggle sidebar/i }).first();
    await expect(toggleButton).toBeVisible({ timeout: 10000 });
  });

  test('14.3 Opening sidebar on mobile shows navigation links', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await goToChat(page);

    // Sidebar starts collapsed on mobile — open it via the trigger button
    const toggleButton = page.getByRole('button', { name: /toggle sidebar/i }).first();
    await expect(toggleButton).toBeVisible({ timeout: 10000 });
    await toggleButton.click({ force: true });

    // Navigation links should now be visible
    await expect(
      page.getByRole('link', { name: /legal notice|mentions légales/i })
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByRole('link', { name: /^privacy$|^confidentialité$/i })
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByRole('link', { name: /how does chatvote work\?|comment fonctionne chatvote/i })
    ).toBeVisible({ timeout: 10000 });
  });

  test('14.5 Chat layout is usable on tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await goToChat(page);

    // Municipality input should be accessible on tablet
    await expect(
      page.getByPlaceholder(/commune|municipality/i).first()
    ).toBeVisible({ timeout: 15000 });

    // Check there is no horizontal overflow — scrollWidth should not exceed clientWidth
    const hasHorizontalOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(hasHorizontalOverflow).toBe(false);
  });

  test('14.6 Chat input and message area scrollable on small screens', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await setupChat(page);

    // Chat input should be visible and accessible even on a small 375px screen
    const chatInput = page.getByPlaceholder(/crivez un message|write a message/i);
    await expect(chatInput).toBeVisible({ timeout: 15000 });
    await expect(chatInput).toBeEnabled({ timeout: 10000 });

    // Verify the input is within the viewport (not scrolled off-screen)
    const box = await chatInput.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(667 + 1); // within viewport height
  });
});
