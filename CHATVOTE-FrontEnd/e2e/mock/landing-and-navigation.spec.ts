import { test, expect } from '@playwright/test';
import { goToChat, setupChat, sendMessage, waitForResponseComplete, selectMunicipality, getChatInput } from '../support/test-helpers';

test.describe('Landing Page and Navigation', () => {
  test('Root URL redirects to /chat', async ({ page }) => {
    await page.goto('/');
    await page.waitForURL('**/chat**');
    await expect(page).toHaveURL(/\/chat/);
  });

  test('/chat page displays logo and municipality input', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByRole('img', { name: 'chatvote' }).first()).toBeVisible();
    await expect(page.getByPlaceholder(/commune|municipality/i).first()).toBeVisible();
    // Chat input should be disabled before municipality selection
    await expect(getChatInput(page)).toBeDisabled();
  });

  test('Header elements are present', async ({ page }) => {
    await goToChat(page);
    await expect(page.getByRole('button', { name: /toggle theme|changer de thème/i })).toBeVisible();
    await expect(page.getByRole('combobox').first()).toBeVisible();
  });

  test('Guide page loads', async ({ page }) => {
    await page.goto('/guide');
    await expect(page).toHaveURL(/\/guide/);
  });

  test('Legal notice page loads', async ({ page }) => {
    await page.goto('/legal-notice');
    await expect(page).toHaveURL(/\/legal-notice/);
  });

  test('Privacy policy page loads', async ({ page }) => {
    await page.goto('/privacy-policy');
    await expect(page).toHaveURL(/\/privacy-policy/);
  });

  test('Donate page loads', async ({ page }) => {
    await page.goto('/donate');
    await expect(page).toHaveURL(/\/donate/);
  });
});
