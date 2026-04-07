"use client";

import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { buildLoginRedirectPath, currentPathWithQuery } from "@/lib/auth-redirect";
import { copyZh } from "@/lib/copy-zh";
import { resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { createRequestId } from "@/lib/request-id";
import type { AuthMeResponse, MutationResponse, OneFileProject } from "@/lib/types";

export const dynamic = "force-dynamic";

type EditableField =
  | "title"
  | "summary"
  | "problemStatement"
  | "solutionApproach"
  | "useCases"
  | "modelDesc"
  | "users"
  | "stage"
  | "formType"
  | "businessModelType"
  | "modelType";

type DetailDraft = {
  title: string;
  summary: string;
  problemStatement: string;
  solutionApproach: string;
  useCases: string;
  modelDesc: string;
  users: string;
  stage: string;
  formType: string;
  businessModelType: string;
  modelType: string;
};

const FORM_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "AI_NATIVE_APP", label: "AI 原生应用" },
  { value: "SAAS", label: "SaaS" },
  { value: "API_SERVICE", label: "API 服务" },
  { value: "AGENT", label: "智能体" },
  { value: "MARKETPLACE", label: "交易市场" },
  { value: "DATA_TOOL", label: "数据工具" },
  { value: "INFRASTRUCTURE", label: "基础设施" },
  { value: "OTHER", label: "其他" },
];

const MODEL_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "B2B_SUBSCRIPTION", label: "B2B 订阅" },
  { value: "B2C_SUBSCRIPTION", label: "B2C 订阅" },
  { value: "USAGE_BASED", label: "按量计费" },
  { value: "COMMISSION", label: "交易抽佣" },
  { value: "ONE_TIME", label: "一次性付费" },
  { value: "OUTSOURCING", label: "外包/服务" },
  { value: "ADS", label: "广告变现" },
  { value: "MARKETPLACE", label: "平台撮合" },
  { value: "HYBRID", label: "混合模式" },
  { value: "UNKNOWN", label: "未知模式" },
];

const BUSINESS_MODEL_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "TOB", label: "ToB" },
  { value: "TOC", label: "ToC" },
  { value: "B2B2C", label: "B2B2C" },
  { value: "B2G", label: "B2G" },
  { value: "C2C", label: "C2C" },
  { value: "UNKNOWN", label: "未知" },
];

const STAGE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "IDEA", label: "构思阶段" },
  { value: "BUILDING", label: "开发中" },
  { value: "MVP", label: "MVP" },
  { value: "VALIDATION", label: "验证阶段" },
  { value: "EARLY_REVENUE", label: "早期收入" },
  { value: "SCALING", label: "规模增长" },
  { value: "MATURE", label: "成熟阶段" },
];

function findOptionLabel(options: Array<{ value: string; label: string }>, value: string): string {
  const upper = (value || "").toUpperCase();
  return options.find((item) => item.value === upper)?.label || value || "待补充";
}

function projectToDraft(project: OneFileProject): DetailDraft {
  return {
    title: project.title || "",
    summary: project.summary || "",
    problemStatement: project.problem_statement || "",
    solutionApproach: project.solution_approach || "",
    useCases: project.use_cases || "",
    modelDesc: project.model_desc || "",
    users: project.users || "",
    stage: project.stage || "BUILDING",
    formType: project.form_type || "OTHER",
    businessModelType: project.business_model_type || "UNKNOWN",
    modelType: project.model_type || "UNKNOWN",
  };
}

