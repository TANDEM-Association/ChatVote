import { expect, test } from "../support/base-test";

/**
 * Navigate to /chat with a municipality pre-set via URL param and wait for
 * the AI SDK chat input to become interactive.
 *
 * Unlike the Socket.IO-era setupChat() helper, the AI SDK view does NOT render
 * [data-testid="chat-form-ready"] or [data-testid="session-initialized"].
 * We wait for the input placeholder that the AI SDK chat view renders.
 */
async function setupAiSdkChat(
  page: import("@playwright/test").Page,
  municipalityCode = "75056",
) {
  await page.goto(`/chat?municipality_code=${municipalityCode}`, {
    waitUntil: "domcontentloaded",
  });
  // Wait for the AI SDK chat input to appear and be enabled
  await expect(getAiSdkChatInput(page)).toBeEnabled({ timeout: 30000 });
}

/**
 * Returns the AI SDK chat input.
 * The AiSdkChatView renders an <input> with placeholder "Posez une question..."
 * when a municipality is set (and "Sélectionnez une commune d'abord..." when not).
 */
function getAiSdkChatInput(page: import("@playwright/test").Page) {
  return page.getByPlaceholder(/Posez une question/i);
}

/**
 * Type a message into the AI SDK chat input and submit with Enter.
 */
async function sendAiSdkMessage(
  page: import("@playwright/test").Page,
  message: string,
) {
  const input = getAiSdkChatInput(page);
  await input.fill(message);
  await input.press("Enter");
}

test.describe("AI SDK Chat", () => {
  test("chat input is enabled after municipality selection", async ({
    page,
  }) => {
    await setupAiSdkChat(page);
    await expect(getAiSdkChatInput(page)).toBeEnabled();
  });

  test("quick suggestions are visible when municipality is set", async ({
    page,
  }) => {
    await setupAiSdkChat(page);
    // The chat view renders suggestion buttons when municipalityCode is set and no messages exist
    await expect(page.locator('[data-testid="quick-suggestions"]')).toBeVisible(
      { timeout: 10000 },
    );
  });

  test("sending a message shows a streaming response", async ({ page }) => {
    await setupAiSdkChat(page);
    await sendAiSdkMessage(
      page,
      "Quelles sont les propositions sur la sécurité ?",
    );

    // The AI SDK renders each message as an <article> element.
    // The assistant reply is the second article (first is the user message).
    await expect(page.locator("article").nth(1)).toBeVisible({
      timeout: 60000,
    });
  });

  test("user message appears in the chat after sending", async ({ page }) => {
    await setupAiSdkChat(page);
    const userMessage = "Parle-moi du logement";
    await sendAiSdkMessage(page, userMessage);

    // The user message is rendered in the first article
    await expect(page.locator("article").first()).toContainText(userMessage, {
      timeout: 15000,
    });
  });

  test("streaming indicator disappears after response completes", async ({
    page,
  }) => {
    await setupAiSdkChat(page);
    await sendAiSdkMessage(
      page,
      "Quelles sont les propositions sur l'écologie ?",
    );

    // Streaming indicator contains a stop button; wait for it to disappear
    // which means the stream completed
    await expect(page.locator("article").nth(1)).toBeVisible({
      timeout: 60000,
    });
    // After streaming, the stop button (square icon inside a round button) is gone
    await expect(
      page.locator('button[type="button"] span.rounded-sm'),
    ).not.toBeVisible({ timeout: 60000 });
  });

  test("follow-up suggestions appear after response", async ({ page }) => {
    await setupAiSdkChat(page);
    await sendAiSdkMessage(page, "Parle-moi du logement");

    // suggestFollowUps tool renders buttons with Sparkles icon and suggestion text
    // We wait for any button that appears inside an article (assistant message area)
    // after the response is complete
    await expect(page.locator("article").nth(1)).toBeVisible({
      timeout: 60000,
    });
    // Follow-up buttons are rendered inside the assistant article as plain buttons
    // The suggestFollowUps tool output renders buttons with rounded-full styling
    const followUpButtons = page
      .locator("article")
      .nth(1)
      .locator("button.rounded-full");
    await expect(followUpButtons.first()).toBeVisible({ timeout: 60000 });
  });

  test("RAG source results appear after search-based response", async ({
    page,
  }) => {
    await setupAiSdkChat(page);
    await sendAiSdkMessage(page, "Comparez les candidats sur l'écologie");

    // Wait for assistant message
    await expect(page.locator("article").nth(1)).toBeVisible({
      timeout: 60000,
    });

    // The searchDocumentsWithRerank tool renders a SourceResultCard with text
    // like "sources trouvées" or "N sources"
    await expect(
      page
        .locator("article")
        .nth(1)
        .getByText(/source/i)
        .first(),
    ).toBeVisible({ timeout: 60000 });
  });
});

test.describe("AI SDK Chat - Feature Flags", () => {
  test("admin config API returns feature flags", async ({ page }) => {
    const response = await page.request.get("/api/admin/ai-config");
    expect(response.ok()).toBe(true);

    const config = await response.json();

    expect(config).toHaveProperty("enableRag");
    expect(config).toHaveProperty("enablePerplexity");
    expect(config).toHaveProperty("enableRagflow");
    expect(config).toHaveProperty("enableDataGouv");
    expect(config).toHaveProperty("enableWidgets");
    expect(config).toHaveProperty("enableVotingRecords");
    expect(config).toHaveProperty("enableParliamentary");
  });

  test("admin config API can toggle enableRagflow", async ({ page }) => {
    // Enable ragflow
    const enableRes = await page.request.put("/api/admin/ai-config", {
      data: { enableRagflow: true },
    });
    expect(enableRes.ok()).toBe(true);
    const enabled = await enableRes.json();
    expect(enabled.enableRagflow).toBe(true);

    // Disable ragflow
    const disableRes = await page.request.put("/api/admin/ai-config", {
      data: { enableRagflow: false },
    });
    expect(disableRes.ok()).toBe(true);
    const disabled = await disableRes.json();
    expect(disabled.enableRagflow).toBe(false);
  });

  test("admin config API returns boolean values for all feature flags", async ({
    page,
  }) => {
    const response = await page.request.get("/api/admin/ai-config");
    const config = await response.json();

    const booleanFlags = [
      "enableRag",
      "enablePerplexity",
      "enableRagflow",
      "enableDataGouv",
      "enableWidgets",
      "enableVotingRecords",
      "enableParliamentary",
    ];

    for (const flag of booleanFlags) {
      expect(typeof config[flag], `${flag} should be boolean`).toBe("boolean");
    }
  });
});
