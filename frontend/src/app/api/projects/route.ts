import { NextRequest } from "next/server";

import { buildQuery, proxyToBackend } from "@/lib/backend-proxy";

export async function GET(req: NextRequest) {
  const path = buildQuery("/v1/projects", req.nextUrl.searchParams);
  return proxyToBackend(req, path);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxyToBackend(req, "/v1/projects", { method: "POST", body });
}
