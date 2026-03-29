#!/usr/bin/env node

/**
 * Landing style health check.
 * By default, auto-starts a temporary Next dev server if target URL is unavailable.
 */

import { spawn } from "node:child_process";
import process from "node:process";

const baseUrl = process.env.LANDING_CHECK_URL || "http://127.0.0.1:3300";
const autoStart = process.env.LANDING_CHECK_AUTOSTART !== "0";
const waitTimeoutMs = Number(process.env.LANDING_CHECK_WAIT_MS || 90_000);

const requiredDomMarkers = [
  "landing-premium",
  "landing-nav",
  "landing-hero",
  "landing-card",
  "landing-value-grid",
];

const requiredCssSnippets = [
  ".landing-premium",
  ".landing-card",
  ".landing-value-grid",
  "--landing-brand",
  "background: linear-gradient(160deg, var(--landing-bg-start), var(--landing-bg-end));",
];

function fail(message) {
  throw new Error(message);
}

function pass(message) {
  console.log(`✅ ${message}`);
}

function extractStylesheetHrefs(html) {
  const hrefs = [];
  const linkRe = /<link\b[^>]*rel=["']stylesheet["'][^>]*>/gi;
  const hrefRe = /href=["']([^"']+)["']/i;
  for (const match of html.matchAll(linkRe)) {
    const tag = match[0];
    const hrefMatch = tag.match(hrefRe);
    if (!hrefMatch) continue;
    hrefs.push(hrefMatch[1]);
  }
  return hrefs;
}

async function fetchText(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  return res.text();
}

function parsePort(url) {
  try {
    const parsed = new URL(url);
    return Number(parsed.port || 80);
  } catch {
    return 3300;
  }
}

async function waitForUrl(url, timeoutMs) {
  const start = Date.now();
  let lastError = "unknown";
  while (Date.now() - start < timeoutMs) {
    try {
      await fetchText(url);
      return;
    } catch (error) {
      lastError = error.message;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw new Error(lastError);
}

function startDevServer(port) {
  const child = spawn("npm", ["run", "dev", "--", "--port", String(port)], {
    cwd: process.cwd(),
    stdio: "ignore",
    shell: process.platform === "win32",
    env: { ...process.env },
  });
  return child;
}

async function run() {
  let devServer = null;
  let html;
  try {
    html = await fetchText(`${baseUrl}/`);
  } catch (error) {
    if (!autoStart) {
      fail(`无法访问 ${baseUrl}/。请先启动前端服务。(${error.message})`);
    }
    const port = parsePort(baseUrl);
    devServer = startDevServer(port);
    try {
      await waitForUrl(`${baseUrl}/`, waitTimeoutMs);
      html = await fetchText(`${baseUrl}/`);
    } catch (waitError) {
      if (devServer && !devServer.killed) devServer.kill("SIGTERM");
      fail(`自动启动临时前端服务失败：${waitError.message}`);
    }
  }

  try {
    for (const marker of requiredDomMarkers) {
      if (!html.includes(marker)) {
        fail(`首页 DOM 缺少关键标记：${marker}`);
      }
    }
    pass("首页 DOM 关键标记存在");

    const hrefs = extractStylesheetHrefs(html).map((href) =>
      href.startsWith("http") ? href : `${baseUrl}${href.startsWith("/") ? "" : "/"}${href}`
    );

    if (!hrefs.length) {
      fail("未找到 stylesheet 链接，无法验证 Landing 样式管线。");
    }

    let cssBundle = "";
    for (const href of hrefs) {
      try {
        cssBundle += `\n/* ${href} */\n`;
        cssBundle += await fetchText(href);
      } catch (error) {
        fail(`拉取样式失败：${href} (${error.message})`);
      }
    }

    for (const snippet of requiredCssSnippets) {
      if (!cssBundle.includes(snippet)) {
        fail(`样式资源缺少关键规则：${snippet}`);
      }
    }
    pass("Landing 关键样式规则已加载");
    pass("样式管线健康检查通过");
  } finally {
    if (devServer && !devServer.killed) {
      devServer.kill("SIGTERM");
    }
  }
}

await run().catch((error) => {
  console.error(`❌ ${error.message}`);
  process.exit(1);
});
