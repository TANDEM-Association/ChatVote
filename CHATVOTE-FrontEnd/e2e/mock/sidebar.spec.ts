import { test, expect } from '../support/base-test';
import { goToChat } from '../support/test-helpers';

test.describe('Sidebar Navigation', () => {
  test('Sidebar has navigation links', async ({ page }) => {
    await goToChat(page);
    // Sidebar links should be visible (sidebar is open by default on desktop)
    await expect(page.getByRole('link', { name: /how does chatvote work\?|comment fonctionne chatvote/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /legal notice|mentions légales/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /^privacy$|^confidentialité$/i })).toBeVisible();
  });

  test('Sidebar has support buttons', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByRole('button', { name: /^log in$|^se connecter$/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^donate$|^faire un don$/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^feedback$/i })).toBeVisible();
  });

  test('Sidebar toggle works', async ({ page }) => {
    await goToChat(page);
    const sidebarLocator = page.locator('[data-variant="sidebar"]');
    // Sidebar starts collapsed (defaultOpen=false)
    await expect(sidebarLocator).toHaveAttribute('data-state', 'collapsed', { timeout: 5000 });
    // Toggle open via keyboard shortcut (Ctrl+B)
    await page.keyboard.press('Control+b');
    await expect(sidebarLocator).toHaveAttribute('data-state', 'expanded', { timeout: 3000 });
    // Toggle closed
    await page.keyboard.press('Control+b');
    await expect(sidebarLocator).toHaveAttribute('data-state', 'collapsed', { timeout: 3000 });
  });
});
