import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // Images stay hashed files under /assets/ instead of data: URIs inlined into the bundle.
  build: { assetsInlineLimit: 0 },
  test: {
    environment: "jsdom",
    css: true,
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/setup.ts"],
  },
});
