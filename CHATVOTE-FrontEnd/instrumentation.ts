export async function register() {
  if (process.env.LANGFUSE_SECRET_KEY) {
    await import('@lib/ai/langfuse-processor');
  }
}
