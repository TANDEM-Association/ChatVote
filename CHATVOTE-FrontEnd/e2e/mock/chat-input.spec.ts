import { expect, test } from "../support/base-test";
import { getChatInput, goToChat, setupChat } from "../support/test-helpers";

test.describe("Chat Input and Message Submission", () => {
  test("Chat input is disabled before municipality selection", async ({
    page,
  }) => {
    await goToChat(page);
    // The chat input is not rendered at all until a municipality is selected
    // (ChatInputGate returns null when no municipality_code is present).
    await expect(getChatInput(page)).not.toBeVisible();
  });

  test("Chat input becomes enabled after municipality selection", async ({
    page,
  }) => {
    await setupChat(page);
    await expect(getChatInput(page)).toBeEnabled();
  });

  test("Pressing Enter submits the message", async ({ page }) => {
    await setupChat(page);
    const chatInput = getChatInput(page);
    await chatInput.fill("Test question");
    await chatInput.press("Enter");
    // The user message should appear in the chat
    await expect(page.getByText("Test question")).toBeVisible({
      timeout: 10000,
    });
  });

  test("Empty input does not submit", async ({ page }) => {
    await setupChat(page);
    const chatInput = getChatInput(page);
    await chatInput.press("Enter");
    // URL should NOT have chat_id
    await expect(page).not.toHaveURL(/chat_id=/);
  });
});
