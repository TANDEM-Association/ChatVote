import { type Theme } from "./types";

export function getTheme(headers: Headers): Theme {
  // Try x-theme header first, then read theme cookie
  const headerTheme = headers.get("x-theme") as Theme | null;
  if (headerTheme) return headerTheme;

  const cookies = headers.get("cookie") ?? "";
  const match = cookies.match(/(?:^|;\s*)theme=(light|dark|system)/);
  if (match) return match[1] as Theme;

  return DEFAULT_THEME;
}

export const DEFAULT_THEME: Theme = "dark";
