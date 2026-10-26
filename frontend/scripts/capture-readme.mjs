import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const destination = path.resolve("../docs/assets/screenshots");
await mkdir(destination, { recursive: true });
await mkdir("public/showcase", { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
});
const base = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3100";
try {
  await page.goto(base);
  await page.getByLabel("Email address").fill("demo@lumina.local");
  await page.getByLabel("Password", { exact: true }).fill("LuminaDemo!2026");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back, Demo" }),
  ).toBeVisible();
  await expect(page.locator(".metric-card > strong").first()).toHaveText("3");
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: path.join(destination, "dashboard.png"),
    fullPage: true,
  });
  await page.goto(`${base}/documents`);
  await expect(page.locator(".data-table tbody tr")).toHaveCount(3);
  await page.screenshot({
    path: path.join(destination, "documents.png"),
    fullPage: true,
  });
  await page.goto(`${base}/chat`);
  await page.locator(".conversation-item").getByRole("button").first().click();
  await expect(
    page.locator(".markdown-content").filter({ hasText: "24 days" }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(destination, "chat.png"),
    fullPage: true,
  });
  await page.goto(`${base}/settings`);
  await page.getByRole("button", { name: "light", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Ask knowledge", exact: true }).click();
  await page.screenshot({
    path: path.join(destination, "mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "dark", exact: true }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  console.log(`Captured actual demo workspace screens in ${destination}`);
} finally {
  await browser.close();
}
