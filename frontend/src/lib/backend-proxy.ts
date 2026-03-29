import { NextRequest, NextResponse } from "next/server";

const BACKEND_API_URL = process.env.BACKEND_API_URL || "http://127.0.0.1:8000";

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

export async function proxyToBackend(
  req: NextRequest,
  path: string,
  init?: { method?: string; body?: unknown },
): Promise<NextResponse> {
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

  const response = await fetch(url, {
    method,
    headers: normalizeHeaders(req),
    body,
    cache: "no-store",
  });

  const text = await response.text();
  const outHeaders = new Headers();
  outHeaders.set("content-type", response.headers.get("content-type") || "application/json");

  const setCookies = typeof response.headers.getSetCookie === "function" ? response.headers.getSetCookie() : [];
  if (setCookies.length > 0) {
    setCookies.forEach((item) => outHeaders.append("set-cookie", item));
  } else {
    const single = response.headers.get("set-cookie");
    if (single) {
      outHeaders.set("set-cookie", single);
    }
  }

  return new NextResponse(text, {
    status: response.status,
    headers: outHeaders,
  });
}

export function buildQuery(path: string, query: URLSearchParams): string {
  const rendered = query.toString();
  return rendered ? `${path}?${rendered}` : path;
}
