"use client";

/**
 * Global error boundary for the root layout.
 *
 * When Next.js serves a stale RSC payload after a deployment (deployment skew),
 * the client gets an unrecoverable error. The default behaviour shows a bare
 * "Application error" page. This component catches it and auto-reloads once
 * so the user silently picks up the fresh deployment.
 */

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Auto-reload once on deployment skew errors.
    // The sessionStorage flag prevents an infinite reload loop.
    const key = `global-error-reload-${error.digest ?? "unknown"}`;
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, "1");
      window.location.reload();
      return;
    }
  }, [error.digest]);

  return (
    <html lang="fr">
      <body
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          fontFamily: "system-ui, sans-serif",
          gap: "1rem",
          padding: "2rem",
          textAlign: "center",
        }}
      >
        <h1>Une erreur est survenue</h1>
        <p style={{ color: "#666", maxWidth: "400px" }}>
          {error.message || "Erreur inattendue. Veuillez réessayer."}
        </p>
        <button
          onClick={() => {
            // Clear the reload guard so a fresh attempt can auto-reload again
            const key = `global-error-reload-${error.digest ?? "unknown"}`;
            sessionStorage.removeItem(key);
            reset();
          }}
          style={{
            padding: "0.75rem 1.5rem",
            borderRadius: "0.5rem",
            border: "none",
            background: "#111",
            color: "#fff",
            cursor: "pointer",
            fontSize: "1rem",
          }}
        >
          Réessayer
        </button>
      </body>
    </html>
  );
}
