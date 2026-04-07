import { expect, test } from "@playwright/test";

test.describe("landing baseline reset", () => {
  test("hero is single-focus and showcase behaves like a manual carousel", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("[data-landing-hero-poster]")).toBeVisible();
    await expect(page.locator("[data-prompt-bar]")).toBeVisible();
    await expect(page.locator("[data-prompt-bar] textarea")).toHaveCount(1);
    await expect(page.locator("[data-prompt-bar] input")).toHaveCount(0);

    const cards = page.locator("[data-showcase-card]");
    await expect(cards).toHaveCount(3);
    await expect(page.locator("[data-showcase-card][data-state='selected']")).toHaveCount(1);

    const nextButton = page.getByRole("button", { name: "查看下一个案例" });
    await nextButton.click();

    await expect(page.locator("[data-showcase-card][data-state='selected']").nth(0)).toContainText("画境工作室");

    await page.locator("[data-showcase-card][data-state='selected'] a").click();
    await expect(page).toHaveURL(/\/card\/9c28454f\?from=landing-example/);
  });
});
