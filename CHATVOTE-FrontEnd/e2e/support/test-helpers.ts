import { type Page, expect } from '@playwright/test';

/**
 * Select a municipality (required before chat input is enabled).
 * Types "Paris" into the municipality search and selects the first result.
 */
export async function selectMunicipality(page: Page, name = 'Paris') {
  // Matches both FR ("Nom de commune ou code postal...") and EN ("Municipality name or postal code...")
  // There are 2 municipality inputs (desktop + mobile) — use .first() for the visible one.
  const municipalityInput = page.getByPlaceholder(/commune|municipality/i).first();
  await expect(municipalityInput).toBeVisible({ timeout: 15000 });
  await municipalityInput.pressSequentially(name, { delay: 50 });

  // Wait for autocomplete dropdown and click the result matching the typed name
  // Use text filter to avoid matching sidebar list items
  const resultButton = page.locator('li').filter({ hasText: name }).first().locator('button');
  await expect(resultButton).toBeVisible({ timeout: 10000 });
  await resultButton.click();

  // Wait for chat input to become enabled (auth + socket ready)
  const chatInput = getChatInput(page);
  await expect(chatInput).toBeEnabled({ timeout: 10000 });
}

/**
 * Navigate to /chat and wait for the page to be ready (hydrated).
 */
export async function goToChat(page: Page) {
  await page.goto('/chat');
  // Wait for the chatvote logo to be visible (page rendered)
  await expect(page.getByRole('img', { name: 'chatvote' }).first()).toBeVisible({ timeout: 15000 });
}

/**
 * Full setup: navigate to /chat with municipality_code pre-set in the URL.
 *
 * Going through the UI municipality selection triggers an RSC re-render via
 * router.replace that can exceed test timeouts in dev mode. Navigating directly
 * with the query param lets the server render the page with municipalityCode
 * from the start, so the chat input is enabled without waiting for a re-render.
 */
export async function setupChat(page: Page, municipalityCode = '75056') {
  await page.goto(`/chat?municipality_code=${municipalityCode}`, { waitUntil: 'domcontentloaded' });
  // ChatDynamicChatInput is outside the Suspense boundary, so it renders immediately
  // with the server-side municipalityCode prop — no need to wait for the logo first.
  await expect(getChatInput(page)).toBeEnabled({ timeout: 30000 });
  // Wait for Socket.IO to be fully connected before allowing message sends.
  // addUserMessage returns early (silently) if socket.io?.connected is false.
  await page.waitForSelector('[data-testid="socket-connected"]', { timeout: 15000 });
  // Wait for anonymous Firebase auth to complete.
  // The chat input form gets data-testid="chat-form-ready" once user.uid is available.
  // Without this, handleSubmit silently returns early because user?.uid is null.
  await page.waitForSelector('[data-testid="chat-form-ready"]', { timeout: 15000 });
  // Wait for the full session initialization round-trip to complete.
  // The socket connects early (setSocketConnected → initializeChatSession) but the
  // store's municipalityCode isn't set until hydrateChatSession runs (after Suspense
  // resolves and ChatMessagesView mounts). The session-initialized indicator appears
  // only when both chatId AND municipalityCode are set, ensuring the session was
  // initialized with the correct scope (local + municipality).
  await page.waitForSelector('[data-testid="session-initialized"]', { timeout: 30000 });
}

/**
 * Get the chat input element (matches both FR and EN placeholders).
 */
export function getChatInput(page: Page) {
  return page.getByPlaceholder(/crivez un message|write a message/i);
}

/**
 * Type a message and submit it.
 */
export async function sendMessage(page: Page, message: string) {
  const chatInput = getChatInput(page);
  await chatInput.fill(message);
  await chatInput.press('Enter');
}

/**
 * Wait for the streaming response to complete (quick replies appear).
 */
export async function waitForResponseComplete(page: Page, timeout = 30000) {
  // Quick replies appear after response is complete
  await expect(
    page.getByRole('button', { name: /what about education/i })
  ).toBeVisible({ timeout });
}
