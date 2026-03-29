import { NextRequest } from "next/server";

import { proxyToBackend, readJsonBody } from "@/lib/backend-proxy";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const parsed = await readJsonBody(req);
  if (!parsed.ok) return parsed.response;
  return proxyToBackend(req, `/v1/projects/${id}/share`, { method: "PATCH", body: parsed.body });
}
