import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.ts", "tests/**/*.ts"],
    languageOptions: { globals: { chrome: "readonly", document: "readonly", window: "readonly", MutationObserver: "readonly", HTMLElement: "readonly", HTMLInputElement: "readonly", HTMLSelectElement: "readonly", HTMLTextAreaElement: "readonly", Event: "readonly", MouseEvent: "readonly", File: "readonly", URL: "readonly", fetch: "readonly", console: "readonly", setTimeout: "readonly", clearTimeout: "readonly" } },
  },
);
