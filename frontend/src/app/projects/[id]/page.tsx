"use client";

import { FormEvent, useEffect, useState } from "react";
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

export default function ProjectDetailPage() {
  const t = copyZh.detail;
  const router = useRouter();
  const routeParams = useParams<{ id: string }>();

  const projectId = String(routeParams.id || "");
  const [authUserId, setAuthUserId] = useState("");
  const [authReady, setAuthReady] = useState(false);

  const [project, setProject] = useState<OneFileProject | null>(null);
  const [updateText, setUpdateText] = useState("");
  const [savingUpdate, setSavingUpdate] = useState(false);
  const [savingShare, setSavingShare] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editSummary, setEditSummary] = useState("");

  useEffect(() => {
    (async () => {
      const meRes = await fetch("/api/auth/me", { cache: "no-store" });
      if (meRes.ok) {
        const meBody = (await meRes.json()) as AuthMeResponse;
        setAuthUserId(meBody.user?.id || "");
      }
      setAuthReady(true);
    })();
  }, []);

  const isOwner = Boolean(project && authUserId && project.owner_user_id === authUserId);

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
      setProject(body.project);
      setEditTitle(body.project.title || "");
      setEditSummary(body.project.summary || "");
    })();
  }, [projectId, authReady, t.loadFailed]);

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

  async function submitUpdate(e: FormEvent) {
    e.preventDefault();
    if (!project || !isOwner) return;

    setSavingUpdate(true);
    setWarning("");
    setError("");

    const res = await fetch(`/api/projects/${project.id}/update`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ update_text: updateText }),
    });

    if (!res.ok) {
      await handleWriteFailure(res, t.updateFailed);
      setSavingUpdate(false);
      return;
    }

    const body = (await res.json()) as MutationResponse;
    setProject(body.project);
    setUpdateText("");
    if (body.used_fallback) {
      const warningMessage = body.warning || copyZh.create.fallbackWarning;
      setWarning(warningMessage);
      toast.warning(warningMessage);
    }
    setSavingUpdate(false);
  }

  async function toggleShare() {
    if (!project || !isOwner) return;
    setSavingShare(true);
    setError("");

    const res = await fetch(`/api/projects/${project.id}/share`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ is_public: !project.share?.is_public }),
    });

    if (res.ok) {
      const body = (await res.json()) as { project: OneFileProject };
      setProject(body.project);
    } else {
      await handleWriteFailure(res, t.shareToggleFailed);
    }

    setSavingShare(false);
  }

  async function submitAdvancedEdit(e: FormEvent) {
    e.preventDefault();
    if (!project || !isOwner) return;
    setSavingEdit(true);
    setError("");

    const res = await fetch(`/api/projects/${project.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: editTitle, summary: editSummary }),
    });

    if (res.ok) {
      const body = (await res.json()) as { project: OneFileProject };
      setProject(body.project);
    } else {
      await handleWriteFailure(res, t.editFailed);
    }

    setSavingEdit(false);
  }

  async function deleteProject() {
    if (!project || !isOwner || deleting) return;
    if (typeof window !== "undefined" && !window.confirm(t.deleteConfirm)) return;
    setDeleting(true);
    setError("");

    const res = await fetch(`/api/projects/${project.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      await handleWriteFailure(res, t.deleteFailed);
      setDeleting(false);
      return;
    }

    router.push("/library");
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

  if (!project) {
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
        <header className="onefile-surface flex flex-wrap items-center justify-between gap-3 p-5 sm:p-6">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--landing-title)]">{project.title}</h1>
            <p className="text-sm onefile-subtle">{project.summary || t.noSummary}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" className="landing-secondary-btn" onClick={() => router.push("/library")}>
              {t.backLibrary}
            </Button>
            <Button variant="ghost" className="landing-secondary-btn" onClick={() => router.push(`/share/${project.id}`)}>
              {t.openShare}
            </Button>
          </div>
        </header>

        {error ? (
          <section className="onefile-panel p-4">
            <p className="text-sm text-destructive">{error}</p>
          </section>
        ) : null}

        {!isOwner ? (
          <section className="onefile-panel p-4">
            <p className="text-sm onefile-subtle">{t.ownerOnlyHint}</p>
          </section>
        ) : null}

        <section className="onefile-panel space-y-3 p-5 sm:p-6">
          <h2 className="onefile-section-title">{t.stateTitle}</h2>
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge className="onefile-stage-badge">{project.stage_label || project.stage || "MVP"}</Badge>
              <Badge variant="secondary" className="bg-white/80 text-[var(--landing-text)]">
                {project.form_type_label || project.form_type || "SaaS"}
              </Badge>
              <Badge variant="secondary" className="bg-white/80 text-[var(--landing-text)]">
                {project.model_type_label || project.model_type || "B2B"}
              </Badge>
              <Badge className={project.share?.is_public ? "onefile-stage-badge" : "bg-white/80 text-[var(--landing-text)]"}>
                {project.share?.is_public ? t.public : t.private}
              </Badge>
            </div>
            <p className="onefile-subtle">
              {t.nextAction}: <span className="text-[var(--landing-title)]">{project.next_action?.text || t.noAction}</span>
            </p>
            <p className="onefile-subtle">
              {t.latestUpdate}: <span className="text-[var(--landing-title)]">{project.latest_update || t.noUpdates}</span>
            </p>
          </div>
        </section>

        <section className="onefile-panel space-y-3 p-5 sm:p-6">
          <h2 className="onefile-section-title">项目正文</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-sm font-medium text-[var(--landing-title)]">问题</p>
              <p className="mt-1 text-sm onefile-subtle">{project.problem_statement || "-"}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--landing-title)]">方案</p>
              <p className="mt-1 text-sm onefile-subtle">{project.solution_approach || "-"}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--landing-title)]">使用场景</p>
              <p className="mt-1 text-sm onefile-subtle">{project.use_cases || "-"}</p>
            </div>
          </div>
        </section>

        {isOwner ? (
          <section className="onefile-panel space-y-4 p-5 sm:p-6">
            <h2 className="onefile-section-title">{t.updateTitle}</h2>
            <div>
              <form onSubmit={submitUpdate} className="space-y-3">
                <Textarea
                  placeholder={t.updatePlaceholder}
                  rows={5}
                  value={updateText}
                  onChange={(e) => setUpdateText(e.target.value)}
                  required
                  className="onefile-input min-h-[7.5rem]"
                />
                <div className="flex gap-2">
                  <Button type="submit" className="landing-cta-btn" disabled={savingUpdate}>
                    {savingUpdate ? t.updating : t.submitUpdate}
                  </Button>
                  <Button type="button" variant="ghost" className="landing-secondary-btn" onClick={toggleShare} disabled={savingShare}>
                    {savingShare ? t.saving : project.share?.is_public ? t.makePrivate : t.makePublic}
                  </Button>
                </div>
                {warning ? <p className="text-sm text-amber-600">{warning}</p> : null}
              </form>
            </div>
            <div className="border-t border-slate-200/70 pt-4">
              <h3 className="mb-3 text-sm font-medium text-[var(--landing-title)]">{t.advancedTitle}</h3>
              <form onSubmit={submitAdvancedEdit} className="space-y-3">
                <Input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  placeholder={t.projectTitlePlaceholder}
                  required
                  className="onefile-input"
                />
                <Textarea
                  value={editSummary}
                  onChange={(e) => setEditSummary(e.target.value)}
                  rows={3}
                  placeholder={t.summaryPlaceholder}
                  className="onefile-input"
                />
                <Button type="submit" variant="ghost" className="landing-secondary-btn" disabled={savingEdit}>
                  {savingEdit ? t.saving : t.saveAdvanced}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="landing-secondary-btn text-destructive hover:text-destructive"
                  onClick={deleteProject}
                  disabled={deleting}
                >
                  {deleting ? t.deleting : t.deleteProject}
                </Button>
              </form>
            </div>
          </section>
        ) : null}

        <section className="onefile-panel space-y-3 p-5 sm:p-6">
          <h2 className="onefile-section-title">{t.timelineTitle}</h2>
          {(project.updates || []).length === 0 ? <p className="text-sm onefile-subtle">{t.noUpdates}</p> : null}
          <div className="space-y-3">
            {(project.updates || []).map((item, idx) => (
              <div key={item.id || `${idx}-${item.created_at || ""}`} className="rounded-xl border border-slate-200/75 bg-white/86 p-3 text-sm">
                <p className="font-medium text-[var(--landing-title)]">{item.kind || t.timelineKindFallback}</p>
                <p className="mt-1 onefile-subtle">{item.content || ""}</p>
                <p className="mt-2 text-xs onefile-caption">
                  {item.created_at || ""} · {t.evidence} {Number(item.evidence_score || 0).toFixed(2)} · {t.alignment}{" "}
                  {Number(item.action_alignment || 0).toFixed(2)}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
