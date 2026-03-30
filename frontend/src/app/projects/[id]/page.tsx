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
import type { AuthMeResponse, MutationResponse, OneFileProject } from "@/lib/types";

export const dynamic = "force-dynamic";

type EditableField = "title" | "summary" | "modelDesc" | "users" | "stage";

type DetailDraft = {
  title: string;
  summary: string;
  modelDesc: string;
  users: string;
  stage: string;
};

function projectToDraft(project: OneFileProject): DetailDraft {
  return {
    title: project.title || "",
    summary: project.summary || "",
    modelDesc: project.model_desc || "",
    users: project.users || "",
    stage: project.stage || "BUILDING",
  };
}

function formatTimelineTime(createdAt: string): string {
  if (!createdAt) return "刚刚";
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "刚刚";

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
  const router = useRouter();
  const routeParams = useParams<{ id: string }>();
  const projectId = String(routeParams.id || "");

  const moreMenuRef = useRef<HTMLDivElement | null>(null);

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

  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");

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
        const meRes = await fetch("/api/auth/me", { cache: "no-store" });
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
      const res = await fetch(`/api/projects/${projectId}`, { cache: "no-store" });
      if (!res.ok) {
        const failure = await resolveApiError(res, t.loadFailed);
        setError(failure.message);
        toast.error(failure.message);
        return;
      }
      const body = (await res.json()) as { project: OneFileProject };
      syncProjectState(body.project);
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
      if (options.allowMultiline && event.shiftKey) return;
      event.preventDefault();
      (event.currentTarget as HTMLElement).blur();
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
    if (field === "modelDesc") payload = { model_desc: draft.modelDesc };
    if (field === "users") payload = { users: draft.users };
    if (field === "stage") payload = { stage: draft.stage };

    setSavingField(field);
    setError("");
    const res = await fetch(`/api/projects/${project.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      await handleWriteFailure(res, t.editFailed);
      setSavingField("");
      return;
    }

    const body = (await res.json()) as { project: OneFileProject };
    syncProjectState(body.project);
    setSavingField("");
    setActiveField("");
  }

  async function toggleShareVisibility() {
    if (!project || !isOwner || savingShare) return;
    setSavingShare(true);
    setError("");

    const res = await fetch(`/api/projects/${project.id}/share`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ is_public: !project.share?.is_public }),
    });

    if (!res.ok) {
      await handleWriteFailure(res, t.shareToggleFailed);
      setSavingShare(false);
      return;
    }
    const body = (await res.json()) as { project: OneFileProject };
    syncProjectState(body.project);
    setSavingShare(false);
    setShowMoreMenu(false);
  }

  async function deleteProject() {
    if (!project || !isOwner || deleting) return;
    if (typeof window !== "undefined" && !window.confirm(t.deleteConfirm)) return;
    setDeleting(true);
    setError("");

    const res = await fetch(`/api/projects/${project.id}`, { method: "DELETE" });
    if (!res.ok) {
      await handleWriteFailure(res, t.deleteFailed);
      setDeleting(false);
      return;
    }
    router.push("/library");
  }

  async function submitProgress() {
    if (!project || !isOwner || !progressDraft.trim()) return;
    setSavingProgress(true);
    setError("");
    setWarning("");

    const res = await fetch(`/api/projects/${project.id}/update`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ update_text: progressDraft.trim() }),
    });

    if (!res.ok) {
      await handleWriteFailure(res, t.updateFailed);
      setSavingProgress(false);
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
    setSavingProgress(false);
  }

  if (error && !project) {
    return (
      <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
        <div className="mx-auto max-w-5xl">
          <div className="onefile-panel p-4">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        </div>
      </main>
    );
  }

  if (!project || !draft) {
    return (
      <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
        <div className="mx-auto max-w-5xl">
          <div className="onefile-panel p-4">
            <p className="text-sm onefile-subtle">{t.loadingProject}</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="onefile-surface p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-2">
              {isOwner && activeField === "title" ? (
                <Input
                  autoFocus
                  className="onefile-draft-input text-2xl font-semibold"
                  value={draft.title}
                  onChange={(event) => updateDraftField("title", event.target.value)}
                  onBlur={() => void saveEditableField("title")}
                  onKeyDown={(event) => onFieldKeyDown(event, "title")}
                />
              ) : isOwner ? (
                <button type="button" className="draft-title-trigger" onClick={() => openFieldEditor("title")}>
                  <h1 className="text-2xl font-semibold text-[var(--landing-title)]">{draft.title || t.projectTitlePlaceholder}</h1>
                </button>
              ) : (
                <h1 className="text-2xl font-semibold text-[var(--landing-title)]">{draft.title || t.projectTitlePlaceholder}</h1>
              )}

              {isOwner && activeField === "summary" ? (
                <Textarea
                  autoFocus
                  rows={3}
                  className="onefile-draft-input min-h-[80px]"
                  value={draft.summary}
                  onChange={(event) => updateDraftField("summary", event.target.value)}
                  onBlur={() => void saveEditableField("summary")}
                  onKeyDown={(event) => onFieldKeyDown(event, "summary", { allowMultiline: true })}
                />
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("summary")}>
                  <p className="text-sm onefile-subtle">{draft.summary || t.noSummary}</p>
                </button>
              ) : (
                <p className="text-sm onefile-subtle">{draft.summary || t.noSummary}</p>
              )}

              <div className="flex flex-wrap gap-2 pt-1">
                <Badge className="onefile-stage-badge">{project.stage_label || draft.stage || "BUILDING"}</Badge>
                <Badge className={project.share?.is_public ? "onefile-stage-badge" : "bg-white/80 text-[var(--landing-text)]"}>
                  {project.share?.is_public ? t.public : t.private}
                </Badge>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button variant="ghost" className="landing-secondary-btn" onClick={() => router.push("/library")}>
                {t.backLibrary}
              </Button>
              <Button variant="ghost" className="landing-secondary-btn" onClick={() => router.push(`/share/${project.id}`)}>
                {t.openShare}
              </Button>
              {isOwner ? (
                <div className="detail-owner-menu" ref={moreMenuRef}>
                  <Button
                    type="button"
                    variant="ghost"
                    className="landing-secondary-btn h-10 w-10 px-0"
                    onClick={() => setShowMoreMenu((prev) => !prev)}
                    aria-label={t.manageMenu}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                  {showMoreMenu ? (
                    <div className="detail-owner-menu-panel">
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
          <section className="onefile-panel p-4">
            <p className="text-sm text-destructive">{error}</p>
          </section>
        ) : null}

        <section className="onefile-panel space-y-4 p-5 sm:p-6">
          <h2 className="onefile-section-title">{t.profileTitle}</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <article className={`draft-display-block draft-inline-editing ${activeField === "summary" ? "is-active" : ""}`}>
              <p className="draft-block-label">{t.fieldSummary}</p>
              {isOwner && activeField === "summary" ? (
                <Textarea
                  autoFocus
                  className="onefile-draft-input min-h-[120px]"
                  value={draft.summary}
                  onChange={(event) => updateDraftField("summary", event.target.value)}
                  onBlur={() => void saveEditableField("summary")}
                  onKeyDown={(event) => onFieldKeyDown(event, "summary", { allowMultiline: true })}
                />
              ) : isOwner ? (
                <button type="button" className="draft-content-trigger" onClick={() => openFieldEditor("summary")}>
                  <p className="draft-block-value">{draft.summary || t.fieldEmpty}</p>
                </button>
              ) : (
                <p className="draft-block-value">{draft.summary || t.fieldEmpty}</p>
              )}
            </article>

            <article className={`draft-display-block draft-inline-editing ${activeField === "modelDesc" ? "is-active" : ""}`}>
              <p className="draft-block-label">{t.fieldModel}</p>
              {isOwner && activeField === "modelDesc" ? (
                <Textarea
                  autoFocus
                  className="onefile-draft-input min-h-[120px]"
                  value={draft.modelDesc}
                  onChange={(event) => updateDraftField("modelDesc", event.target.value)}
                  onBlur={() => void saveEditableField("modelDesc")}
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
              <p className="draft-block-label">{t.fieldUsers}</p>
              {isOwner && activeField === "users" ? (
                <Input
                  autoFocus
                  className="onefile-draft-input"
                  value={draft.users}
                  onChange={(event) => updateDraftField("users", event.target.value)}
                  onBlur={() => void saveEditableField("users")}
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
          </div>
          {savingField ? <p className="text-xs onefile-caption">{t.saving}</p> : null}
        </section>

        <section className="onefile-panel space-y-4 p-5 sm:p-6">
          <div className="flex items-center justify-between gap-2">
            <h2 className="onefile-section-title">{t.timelineTitle}</h2>
            {isOwner ? (
              <Button type="button" variant="ghost" className="landing-secondary-btn h-9 px-3" onClick={() => setShowProgressComposer(true)}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                {t.addProgress}
              </Button>
            ) : null}
          </div>

          {timelineItems.length === 0 ? <p className="text-sm onefile-subtle">{t.noUpdates}</p> : null}
          <div className="detail-progress-feed">
            {timelineItems.map((item, idx) => (
              <article key={item.id || `${idx}-${item.created_at || ""}`} className="detail-progress-item">
                <p className="detail-progress-time">{formatTimelineTime(item.created_at || "")}</p>
                <p className="detail-progress-content">{item.content || t.noUpdates}</p>
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
              className="onefile-draft-input"
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
              <Button type="button" variant="ghost" className="landing-secondary-btn h-9 px-4" onClick={() => setShowProgressComposer(false)}>
                {t.cancel}
              </Button>
              <Button type="button" className="landing-cta-btn h-9 px-4" onClick={() => void submitProgress()} disabled={savingProgress || !progressDraft.trim()}>
                {savingProgress ? t.updating : t.submitUpdate}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
