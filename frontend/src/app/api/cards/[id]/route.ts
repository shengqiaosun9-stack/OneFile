import { NextRequest } from "next/server";

import { buildQuery, proxyToBackend } from "@/lib/backend-proxy";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToBackend(req, buildQuery(`/v1/cards/${id}`, req.nextUrl.searchParams));
}
