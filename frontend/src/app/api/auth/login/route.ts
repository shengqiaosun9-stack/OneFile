import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/backend-proxy";

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxyToBackend(req, "/v1/auth/login", { method: "POST", body });
}
