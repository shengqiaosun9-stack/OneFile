export const GUEST_EMAIL = "guest@onefile.app";
const EMAIL_KEY = "onefile_email";

export function saveEmail(email: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(EMAIL_KEY, email);
}

export function loadEmail(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(EMAIL_KEY) || "";
}

export function clearEmail(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(EMAIL_KEY);
}

export function currentEmailFromUrl(search: URLSearchParams): string {
  return search.get("email") || "";
}
