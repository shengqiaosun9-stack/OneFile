"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { buildLoginRedirectPath, currentPathWithQuery } from "@/lib/auth-redirect";
import { copyZh } from "@/lib/copy-zh";
import { resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import type { AuthMeResponse, CtaResponse, OneFileProject, ShareResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default function SharePage() {
  const t = copyZh.share;
  const router = useRouter();
  const routeParams = useParams<{ id: string }>();
  const projectId = String(routeParams.id || "");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reloadTick, setReloadTick] = useState(0);

  const [project, setProject] = useState<OneFileProject | null>(null);
  const [accessGranted, setAccessGranted] = useState(false);
  const [message, setMessage] = useState("");
  const [canRetry, setCanRetry] = useState(false);
  const [posterGenerating, setPosterGenerating] = useState(false);
  const posterRef = useRef<HTMLDivElement | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const meRes = await fetchWithTimeout("/api/auth/me", { cache: "no-store" }, 10_000);
        if (!meRes.ok) return;
        const me = (await meRes.json()) as AuthMeResponse;
        setIsAuthenticated(Boolean(me.user?.email));
      } catch {
        // Keep share page readable in guest mode.
      }
    })();
  }, [reloadTick]);

  useEffect(() => {
    if (!projectId) return;

    (async () => {
      setLoading(true);
      setProject(null);
      setMessage("");
      setCanRetry(false);
      try {
        const res = await fetchWithTimeout(`/api/share/${projectId}`, { cache: "no-store" }, 12_000);
        if (!res.ok) {
          const failure = await resolveApiError(res, t.loadFailed);
          setMessage(failure.message);
          setCanRetry(true);
          toast.error(failure.message);
          return;
        }
        const body = (await res.json()) as ShareResponse;
        setProject(body.project);
        setAccessGranted(body.access_granted);
        if (!body.access_granted) {
          setMessage(t.privateMessage);
        }
      } catch {
        setMessage(t.loadTimeout);
        setCanRetry(true);
        toast.error(t.loadTimeout);
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, reloadTick, t.loadFailed, t.loadTimeout, t.privateMessage]);

  async function handleCta() {
    if (!projectId) return;
    try {
      const res = await fetchWithTimeout(
        `/api/share/${projectId}/cta`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ cta: "start_project", source: "share_page_cta", ref: "share_page" }),
        },
        10_000,
      );

        if (!res.ok) {
          const failure = await resolveApiError(res, t.ctaFailed);
          if (failure.status === 401) {
            toast.error(failure.message);
            router.push(buildLoginRedirectPath(currentPathWithQuery(`/share/${projectId}`), failure.code || "unauthorized"));
            return;
          }
          setMessage(failure.message);
          setCanRetry(false);
          toast.error(failure.message);
          return;
        }

      const body = (await res.json()) as CtaResponse;
      const next = new URLSearchParams();
      next.set("cta_token", body.cta_token);
      const target = `/projects/new?${next.toString()}`;
      if (isAuthenticated) {
        router.push(target);
        return;
      }
      router.push(`/?next=${encodeURIComponent(target)}`);
    } catch {
      setMessage(t.ctaTimeout);
      setCanRetry(false);
      toast.error(t.ctaTimeout);
    }
  }

  async function handleGeneratePoster() {
    if (!project || !projectId) return;
    if (!project.share?.is_public) {
      toast.error(t.posterOnlyPublic);
      return;
    }
    if (!posterRef.current) return;

    setPosterGenerating(true);
    try {
      const [{ toPng }, QRCode] = await Promise.all([import("html-to-image"), import("qrcode")]);
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const shareUrl = `${origin}/share/${projectId}`;
      const nextQr = await QRCode.toDataURL(shareUrl, {
        width: 220,
        margin: 1,
        color: { dark: "#1E293B", light: "#FFFFFF" },
      });
      setQrDataUrl(nextQr);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const png = await toPng(posterRef.current, {
        cacheBust: true,
        pixelRatio: 2,
        backgroundColor: "#F5F8FB",
      });
      const link = document.createElement("a");
      link.download = `${project.title || "onefile"}-poster.png`;
      link.href = png;
      link.click();
      toast.success(t.posterDone);
    } catch {
      toast.error(t.posterFailed);
    } finally {
      setPosterGenerating(false);
    }
  }

  async function handleCopyLink() {
    if (!projectId || typeof window === "undefined") return;
    const link = `${window.location.origin}/share/${projectId}`;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(link);
      } else {
        const input = document.createElement("textarea");
        input.value = link;
        input.setAttribute("readonly", "true");
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        document.body.removeChild(input);
      }
      toast.success(t.copyLinkDone);
    } catch {
      toast.error(t.copyLinkFailed);
    }
  }

  return (
    <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="onefile-surface flex flex-wrap items-center justify-between gap-3 p-5 sm:p-6">
          <div>
            <p className="text-sm onefile-caption">{t.title}</p>
            <h1 className="text-2xl font-semibold text-[var(--landing-title)]">{project?.title || "项目分享"}</h1>
          </div>
          <Button
            variant="ghost"
            className="landing-secondary-btn h-10 px-4"
            onClick={() => router.push("/library")}
          >
            {t.backLibrary}
          </Button>
        </header>

        {loading ? (
          <div className="onefile-panel p-4">
            <p className="text-sm onefile-subtle">{t.loading}</p>
          </div>
        ) : null}
        {message ? (
          <div className="onefile-panel space-y-3 p-4">
            <p className="text-sm onefile-subtle">{message}</p>
            {canRetry ? (
              <Button
                type="button"
                variant="ghost"
                className="landing-secondary-btn h-9 px-4"
                onClick={() => setReloadTick((prev) => prev + 1)}
              >
                {t.retryLoad}
              </Button>
            ) : null}
          </div>
        ) : null}

        {project && accessGranted ? (
          <>
            <section className="onefile-panel space-y-4 p-5 text-sm sm:p-6">
              <p className="text-base onefile-subtle">{project.summary || t.noSummary}</p>
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <p className="font-medium text-[var(--landing-title)]">{t.problem}</p>
                  <p className="mt-1 onefile-subtle">{project.problem_statement || "-"}</p>
                </div>
                <div>
                  <p className="font-medium text-[var(--landing-title)]">{t.solution}</p>
                  <p className="mt-1 onefile-subtle">{project.solution_approach || "-"}</p>
                </div>
                <div>
                  <p className="font-medium text-[var(--landing-title)]">{t.useCases}</p>
                  <p className="mt-1 onefile-subtle">{project.use_cases || "-"}</p>
                </div>
              </div>
            </section>

            <section className="onefile-surface flex flex-col items-center gap-3 p-6 text-center">
              <p className="onefile-subtle">
                {isAuthenticated ? "如果你也在做类似项目，可以直接开始创建你的档案。" : "登录后可创建并管理你自己的项目档案。"}
              </p>
              <Button className="landing-cta-btn h-10 px-5" onClick={handleCta}>
                {t.cta}
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="landing-secondary-btn h-10 px-5"
                onClick={handleCopyLink}
              >
                {t.copyLinkButton}
              </Button>
              {project.share?.is_public ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="landing-secondary-btn h-10 px-5"
                  onClick={handleGeneratePoster}
                  disabled={posterGenerating}
                >
                  {posterGenerating ? t.posterGenerating : t.posterButton}
                </Button>
              ) : (
                <p className="text-xs onefile-caption">{t.posterOnlyPublic}</p>
              )}
              <p className="text-xs onefile-caption">{t.wechatFallbackHint}</p>
            </section>

            <div className="onefile-poster-render">
              <div ref={posterRef} className="onefile-poster-shell">
                <div className="onefile-poster-card">
                  <p className="onefile-poster-brand">OneFile · 一人档</p>
                  <h2 className="onefile-poster-title">{project.title || "主体名称"}</h2>
                  <p className="onefile-poster-summary">{project.summary || t.noSummary}</p>
                  <div className="onefile-poster-grid">
                    <div>
                      <p className="onefile-poster-label">目标用户</p>
                      <p className="onefile-poster-value">{project.users || "-"}</p>
                    </div>
                    <div>
                      <p className="onefile-poster-label">商业模式</p>
                      <p className="onefile-poster-value">{project.model_type_label || project.model_type || "-"}</p>
                    </div>
                    <div>
                      <p className="onefile-poster-label">发展阶段</p>
                      <p className="onefile-poster-value">{project.stage_label || project.stage || "-"}</p>
                    </div>
                    <div>
                      <p className="onefile-poster-label">最近更新</p>
                      <p className="onefile-poster-value">{project.latest_update || "-"}</p>
                    </div>
                  </div>
                  <div className="onefile-poster-qr-row">
                    {qrDataUrl ? (
                      <Image
                        src={qrDataUrl}
                        alt="share qr"
                        width={220}
                        height={220}
                        unoptimized
                        className="onefile-poster-qr"
                      />
                    ) : (
                      <div className="onefile-poster-qr" />
                    )}
                    <div>
                      <p className="onefile-poster-cta">扫码查看完整档案 / 创建你的档案</p>
                      <p className="onefile-poster-foot">{(project.updated_at || "").slice(0, 10)}</p>
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
