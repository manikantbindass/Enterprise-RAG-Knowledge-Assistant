import { test, expect } from "@playwright/test";

test("public showcase opens all real screens without authentication", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Scattered knowledge. Connected understanding.",
    }),
  ).toBeVisible();
  for (const name of [
    "Overview",
    "Document library",
    "Ask knowledge",
    "On the move",
  ]) {
    await page.getByRole("tab", { name, exact: true }).click();
    const image = page.getByRole("tabpanel").locator("img");
    await expect(image).toBeVisible();
    await expect
      .poll(() =>
        image.evaluate(
          (element: HTMLImageElement) =>
            element.complete && element.naturalWidth > 0,
        ),
      )
      .toBe(true);
  }
  await expect(
    page.getByText("They do not provide a hosted login.", { exact: false }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/public-showcase-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
