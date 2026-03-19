import { LangfuseSpanProcessor } from '@langfuse/otel';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';

// Only initialise when Langfuse credentials are present
if (process.env.LANGFUSE_SECRET_KEY) {
  const tracerProvider = new NodeTracerProvider({
    spanProcessors: [new LangfuseSpanProcessor()],
  });
  tracerProvider.register();
}
