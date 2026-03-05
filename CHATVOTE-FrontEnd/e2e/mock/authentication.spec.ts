import { test, expect } from '../support/base-test';
import { goToChat } from '../support/test-helpers';

test.describe('Authentication', () => {
  test('Login button is visible in sidebar', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByRole('button', { name: /log in|se connecter/i })).toBeVisible();
  });

  test('Login button opens login modal', async ({ page }) => {
    await goToChat(page);
    // Click the icon-bar login button (first match avoids sidebar panel which may be clipped)
    await page.locator('[data-sidebar="login"]').first().click();
    // Wait for login form's email input to confirm modal opened (portal + animation delay)
    await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 10000 });
  });
});
