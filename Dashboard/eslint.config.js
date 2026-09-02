// ESLint flat config para o Dashboard React (TypeScript + JSX).
// Foco em erros reais, regras de hooks e acessibilidade; estilo fica a cargo
// do tsc/prettier.
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Conjunto recomendado do plugin (a maioria já "error") — gate que teria
      // pego, em CI, os defeitos catalogados na Onda 2 do plano de revisão
      // geral do frontend: role="img" apagando conteúdo real, <svg> clicável
      // sem teclado, <th> sem cabeçalho, etc.
      ...jsxA11y.flatConfigs.recommended.rules,
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-undef": "off",
      "prefer-const": ["warn", { destructuring: "all" }],
      "eqeqeq": ["error", "always", { null: "ignore" }],
      "no-var": "error",
    },
  },
];
