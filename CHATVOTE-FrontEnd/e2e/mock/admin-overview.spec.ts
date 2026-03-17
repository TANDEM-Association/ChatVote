import { type Page } from "@playwright/test";

import { expect, test } from "../support/base-test";

declare global {
  interface Window {
    __adminMockLog: string[];
  }
}

const SECRET = "test-secret";
const ADMIN_URL = `/admin/dashboard/${SECRET}`;

const WARNINGS_MOCK_HEALTHY = {
  data: [],
  ops: [],
  chat: [],
  counts: { critical: 0, warning: 0, info: 0 },
};

const WARNINGS_MOCK_WITH_ISSUES = {
  data: [
    {
      level: "critical",
      title: "Missing party data",
      message: "3 parties have no manifesto indexed",
      tab: "coverage",
    },
  ],
  ops: [
    {
      level: "warning",
      title: "Scraper behind schedule",
      message: "Last run was 48h ago",
      tab: "pipeline",
    },
  ],
  chat: [
    {
      level: "info",
      title: "Low engagement",
      message: "Average session length dropped 20%",
      tab: "chat-sessions",
    },
  ],
  counts: { critical: 1, warning: 1, info: 1 },
};

/**
 * Mock admin APIs via addInitScript — patches window.fetch before any scripts
 * run. Intercepts both data-sources/status (for PipelineTab) and
 * dashboard/warnings (for OverviewTab).
 */
async function mockAdminApis(
  page: Page,
  warningsData: Record<string, unknown> = WARNINGS_MOCK_HEALTHY,
) {
  const warningsJson = JSON.stringify(warningsData);
  await page.addInitScript((mockWarnings) => {
    const originalFetch = window.fetch;
    window.__adminMockLog = [] as string[];
    window.fetch = async function patchedFetch(
      input: RequestInfo | URL,
      init?: RequestInit,
    ) {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;

      if (url.includes("/api/v1/admin/dashboard/warnings")) {
        return new Response(mockWarnings, {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/admin/data-sources/status")) {
        return new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/admin/maintenance")) {
        return new Response(JSON.stringify({ enabled: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/admin/data-sources/k8s-status")) {
        return new Response(JSON.stringify({ available: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return originalFetch.call(window, input, init);
    };
  }, warningsJson);
}

test.describe("Admin Dashboard Overview Tab (mocked)", () => {
  test.beforeEach(async ({ expectedErrors }) => {
    expectedErrors.push(/webpack-hmr/);
    expectedErrors.push(/auth\/network-request-failed/);
    expectedErrors.push(/FirebaseError/);
    expectedErrors.push(/Failed to load resource/);
    expectedErrors.push(/analytics/i);
    expectedErrors.push(/API key not valid/);
    expectedErrors.push(/permission-denied/);
    expectedErrors.push(/No matching allow statements/);
  });

  test("Overview tab is visible by default when loading admin dashboard", async ({
    page,
  }) => {
    await mockAdminApis(page);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(
      page.getByRole("heading", { name: "Admin Dashboard" }),
    ).toBeVisible({ timeout: 15000 });

    // Overview button should be active/selected by default
    await expect(page.getByRole("button", { name: "Overview" })).toBeVisible({
      timeout: 15000,
    });
  });

  test("Overview tab shows healthy state message when no warnings", async ({
    page,
  }) => {
    await mockAdminApis(page, WARNINGS_MOCK_HEALTHY);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(
      page.getByRole("heading", { name: "Admin Dashboard" }),
    ).toBeVisible({ timeout: 15000 });

    // When all counts are 0, overview shows "No warnings — all systems healthy"
    await expect(
      page.getByText(/No warnings.*all systems healthy/i),
    ).toBeVisible({ timeout: 15000 });
  });

  test("Overview tab shows section headings for warning categories", async ({
    page,
  }) => {
    await mockAdminApis(page, WARNINGS_MOCK_HEALTHY);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(
      page.getByRole("heading", { name: "Admin Dashboard" }),
    ).toBeVisible({ timeout: 15000 });

    // Section headings are always rendered regardless of warning count
    await expect(page.getByText(/Data Completeness/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText(/Operational/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText(/Chat Quality/i)).toBeVisible({
      timeout: 15000,
    });
  });

  test("Overview tab shows warning counts when issues exist", async ({
    page,
  }) => {
    await mockAdminApis(page, WARNINGS_MOCK_WITH_ISSUES);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(
      page.getByRole("heading", { name: "Admin Dashboard" }),
    ).toBeVisible({ timeout: 15000 });

    await expect(page.getByText(/1 critical/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText(/1 warning/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/1 info/i)).toBeVisible({ timeout: 15000 });
  });

  test("Refresh button is visible on Overview tab", async ({ page }) => {
    await mockAdminApis(page);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(
      page.getByRole("heading", { name: "Admin Dashboard" }),
    ).toBeVisible({ timeout: 15000 });

    await expect(page.getByRole("button", { name: /Refresh/i })).toBeVisible({
      timeout: 15000,
    });
  });

  test("tab switching: click Pipeline then back to Overview", async ({
    page,
  }) => {
    await mockAdminApis(page);
    await page.goto(ADMIN_URL, { timeout: 30000 });

    await expect(
      page.getByRole("heading", { name: "Admin Dashboard" }),
    ).toBeVisible({ timeout: 15000 });

    // Switch to Pipeline tab
    await page.getByRole("button", { name: "Pipeline" }).click();
    await expect(page).toHaveURL(/tab=pipeline/, { timeout: 10000 });

    // Switch back to Overview tab
    await page.getByRole("button", { name: "Overview" }).click();
    await expect(page).toHaveURL(/tab=overview/, { timeout: 10000 });

    // Overview content should be visible again
    await expect(page.getByText(/Data Completeness/i)).toBeVisible({
      timeout: 15000,
    });
  });
});
