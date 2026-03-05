import { test, expect } from '../support/base-test';
import { goToChat, setupChat, sendMessage } from '../support/test-helpers';

/**
 * Helper: navigate to /chat, open the login modal, and wait for the email input.
 */
async function openLoginModal(page: Parameters<typeof goToChat>[0]) {
  await goToChat(page);
  // Wait for the sidebar login button to be visible and actionable
  const loginBtn = page.locator('[data-sidebar="login"]').first();
  await expect(loginBtn).toBeVisible({ timeout: 15000 });
  // Sidebar buttons are covered by the main content area — use dispatchEvent to bypass.
  await loginBtn.dispatchEvent('click');
  // Wait for the login form to appear inside the modal
  await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 10000 });
}

/** Locate the login form submit button scoped to the modal overlay. */
function getSubmitButton(page: Parameters<typeof goToChat>[0]) {
  return page.locator('.fixed.inset-0.z-50 form button[type="submit"]');
}

test.describe('Authentication Extended', () => {
  test('12.3 Login form validates required fields', async ({ page }) => {
    await openLoginModal(page);

    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
    await expect(passwordInput).toBeVisible({ timeout: 5000 });

    // Click submit without filling any field — HTML5 validation blocks submission.
    await getSubmitButton(page).click();

    // The form must still be open (submission was blocked by HTML5 validation).
    await expect(emailInput).toBeVisible({ timeout: 5000 });

    // Confirm the email field is marked invalid by the browser.
    const isValid = await emailInput.evaluate((el) => (el as HTMLInputElement).validity.valid);
    expect(isValid).toBe(false);
  });

  test('12.4 Login form validates email format', async ({ page }) => {
    await openLoginModal(page);

    await page.locator('input[type="email"]').fill('notanemail');
    await page.locator('input[type="password"]').fill('somepassword');

    await getSubmitButton(page).click();

    // HTML5 type="email" rejects the value — form stays open and field is invalid.
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
    const isValid = await emailInput.evaluate((el) => (el as HTMLInputElement).validity.valid);
    expect(isValid).toBe(false);
  });

  test('12.5 Login with invalid credentials shows error toast', async ({ page }) => {
    await openLoginModal(page);

    await page.locator('input[type="email"]').fill('nonexistent@example.com');
    await page.locator('input[type="password"]').fill('wrongpassword123');

    await getSubmitButton(page).click();

    // Firebase Auth emulator rejects unknown credentials → app shows a sonner error toast.
    // Possible messages:
    //   EN: "The entered credentials are invalid." / FR: "Les données saisies sont invalides."
    //   EN: "An error occurred. Please reload..." / FR: "Une erreur s'est produite..."
    // Match any sonner error toast that appears.
    await expect(
      page.locator('[data-sonner-toast][data-type="error"]')
    ).toBeVisible({ timeout: 15000 });
  });

  test('12.6 Switching from login to registration mode', async ({ page }) => {
    await openLoginModal(page);

    // Verify we start in login mode (EN "Log in" / FR "Se connecter").
    await expect(
      page.getByRole('heading', { name: /log in|se connecter/i })
    ).toBeVisible({ timeout: 5000 });

    // Click the toggle link to switch to register mode.
    // EN "Sign up" / FR "S'inscrire" — it's in the bottom text area.
    const toggleLink = page.locator('.fixed.inset-0.z-50 form button[type="button"]').filter({
      hasText: /sign up|s'inscrire/i,
    });
    await toggleLink.click();

    // The heading should change to register mode.
    await expect(
      page.getByRole('heading', { name: /sign up|s'inscrire/i })
    ).toBeVisible({ timeout: 5000 });

    // The submit button label should also change.
    await expect(getSubmitButton(page)).toHaveText(/sign up|s'inscrire/i, { timeout: 5000 });
  });

  test('12.7 Forgot password link shows reset form', async ({ page }) => {
    await openLoginModal(page);

    // Click the "Forgot password?" / "Mot de passe oublié ?" link button.
    await page.getByRole('button', { name: /forgot password|mot de passe oublié/i }).click();

    // The PasswordResetForm is rendered in place — heading changes.
    await expect(
      page.getByRole('heading', { name: /forgot password|mot de passe oublié/i })
    ).toBeVisible({ timeout: 5000 });

    // The form should contain an email input and a submit button.
    await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 5000 });
    await expect(
      page.getByRole('button', { name: /send link|envoyer/i })
    ).toBeVisible({ timeout: 5000 });
  });

  test('12.8 Successful login updates UI', async ({ page }) => {
    const EMULATOR_URL = 'http://localhost:9099';
    const TEST_EMAIL = `e2e-test-${Date.now()}@example.com`;
    const TEST_PASSWORD = 'TestPass123';

    // Create a test user via Firebase Auth emulator REST API.
    const signUpRes = await page.request.post(
      `${EMULATOR_URL}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake-api-key`,
      {
        data: { email: TEST_EMAIL, password: TEST_PASSWORD, returnSecureToken: true },
      },
    );

    if (!signUpRes.ok()) {
      test.skip();
      return;
    }

    await openLoginModal(page);

    await page.locator('input[type="email"]').fill(TEST_EMAIL);
    await page.locator('input[type="password"]').fill(TEST_PASSWORD);

    await getSubmitButton(page).click();

    // On success, one of two things happens:
    //   1. New users: newsletter opt-in form appears (newsletter_allowed undefined)
    //   2. Returning users: modal closes + success toast
    // In both cases the login email/password form disappears.
    await expect(page.locator('input[type="password"]')).not.toBeVisible({ timeout: 15000 });
  });

  test('12.9 Anonymous users can chat without logging in', async ({ page }) => {
    // setupChat navigates with municipality_code pre-set, completes anonymous auth,
    // and waits for socket connection + session initialization.
    await setupChat(page);

    // Chat input must be enabled for anonymous users — no auth prompt required.
    const chatInput = page.getByPlaceholder(/crivez un message|write a message/i);
    await expect(chatInput).toBeEnabled({ timeout: 10000 });

    // Sending a message should trigger a streamed response (no auth gate).
    await sendMessage(page, 'What is your education policy?');
    await expect(page.getByText('Response chunk')).toBeVisible({ timeout: 30000 });
  });
});
