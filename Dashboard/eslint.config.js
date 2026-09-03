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
        // Habilita as regras type-aware do @typescript-eslint. `projectService`
        // resolve o tsconfig por arquivo sem precisar listar `project`.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
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
      // Regras type-aware — o app inteiro é construído sobre promises e essas
      // três estavam inativas (plugin registrado, nenhum preset aplicado).
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/await-thenable": "error",
      // Resto do preset type-checked, como aviso: pegam bug real sem o ruído
      // do subconjunto `no-unsafe-*` (que num app com `res.json() as T` acende
      // em toda chamada de API). `require-await` e `no-redundant-type-constituents`
      // ficaram de fora desta rodada — geram aviso em async mantido por assinatura
      // e são backlog da Onda 6.
      "@typescript-eslint/no-for-in-array": "warn",
      "@typescript-eslint/no-implied-eval": "warn",
      "@typescript-eslint/no-unnecessary-type-assertion": "warn",
      "@typescript-eslint/unbound-method": "warn",
      "prefer-const": ["warn", { destructuring: "all" }],
      "eqeqeq": ["error", "always", { null: "ignore" }],
      "no-var": "error",
    },
  },
];
