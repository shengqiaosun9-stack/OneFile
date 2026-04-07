import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/backend-proxy";

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToBackend(req, `/v1/cards/${id}/claim`, { method: "POST", body: {} });
}
