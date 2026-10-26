import { test, expect } from "@playwright/test";

test("register, upload, ask with sources, reload and sign out", async ({
  page,
}, testInfo) => {
  const email = `browser-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Browser Tester");
  await page
    .getByLabel("Organization", { exact: true })
    .fill("Verification workspace");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-verification-password!");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back, Browser" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("dashboard.png"),
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Documents", exact: false })
    .first()
    .click();
  await page.locator("input[type=file]").setInputFiles({
    name: "leave-policy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Company annual leave policy: employees receive 24 days of paid leave. Requests require manager approval.",
    ),
  });
  await expect(
    page.getByRole("table").getByText("indexed", { exact: true }),
  ).toBeVisible({
    timeout: 20000,
  });
  await page
    .getByRole("button", { name: /leave-policy.txt.*KB|leave-policy.txt.*B/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "leave-policy.txt" }),
  ).toBeVisible();
  await expect(page.getByText(/employees receive 24 days/)).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath("documents.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Ask knowledge", exact: true }).click();
  await page
    .getByLabel("Ask a question about your documents")
    .fill("What is the annual leave policy?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.locator(".markdown-content").filter({ hasText: "24 days" }),
  ).toBeVisible();
  await page.locator(".message-sources").getByRole("button").first().click();
  await expect(
    page.getByRole("heading", { name: "leave-policy.txt" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath("chat.png"),
    fullPage: true,
  });
  await page.reload();
  await page.locator(".conversation-item").getByRole("button").first().click();
  await expect(
    page.locator(".markdown-content").filter({ hasText: "24 days" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "light", exact: true }).click();
  await expect(page.locator("html")).toHaveClass(/light/);
  await page.getByRole("button", { name: "system", exact: true }).click();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).not.toHaveClass(/light/);
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveClass(/light/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Ask knowledge", exact: true }).click();
  await expect(page.getByLabel("Choose conversation")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("mobile-chat.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back", exact: true }),
  ).toBeVisible();
});

test("mobile login has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Welcome back", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
