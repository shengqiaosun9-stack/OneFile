import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/backend-proxy";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await req.json();
  return proxyToBackend(req, `/v1/projects/${id}/share`, { method: "PATCH", body });
}
