import { type Theme } from "./types";

export function getTheme(headers: Headers): Theme {
  const theme = (headers.get("x-theme") as Theme) ?? "dark";
  return theme;
}

export const DEFAULT_THEME: Theme = "dark";
