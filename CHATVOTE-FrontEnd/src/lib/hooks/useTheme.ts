import React from "react";

import { DEFAULT_THEME } from "@lib/theme/getTheme";
import { setTheme } from "@lib/theme/setTheme";
import { type Theme } from "@lib/theme/types";

export function useTheme(theme?: Theme) {
  const computedTheme = theme ?? DEFAULT_THEME;

  React.useLayoutEffect(() => {
    document.documentElement.setAttribute("data-theme", computedTheme);

    setTheme(computedTheme);
  }, [computedTheme]);

  return {
    theme: computedTheme,
    setTheme: (theme: Theme) => {
      document.documentElement.setAttribute("data-theme", theme);
      setTheme(theme);
    },
  };
}
