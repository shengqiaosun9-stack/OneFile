import { NextRequest, NextResponse } from "next/server";

const RAW_BACKEND_API_URL = process.env.BACKEND_API_URL?.trim();
const BACKEND_API_URL = RAW_BACKEND_API_URL || "http://127.0.0.1:8000";
const RAW_BACKEND_TIMEOUT_MS = Number.parseInt(process.env.BACKEND_TIMEOUT_MS || "70000", 10);
const BACKEND_TIMEOUT_MS = Number.isFinite(RAW_BACKEND_TIMEOUT_MS)
  ? Math.max(8_000, Math.min(RAW_BACKEND_TIMEOUT_MS, 120_000))
  : 70_000;

type ApiErrorPayload = {
  error: string;
  message: string;
};

function joinUrl(path: string): string {
  return `${BACKEND_API_URL.replace(/\/$/, "")}${path}`;
}

function normalizeHeaders(req: NextRequest): HeadersInit {
  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  const cookie = req.headers.get("cookie");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  if (cookie) {
    headers.set("cookie", cookie);
  }
  return headers;
}

function jsonError(status: number, error: string, message: string): NextResponse {
  return NextResponse.json(
    {
      error,
      message,
    } satisfies ApiErrorPayload,
    { status },
  );
}

export function apiErrorResponse(status: number, error: string, message: string): NextResponse {
  return jsonError(status, error, message);
}

export async function readJsonBody(req: NextRequest): Promise<{ ok: true; body: unknown } | { ok: false; response: NextResponse }> {
  try {
    const body = (await req.json()) as unknown;
    return { ok: true, body };
  } catch {
    return {
      ok: false,
      response: jsonError(400, "invalid_json", "请求体格式不正确，请检查后重试。"),
    };
  }
}

function asApiErrorText(raw: string): ApiErrorPayload {
  const fallbackMessage = "服务暂时不可用，请稍后重试。";
  try {
    const payload = JSON.parse(raw) as Partial<ApiErrorPayload>;
    const error = (payload.error || "request_failed").trim() || "request_failed";
    const message = (payload.message || fallbackMessage).trim() || fallbackMessage;
    return { error, message };
  } catch {
    return {
      error: "request_failed",
      message: raw.trim() || fallbackMessage,
    };
  }
}

function appendSetCookieHeaders(source: Response, target: Headers): void {
  const setCookies = typeof source.headers.getSetCookie === "function" ? source.headers.getSetCookie() : [];
  if (setCookies.length > 0) {
    setCookies.forEach((item) => target.append("set-cookie", item));
    return;
  }
  const single = source.headers.get("set-cookie");
  if (single) {
    target.set("set-cookie", single);
  }
}

export async function proxyToBackend(
  req: NextRequest,
  path: string,
  init?: { method?: string; body?: unknown },
): Promise<NextResponse> {
  if (!RAW_BACKEND_API_URL && process.env.NODE_ENV === "production") {
    return jsonError(503, "backend_not_configured", "后端服务地址未配置，请联系管理员。");
  }

  const url = joinUrl(path);
  const method = init?.method || req.method;
  let body: BodyInit | undefined;
  if (init?.body !== undefined) {
    body = JSON.stringify(init.body);
  } else if (method !== "GET" && method !== "HEAD") {
    const buf = await req.arrayBuffer();
    if (buf.byteLength > 0) {
      body = Buffer.from(buf);
    }
  }

  let response: Response;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  try {
    response = await fetch(url, {
      method,
      headers: normalizeHeaders(req),
      body,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return jsonError(504, "backend_timeout", "后端响应超时，请稍后重试。");
    }
    return jsonError(502, "backend_unreachable", "后端服务暂时不可用，请稍后重试。");
  } finally {
    clearTimeout(timeoutId);
  }

  const text = await response.text();
  const contentType = response.headers.get("content-type") || "";

  if (!response.ok) {
    const payload =
      contentType.includes("application/json") || text.trim().startsWith("{")
        ? asApiErrorText(text)
        : { error: "request_failed", message: text.trim() || "服务暂时不可用，请稍后重试。" };
    const jsonResponse = NextResponse.json(payload, { status: response.status });
    appendSetCookieHeaders(response, jsonResponse.headers);
    return jsonResponse;
  }

  const outHeaders = new Headers();
  if (contentType) {
    outHeaders.set("content-type", contentType);
  }
  appendSetCookieHeaders(response, outHeaders);

  if (response.status === 204 || text.length === 0) {
    return new NextResponse(null, { status: response.status, headers: outHeaders });
  }

  return new NextResponse(text, { status: response.status, headers: outHeaders });
}

export function buildQuery(path: string, query: URLSearchParams): string {
  const rendered = query.toString();
  return rendered ? `${path}?${rendered}` : path;
}
