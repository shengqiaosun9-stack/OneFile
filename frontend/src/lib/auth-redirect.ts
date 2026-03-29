function safeNextPath(nextPath: string): string {
  if (!nextPath || !nextPath.startsWith("/") || nextPath.startsWith("//")) return "/library";
  return nextPath;
}

export function buildLoginRedirectPath(nextPath: string, reason = "unauthorized"): string {
  const query = new URLSearchParams();
  query.set("next", safeNextPath(nextPath));
  query.set("reason", reason);
  return `/?${query.toString()}`;
}

export function currentPathWithQuery(fallback = "/library"): string {
  if (typeof window === "undefined") return fallback;
  const pathname = window.location.pathname || fallback;
  const search = window.location.search || "";
  return `${pathname}${search}`;
}
