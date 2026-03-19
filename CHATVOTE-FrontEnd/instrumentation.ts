export async function register() {
  // Only initialise when Langfuse credentials are present (server-side only)
  if (process.env.LANGFUSE_SECRET_KEY) {
    const { LangfuseSpanProcessor } = await import('@langfuse/otel');
    const { NodeTracerProvider } = await import('@opentelemetry/sdk-trace-node');

    const tracerProvider = new NodeTracerProvider({
      spanProcessors: [new LangfuseSpanProcessor()],
    });
    tracerProvider.register();
  }
}
