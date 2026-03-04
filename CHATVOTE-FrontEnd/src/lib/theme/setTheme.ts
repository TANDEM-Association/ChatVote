"use client";

import { type Theme } from "./types";

export function setTheme(theme: Theme): void {
  const isProduction = process.env.NODE_ENV === "production";
  const secure = isProduction ? ";secure" : "";

  document.cookie = `theme=${theme};path=/;samesite=lax${secure};max-age=31536000`;
}
