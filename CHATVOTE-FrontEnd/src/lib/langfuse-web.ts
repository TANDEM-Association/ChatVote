/**
 * Send a user-feedback score to Langfuse via the server-side API route.
 *
 * This avoids mixed-content blocks (HTTPS frontend → HTTP Langfuse) by
 * routing through /api/feedback which uses the server-side Langfuse SDK.
 */
export function scoreFeedback(
  traceId: string,
  value: "like" | "dislike",
  comment?: string,
) {
  fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ traceId, value, comment }),
  }).catch(() => {
    // Non-critical — don't break UX if feedback scoring fails
  });
}
