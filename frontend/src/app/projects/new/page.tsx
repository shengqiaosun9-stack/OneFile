"use client";

import { ChangeEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Paperclip, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { buildLoginRedirectPath, currentPathWithQuery } from "@/lib/auth-redirect";
import { copyZh } from "@/lib/copy-zh";
import { resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { createRequestId } from "@/lib/request-id";
import { saveEmail } from "@/lib/session";
import type { AuthMeResponse, BpExtractResponse, MutationResponse, OneFileProject } from "@/lib/types";

export const dynamic = "force-dynamic";

type CreateViewState = "input" | "generating" | "draft";
type DraftStage = "IDEA" | "BUILDING" | "EARLY_REVENUE";
type EditableField = "title" | "what" | "monetization" | "currentState" | "progress" | "keyMetric";

type DraftFields = {
  id: string;
  title: string;
  what: string;
  monetization: string;
  currentState: DraftStage;
  progress: string;
  keyMetric: string;
  updatedAt: string;
};

const STAGE_OPTIONS: Array<{ code: DraftStage; labelKey: "stateIdea" | "stateBuilding" | "stateLaunched" }> = [
  { code: "IDEA", labelKey: "stateIdea" },
  { code: "BUILDING", labelKey: "stateBuilding" },
  { code: "EARLY_REVENUE", labelKey: "stateLaunched" },
];

function readCtaTokenFromUrl(): string {
  if (typeof window === "undefined") return "";
  const query = new URLSearchParams(window.location.search);
  return (query.get("cta_token") || "").trim();
}

function normalizeDraftStage(value: string): DraftStage {
  const upper = value.toUpperCase();
  if (upper === "IDEA") return "IDEA";
  if (upper === "EARLY_REVENUE" || upper === "SCALING" || upper === "MATURE") return "EARLY_REVENUE";
  return "BUILDING";
}

function projectToDraft(project: OneFileProject): DraftFields {
  return {
    id: project.id,
    title: project.title || "未命名项目",
    what: project.summary || "",
    monetization: project.model_desc || "",
    currentState: normalizeDraftStage(project.stage || ""),
    progress: project.latest_update || "",
    keyMetric: project.stage_metric || "",
    updatedAt: project.updated_at || "",
  };
}

function inferOptionalTitle(rawInput: string): string {
  const text = rawInput.trim();
  if (!text) return "";
  if (text.length > 24) return "";
  if (/[\n。！？.!?]/.test(text)) return "";
  return text;
}

function formatProgressRelativeLabel(updatedAt: string): string {
  if (!updatedAt) return "刚刚";
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) return "刚刚";

  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
  if (sameDay) {
    const diffMinutes = Math.floor((now.getTime() - date.getTime()) / 60_000);
    if (diffMinutes <= 15) return "刚刚";
    return "今天";
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate();
  if (isYesterday) return "昨天";

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export default function NewProjectPage() {
  const t = copyZh.create;
  const router = useRouter();

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [email, setEmail] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [authProbeTick, setAuthProbeTick] = useState(0);
  const [authProbeError, setAuthProbeError] = useState("");

  const [viewState, setViewState] = useState<CreateViewState>("input");
  const [rawInput, setRawInput] = useState("");
  const [supplementalText, setSupplementalText] = useState("");
  const [attachedFileName, setAttachedFileName] = useState("");
  const [bpMetaText, setBpMetaText] = useState("");
  const [bpParsing, setBpParsing] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");

  const [draft, setDraft] = useState<DraftFields | null>(null);
  const [savedDraft, setSavedDraft] = useState<DraftFields | null>(null);
  const [savingField, setSavingField] = useState<EditableField | "">("");
  const [savedField, setSavedField] = useState<EditableField | "">("");
  const [activeEditableField, setActiveEditableField] = useState<EditableField | "">("");
  const [firstClickHintSeen, setFirstClickHintSeen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    (async () => {
      setAuthReady(false);
      setAuthProbeError("");
      try {
        const meRes = await fetchWithTimeout("/api/auth/me", { cache: "no-store" }, 30_000);
        if (!meRes.ok) {
          setAuthReady(true);
          return;
        }
        const me = (await meRes.json()) as AuthMeResponse;
        setEmail(me.user?.email || "");
        if (me.user?.email) {
          saveEmail(me.user.email);
        }
      } catch {
        setAuthProbeError(t.authCheckFailed);
      } finally {
        setAuthReady(true);
      }
    })();
  }, [authProbeTick, t.authCheckFailed]);

  const canGenerate = useMemo(
    () => (rawInput.trim().length > 0 || supplementalText.trim().length > 0) && !bpParsing && viewState !== "generating",
    [bpParsing, rawInput, supplementalText, viewState],
  );

  async function uploadPdfFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError(t.uploadTypeInvalid);
      toast.error(t.uploadTypeInvalid);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError(t.uploadTooLarge);
      toast.error(t.uploadTooLarge);
      return;
    }

    setBpParsing(true);
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetchWithTimeout(
        "/api/uploads/bp-extract",
        {
          method: "POST",
          body: formData,
        },
        60_000,
      );
      if (!res.ok) {
        const failure = await resolveApiError(res, t.uploadFailed);
        if (failure.status === 401) {
          toast.error(failure.message);
          router.push(buildLoginRedirectPath(currentPathWithQuery("/projects/new"), failure.code || "unauthorized"));
          return;
        }
        setError(failure.message);
        toast.error(failure.message);
        setSupplementalText("");
        setBpMetaText("");
        setAttachedFileName("");
        return;
      }
      const body = (await res.json()) as BpExtractResponse;
      const summary = `${t.uploadParsed}：${body.page_count} 页，${body.text_chars} 字${body.truncated ? "（已截断）" : ""}`;
      setSupplementalText(body.extracted_text || "");
      setAttachedFileName(file.name);
      setBpMetaText(summary);
      toast.success(summary);
    } catch {
      setError(t.uploadNetworkFailed);
      toast.error(t.uploadNetworkFailed);
    } finally {
      setBpParsing(false);
    }
  }

  function onSelectBpFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void uploadPdfFile(file);
    event.target.value = "";
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      if (canGenerate) {
        void submitGenerate();
      }
    }
  }

  async function submitGenerate() {
    if (!email) {
      setError(t.needLoginDesc);
      toast.error(t.needLoginDesc);
      return;
    }
    if (!rawInput.trim() && !supplementalText.trim()) {
      setError(t.missingInput);
      toast.error(t.missingInput);
      return;
    }

    setError("");
    setWarning("");
    setViewState("generating");
    const ctaToken = readCtaTokenFromUrl();

    try {
      const res = await fetchWithTimeout(
        "/api/project/generate",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            raw_input: rawInput,
            optional_title: inferOptionalTitle(rawInput),
            file_text: supplementalText,
            cta_token: ctaToken,
            request_id: createRequestId("generate"),
          }),
        },
        60_000,
      );

      if (!res.ok) {
        const failure = await resolveApiError(res, t.createFailed);
        if (failure.status === 401) {
          toast.error(failure.message);
          router.push(buildLoginRedirectPath(currentPathWithQuery("/projects/new"), failure.code || "unauthorized"));
          return;
        }
        setError(failure.message);
        toast.error(failure.message);
        setViewState("input");
        return;
      }

      const body = (await res.json()) as MutationResponse;
      if (body.used_fallback) {
        const warningMessage = body.warning || t.fallbackWarning;
        setWarning(warningMessage);
        toast.warning(warningMessage);
      }
      if (body.idempotent_replay) {
        toast.message("重复提交已合并，已返回上一次成功结果。");
      }
      const nextDraft = projectToDraft(body.project);
      setDraft(nextDraft);
      setSavedDraft(nextDraft);
      setActiveEditableField("");
      setFirstClickHintSeen(false);
      setViewState("draft");
    } catch {
      setError(t.createNetworkFailed);
      toast.error(t.createNetworkFailed);
      setViewState("input");
    }
  }

  async function saveDraftField(field: EditableField) {
    if (!draft || !savedDraft) return;
    const fieldValue = draft[field];
    if (fieldValue === savedDraft[field]) return;

    let payload: Record<string, string> = {};
    if (field === "title") payload = { title: draft.title };
    if (field === "what") payload = { summary: draft.what };
    if (field === "monetization") payload = { model_desc: draft.monetization };
    if (field === "currentState") payload = { stage: draft.currentState };
    if (field === "progress") payload = { latest_update: draft.progress };
    if (field === "keyMetric") payload = { stage_metric: draft.keyMetric };

    setSavingField(field);
    setError("");
    try {
      const res = await fetchWithTimeout(
        `/api/projects/${draft.id}`,
        {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        },
        45_000,
      );
      if (!res.ok) {
        const failure = await resolveApiError(res, t.saveFailed);
        if (failure.status === 401) {
          toast.error(failure.message);
          router.push(buildLoginRedirectPath(currentPathWithQuery("/projects/new"), failure.code || "unauthorized"));
          return;
        }
        setError(failure.message);
        toast.error(failure.message);
        return;
      }

      const body = (await res.json()) as { project: OneFileProject };
      const nextDraft = projectToDraft(body.project);
      setDraft(nextDraft);
      setSavedDraft(nextDraft);
      setSavedField(field);
      window.setTimeout(() => {
        setSavedField((current) => (current === field ? "" : current));
      }, 1600);
    } catch {
      setError(t.saveFailed);
      toast.error(t.saveFailed);
    } finally {
      setSavingField("");
    }
  }

  function stageLabelOf(code: DraftStage): string {
    const found = STAGE_OPTIONS.find((item) => item.code === code);
    return found ? t[found.labelKey] : t.stateBuilding;
  }

  function activateField(field: EditableField) {
    if (field === "title") setFirstClickHintSeen(true);
    setSavedField("");
    setActiveEditableField(field);
  }

  function updateDraftField(field: EditableField, value: string) {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  }

  function cancelFieldEdit(field: EditableField) {
    setDraft((prev) => {
      if (!prev || !savedDraft) return prev;
      return { ...prev, [field]: savedDraft[field] };
    });
    setActiveEditableField("");
  }

  function onFieldKeyDown(
    event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
    field: EditableField,
    options: { allowMultiline?: boolean } = {},
  ) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelFieldEdit(field);
      return;
    }
    if (event.key === "Enter") {
      if (options.allowMultiline && event.shiftKey) return;
      event.preventDefault();
      (event.currentTarget as HTMLElement).blur();
    }
  }

  const progressRelativeLabel = useMemo(() => formatProgressRelativeLabel(draft?.updatedAt || ""), [draft?.updatedAt]);

  async function copyShareLink() {
    if (!draft?.id || typeof window === "undefined") return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/card/${draft.id}`);
      toast.success(t.copied);
    } catch {
      toast.error(t.saveFailed);
    }
  }

  if (authReady && !email) {
    const ctaToken = readCtaTokenFromUrl();
    const loginNext = ctaToken ? `/projects/new?cta_token=${encodeURIComponent(ctaToken)}` : "/projects/new";
    return (
      <main className="app-shell app-shell--work min-h-screen px-6 py-8 sm:px-8 sm:py-10">
        <div className="mx-auto max-w-3xl space-y-6">
          <section className="content-panel space-y-3 p-5 sm:p-6">
            <h1 className="text-xl font-semibold text-[var(--landing-title)]">{t.needLoginTitle}</h1>
            <p className="text-sm content-subtle">{t.needLoginDesc}</p>
            {authProbeError ? <p className="text-sm text-destructive">{authProbeError}</p> : null}
            {authProbeError ? (
              <Button variant="ghost" className="action-secondary-btn h-10 px-4" onClick={() => setAuthProbeTick((prev) => prev + 1)}>
                {t.retryAuthCheck}
              </Button>
            ) : null}
            <Button className="action-primary-btn h-10 px-5" onClick={() => router.push(`/?next=${encodeURIComponent(loginNext)}`)}>
              {t.goLogin}
            </Button>
          </section>
        </div>
      </main>
    );
  }

  if (!authReady) {
    return (
      <main className="app-shell app-shell--work min-h-screen px-6 py-8 sm:px-8 sm:py-10">
        <div className="mx-auto max-w-3xl">
          <section className="content-panel p-5 sm:p-6">
            <p className="text-sm content-subtle">{copyZh.common.loading}</p>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="app-shell app-shell--work min-h-screen px-6 py-8 sm:px-8 sm:py-10">
      <div className="mx-auto max-w-4xl">
        <section className="compose-shell">
          <header className="space-y-2 text-center">
            <p className="text-xs uppercase tracking-[0.16em] text-[var(--landing-caption)]">OnePitch · 一眼项目</p>
            <h1 className="compose-title">{t.title}</h1>
            <p className="compose-subtitle">{viewState === "draft" ? t.draftSubtitle : t.subtitle}</p>
          </header>

          {viewState !== "draft" ? (
            <div className="compose-composer">
              <div
                className={`compose-textarea-wrap ${dragActive ? "is-drag-active" : ""}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={(event) => {
                  event.preventDefault();
                  setDragActive(false);
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragActive(false);
                  const file = event.dataTransfer.files?.[0];
                  if (file) {
                    void uploadPdfFile(file);
                  }
                }}
              >
                <Textarea
                  className="compose-textarea"
                  placeholder={t.inputPlaceholder}
                  value={rawInput}
                  onChange={(event) => setRawInput(event.target.value)}
                  onKeyDown={onInputKeyDown}
                  rows={11}
                  disabled={viewState === "generating"}
                />
                <p className="compose-shortcut">{t.shortcutHint}</p>
              </div>

              <div className="compose-actions">
                <div className="flex items-center gap-2">
                  <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" className="hidden" onChange={onSelectBpFile} />
                  <Button
                    type="button"
                    variant="ghost"
                    className="action-secondary-btn h-9 px-3"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={bpParsing || viewState === "generating"}
                  >
                    {bpParsing ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Paperclip className="mr-1 h-3.5 w-3.5" />}
                    {t.addMaterial}
                  </Button>
                  <p className="text-xs content-caption">{t.dropHint}</p>
                </div>
                <Button type="button" className="action-primary-btn h-10 px-5" onClick={() => void submitGenerate()} disabled={!canGenerate}>
                  {viewState === "generating" ? t.generating : t.generate}
                </Button>
              </div>

              {attachedFileName ? (
                <p className="text-sm text-[var(--landing-text)]">
                  {t.attachedPrefix}：{attachedFileName}
                </p>
              ) : null}
              {bpMetaText ? <p className="text-xs text-emerald-700">{bpMetaText}</p> : null}
              {supplementalText ? <p className="text-xs content-caption">{t.uploadMergedHint}</p> : null}
            </div>
          ) : null}

          {viewState === "draft" && draft ? (
            <div className="draft-card">
              <div className="draft-card-meta-row">
                <p className="text-sm text-[var(--landing-caption)]">{t.draftTitle}</p>
                <p className="draft-ready-state">{t.draftReadyState}</p>
              </div>

              <article className={`draft-display-block draft-inline-editing ${activeEditableField === "title" ? "is-active" : ""}`}>
                <div className="draft-title-row">
                  {activeEditableField === "title" ? (
                    <Input
                      autoFocus
                      className="editor-field-input text-2xl font-semibold"
                      value={draft.title}
                      onChange={(event) => updateDraftField("title", event.target.value)}
                      onBlur={() => {
                        setActiveEditableField("");
                        void saveDraftField("title");
                      }}
                      onKeyDown={(event) => onFieldKeyDown(event, "title")}
                    />
                  ) : (
                    <button type="button" className="draft-title-trigger" onClick={() => activateField("title")}>
                      <h2 className="draft-title-text">{draft.title || t.titleFallback}</h2>
                    </button>
                  )}
                  {!firstClickHintSeen && activeEditableField !== "title" ? (
                    <button type="button" className="draft-title-hint" onClick={() => activateField("title")}>
                      {t.clickToEdit}
                    </button>
                  ) : null}
                </div>
              </article>

              <article className={`draft-display-block draft-inline-editing ${activeEditableField === "what" ? "is-active" : ""}`}>
                <p className="draft-block-label">{t.fieldWhat}</p>
                {activeEditableField === "what" ? (
                  <Textarea
                    autoFocus
                    className="editor-field-input min-h-[112px]"
                    value={draft.what}
                    onChange={(event) => updateDraftField("what", event.target.value)}
                    onBlur={() => {
                      setActiveEditableField("");
                      void saveDraftField("what");
                    }}
                    onKeyDown={(event) => onFieldKeyDown(event, "what", { allowMultiline: true })}
                  />
                ) : (
                  <button type="button" className="draft-content-trigger" onClick={() => activateField("what")}>
                    <p className="draft-block-value">{draft.what || t.fieldEmpty}</p>
                  </button>
                )}
              </article>

              <article className={`draft-display-block draft-inline-editing ${activeEditableField === "monetization" ? "is-active" : ""}`}>
                <p className="draft-block-label">{t.fieldMonetization}</p>
                {activeEditableField === "monetization" ? (
                  <Textarea
                    autoFocus
                    className="editor-field-input min-h-[92px]"
                    value={draft.monetization}
                    onChange={(event) => updateDraftField("monetization", event.target.value)}
                    onBlur={() => {
                      setActiveEditableField("");
                      void saveDraftField("monetization");
                    }}
                    onKeyDown={(event) => onFieldKeyDown(event, "monetization", { allowMultiline: true })}
                  />
                ) : (
                  <button type="button" className="draft-content-trigger" onClick={() => activateField("monetization")}>
                    <p className="draft-block-value">{draft.monetization || t.fieldEmpty}</p>
                  </button>
                )}
              </article>

              <article className={`draft-display-block draft-inline-editing ${activeEditableField === "currentState" ? "is-active" : ""}`}>
                <p className="draft-block-label">{t.fieldCurrentState}</p>
                {activeEditableField === "currentState" ? (
                  <select
                    autoFocus
                    className="editor-field-input h-11 rounded-lg px-3 text-sm"
                    value={draft.currentState}
                    onChange={(event) => updateDraftField("currentState", event.target.value)}
                    onBlur={() => {
                      setActiveEditableField("");
                      void saveDraftField("currentState");
                    }}
                    onKeyDown={(event) => onFieldKeyDown(event, "currentState")}
                  >
                    {STAGE_OPTIONS.map((item) => (
                      <option key={item.code} value={item.code}>
                        {t[item.labelKey]}
                      </option>
                    ))}
                  </select>
                ) : (
                  <button type="button" className="draft-content-trigger" onClick={() => activateField("currentState")}>
                    <p className="draft-block-value">{stageLabelOf(draft.currentState)}</p>
                  </button>
                )}
              </article>

              <article className={`draft-progress-event draft-inline-editing ${activeEditableField === "progress" ? "is-active" : ""}`}>
                <p className="draft-block-label">{t.fieldProgress}</p>
                {activeEditableField === "progress" ? (
                  <Input
                    autoFocus
                    className="editor-field-input"
                    value={draft.progress}
                    onChange={(event) => updateDraftField("progress", event.target.value)}
                    onBlur={() => {
                      setActiveEditableField("");
                      void saveDraftField("progress");
                    }}
                    onKeyDown={(event) => onFieldKeyDown(event, "progress")}
                  />
                ) : (
                  <button type="button" className="draft-content-trigger" onClick={() => activateField("progress")}>
                    <p className="draft-event-line">
                      <span className="draft-event-time">{progressRelativeLabel} ·</span>
                      <span>{draft.progress || t.progressEmpty}</span>
                    </p>
                  </button>
                )}
              </article>

              <article className={`draft-display-block draft-inline-editing ${activeEditableField === "keyMetric" ? "is-active" : ""}`}>
                <p className="draft-block-label">{t.fieldMetric}</p>
                {activeEditableField === "keyMetric" ? (
                  <Input
                    autoFocus
                    className="editor-field-input"
                    value={draft.keyMetric}
                    onChange={(event) => updateDraftField("keyMetric", event.target.value)}
                    onBlur={() => {
                      setActiveEditableField("");
                      void saveDraftField("keyMetric");
                    }}
                    onKeyDown={(event) => onFieldKeyDown(event, "keyMetric")}
                  />
                ) : (
                  <button type="button" className="draft-content-trigger" onClick={() => activateField("keyMetric")}>
                    <p className="draft-block-value">{draft.keyMetric || t.fieldEmpty}</p>
                  </button>
                )}
              </article>

              <div className="flex items-center justify-between gap-3 text-xs content-caption">
                <span>{savingField ? t.autoSaveSaving : savedField ? t.autoSaveSaved : t.continueEditHint}</span>
                <span>{t.shareActionsHint}</span>
              </div>

              <div className="flex flex-wrap gap-2 pt-2">
                <Button type="button" variant="ghost" className="action-secondary-btn h-10 px-4" onClick={() => void copyShareLink()}>
                  {t.copyShareLink}
                </Button>
                <Button
                  type="button"
                  className="action-primary-btn h-10 px-5"
                  onClick={() =>
                    router.push(
                      `/card/${draft.id}?from=create-draft&return=${encodeURIComponent(`/edit/${draft.id}`)}`,
                    )
                  }
                >
                  {t.previewSharePage}
                </Button>
              </div>
            </div>
          ) : null}

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {warning ? <p className="text-sm text-amber-600">{warning}</p> : null}
        </section>
      </div>
    </main>
  );
}
