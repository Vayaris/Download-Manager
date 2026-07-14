const { test, expect } = require("@playwright/test");

const viewports = [
  { name: "mobile", width: 390, height: 844 },
  { name: "desktop", width: 1920, height: 1080 },
  { name: "ultrawide", width: 3440, height: 1440 },
];

for (const viewport of viewports) {
  test(`modern shell fits ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/index.html");
    await expect(page.locator("html")).toHaveAttribute("data-ui-style", "modern");
    await expect(page.locator(".app")).toBeVisible();

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
}
