const DEFAULT_APP_URL = "https://app.chatvote.org";

/**
 * Check if code is running on the client side
 */
function isClient(): boolean {
  return typeof window !== "undefined";
}

/**
 * Get the app URL synchronously.
 * - Client-side: uses window.location.origin
 * - Server-side: uses NEXT_PUBLIC_APP_URL env var or default
 *
 * Use this for client components or when async is not possible.
 */
export function getAppUrlSync(): string {
  if (isClient()) {
    return window.location.origin;
  }

  return process.env.NEXT_PUBLIC_APP_URL ?? DEFAULT_APP_URL;
}

/**
 * Get the app URL asynchronously.
 * - Server-side: tries to get the host from request headers first
 * - Falls back to NEXT_PUBLIC_APP_URL env var or default
 *
 * Use this in Server Components, API routes, or server actions.
 */
export async function getAppUrl(): Promise<string> {
  if (isClient()) {
    return window.location.origin;
  }

  try {
    const { headers } = await import("next/headers");
    const headersList = await headers();
    const host = headersList.get("host");
    const protocol = headersList.get("x-forwarded-proto") ?? "https";

    if (host !== null) {
      return `${protocol}://${host}`;
    }
  } catch {
    // headers() not available (e.g., during build or static generation)
  }

  return process.env.NEXT_PUBLIC_APP_URL ?? DEFAULT_APP_URL;
}
