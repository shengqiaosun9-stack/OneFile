import { NextRequest } from "next/server";

import { proxyToBackend, readJsonBody } from "@/lib/backend-proxy";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ subjectType: string; subjectId: string }> },
) {
  const { subjectType, subjectId } = await params;
  return proxyToBackend(req, `/v1/ops/profiles/${subjectType}/${subjectId}`);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ subjectType: string; subjectId: string }> },
) {
  const { subjectType, subjectId } = await params;
  const parsed = await readJsonBody(req);
  if (!parsed.ok) return parsed.response;
  return proxyToBackend(req, `/v1/ops/profiles/${subjectType}/${subjectId}`, { method: "PATCH", body: parsed.body });
}
