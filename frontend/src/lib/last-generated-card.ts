const LAST_GENERATED_CARD_KEY = "onepitch_last_generated_card";

export function saveLastGeneratedCardId(projectId: string): void {
  if (typeof window === "undefined" || !projectId) return;
  window.sessionStorage.setItem(LAST_GENERATED_CARD_KEY, projectId);
}

export function loadLastGeneratedCardId(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(LAST_GENERATED_CARD_KEY) || "";
}

export function clearLastGeneratedCardId(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(LAST_GENERATED_CARD_KEY);
}
