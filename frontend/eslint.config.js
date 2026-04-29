import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        projectService: false,
      },
      globals: globals.browser,
    },
    rules: {
      "@typescript-eslint/no-misused-promises": "off",
    },
  }
);

