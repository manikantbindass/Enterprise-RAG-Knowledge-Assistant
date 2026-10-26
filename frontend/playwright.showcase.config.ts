import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/showcase",
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: process.env.SHOWCASE_URL || "http://127.0.0.1:3200",
    screenshot: "only-on-failure",
  },
});
