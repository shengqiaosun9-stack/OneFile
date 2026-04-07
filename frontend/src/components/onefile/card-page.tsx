"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buildLoginRedirectPath, currentPathWithQuery } from "@/lib/auth-redirect";
import { copyZh } from "@/lib/copy-zh";
import { resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { clearLastGeneratedCardId, loadLastGeneratedCardId } from "@/lib/last-generated-card";
import type { AuthMeResponse, CtaResponse, OneFileProject, ShareResponse } from "@/lib/types";

export function CardPage({ projectId }: { projectId: string }) {
  const t = copyZh.share;
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authUserId, setAuthUserId] = useState("");
  const [loading, setLoading] = useState(true);
  const [project, setProject] = useState<OneFileProject | null>(null);
  const [message, setMessage] = useState("");
  const [canRetry, setCanRetry] = useState(false);
  const [posterGenerating, setPosterGenerating] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [ownershipHintVisible, setOwnershipHintVisible] = useState(false);
  const posterRef = useRef<HTMLDivElement | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState("");

  const isTemporary = project?.entity_type === "temporary_card" || project?.claim_status === "unclaimed";
  const isOwner = Boolean(project && authUserId && project.owner_user_id === authUserId);
  const source = searchParams.get("from");
  const returnPathRaw = (searchParams.get("return") || "").trim();
  const returnPath = returnPathRaw.startsWith("/") && !returnPathRaw.startsWith("//") ? returnPathRaw : "";
  const fromLibrary = source === "library";
  const fromLandingExample = source === "landing-example";
  const fromEdit = source === "edit";
  const fromCreateDraft = source === "create-draft";
  const backLabel = returnPath
    ? fromEdit
      ? t.backEdit
      : fromCreateDraft
        ? t.backDraft
        : t.backHome
    : fromLibrary
      ? t.backLibrary
      : t.backHome;
  const backTarget = returnPath || (fromLibrary ? "/library" : fromLandingExample ? "/" : "/");

  useEffect(() => {
    (async () => {
      try {
        const meRes = await fetchWithTimeout("/api/auth/me", { cache: "no-store" }, 12_000);
        if (!meRes.ok) return;
        const me = (await meRes.json()) as AuthMeResponse;
        setIsAuthenticated(Boolean(me.user?.email));
        setAuthUserId(me.user?.id || "");
      } catch {
        // guest path is valid
      }
    })();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    (async () => {
      setLoading(true);
      setMessage("");
      setCanRetry(false);
      try {
        const res = await fetchWithTimeout(`/api/cards/${projectId}`, { cache: "no-store" }, 20_000);
        if (!res.ok) {
          const failure = await resolveApiError(res, t.loadFailed);
          setMessage(failure.message);
          setCanRetry(true);
          return;
        }
        const body = (await res.json()) as ShareResponse;
        setProject(body.project);
      } catch {
        setMessage(t.loadTimeout);
        setCanRetry(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, t.loadFailed, t.loadTimeout]);

  useEffect(() => {
    if (!projectId) return;
    setOwnershipHintVisible(loadLastGeneratedCardId() === projectId);
  }, [projectId]);

  async function handleCopyLink() {
    if (typeof window === "undefined") return;
    const link = `${window.location.origin}/card/${projectId}`;
    try {
      await navigator.clipboard.writeText(link);
      toast.success(t.copyLinkDone);
    } catch {
      toast.error(t.copyLinkFailed);
    }
  }

  async function handleGeneratePoster() {
    if (!project || !project.share?.is_public || !posterRef.current) {
      toast.error(t.posterOnlyPublic);
      return;
    }
    setPosterGenerating(true);
    try {
      const [{ toPng }, QRCode] = await Promise.all([import("html-to-image"), import("qrcode")]);
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const shareUrl = `${origin}/card/${projectId}`;
      const nextQr = await QRCode.toDataURL(shareUrl, {
        width: 220,
        margin: 1,
        color: { dark: "#f8fafc", light: "#111827" },
      });
      setQrDataUrl(nextQr);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const png = await toPng(posterRef.current, {
        cacheBust: true,
        pixelRatio: 2,
        backgroundColor: "#020617",
      });
      const link = document.createElement("a");
      link.download = `${project.title || "onepitch"}-poster.png`;
      link.href = png;
      link.click();
      toast.success(t.posterDone);
    } catch {
      toast.error(t.posterFailed);
    } finally {
      setPosterGenerating(false);
    }
  }

  const handleClaimAndEdit = useCallback(async () => {
    if (claiming) return;
    if (!isAuthenticated) {
      router.push(buildLoginRedirectPath(currentPathWithQuery(`/card/${projectId}?claim=1`), "unauthorized"));
      return;
    }

    setClaiming(true);
    try {
      const res = await fetchWithTimeout(`/api/cards/${projectId}/claim`, { method: "POST" }, 20_000);
      if (!res.ok) {
        const failure = await resolveApiError(res, "认领失败，请稍后重试。");
        toast.error(failure.message);
        return;
      }
      clearLastGeneratedCardId();
      router.push(`/edit/${projectId}`);
    } catch {
      toast.error("认领失败，请稍后重试。");
    } finally {
      setClaiming(false);
    }
  }, [claiming, isAuthenticated, projectId, router]);

  function handleEditAction() {
    if (isOwner) {
      router.push(`/edit/${projectId}`);
      return;
    }
    if (isTemporary) {
      void handleClaimAndEdit();
    }
  }

  useEffect(() => {
    if (!projectId || !isAuthenticated || searchParams.get("claim") !== "1" || claiming) return;
    void handleClaimAndEdit();
  }, [claiming, handleClaimAndEdit, isAuthenticated, projectId, searchParams]);

  async function handleStartOwnCard() {
    try {
      const res = await fetchWithTimeout(
        `/api/share/${projectId}/cta`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ cta: "start_project", source: "card_page_cta", ref: "card_page" }),
        },
        10_000,
      );
      if (!res.ok) {
        const failure = await resolveApiError(res, t.ctaFailed);
        toast.error(failure.message);
        router.push("/");
        return;
      }
      const body = (await res.json()) as CtaResponse;
      const next = new URLSearchParams();
      next.set("mode", "quick");
      next.set("from", "card");
      next.set("cta_token", body.cta_token);
      router.push(`/?${next.toString()}`);
    } catch {
      toast.error(t.ctaTimeout);
      router.push("/?mode=quick&from=card");
    }
  }

  return (
    <main className="app-shell app-shell--public min-h-screen px-5 py-5 sm:px-7 sm:py-7">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="card-topbar">
          <div className="space-y-1">
            <p className="text-sm content-caption">OnePitch · 一眼项目</p>
            <p className="card-topbar-copy">一张可以直接发出去的项目对象。</p>
          </div>
          <div className="card-topbar-actions">
            <Button variant="ghost" className="action-secondary-btn h-10 px-4" onClick={() => router.push(backTarget)}>
              {backLabel}
            </Button>
            {isOwner || isTemporary ? (
              <Button className="action-primary-btn h-10 px-4" onClick={handleEditAction} disabled={claiming}>
                {claiming ? "处理中..." : isOwner ? t.editCard : t.editToClaim}
              </Button>
            ) : null}
          </div>
        </header>

        {loading ? (
          <div className="project-card-surface project-card-surface--loading">
            <p className="text-sm content-subtle">{t.loading}</p>
          </div>
        ) : null}

        {message ? (
          <div className="project-card-surface project-card-surface--loading space-y-3">
            <p className="text-sm content-subtle">{message}</p>
            {canRetry ? (
              <Button variant="ghost" className="action-secondary-btn h-9 px-4" onClick={() => window.location.reload()}>
                {t.retryLoad}
              </Button>
            ) : null}
          </div>
        ) : null}

        {project ? (
          <>
            <section className="project-card-surface project-card-surface--public" data-state={isOwner ? "owner-view" : isTemporary ? "claimed" : "ready"}>
              <div className="project-card-hero">
                <p className="project-card-kicker">Project card surface</p>
                <h1 className="project-card-summary">{project.summary || "项目摘要待补充"}</h1>
                <div className="project-card-title-row">
                  <p className="project-card-title">{project.title || "项目卡"}</p>
                  {project.stage_label ? <Badge className="stage-badge stage-badge--public">{project.stage_label}</Badge> : null}
                </div>
                {ownershipHintVisible && isTemporary ? (
                  <p className="project-card-ownership-hint">{t.ownershipHint}</p>
                ) : null}
              </div>

              <div className="project-card-context-flow">
                <article className="project-card-context-line">
                  <p className="project-card-label">{t.problem}</p>
                  <p className="project-card-value">{project.problem_statement || "-"}</p>
                </article>
                <article className="project-card-context-line">
                  <p className="project-card-label">{t.solution}</p>
                  <p className="project-card-value">{project.solution_approach || "-"}</p>
                </article>
                <article className="project-card-context-line">
                  <p className="project-card-label">目标用户</p>
                  <p className="project-card-value">{project.users || "-"}</p>
                </article>
              </div>

              <div className="project-card-status-flow">
                <article className="project-card-status-line">
                  <p className="project-card-label">当前阶段</p>
                  <p className="project-card-status-copy">{project.stage_label || "待补充"}</p>
                </article>
                <article className="project-card-status-line">
                  <p className="project-card-label">下一步计划</p>
                  <p className="project-card-status-copy">{project.next_action?.text || project.latest_update || "待补充"}</p>
                </article>
              </div>

              <p className="project-card-updated">更新时间：{project.updated_at || "-"}</p>
            </section>

            <section className="action-zone" data-state="share-ready">
              <div className="action-zone-copy">
                <p className="action-zone-kicker">Share-ready</p>
                <p className="action-zone-text">先把它发出去。需要修的时候，再回来认领和编辑。</p>
              </div>
              <div className="action-zone-buttons">
                <Button className="action-primary-btn h-11 min-w-[220px] px-6" onClick={handleCopyLink}>
                  复制项目卡链接
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="action-secondary-btn h-11 min-w-[220px] px-6"
                  onClick={handleGeneratePoster}
                  disabled={posterGenerating || !project.share?.is_public}
                >
                  {posterGenerating ? t.posterGenerating : "生成分享海报"}
                </Button>
              </div>
              <p className="action-zone-footnote">如果微信内打不开，优先发海报或把链接粘贴到系统浏览器。</p>
            </section>

            <section className="content-surface content-surface--quiet flex flex-col items-center gap-3 p-6 text-center">
              <p className="content-subtle">看完这张卡，也可以直接做你自己的。</p>
              <button type="button" className="inline-nav-link" onClick={handleStartOwnCard}>
                {t.cta}
              </button>
              <button
                type="button"
                className="inline-nav-link opacity-80"
                onClick={() => router.push("/projects/new?mode=rich&from=card")}
              >
                {t.ctaRich}
              </button>
            </section>

            <div className="poster-surface-render">
              <div ref={posterRef} className="poster-surface-shell">
                <div className="poster-surface">
                  <p className="poster-surface-brand">OnePitch · 一眼项目</p>
                  <h2 className="poster-surface-summary">{project.summary || "一句话说明待补充"}</h2>
                  <div className="poster-surface-heading-row">
                    <p className="poster-surface-title">{project.title || "主体名称"}</p>
                    <p className="poster-surface-stage">{project.stage_label || "当前状态待补充"}</p>
                  </div>
                  <div className="poster-surface-grid">
                    <div>
                      <p className="poster-surface-label">问题</p>
                      <p className="poster-surface-value">{project.problem_statement || "-"}</p>
                    </div>
                    <div>
                      <p className="poster-surface-label">目标用户</p>
                      <p className="poster-surface-value">{project.users || "-"}</p>
                    </div>
                  </div>
                  <div className="poster-surface-qr-row">
                    {qrDataUrl ? (
                      <Image src={qrDataUrl} alt="card qr" width={220} height={220} unoptimized className="poster-surface-qr" />
                    ) : (
                      <div className="poster-surface-qr" />
                    )}
                    <div>
                      <p className="poster-surface-cta">扫码做一个你自己的项目卡</p>
                      <p className="poster-surface-foot">{project.updated_at?.slice(0, 10) || "-"}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}
