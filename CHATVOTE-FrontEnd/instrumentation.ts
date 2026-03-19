export async function register() {
  if (process.env.LANGFUSE_SECRET_KEY) {
    // Dynamic import to avoid loading langfuse when not configured
    const { langfuseSpanProcessor } = await import('@lib/ai/langfuse-processor');
    const { NodeTracerProvider } = await import('@opentelemetry/sdk-trace-node');

    const tracerProvider = new NodeTracerProvider({
      spanProcessors: [langfuseSpanProcessor],
    });
    tracerProvider.register();
  }
}
