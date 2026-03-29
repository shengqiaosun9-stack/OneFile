import { NextRequest } from "next/server";

import { buildQuery, proxyToBackend } from "@/lib/backend-proxy";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const path = buildQuery(`/v1/share/${id}`, req.nextUrl.searchParams);
  return proxyToBackend(req, path);
}
