import { NextRequest } from "next/server";

import { buildQuery, proxyToBackend, readJsonBody } from "@/lib/backend-proxy";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = buildQuery(`/v1/projects/${id}`, req.nextUrl.searchParams);
  return proxyToBackend(req, path);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const parsed = await readJsonBody(req);
  if (!parsed.ok) return parsed.response;
  return proxyToBackend(req, `/v1/projects/${id}`, { method: "PATCH", body: parsed.body });
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = buildQuery(`/v1/projects/${id}`, req.nextUrl.searchParams);
  return proxyToBackend(req, path, { method: "DELETE" });
}
