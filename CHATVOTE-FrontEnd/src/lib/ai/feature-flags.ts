/**
 * Feature flags for AI SDK integration.
 * AI SDK is enabled by default. Set NEXT_PUBLIC_ENABLE_AI_SDK=false to disable.
 *
 * URL override: ?mode=ai activates AI SDK regardless of this flag.
 */
export const AI_SDK_ENABLED = process.env.NEXT_PUBLIC_ENABLE_AI_SDK !== 'false';
