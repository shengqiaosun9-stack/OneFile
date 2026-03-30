import { expect, test } from "@playwright/test";

test.describe("landing showcase carousel", () => {
  test("desktop: arrows and dots navigate showcase, card click jumps to guest library", async ({ page }) => {
    await page.goto("/");

    const cards = page.locator("#landing-showcase .landing-showcase-item");
    const dots = page.locator("#landing-showcase .landing-showcase-dot");
    const track = page.locator("#landing-showcase .landing-showcase-track");
    const prevButton = page.getByRole("button", { name: "查看上一个案例" });
    const nextButton = page.getByRole("button", { name: "查看下一个案例" });

    await expect(cards).toHaveCount(8);
    await expect(dots).toHaveCount(8);
    await expect(prevButton).toBeDisabled();
    await expect(nextButton).toBeEnabled();

    const beforeScrollLeft = await track.evaluate((element) => (element as HTMLDivElement).scrollLeft);
    await nextButton.click();
    await expect
      .poll(async () => track.evaluate((element) => (element as HTMLDivElement).scrollLeft))
      .toBeGreaterThan(beforeScrollLeft);

    await dots.nth(3).click();
    await expect(dots.nth(3)).toHaveClass(/is-active/);

    await page.locator("#landing-showcase .landing-showcase-card-link").nth(3).click();
    await expect(page).toHaveURL(/\/library\?mode=guest/);
  });

  test("mobile: arrows visible and horizontal scroll updates active item", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    const dots = page.locator("#landing-showcase .landing-showcase-dot");
    const prevButton = page.getByRole("button", { name: "查看上一个案例" });
    const nextButton = page.getByRole("button", { name: "查看下一个案例" });
    const track = page.locator("#landing-showcase .landing-showcase-track");

    await expect(prevButton).toBeVisible();
    await expect(nextButton).toBeVisible();
    await expect(prevButton).toBeDisabled();

    await nextButton.click();
    await expect(dots.nth(1)).toHaveClass(/is-active/);

    await track.evaluate((element) => {
      const trackEl = element as HTMLDivElement;
      trackEl.scrollLeft = trackEl.scrollWidth;
      trackEl.dispatchEvent(new Event("scroll"));
    });

    await expect(dots.nth(7)).toHaveClass(/is-active/);
  });
});
