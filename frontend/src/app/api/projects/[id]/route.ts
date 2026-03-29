import { NextRequest } from "next/server";

import { buildQuery, proxyToBackend } from "@/lib/backend-proxy";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = buildQuery(`/v1/projects/${id}`, req.nextUrl.searchParams);
  return proxyToBackend(req, path);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await req.json();
  return proxyToBackend(req, `/v1/projects/${id}`, { method: "PATCH", body });
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = buildQuery(`/v1/projects/${id}`, req.nextUrl.searchParams);
  return proxyToBackend(req, path, { method: "DELETE" });
}
