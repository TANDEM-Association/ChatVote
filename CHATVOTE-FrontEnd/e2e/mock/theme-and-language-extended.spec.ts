import { test, expect } from '../support/base-test';
import { goToChat } from '../support/test-helpers';

test.describe('Theme and Language Extended', () => {
  test('13.3 Switching language from French to English translates UI', async ({ page }) => {
    await goToChat(page);

    // The language switcher is a <Select> combobox (LanguageSwitcher component)
    const languageSwitcher = page.getByRole('combobox').first();
    await expect(languageSwitcher).toBeVisible({ timeout: 10000 });

    // Open the combobox and select English
    await languageSwitcher.click();
    await page.getByRole('option', { name: /english|en/i }).click();

    // Wait for the locale change to propagate (router.refresh())
    await expect(
      page.getByRole('button', { name: /^log in$/i })
    ).toBeVisible({ timeout: 15000 });

    // Municipality placeholder should be in English
    await expect(
      page.getByPlaceholder(/municipality/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('13.4 Switching language from English to French translates UI', async ({ page }) => {
    await goToChat(page);

    // Switch to English first
    const languageSwitcher = page.getByRole('combobox').first();
    await expect(languageSwitcher).toBeVisible({ timeout: 10000 });
    await languageSwitcher.click();
    await page.getByRole('option', { name: /english|en/i }).click();
    await expect(
      page.getByRole('button', { name: /^log in$/i })
    ).toBeVisible({ timeout: 15000 });

    // Now switch back to French
    await languageSwitcher.click();
    await page.getByRole('option', { name: /french|français|fr/i }).click();

    // French login button text
    await expect(
      page.getByRole('button', { name: /^se connecter$/i })
    ).toBeVisible({ timeout: 15000 });

    // Municipality placeholder should be in French
    await expect(
      page.getByPlaceholder(/commune/i)
    ).toBeVisible({ timeout: 10000 });
  });

  // FIXME: Theme set via next-themes reverts to default after full-page navigation in dev mode.
  // The SSR-rendered page always has data-theme="dark" and client hydration does not re-apply
  // the stored preference quickly enough. This is a known next-themes SSR limitation.
  test.fixme('13.5 Theme preference persists across navigation', async ({ page }) => {
    await goToChat(page);

    const html = page.locator('html');

    // Read the initial theme before opening the dropdown
    const initialTheme = await html.getAttribute('data-theme') ?? 'dark';
    const targetTheme = initialTheme === 'dark' ? 'light' : 'dark';

    // Open theme dropdown and select the opposite theme
    await page.getByRole('button', { name: /toggle theme|changer de thème/i }).click();
    const menuItem = targetTheme === 'dark'
      ? page.getByRole('menuitem', { name: /^dark$|^sombre$/i })
      : page.getByRole('menuitem', { name: /^light$|^clair$/i });
    await menuItem.click();
    await expect(html).toHaveAttribute('data-theme', targetTheme, { timeout: 5000 });

    // Navigate to /guide and wait for full load
    await page.goto('/guide', { waitUntil: 'load' });
    await expect(page).toHaveURL(/\/guide/);

    // Theme attribute should persist (may need hydration time after SSR)
    await expect(html).toHaveAttribute('data-theme', targetTheme, { timeout: 15000 });

    // Navigate back to /chat
    await page.goto('/chat', { waitUntil: 'load' });
    await page.waitForURL('**/chat**');

    // Theme should persist
    await expect(html).toHaveAttribute('data-theme', targetTheme, { timeout: 15000 });
  });

  test('13.6 Language preference persists across navigation', async ({ page }) => {
    await goToChat(page);

    // Switch to English
    const languageSwitcher = page.getByRole('combobox').first();
    await expect(languageSwitcher).toBeVisible({ timeout: 10000 });
    await languageSwitcher.click();
    await page.getByRole('option', { name: /english|en/i }).click();
    await expect(
      page.getByRole('button', { name: /^log in$/i })
    ).toBeVisible({ timeout: 15000 });

    // Navigate to /guide
    await page.goto('/guide');
    await expect(page).toHaveURL(/\/guide/);
    // Guide page title should be in English
    await expect(
      page.getByRole('heading', { name: /what can i do with chatvote/i })
    ).toBeVisible({ timeout: 10000 });

    // Navigate back to /chat
    await page.goto('/chat');
    await page.waitForURL('**/chat**');

    // UI should still be in English
    await expect(
      page.getByRole('button', { name: /^log in$/i })
    ).toBeVisible({ timeout: 15000 });
  });
});
