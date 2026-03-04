import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import tailwind from "eslint-plugin-tailwindcss";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  ...tailwind.configs["flat/recommended"].map((block) => ({
    ...block,
    settings: {
      ...(block.settings ?? {}),
      tailwindcss: {
        ...(block.settings?.tailwindcss ?? {}),
        config: {
          content: [
            "./app/**/*.{js,ts,jsx,tsx,mdx}",
            "./src/**/*.{js,ts,jsx,tsx,mdx}",
          ],
          theme: {},
          plugins: [],
        },
      },
    },
  })),
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: {
      "unused-imports": (await import("eslint-plugin-unused-imports")).default,
      prettier: (await import("eslint-plugin-prettier")).default,
      "simple-import-sort": (await import("eslint-plugin-simple-import-sort"))
        .default,
    },
    rules: {
      "prettier/prettier": "error",
      "@typescript-eslint/no-unused-vars": "off",
      "unused-imports/no-unused-imports": "error",
      "unused-imports/no-unused-vars": [
        "warn",
        {
          vars: "all",
          varsIgnorePattern: "^_",
          args: "after-used",
          argsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        {
          prefer: "type-imports",
          disallowTypeAnnotations: false,
          fixStyle: "inline-type-imports",
        },
      ],
      "import/consistent-type-specifier-style": ["error", "prefer-inline"],
      "no-console": ["error", { allow: ["warn", "error", "info"] }],
      // Utilise simple-import-sort pour un auto-fix fiable
      "simple-import-sort/imports": [
        "error",
        {
          groups: [
            // React en premier
            ["^react$", "^react-dom$"],
            // Next.js
            ["^next(/.*)?$"],
            // Packages externes
            ["^@?\\w"],
            // Imports internes avec alias @/
            ["^@/"],
            // Imports relatifs parent (..)
            ["^\\.\\.(?!/?$)", "^\\.\\./?$"],
            // Imports relatifs sibling (.)
            ["^\\./(?=.*/)(?!/?$)", "^\\.(?!/?$)", "^\\./?$"],
            // Style imports
            ["^.+\\.s?css$"],
          ],
        },
      ],
      "simple-import-sort/exports": "error",
      "import/newline-after-import": "error",
      "import/no-duplicates": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "tailwindcss/classnames-order": "warn",
      "tailwindcss/no-custom-classname": "off",
      "react-hooks/refs": "off",
    },
  },
  // Ignores par défaut Next
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
