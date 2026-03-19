import { LangfuseSpanProcessor } from '@langfuse/otel';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';

// Singleton span processor
export const langfuseSpanProcessor = new LangfuseSpanProcessor();

// Register the OTEL tracer provider at module level
const tracerProvider = new NodeTracerProvider({
  spanProcessors: [langfuseSpanProcessor],
});
tracerProvider.register();
