import React from "react";

import { DEFAULT_THEME } from "@lib/theme/getTheme";
import { setTheme as persistTheme } from "@lib/theme/setTheme";
import { type Theme } from "@lib/theme/types";

function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    if (typeof window === "undefined") return "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return theme;
}

export function useTheme(theme?: Theme) {
  const preference = theme ?? DEFAULT_THEME;
  const [resolved, setResolved] = React.useState<"light" | "dark">(() =>
    resolveTheme(preference),
  );

  React.useLayoutEffect(() => {
    const r = resolveTheme(preference);
    setResolved(r);
    document.documentElement.setAttribute("data-theme", r);
  }, [preference]);

  React.useEffect(() => {
    if (preference !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      const r = e.matches ? "dark" : "light";
      setResolved(r);
      document.documentElement.setAttribute("data-theme", r);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [preference]);

  return {
    theme: resolved,
    setTheme: (newTheme: Theme) => {
      const r = resolveTheme(newTheme);
      setResolved(r);
      document.documentElement.setAttribute("data-theme", r);
      persistTheme(newTheme);
    },
  };
}
