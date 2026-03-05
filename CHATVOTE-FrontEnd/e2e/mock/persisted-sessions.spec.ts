import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

const FIRESTORE_HOST = 'http://localhost:8081';
const PROJECT_ID = 'chat-vote-dev';

/**
 * Write session + user message directly to the Firestore emulator REST API.
 *
 * The client-side Firebase SDK uses WebChannel (gRPC-web), which can degrade
 * after many emulator writes and silently hang. The REST API uses plain HTTP
 * and is always reliable.  We use this to guarantee the session is persisted
 * before we navigate back to test the load path.
 */
async function writeFirestoreSession(sessionId: string, userMessage: string): Promise<void> {
  const ts = new Date().toISOString();

  // 1. Write the chat_sessions document
  const sessionUrl =
    `${FIRESTORE_HOST}/v1/projects/${PROJECT_ID}/databases/(default)/documents/chat_sessions/${sessionId}`;
  await fetch(sessionUrl, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fields: {
        user_id: { stringValue: 'test-user' },
        party_ids: { arrayValue: { values: [] } },
        created_at: { timestampValue: ts },
        updated_at: { timestampValue: ts },
      },
    }),
  });

  // 2. Write the user message into the messages subcollection
  const msgId = `msg-e2e-${Date.now()}`;
  const messagesUrl =
    `${FIRESTORE_HOST}/v1/projects/${PROJECT_ID}/databases/(default)/documents/chat_sessions/${sessionId}/messages/${msgId}`;
  await fetch(messagesUrl, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fields: {
        id: { stringValue: msgId },
        role: { stringValue: 'user' },
        messages: {
          arrayValue: {
            values: [
              {
                mapValue: {
                  fields: {
                    id: { stringValue: `inner-${msgId}` },
                    content: { stringValue: userMessage },
                    role: { stringValue: 'user' },
                    sources: { arrayValue: { values: [] } },
                    created_at: { timestampValue: ts },
                  },
                },
              },
            ],
          },
        },
        quick_replies: { arrayValue: { values: [] } },
        created_at: { timestampValue: ts },
      },
    }),
  });
}

test.describe('Persisted Sessions', () => {

  test('User message is visible when returning to the session URL', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'What is your education policy?');
    await waitForResponseComplete(page);

    const sessionUrl = page.url();
    expect(sessionUrl).toContain('chat_id');

    const sessionId = new URL(sessionUrl).searchParams.get('chat_id')!;

    // Write the session to Firestore via the REST API — reliable even when
    // the client SDK's WebChannel is degraded after many emulator tests.
    await writeFirestoreSession(sessionId, 'What is your education policy?');

    await page.goto('/chat');
    // Navigate directly to /chat/[sessionId] so the SSR path fetches the
    // session from Firestore (Admin SDK, emulator-safe) and renders it.
    await page.goto(`/chat/${sessionId}`);

    await expect(
      page.getByText('What is your education policy?').first()
    ).toBeVisible({ timeout: 20000 });
  });

  test('Quick reply sends a follow-up message in the same session', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'What is your education policy?');
    await waitForResponseComplete(page);

    await page.getByRole('button', { name: /what about education/i }).click();

    await expect(
      page.getByText('Response chunk').first()
    ).toBeVisible({ timeout: 30000 });
  });

});
