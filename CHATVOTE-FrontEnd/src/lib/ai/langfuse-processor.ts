import { LangfuseSpanProcessor } from '@langfuse/otel';

// Singleton span processor — shared between instrumentation.ts and route handlers.
// instrumentation.ts registers this with the NodeTracerProvider.
// Route handlers call forceFlush() via after() to ensure spans are sent.
export const langfuseSpanProcessor = new LangfuseSpanProcessor();
