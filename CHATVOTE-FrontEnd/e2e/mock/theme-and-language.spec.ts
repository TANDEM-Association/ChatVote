import { test, expect } from '@playwright/test';
import { goToChat } from '../support/test-helpers';

test.describe('Theme and Language', () => {
  test('Theme toggle switches between light and dark', async ({ page }) => {
    await goToChat(page);
    const html = page.locator('html');
    const initialTheme = await html.getAttribute('data-theme');
    // Click the toggle button to open the dropdown menu
    await page.getByRole('button', { name: /toggle theme|changer de thème/i }).click();
    // Select the opposite theme from the dropdown menu (FR: Clair/Sombre, EN: Light/Dark)
    const targetTheme = initialTheme === 'light' ? /dark|sombre/i : /light|clair/i;
    await page.getByRole('menuitem', { name: targetTheme }).click();
    // Theme attribute should change
    await expect(html).not.toHaveAttribute('data-theme', initialTheme ?? 'dark', { timeout: 3000 });
  });

  test('Language switcher is visible', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByRole('combobox').first()).toBeVisible();
  });
});
