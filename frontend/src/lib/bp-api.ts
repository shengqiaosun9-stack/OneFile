import { fetchWithTimeout } from "@/lib/fetch-with-timeout";

export async function readApiJson<T>(res: Response): Promise<T> {
  const payload = (await res.json().catch(() => ({}))) as { message?: string };
  if (!res.ok) {
    throw new Error(payload.message || "请求失败，请稍后重试。");
  }
  return payload as T;
}

export async function bpGet<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(path, { cache: "no-store" }, 30_000);
  return readApiJson<T>(res);
}

export async function bpSend<T>(path: string, payload: unknown, method: "POST" | "PATCH" = "POST"): Promise<T> {
  const res = await fetchWithTimeout(
    path,
    {
      method,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
    45_000,
  );
  return readApiJson<T>(res);
}
