import { NextRequest } from "next/server";

import { proxyToBackend, readJsonBody } from "@/lib/backend-proxy";

export async function POST(req: NextRequest) {
  const parsed = await readJsonBody(req);
  if (!parsed.ok) return parsed.response;
  return proxyToBackend(req, "/v1/auth/login/verify", { method: "POST", body: parsed.body });
}
