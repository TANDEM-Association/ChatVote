/**
 * Feature flags for AI SDK integration.
 * Set NEXT_PUBLIC_ENABLE_AI_SDK=true in .env.local to enable.
 *
 * URL override: ?mode=ai activates AI SDK without the env var or toggle.
 */
export const AI_SDK_ENABLED = process.env.NEXT_PUBLIC_ENABLE_AI_SDK === 'true';
