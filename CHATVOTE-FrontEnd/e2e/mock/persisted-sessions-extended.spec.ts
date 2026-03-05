import { test, expect } from '../support/base-test';
import { setupChat, sendMessage, waitForResponseComplete } from '../support/test-helpers';

// These tests depend on streaming completing — run serially to avoid
// race conditions with the mock server's in-flight response state.
test.describe.serial('Persisted Sessions Extended', () => {
  // FIXME: Title renders in collapsed sidebar — not visible on default viewport.
  // Needs sidebar expansion or checking document.title instead.
  test.fixme('11.2 Page title updates after response completes', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'What is your education policy?');
    await waitForResponseComplete(page);

    // The mock server emits quick_replies_and_title_ready with title: 'Test Chat Title'.
    // The store sets currentChatTitle which is reflected in the sidebar history link.
    // Wait for the title to appear somewhere visible in the page — sidebar history or
    // any element that renders the session title.
    await expect(
      page.getByText('Test Chat Title')
    ).toBeVisible({ timeout: 15000 });
  });

  // FIXME: Mock server doesn't persist sessions to Firestore, so sidebar
  // history has no entries. Needs Firestore write like persisted-sessions.spec.ts.
  test.fixme('11.4 Sidebar shows chat history entries after a completed chat', async ({ page }) => {
    await setupChat(page);
    await sendMessage(page, 'What is your education policy?');
    await waitForResponseComplete(page);

    // Open the sidebar if it is collapsed (defaultOpen=false)
    const sidebarLocator = page.locator('[data-variant="sidebar"]');
    const sidebarState = await sidebarLocator.getAttribute('data-state');
    if (sidebarState === 'collapsed') {
      await page.keyboard.press('Control+b');
      await expect(sidebarLocator).toHaveAttribute('data-state', 'expanded', { timeout: 5000 });
    }

    // The SidebarHistory component renders links for each ChatSession.
    // After a completed session, Firebase writes the title; the anonymous user's
    // history listener picks it up and renders at least one history link.
    // Accept any link inside the sidebar that points to /chat/<id>.
    const historyLink = page.locator('[data-variant="sidebar"] a[href*="/chat/"]').first();
    await expect(historyLink).toBeVisible({ timeout: 20000 });
  });
});
