import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const PROJECT_DETAIL_URL_RE = /\/projects\/(?!new(?:[/?#]|$))[^/?#]+/;

type LoginOptions = {
  openModalFromLanding?: boolean;
};

function readStoreSnapshot(): { events?: Array<Record<string, unknown>> } {
  const storePath = resolve(process.cwd(), "../.tmp/e2e-projects.json");
  const raw = readFileSync(storePath, "utf-8");
  return JSON.parse(raw) as { events?: Array<Record<string, unknown>> };
}

async function loginWithEmailCode(
  page: import("@playwright/test").Page,
  email: string,
  expectedUrl: RegExp = /\/library/,
  options: LoginOptions = { openModalFromLanding: true },
) {
  if (options.openModalFromLanding !== false) {
    await page.goto("/");
    await page.getByRole("button", { name: "开始使用 →" }).first().click();
  } else {
    const dialog = page.getByRole("dialog");
    const visible = await dialog.isVisible().catch(() => false);
    if (!visible) {
      await page.getByRole("button", { name: "开始使用 →" }).first().click();
    }
  }

  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByPlaceholder("请输入邮箱，例如 you@company.com").fill(email);
  await page.getByRole("button", { name: "发送验证码" }).click();

  await expect(page.getByText("验证码已发送到你的邮箱。")).toBeVisible();
  const debugText = await page.locator("text=开发模式验证码：").first().textContent();
  const code = debugText?.match(/(\d{6})/)?.[1];
  expect(code).toBeTruthy();

  await page.getByPlaceholder("请输入 6 位验证码").fill(code!);
  await page.getByRole("button", { name: "验证并登录" }).click();

  await expect(page).toHaveURL(expectedUrl);
}

test.describe("auth + permission e2e", () => {
  test("退出后切换账号：新账号不能编辑旧账号项目", async ({ page }) => {
    test.setTimeout(180_000);

    await loginWithEmailCode(page, "owner.switch@example.com");
    await expect(page.getByText("公开项目库")).toBeVisible();

    await page.goto("/projects/new");
    await page.getByPlaceholder("项目 / 公司名称").fill("Switch 权限测试项目");
    await page.getByPlaceholder("描述你的想法、目标用户和当前进展").fill("owner 账号创建，用于验证退出后账号切换权限。");
    await page.getByRole("button", { name: "生成项目" }).click();
    await expect(page).toHaveURL(PROJECT_DETAIL_URL_RE);
    await expect(page.getByRole("button", { name: "提交更新" })).toBeVisible();

    const ownerProjectId = page.url().match(/\/projects\/(?!new(?:[/?#]|$))([^/?#]+)/)?.[1];
    expect(ownerProjectId).toBeTruthy();

    await page.goto("/library");
    await page.getByRole("button", { name: "退出登录" }).click();
    await expect(page.getByRole("button", { name: "登录后可创建项目" })).toBeVisible();

    await page.goto(`/projects/${ownerProjectId}`);
    await expect(page.getByText("你当前是浏览模式。登录且为项目所有者后，才可更新、编辑和修改公开状态。")).toBeVisible();
    await expect(page.getByRole("button", { name: "提交更新" })).toHaveCount(0);

    await loginWithEmailCode(page, "intruder.switch@example.com");
    await page.goto(`/projects/${ownerProjectId}`);
    await expect(page.getByText("你当前是浏览模式。登录且为项目所有者后，才可更新、编辑和修改公开状态。")).toBeVisible();
    await expect(page.getByRole("button", { name: "提交更新" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "设为私有" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "设为公开" })).toHaveCount(0);
  });

  test("分享 CTA 回流：未登录访客登录后保留 cta_token 并完成创建归因", async ({ page }) => {
    test.setTimeout(180_000);

    await loginWithEmailCode(page, "owner.cta@example.com");
    await page.goto("/projects/new");
    await page.getByPlaceholder("项目 / 公司名称").fill("CTA 源项目");
    await page.getByPlaceholder("描述你的想法、目标用户和当前进展").fill("用于验证分享回流创建归因。");
    await page.getByRole("button", { name: "生成项目" }).click();
    await expect(page).toHaveURL(PROJECT_DETAIL_URL_RE);
    await expect(page.getByRole("button", { name: "提交更新" })).toBeVisible();
    const sourceProjectId = page.url().match(/\/projects\/(?!new(?:[/?#]|$))([^/?#]+)/)?.[1];
    expect(sourceProjectId).toBeTruthy();

    await page.goto("/library");
    await page.getByRole("button", { name: "退出登录" }).click();
    await expect(page.getByRole("button", { name: "登录后可创建项目" })).toBeVisible();

    await page.goto(`/share/${sourceProjectId}`);
    await expect(page.getByRole("button", { name: "用 OneFile 创建你的项目档案 →" })).toBeVisible();
    await page.getByRole("button", { name: "用 OneFile 创建你的项目档案 →" }).click();

    await expect(page).toHaveURL(/\/\?next=%2Fprojects%2Fnew%3Fcta_token%3D/);
    await loginWithEmailCode(page, "visitor.cta@example.com", /\/projects\/new\?cta_token=/, { openModalFromLanding: false });

    await page.getByPlaceholder("项目 / 公司名称").fill("CTA 回流新项目");
    await page.getByPlaceholder("描述你的想法、目标用户和当前进展").fill("访客经分享回流后创建。");
    await page.getByRole("button", { name: "生成项目" }).click();
    await expect(page).toHaveURL(PROJECT_DETAIL_URL_RE);
    const convertedProjectId = page.url().match(/\/projects\/(?!new(?:[/?#]|$))([^/?#]+)/)?.[1];
    expect(convertedProjectId).toBeTruthy();

    const store = readStoreSnapshot();
    const events = (store.events || []).filter((item) => item && typeof item === "object");
    const attributedCreate = events.find((item) => {
      if (item.event_type !== "share_conversion_attributed") return false;
      if (item.project_id !== sourceProjectId) return false;
      const payload = (item.payload || {}) as Record<string, unknown>;
      return payload.conversion_kind === "create" && payload.converted_project_id === convertedProjectId;
    });
    expect(attributedCreate).toBeTruthy();
  });

  test("owner 可高级编辑、设私有并删除；访客在私有状态下受限", async ({ browser, page }) => {
    test.setTimeout(180_000);

    await loginWithEmailCode(page, "owner.lifecycle@example.com");
    await page.goto("/projects/new");
    await page.getByPlaceholder("项目 / 公司名称").fill("生命周期测试项目");
    await page.getByPlaceholder("描述你的想法、目标用户和当前进展").fill("用于验证高级编辑、私有切换和删除。");
    await page.getByRole("button", { name: "生成项目" }).click();
    await expect(page).toHaveURL(PROJECT_DETAIL_URL_RE);

    const projectId = page.url().match(/\/projects\/(?!new(?:[/?#]|$))([^/?#]+)/)?.[1];
    expect(projectId).toBeTruthy();

    await page.getByPlaceholder("项目标题").fill("生命周期测试项目 v2");
    await page.getByPlaceholder("一句话摘要").fill("已完成高级编辑");
    await page.getByRole("button", { name: "保存高级编辑" }).click();
    await expect(page.getByRole("heading", { name: "生命周期测试项目 v2" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "一句话摘要" })).toHaveValue("已完成高级编辑");

    await page.getByRole("button", { name: "设为私有" }).click();
    await expect(page.getByRole("button", { name: "设为公开" })).toBeVisible();

    const guestContext = await browser.newContext();
    const guestPage = await guestContext.newPage();
    await guestPage.goto(`/share/${projectId}`);
    await expect(guestPage.getByText("该项目当前为私有，仅项目所有者可预览。")).toBeVisible();
    await expect(guestPage.getByRole("button", { name: "用 OneFile 创建你的项目档案 →" })).toHaveCount(0);
    await guestContext.close();

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "删除项目" }).click();
    await expect(page).toHaveURL(/\/library/);

    await page.goto(`/projects/${projectId}`);
    await expect(page.locator("main .onefile-panel p.text-destructive")).toContainText("目标内容不存在或已删除。");
  });
});
