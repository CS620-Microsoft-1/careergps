import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Component tests: React components rendered in jsdom with Testing Library.
// The pure logic in lib/ keeps its node:test suite (npm test); end-to-end tests are in e2e/ (Playwright).
export default defineConfig({
  // Same as the "@/*" path in tsconfig.json.
  resolve: { alias: [{ find: /^@\//, replacement: fileURLToPath(new URL("./", import.meta.url)) }] },
  // The automatic runtime, as Next.js uses: no `import React` needed in components.
  oxc: { jsx: { runtime: "automatic" } },
  test: {
    environment: "jsdom",
    include: ["components/**/*.test.tsx"],
    setupFiles: ["./test/setup.ts"],
  },
});
