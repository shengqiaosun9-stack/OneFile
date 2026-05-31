import { NextRequest } from "next/server";

import { buildQuery, proxyToBackend, readJsonBody } from "@/lib/backend-proxy";

async function forward(req: NextRequest, method: "GET" | "POST" | "PATCH", path: string[]) {
  const backendPath = buildQuery(`/v1/ops/${path.map(encodeURIComponent).join("/")}`, req.nextUrl.searchParams);
  if (method === "GET") return proxyToBackend(req, backendPath);
  const parsed = await readJsonBody(req);
  if (!parsed.ok) return parsed.response;
  return proxyToBackend(req, backendPath, { method, body: parsed.body });
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "GET", path);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "POST", path);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "PATCH", path);
}
