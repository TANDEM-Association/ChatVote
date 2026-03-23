import { describe, expect, it, vi } from "vitest";

// Mock firebase-admin before importing ai-config (which imports db at module level)
vi.mock("@lib/firebase/firebase-admin", () => ({
  db: {
    collection: vi.fn().mockReturnValue({
      doc: vi.fn().mockReturnValue({
        get: vi.fn().mockResolvedValue({ exists: false, data: () => ({}) }),
      }),
    }),
  },
}));

import { AI_CONFIG_DEFAULTS, type AiConfig } from "@lib/ai/ai-config";

describe("ai-config", () => {
  describe("AI_CONFIG_DEFAULTS", () => {
    it("has correct default values for all fields", () => {
      expect(AI_CONFIG_DEFAULTS).toEqual({
        maxSearchCalls: 3,
        docsPerCandidateShallow: 3,
        docsPerCandidateDeep: 5,
        docsPerSearchShallow: 6,
        docsPerSearchDeep: 8,
        scoreThreshold: 0.25,
        primaryModel: "scaleway-qwen",
        fallbackModel: "gemini-2.5-flash",
        rateLimitMax: 20,
        enableRag: true,
        enablePerplexity: true,
        enableDataGouv: false,
        enableWidgets: false,
        enableVotingRecords: false,
        enableParliamentary: false,
        enableRagflow: false,
      });
    });

    it("enableRagflow defaults to false", () => {
      expect(AI_CONFIG_DEFAULTS.enableRagflow).toBe(false);
    });

    it("enableRag defaults to true", () => {
      expect(AI_CONFIG_DEFAULTS.enableRag).toBe(true);
    });

    it("enablePerplexity defaults to true", () => {
      expect(AI_CONFIG_DEFAULTS.enablePerplexity).toBe(true);
    });

    it("all feature flags are booleans", () => {
      const booleanKeys: (keyof AiConfig)[] = [
        "enableRag",
        "enablePerplexity",
        "enableDataGouv",
        "enableWidgets",
        "enableVotingRecords",
        "enableParliamentary",
        "enableRagflow",
      ];
      for (const key of booleanKeys) {
        expect(typeof AI_CONFIG_DEFAULTS[key]).toBe("boolean");
      }
    });

    it("numeric config values are positive numbers", () => {
      expect(AI_CONFIG_DEFAULTS.maxSearchCalls).toBeGreaterThan(0);
      expect(AI_CONFIG_DEFAULTS.docsPerCandidateShallow).toBeGreaterThan(0);
      expect(AI_CONFIG_DEFAULTS.docsPerCandidateDeep).toBeGreaterThan(0);
      expect(AI_CONFIG_DEFAULTS.docsPerSearchShallow).toBeGreaterThan(0);
      expect(AI_CONFIG_DEFAULTS.docsPerSearchDeep).toBeGreaterThan(0);
      expect(AI_CONFIG_DEFAULTS.rateLimitMax).toBeGreaterThan(0);
    });

    it("scoreThreshold is between 0 and 1", () => {
      expect(AI_CONFIG_DEFAULTS.scoreThreshold).toBeGreaterThanOrEqual(0);
      expect(AI_CONFIG_DEFAULTS.scoreThreshold).toBeLessThanOrEqual(1);
    });

    it("deep docs count is greater than shallow", () => {
      expect(AI_CONFIG_DEFAULTS.docsPerCandidateDeep).toBeGreaterThan(
        AI_CONFIG_DEFAULTS.docsPerCandidateShallow,
      );
      expect(AI_CONFIG_DEFAULTS.docsPerSearchDeep).toBeGreaterThan(
        AI_CONFIG_DEFAULTS.docsPerSearchShallow,
      );
    });
  });
});
