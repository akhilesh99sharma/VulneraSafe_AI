/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static client-side app. `base` is the GitHub Pages repo path so that
// `import.meta.env.BASE_URL` resolves artifact fetches under /VulneraSafe_AI/
// (Req 12.9, 15.1, 15.2).
export default defineConfig({
  base: "/VulneraSafe_AI/",
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    css: false,
  },
});