function parseProjectTime(createdAt: string): Date | null {
  if (!createdAt) return null;
  const hasTimezone = /([zZ]|[+\-]\d{2}:\d{2})$/.test(createdAt);
  let parsed = new Date(createdAt);
  if (Number.isNaN(parsed.getTime()) && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(createdAt)) {
    parsed = new Date(`${createdAt.replace(" ", "T")}Z`);
  } else if (!hasTimezone && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(createdAt)) {
    parsed = new Date(`${createdAt.replace(" ", "T")}Z`);
  }
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function formatTimelineTime(createdAt: string): string {
  if (!createdAt) return "刚刚";
  const date = parseProjectTime(createdAt);
  if (!date) return "刚刚";

  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  if (sameDay) return `今天 ${hh}:${mm}`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate();
  if (isYesterday) return `昨天 ${hh}:${mm}`;

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export default function ProjectDetailPage() {
  const t = copyZh.detail;
  const brand = copyZh.common.brand;
  const router = useRouter();
  const routeParams = useParams<{ id: string }>();
  const projectId = String(routeParams.id || "");

  const moreMenuRef = useRef<HTMLDivElement | null>(null);
  const profileSectionRef = useRef<HTMLElement | null>(null);

  const [authUserId, setAuthUserId] = useState("");
  const [authReady, setAuthReady] = useState(false);

  const [project, setProject] = useState<OneFileProject | null>(null);
  const [draft, setDraft] = useState<DetailDraft | null>(null);
  const [savedDraft, setSavedDraft] = useState<DetailDraft | null>(null);
  const [activeField, setActiveField] = useState<EditableField | "">("");

  const [savingField, setSavingField] = useState<EditableField | "">("");
  const [savingShare, setSavingShare] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [showProgressComposer, setShowProgressComposer] = useState(false);
  const [progressDraft, setProgressDraft] = useState("");
  const [savingProgress, setSavingProgress] = useState(false);
  const [editingUpdateId, setEditingUpdateId] = useState("");
  const [editingUpdateContent, setEditingUpdateContent] = useState("");
  const [savingUpdateId, setSavingUpdateId] = useState("");
  const [deletingUpdateId, setDeletingUpdateId] = useState("");

  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [saveHintField, setSaveHintField] = useState<EditableField | "">("");

  const isOwner = Boolean(project && authUserId && project.owner_user_id === authUserId);

  function syncProjectState(nextProject: OneFileProject) {
    setProject(nextProject);
    const mapped = projectToDraft(nextProject);
    setDraft(mapped);
    setSavedDraft(mapped);
  }

  useEffect(() => {
    (async () => {
      try {
        const meRes = await fetchWithTimeout("/api/auth/me", { cache: "no-store" }, 30_000);
        if (meRes.ok) {
          const meBody = (await meRes.json()) as AuthMeResponse;
          setAuthUserId(meBody.user?.id || "");
        }
      } finally {
        setAuthReady(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!projectId || !authReady) return;
    (async () => {
      try {
        const res = await fetchWithTimeout(`/api/projects/${projectId}`, { cache: "no-store" }, 30_000);
        if (!res.ok) {
          const failure = await resolveApiError(res, t.loadFailed);
          setError(failure.message);
          toast.error(failure.message);
          return;
        }
        const body = (await res.json()) as { project: OneFileProject };
        syncProjectState(body.project);
      } catch {
        setError(t.loadFailed);
        toast.error(t.loadFailed);
      }
    })();
  }, [projectId, authReady, t.loadFailed]);

  useEffect(() => {
    if (!showMoreMenu) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!moreMenuRef.current) return;
      if (!moreMenuRef.current.contains(event.target as Node)) {
        setShowMoreMenu(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [showMoreMenu]);

  const timelineItems = useMemo(() => {
    const list = project?.updates || [];
    if (list.length > 0) return list;
    if (project?.latest_update) {
      return [
        {
          id: "latest-update-fallback",
          kind: "latest_update",
          content: project.latest_update,
          created_at: project.updated_at || "",
        },
      ];
    }
    return [];
  }, [project?.updates, project?.latest_update, project?.updated_at]);

  async function handleWriteFailure(response: Response, fallback: string): Promise<void> {
    const failure = await resolveApiError(response, fallback);
    if (failure.status === 401) {
      toast.error(failure.message);
      router.push(buildLoginRedirectPath(currentPathWithQuery(`/projects/${projectId}`), failure.code || "unauthorized"));
      return;
    }
    setError(failure.message);
    toast.error(failure.message);
  }

  function openFieldEditor(field: EditableField) {
    if (!isOwner) return;
    setActiveField(field);
  }

  function updateDraftField(field: EditableField, value: string) {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  }

  function cancelFieldEditing(field: EditableField) {
    setDraft((prev) => {
      if (!prev || !savedDraft) return prev;
      return { ...prev, [field]: savedDraft[field] };
    });
    setActiveField("");
  }

  function onFieldKeyDown(
    event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
    field: EditableField,
    options: { allowMultiline?: boolean } = {},
  ) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelFieldEditing(field);
      return;
    }
    if (event.key === "Enter") {
      if (options.allowMultiline && !event.metaKey && !event.ctrlKey) return;
      event.preventDefault();
      void saveEditableField(field);
    }
  }

  async function saveEditableField(field: EditableField) {
    if (!project || !isOwner || !draft || !savedDraft) return;
    if (draft[field] === savedDraft[field]) {
      setActiveField("");
      return;
    }

    let payload: Record<string, string> = {};
    if (field === "title") payload = { title: draft.title };
    if (field === "summary") payload = { summary: draft.summary };
    if (field === "problemStatement") payload = { problem_statement: draft.problemStatement };
    if (field === "solutionApproach") payload = { solution_approach: draft.solutionApproach };
    if (field === "useCases") payload = { use_cases: draft.useCases };
    if (field === "modelDesc") payload = { model_desc: draft.modelDesc };
    if (field === "users") payload = { users: draft.users };
    if (field === "stage") payload = { stage: draft.stage };
    if (field === "formType") payload = { form_type: draft.formType };
    if (field === "businessModelType") payload = { business_model_type: draft.businessModelType };
    if (field === "modelType") payload = { model_type: draft.modelType };

    setSavingField(field);
    setError("");
    try {
      const res = await fetchWithTimeout(
        `/api/projects/${project.id}`,
        {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        },
        45_000,
      );

      if (!res.ok) {
        await handleWriteFailure(res, t.editFailed);
        return;
      }

      const body = (await res.json()) as { project: OneFileProject };
      syncProjectState(body.project);
      setActiveField("");
      setSaveHintField(field);
      window.setTimeout(() => {
        setSaveHintField((current) => (current === field ? "" : current));
      }, 1800);
    } catch {
      setError(t.editFailed);
      toast.error(t.editFailed);
    } finally {
      setSavingField("");
    }
  }

  async function toggleShareVisibility() {
    if (!project || !isOwner || savingShare) return;
    setSavingShare(true);
    setError("");

    try {
      const res = await fetchWithTimeout(
        `/api/projects/${project.id}/share`,
        {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ is_public: !project.share?.is_public }),
        },
        45_000,
      );

      if (!res.ok) {
        await handleWriteFailure(res, t.shareToggleFailed);
        return;
      }
      const body = (await res.json()) as { project: OneFileProject };
      syncProjectState(body.project);
      setShowMoreMenu(false);
    } catch {
      setError(t.shareToggleFailed);
      toast.error(t.shareToggleFailed);
    } finally {
      setSavingShare(false);
    }
  }

  async function deleteProject() {
    if (!project || !isOwner || deleting) return;
    if (typeof window !== "undefined" && !window.confirm(t.deleteConfirm)) return;
    setDeleting(true);
    setError("");

    try {
      const res = await fetchWithTimeout(`/api/projects/${project.id}`, { method: "DELETE" }, 45_000);
      if (!res.ok) {
        await handleWriteFailure(res, t.deleteFailed);
        return;
      }
      router.push("/library");
    } catch {
      setError(t.deleteFailed);
      toast.error(t.deleteFailed);
    } finally {
      setDeleting(false);
    }
  }

  async function submitProgress() {
    if (!project || !isOwner || !progressDraft.trim()) return;
    setSavingProgress(true);
    setError("");
    setWarning("");

    try {
      const res = await fetchWithTimeout(
        `/api/projects/${project.id}/update`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ update_text: progressDraft.trim(), request_id: createRequestId("update") }),
        },
        60_000,
      );

      if (!res.ok) {
        await handleWriteFailure(res, t.updateFailed);
        return;
      }

      const body = (await res.json()) as MutationResponse;
      syncProjectState(body.project);
      setProgressDraft("");
      setShowProgressComposer(false);
      if (body.used_fallback) {
        const warningMessage = body.warning || copyZh.create.fallbackWarning;
        setWarning(warningMessage);
        toast.warning(warningMessage);
      }
      if (body.idempotent_replay) {
        toast.message("重复请求已合并，已返回上一次成功结果。");
      }
    } catch {
      setError("请求可能已提交，请先刷新页面确认，避免重复提交。");
      toast.error("请求可能已提交，请先刷新页面确认，避免重复提交。");
    } finally {
      setSavingProgress(false);
    }
  }

  function startEditProgress(updateId: string, content: string) {
    setEditingUpdateId(updateId);
    setEditingUpdateContent(content || "");
  }

  function cancelEditProgress() {
    setEditingUpdateId("");
    setEditingUpdateContent("");
  }

  async function submitEditProgress(updateId: string) {
    if (!project || !isOwner || !updateId || !editingUpdateContent.trim()) return;
    setSavingUpdateId(updateId);
    setError("");
    try {
      const res = await fetchWithTimeout(
        `/api/projects/${project.id}/updates/${updateId}`,
        {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ content: editingUpdateContent.trim() }),
        },
        45_000,
      );
      if (!res.ok) {
        await handleWriteFailure(res, t.updateFailed);
        return;
      }
      const body = (await res.json()) as { project: OneFileProject };
      syncProjectState(body.project);
      cancelEditProgress();
      toast.success("进展已更新。");
    } catch {
      setError(t.updateFailed);
      toast.error(t.updateFailed);
    } finally {
      setSavingUpdateId("");
    }
  }

  async function removeProgress(updateId: string) {
    if (!project || !isOwner || !updateId || deletingUpdateId) return;
    if (typeof window !== "undefined" && !window.confirm("确认删除这条进展？")) return;
    setDeletingUpdateId(updateId);
    setError("");
    try {
      const res = await fetchWithTimeout(`/api/projects/${project.id}/updates/${updateId}`, { method: "DELETE" }, 45_000);
      if (!res.ok) {
        await handleWriteFailure(res, t.updateFailed);
        return;
      }
      const body = (await res.json()) as { project: OneFileProject };
      syncProjectState(body.project);
      if (editingUpdateId === updateId) {
        cancelEditProgress();
      }
      toast.success("进展已删除。");
    } catch {
      setError(t.updateFailed);
      toast.error(t.updateFailed);
    } finally {
      setDeletingUpdateId("");
    }
  }

  function openProjectEditorFromMenu() {
    setShowMoreMenu(false);
    setActiveField("summary");
    profileSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderFieldActions(field: EditableField) {
    if (!isOwner) return null;
    const isSaving = savingField === field;
    const showSaved = saveHintField === field && !activeField;

    if (activeField === field) {
      return (
        <div className="draft-field-actions">
          <button type="button" className="draft-field-action" onMouseDown={(event) => event.preventDefault()} onClick={() => cancelFieldEditing(field)}>
            {t.fieldCancel}
          </button>
          <button
            type="button"
            className="draft-field-action is-primary"
            disabled={isSaving}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => void saveEditableField(field)}
          >
            {isSaving ? t.saving : t.fieldSave}
          </button>
        </div>
      );
    }

    return (
      <div className="draft-field-actions">
        {showSaved ? <span className="draft-field-saved">{t.savedHint}</span> : null}
        <button type="button" className="draft-field-action" onClick={() => openFieldEditor(field)}>
          {t.fieldEdit}
        </button>
      </div>
    );
  }

  if (error && !project) {
    return (
      <main className="app-shell app-shell--work min-h-screen px-6 py-7 sm:px-8 sm:py-9">
        <div className="mx-auto max-w-5xl">
          <div className="content-panel p-4">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        </div>
      </main>
    );
  }

  if (!project || !draft) {
    return (
      <main className="app-shell app-shell--work min-h-screen px-6 py-7 sm:px-8 sm:py-9">
        <div className="mx-auto max-w-5xl">
          <div className="content-panel p-4">
            <p className="text-sm content-subtle">{t.loadingProject}</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="app-shell app-shell--work min-h-screen px-6 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="content-surface p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="draft-editor-hero">
              <div className="draft-editor-topline">
                <p className="text-sm font-medium text-[var(--landing-caption)]">{brand}</p>
                <div className="flex flex-wrap gap-2">
                  <Badge className="stage-badge">{project.stage_label || draft.stage || "BUILDING"}</Badge>
                  <Badge className={project.share?.is_public ? "stage-badge" : "border-white/15 bg-white/5 text-[var(--landing-text)]"}>
                    {project.share?.is_public ? t.public : t.private}
                  </Badge>
                </div>
              </div>

              {isOwner && activeField === "title" ? (
                <div className="draft-hero-editor">
                  <Input
                    autoFocus
                    className="editor-field-input text-2xl font-semibold sm:text-3xl"
                    value={draft.title}
                    onChange={(event) => updateDraftField("title", event.target.value)}
                    onKeyDown={(event) => onFieldKeyDown(event, "title")}
                  />
                  {renderFieldActions("title")}
                </div>
              ) : isOwner ? (
                <div className="draft-hero-display">
                  <button type="button" className="draft-title-trigger" onClick={() => openFieldEditor("title")}>
                    <h1 className="text-2xl font-semibold text-[var(--landing-title)] sm:text-3xl">{draft.title || t.projectTitlePlaceholder}</h1>
                  </button>
                  {renderFieldActions("title")}
                </div>
              ) : (
                <h1 className="text-2xl font-semibold text-[var(--landing-title)] sm:text-3xl">{draft.title || t.projectTitlePlaceholder}</h1>
              )}

              {isOwner && activeField === "summary" ? (
                <div className="draft-hero-editor">
                  <Textarea
                    autoFocus
                    rows={4}
                    className="editor-field-input min-h-[110px]"
                    value={draft.summary}
                    onChange={(event) => updateDraftField("summary", event.target.value)}
                    onKeyDown={(event) => onFieldKeyDown(event, "summary", { allowMultiline: true })}
                  />
                  {renderFieldActions("summary")}
                </div>
              ) : isOwner ? (
                <div className="draft-hero-display">
                  <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("summary")}>
                    <p className="text-sm content-subtle">{draft.summary || t.noSummary}</p>
                  </button>
                  {renderFieldActions("summary")}
                </div>
              ) : (
                <p className="text-sm content-subtle">{draft.summary || t.noSummary}</p>
              )}
            </div>

            <div className="detail-header-nav self-start">
              <Button variant="ghost" className="detail-header-link" onClick={() => router.push("/library")}>
                {t.backLibrary}
              </Button>
              <Button
                variant="ghost"
                className="detail-header-link"
                onClick={() => router.push(`/card/${project.id}?from=edit&return=${encodeURIComponent(`/projects/${project.id}`)}`)}
              >
                {t.openShare}
              </Button>
              {isOwner ? (
                <div className="detail-owner-menu" ref={moreMenuRef}>
                  <Button
                    type="button"
                    variant="ghost"
                    className="detail-header-link detail-header-icon"
                    onClick={() => setShowMoreMenu((prev) => !prev)}
                    aria-label={t.manageMenu}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                  {showMoreMenu ? (
                    <div className="detail-owner-menu-panel">
                      <button type="button" className="detail-owner-menu-item" onClick={openProjectEditorFromMenu}>
                        {t.editProject}
                      </button>
                      <button type="button" className="detail-owner-menu-item" onClick={() => void toggleShareVisibility()} disabled={savingShare}>
                        {savingShare ? t.saving : project.share?.is_public ? t.makePrivate : t.makePublic}
                      </button>
                      <button type="button" className="detail-owner-menu-item danger" onClick={() => void deleteProject()} disabled={deleting}>
                        {deleting ? t.deleting : t.deleteProject}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {error ? (
          <section className="content-panel p-4">
            <p className="text-sm text-destructive">{error}</p>
          </section>
        ) : null}

        <section ref={profileSectionRef} className="content-panel space-y-4 p-5 sm:p-6">
          <h2 className="content-section-title">{t.profileTitle}</h2>
          <div className="detail-edit-groups">
            <section className="detail-edit-group">
              <div className="detail-edit-group-head">
                <h3 className="detail-edit-group-title">{t.expressionTitle}</h3>
              </div>
              <div className="detail-expression-flow">
                <article className={`detail-expression-item ${activeField === "problemStatement" ? "is-active" : ""}`}>
                  <div className="detail-expression-head">
                    <p className="detail-expression-label">{t.fieldProblem}</p>
                    {renderFieldActions("problemStatement")}
                  </div>
                  {isOwner && activeField === "problemStatement" ? (
                    <Textarea
                      autoFocus
                      className="editor-field-input detail-expression-input min-h-[120px]"
                      value={draft.problemStatement}
                      onChange={(event) => updateDraftField("problemStatement", event.target.value)}
                      onKeyDown={(event) => onFieldKeyDown(event, "problemStatement", { allowMultiline: true })}
                    />
                  ) : isOwner ? (
                    <button type="button" className="detail-expression-trigger" onClick={() => openFieldEditor("problemStatement")}>
                      <p className="detail-expression-value">{draft.problemStatement || t.fieldEmpty}</p>
                    </button>
                  ) : (
                    <p className="detail-expression-value">{draft.problemStatement || t.fieldEmpty}</p>
                  )}
                </article>

                <article className={`detail-expression-item ${activeField === "solutionApproach" ? "is-active" : ""}`}>
                  <div className="detail-expression-head">
                    <p className="detail-expression-label">{t.fieldSolution}</p>
                    {renderFieldActions("solutionApproach")}
                  </div>
                  {isOwner && activeField === "solutionApproach" ? (
                    <Textarea
                      autoFocus
                      className="editor-field-input detail-expression-input min-h-[120px]"
                      value={draft.solutionApproach}
                      onChange={(event) => updateDraftField("solutionApproach", event.target.value)}
                      onKeyDown={(event) => onFieldKeyDown(event, "solutionApproach", { allowMultiline: true })}
                    />
                  ) : isOwner ? (
                    <button type="button" className="detail-expression-trigger" onClick={() => openFieldEditor("solutionApproach")}>
                      <p className="detail-expression-value">{draft.solutionApproach || t.fieldEmpty}</p>
                    </button>
                  ) : (
                    <p className="detail-expression-value">{draft.solutionApproach || t.fieldEmpty}</p>
                  )}
                </article>

                <article className={`detail-expression-item ${activeField === "useCases" ? "is-active" : ""}`}>
                  <div className="detail-expression-head">
                    <p className="detail-expression-label">{t.fieldUseCases}</p>
                    {renderFieldActions("useCases")}
                  </div>
                  {isOwner && activeField === "useCases" ? (
                    <Textarea
                      autoFocus
                      className="editor-field-input detail-expression-input min-h-[120px]"
                      value={draft.useCases}
                      onChange={(event) => updateDraftField("useCases", event.target.value)}
                      onKeyDown={(event) => onFieldKeyDown(event, "useCases", { allowMultiline: true })}
                    />
                  ) : isOwner ? (
                    <button type="button" className="detail-expression-trigger" onClick={() => openFieldEditor("useCases")}>
                      <p className="detail-expression-value">{draft.useCases || t.fieldEmpty}</p>
                    </button>
                  ) : (
                    <p className="detail-expression-value">{draft.useCases || t.fieldEmpty}</p>
                  )}
                </article>
              </div>
            </section>

            <section className="detail-edit-group">
              <div className="detail-edit-group-head">
                <h3 className="detail-edit-group-title">{t.businessTitle}</h3>
              </div>
              <p className="detail-edit-group-hint">{t.businessHint}</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <article className={`draft-display-block draft-inline-editing ${activeField === "modelDesc" ? "is-active" : ""}`}>
              <div className="draft-block-head">
                <p className="draft-block-label">{t.fieldModel}</p>
                {renderFieldActions("modelDesc")}
              </div>
              {isOwner && activeField === "modelDesc" ? (
                <Textarea
                  autoFocus
                  className="editor-field-input min-h-[120px]"
                  value={draft.modelDesc}
                  onChange={(event) => updateDraftField("modelDesc", event.target.value)}
                  onKeyDown={(event) => onFieldKeyDown(event, "modelDesc", { allowMultiline: true })}
                />
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("modelDesc")}>
                  <p className="draft-block-value">{draft.modelDesc || t.fieldEmpty}</p>
                </button>
              ) : (
                <p className="draft-block-value">{draft.modelDesc || t.fieldEmpty}</p>
              )}
            </article>

            <article className={`draft-display-block draft-inline-editing ${activeField === "users" ? "is-active" : ""}`}>
              <div className="draft-block-head">
                <p className="draft-block-label">{t.fieldUsers}</p>
                {renderFieldActions("users")}
              </div>
              {isOwner && activeField === "users" ? (
                <Input
                  autoFocus
                  className="editor-field-input"
                  value={draft.users}
                  onChange={(event) => updateDraftField("users", event.target.value)}
                  onKeyDown={(event) => onFieldKeyDown(event, "users")}
                />
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("users")}>
                  <p className="draft-block-value">{draft.users || t.fieldEmpty}</p>
                </button>
              ) : (
                <p className="draft-block-value">{draft.users || t.fieldEmpty}</p>
              )}
            </article>

            <article className={`draft-display-block draft-inline-editing ${activeField === "formType" ? "is-active" : ""}`}>
              <div className="draft-block-head">
                <p className="draft-block-label">{t.fieldFormType}</p>
                {renderFieldActions("formType")}
              </div>
              {isOwner && activeField === "formType" ? (
                <select
                  autoFocus
                  className="field-select h-10 w-full rounded-lg px-3 text-sm"
                  value={draft.formType}
                  onChange={(event) => updateDraftField("formType", event.target.value)}
                  onKeyDown={(event) => onFieldKeyDown(event, "formType")}
                >
                  {FORM_TYPE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("formType")}>
                  <p className="draft-block-value">{findOptionLabel(FORM_TYPE_OPTIONS, draft.formType)}</p>
                </button>
              ) : (
                <p className="draft-block-value">{project.form_type_label || findOptionLabel(FORM_TYPE_OPTIONS, draft.formType)}</p>
              )}
            </article>

            <article className={`draft-display-block draft-inline-editing ${activeField === "businessModelType" ? "is-active" : ""}`}>
              <div className="draft-block-head">
                <p className="draft-block-label">{t.fieldBusinessModel}</p>
                {renderFieldActions("businessModelType")}
              </div>
              {isOwner && activeField === "businessModelType" ? (
                <select
                  autoFocus
                  className="field-select h-10 w-full rounded-lg px-3 text-sm"
                  value={draft.businessModelType}
                  onChange={(event) => updateDraftField("businessModelType", event.target.value)}
                  onKeyDown={(event) => onFieldKeyDown(event, "businessModelType")}
                >
                  {BUSINESS_MODEL_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("businessModelType")}>
                  <p className="draft-block-value">{findOptionLabel(BUSINESS_MODEL_OPTIONS, draft.businessModelType)}</p>
                </button>
              ) : (
                <p className="draft-block-value">
                  {project.business_model_type_label || findOptionLabel(BUSINESS_MODEL_OPTIONS, draft.businessModelType)}
                </p>
              )}
            </article>

            <article className={`draft-display-block draft-inline-editing ${activeField === "modelType" ? "is-active" : ""}`}>
              <div className="draft-block-head">
                <p className="draft-block-label">{t.fieldModelType}</p>
                {renderFieldActions("modelType")}
              </div>
              {isOwner && activeField === "modelType" ? (
                <select
                  autoFocus
                  className="field-select h-10 w-full rounded-lg px-3 text-sm"
                  value={draft.modelType}
                  onChange={(event) => updateDraftField("modelType", event.target.value)}
                  onKeyDown={(event) => onFieldKeyDown(event, "modelType")}
                >
                  {MODEL_TYPE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("modelType")}>
                  <p className="draft-block-value">{findOptionLabel(MODEL_TYPE_OPTIONS, draft.modelType)}</p>
                </button>
              ) : (
                <p className="draft-block-value">{project.model_type_label || findOptionLabel(MODEL_TYPE_OPTIONS, draft.modelType)}</p>
              )}
            </article>
              </div>
            </section>

            <section className="detail-edit-group">
              <div className="detail-edit-group-head">
                <h3 className="detail-edit-group-title">{t.progressInfoTitle}</h3>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <article className={`draft-display-block draft-inline-editing ${activeField === "stage" ? "is-active" : ""}`}>
              <div className="draft-block-head">
                <p className="draft-block-label">{t.fieldStage}</p>
                {renderFieldActions("stage")}
              </div>
              {isOwner && activeField === "stage" ? (
                <select
                  autoFocus
                  className="field-select h-10 w-full rounded-lg px-3 text-sm"
                  value={draft.stage}
                  onChange={(event) => updateDraftField("stage", event.target.value)}
                  onKeyDown={(event) => onFieldKeyDown(event, "stage")}
                >
                  {STAGE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("stage")}>
                  <p className="draft-block-value">{findOptionLabel(STAGE_OPTIONS, draft.stage)}</p>
                </button>
              ) : (
                <p className="draft-block-value">{project.stage_label || findOptionLabel(STAGE_OPTIONS, draft.stage)}</p>
              )}
            </article>
              </div>
            </section>
          </div>
          {savingField ? <p className="text-xs content-caption">{t.saving}</p> : null}
        </section>

        <section className="content-panel space-y-4 p-5 sm:p-6">
          <div className="flex items-center justify-between gap-2">
            <h2 className="content-section-title">{t.timelineTitle}</h2>
            {isOwner ? (
              <Button type="button" variant="ghost" className="action-secondary-btn h-9 px-3" onClick={() => setShowProgressComposer(true)}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                {t.addProgress}
              </Button>
            ) : null}
          </div>

          {timelineItems.length === 0 ? <p className="text-sm content-subtle">{t.noUpdates}</p> : null}
          <div className="detail-progress-feed">
            {timelineItems.map((item, idx) => (
              <article key={item.id || `${idx}-${item.created_at || ""}`} className="detail-progress-item">
                <div className="detail-progress-rail" aria-hidden="true">
                  <span className="detail-progress-dot" />
                  {idx !== timelineItems.length - 1 ? <span className="detail-progress-line" /> : null}
                </div>
                <div className="detail-progress-body">
                  <div className="flex items-center justify-between gap-3">
                    <p className="detail-progress-time">{formatTimelineTime(item.created_at || "")}</p>
                    {isOwner && item.id ? (
                      <div className="detail-progress-actions">
                      <button
                        type="button"
                        className="text-xs content-caption transition-colors hover:text-[var(--landing-brand)]"
                        onClick={() => startEditProgress(item.id || "", item.content || "")}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="text-xs text-destructive/90 transition-colors hover:text-destructive"
                        disabled={deletingUpdateId === item.id}
                        onClick={() => void removeProgress(item.id || "")}
                      >
                        {deletingUpdateId === item.id ? "删除中..." : "删除"}
                      </button>
                      </div>
                    ) : null}
                  </div>
                  {editingUpdateId === item.id ? (
                    <div className="mt-2 space-y-2">
                      <Textarea
                        rows={3}
                        className="editor-field-input"
                        value={editingUpdateContent}
                        onChange={(event) => setEditingUpdateContent(event.target.value)}
                      />
                      <div className="flex items-center justify-end gap-2">
                        <Button type="button" variant="ghost" className="action-secondary-btn h-8 px-3" onClick={cancelEditProgress}>
                          取消
                        </Button>
                        <Button
                          type="button"
                          className="action-primary-btn h-8 px-3"
                          disabled={!editingUpdateContent.trim() || savingUpdateId === item.id}
                          onClick={() => void submitEditProgress(item.id || "")}
                        >
                          {savingUpdateId === item.id ? "保存中..." : "保存"}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="detail-progress-content">{item.content || t.noUpdates}</p>
                  )}
                </div>
              </article>
            ))}
          </div>
          {warning ? <p className="text-sm text-amber-600">{warning}</p> : null}
        </section>
      </div>

      {showProgressComposer && isOwner ? (
        <div className="detail-progress-modal-backdrop">
          <div className="detail-progress-modal">
            <h3 className="text-base font-semibold text-[var(--landing-title)]">{t.addProgress}</h3>
            <Textarea
              autoFocus
              rows={4}
              className="editor-field-input"
              placeholder={t.updatePlaceholder}
              value={progressDraft}
              onChange={(event) => setProgressDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  setShowProgressComposer(false);
                  return;
                }
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void submitProgress();
                }
              }}
            />
            <div className="flex items-center justify-end gap-2">
              <Button type="button" variant="ghost" className="action-secondary-btn h-9 px-4" onClick={() => setShowProgressComposer(false)}>
                {t.cancel}
              </Button>
              <Button type="button" className="action-primary-btn h-9 px-4" onClick={() => void submitProgress()} disabled={savingProgress || !progressDraft.trim()}>
                {savingProgress ? t.updating : t.submitUpdate}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
