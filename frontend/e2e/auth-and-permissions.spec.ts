import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

type LoginOptions = {
  openModalFromLanding?: boolean;
};

async function getLatestProjectId(page: import("@playwright/test").Page): Promise<string> {
  for (let i = 0; i < 5; i += 1) {
    const resp = await page.request.get("/api/projects");
    expect(resp.ok()).toBeTruthy();
    const body = (await resp.json()) as { projects?: Array<{ id: string }> };
    const id = body.projects?.[0]?.id;
    if (id) return id;
    await page.waitForTimeout(500);
  }
  throw new Error("failed to get created project id from /api/projects");
}

async function listProjectIds(page: import("@playwright/test").Page): Promise<string[]> {
  const resp = await page.request.get("/api/projects");
  expect(resp.ok()).toBeTruthy();
  const body = (await resp.json()) as { projects?: Array<{ id: string }> };
  return (body.projects || []).map((item) => item.id).filter(Boolean);
}

async function createProjectFromNewFlow(page: import("@playwright/test").Page, input: string): Promise<string> {
  const beforeIds = new Set(await listProjectIds(page));
  await page.goto("/projects/new");
  await expect(page.getByRole("button", { name: "生成档案" })).toHaveClass(/landing-cta-btn/);
  await page
    .getByPlaceholder("用一句话描述你的项目，或直接输入项目名称，也可以粘贴已有内容 / BP")
    .fill(input);
  await page.getByRole("button", { name: "生成档案" }).click();
  await expect(page.getByText("项目草稿已生成")).toBeVisible();
  for (let i = 0; i < 5; i += 1) {
    const ids = await listProjectIds(page);
    const createdId = ids.find((id) => !beforeIds.has(id));
    if (createdId) return createdId;
    await page.waitForTimeout(500);
  }
  return getLatestProjectId(page);
}

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

  await expect(page.getByRole("dialog").getByText("验证码已发送到你的邮箱。")).toBeVisible();
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

    const ownerProjectId = await createProjectFromNewFlow(page, "Switch 权限测试项目。owner 账号创建，用于验证退出后账号切换权限。");
    await page.goto(`/projects/${ownerProjectId}`);
    await expect(page.getByRole("button", { name: "添加进展" })).toBeVisible();
    await expect(page.getByLabel("更多操作")).toBeVisible();

    await page.goto("/library");
    await page.getByRole("button", { name: "退出登录" }).click();
    await expect(page.getByRole("button", { name: "登录后可创建项目" })).toBeVisible();

    await page.goto(`/projects/${ownerProjectId}`);
    await expect(page.getByRole("button", { name: "添加进展" })).toHaveCount(0);
    await expect(page.getByLabel("更多操作")).toHaveCount(0);

    await loginWithEmailCode(page, "intruder.switch@example.com");
    await page.goto(`/projects/${ownerProjectId}`);
    await expect(page.getByRole("button", { name: "添加进展" })).toHaveCount(0);
    await expect(page.getByLabel("更多操作")).toHaveCount(0);
  });

  test("分享 CTA 回流：未登录访客登录后保留 cta_token 并完成创建归因", async ({ page }) => {
    test.setTimeout(180_000);

    await loginWithEmailCode(page, "owner.cta@example.com");
    const sourceProjectId = await createProjectFromNewFlow(page, "CTA 源项目，用于验证分享回流创建归因。");
    await page.goto(`/projects/${sourceProjectId}`);
    await expect(page.getByRole("button", { name: "添加进展" })).toBeVisible();

    await page.goto("/library");
    await page.getByRole("button", { name: "退出登录" }).click();
    await expect(page.getByRole("button", { name: "登录后可创建项目" })).toBeVisible();

    await page.goto(`/share/${sourceProjectId}`);
    await expect(page.getByRole("button", { name: "用 OneFile 创建你的项目档案 →" })).toBeVisible();
    await page.getByRole("button", { name: "用 OneFile 创建你的项目档案 →" }).click();

    await expect(page).toHaveURL(/\/\?next=%2Fprojects%2Fnew%3Fcta_token%3D/);
    await loginWithEmailCode(page, "visitor.cta@example.com", /\/projects\/new\?cta_token=/, { openModalFromLanding: false });

    const beforeVisitorIds = new Set(await listProjectIds(page));
    await page
      .getByPlaceholder("用一句话描述你的项目，或直接输入项目名称，也可以粘贴已有内容 / BP")
      .fill("CTA 回流新项目，访客经分享回流后创建。");
    await page.getByRole("button", { name: "生成档案" }).click();
    await expect(page.getByText("项目草稿已生成")).toBeVisible();
    const visitorIds = await listProjectIds(page);
    const convertedProjectId = visitorIds.find((id) => !beforeVisitorIds.has(id)) || (await getLatestProjectId(page));

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
    const projectId = await createProjectFromNewFlow(page, "生命周期测试项目，用于验证高级编辑、私有切换和删除。");
    await page.goto(`/projects/${projectId}`);

    await page.getByRole("heading", { level: 1 }).click();
    await page.locator("input.onefile-draft-input").first().fill("生命周期测试项目 v2");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "生命周期测试项目 v2" })).toBeVisible();

    await page.getByLabel("更多操作").click();
    await page.getByRole("button", { name: "设为私有" }).click();
    await expect(page.locator("header").locator("span").filter({ hasText: /^私有$/ }).first()).toBeVisible();

    const guestContext = await browser.newContext();
    const guestPage = await guestContext.newPage();
    await guestPage.goto(`/share/${projectId}`);
    await expect(guestPage.getByText("该项目当前为私有，仅项目所有者可预览。")).toBeVisible();
    await expect(guestPage.getByRole("button", { name: "用 OneFile 创建你的项目档案 →" })).toHaveCount(0);
    await guestContext.close();

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByLabel("更多操作").click();
    await page.getByRole("button", { name: "删除项目" }).click();
    await expect(page).toHaveURL(/\/library/);

    await page.goto(`/projects/${projectId}`);
    await expect(page.locator("main .onefile-panel p.text-destructive")).toContainText("目标内容不存在或已删除。");
  });
});
