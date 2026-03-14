import { test, expect } from '../support/base-test';
import { goToChat } from '../support/test-helpers';

test.describe('Guide and Help', () => {
  test('Learn more link is visible', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByRole('button', { name: /learn more here|en savoir plus/i }).first()).toBeVisible();
  });

  test('Guide page is accessible from sidebar', async ({ page }) => {
    await goToChat(page);
    const guideLink = page.getByRole('link', { name: /how does chatvote work\?|comment fonctionne chatvote/i });
    await expect(guideLink).toBeVisible();
    await expect(guideLink).toHaveAttribute('href', '/guide');
  });
});
