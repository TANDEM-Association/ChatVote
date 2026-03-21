import { LangfuseWeb } from "langfuse";

let instance: LangfuseWeb | null = null;

export function getLangfuseWeb(): LangfuseWeb | null {
  if (typeof window === "undefined") return null;

  const publicKey = process.env.NEXT_PUBLIC_LANGFUSE_PUBLIC_KEY;
  const baseUrl = process.env.NEXT_PUBLIC_LANGFUSE_HOST;
  if (!publicKey) return null;

  if (!instance) {
    instance = new LangfuseWeb({ publicKey, baseUrl });
  }
  return instance;
}

export function scoreFeedback(
  traceId: string,
  value: "like" | "dislike",
  comment?: string,
) {
  const lf = getLangfuseWeb();
  if (!lf) return;

  lf.score({
    traceId,
    name: "user-feedback",
    value: value === "like" ? 1 : 0,
    comment,
  });
}
