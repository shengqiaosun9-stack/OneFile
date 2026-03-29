"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileTextIcon, PenLineIcon, RefreshCwIcon, Share2Icon, SparklesIcon, WaypointsIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { copyZh } from "@/lib/copy-zh";
import { getApiErrorMessage, resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { saveEmail } from "@/lib/session";
import type { AuthResponse, AuthStartResponse, ListResponse, OneFileProject } from "@/lib/types";

type ShowcaseBlueprint = {
  key: string;
  title: string;
  audience: string;
  updatedText: string;
  summary: string;
  preferredProjectIds: string[];
};

type ShowcaseCard = ShowcaseBlueprint & {
  projectId?: string;
};

const SHOWCASE_BLUEPRINTS: ShowcaseBlueprint[] = [
  {
    key: "solotax",
    title: "SoloTax Studio",
    audience: "SaaS创始人",
    updatedText: "3.27",
    summary: "自动生成税务整理建议，降低一人团队财务决策成本。",
    preferredProjectIds: ["p_demo_001", "p_demo_002"],
  },
  {
    key: "writer",
    title: "云笔工作室",
    audience: "自由职业者",
    updatedText: "3.25",
    summary: "围绕内容产出和交付节奏，沉淀可复用的写作工作流。",
    preferredProjectIds: ["p_demo_002", "p_demo_001"],
  },
  {
    key: "opc-dash",
    title: "星云增长实验室",
    audience: "独立开发者",
    updatedText: "3.20",
    summary: "统一追踪获客、转化和版本节奏，形成可分享的增长视图。",
    preferredProjectIds: ["p_demo_003", "p_demo_001", "p_demo_002"],
  },
];

function resolveShowcaseCards(publicProjects: OneFileProject[]): ShowcaseCard[] {
  const byId = new Map(publicProjects.map((item) => [item.id, item]));
  const used = new Set<string>();
  return SHOWCASE_BLUEPRINTS.map((card, index) => {
    let selected = card.preferredProjectIds.map((id) => byId.get(id)).find(Boolean);
    if (!selected && publicProjects.length > 0) {
      selected = publicProjects.find((item) => !used.has(item.id)) || publicProjects[index % publicProjects.length];
    }
    if (selected) used.add(selected.id);
    return {
      ...card,
      projectId: selected?.id,
    };
  });
}

export default function LandingPage() {
  const t = copyZh.landing;
  const router = useRouter();
  const mainRef = useRef<HTMLElement | null>(null);

  const [loginOpen, setLoginOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [authStep, setAuthStep] = useState<"email" | "code">("email");
  const [debugCode, setDebugCode] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showcaseCards, setShowcaseCards] = useState<ShowcaseCard[]>(() => resolveShowcaseCards([]));
  const [cardsLoading, setCardsLoading] = useState(true);
  const [activeShowcaseIndex, setActiveShowcaseIndex] = useState(0);
  const [nextPathRaw, setNextPathRaw] = useState("");
  const [reasonRaw, setReasonRaw] = useState("");
  const showcaseTrackRef = useRef<HTMLDivElement | null>(null);
  const showcaseCardRefs = useRef<Array<HTMLElement | null>>([]);
  const nextPath = useMemo(() => {
    const candidate = nextPathRaw.trim();
    if (!candidate) return "/library";
    if (!candidate.startsWith("/") || candidate.startsWith("//")) return "/library";
    return candidate;
  }, [nextPathRaw]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = new URLSearchParams(window.location.search);
    setNextPathRaw(query.get("next") || "");
    setReasonRaw((query.get("reason") || "").trim());
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/projects", { cache: "no-store" });
        if (!res.ok) {
          setCardsLoading(false);
          return;
        }
        const body = (await res.json()) as ListResponse;
        const publics = (body.projects || []).filter((item) => Boolean(item.share?.is_public));
        setShowcaseCards(resolveShowcaseCards(publics));
      } catch {
        setShowcaseCards(resolveShowcaseCards([]));
      } finally {
        setCardsLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (nextPathRaw) {
      setLoginOpen(true);
    }
  }, [nextPathRaw]);

  useEffect(() => {
    if (!reasonRaw) return;
    const message = getApiErrorMessage({ error: reasonRaw, message: "" }, t.loginFailed);
    setError(message);
    setLoginOpen(true);
    toast.error(message);
  }, [reasonRaw, t.loginFailed]);

  useEffect(() => {
    if (authStep !== "code" || resendCooldown <= 0) return;
    const timer = window.setInterval(() => {
      setResendCooldown((current) => (current <= 1 ? 0 : current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [authStep, resendCooldown]);

  const getShowcaseItems = useCallback(() => showcaseCardRefs.current.filter(Boolean) as HTMLElement[], []);

  const syncShowcaseIndex = useCallback(() => {
    const track = showcaseTrackRef.current;
    const items = getShowcaseItems();
    if (!track || items.length === 0) return;
    const viewportCenter = track.scrollLeft + track.clientWidth / 2;
    let nearest = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    items.forEach((item, index) => {
      const center = item.offsetLeft + item.offsetWidth / 2;
      const distance = Math.abs(center - viewportCenter);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = index;
      }
    });
    setActiveShowcaseIndex(nearest);
  }, [getShowcaseItems]);

  const scrollToShowcaseIndex = useCallback(
    (index: number) => {
      const items = getShowcaseItems();
      if (!items.length) return;
      const safeIndex = Math.max(0, Math.min(index, items.length - 1));
      const target = items[safeIndex];
      target.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
      setActiveShowcaseIndex(safeIndex);
    },
    [getShowcaseItems]
  );

  const onShowcaseStep = useCallback(
    (direction: -1 | 1) => {
      const items = getShowcaseItems();
      if (!items.length) return;
      scrollToShowcaseIndex(activeShowcaseIndex + direction);
    },
    [activeShowcaseIndex, getShowcaseItems, scrollToShowcaseIndex]
  );

  useEffect(() => {
    const track = showcaseTrackRef.current;
    if (!track) return;
    let rafId = 0;
    const onScroll = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(syncShowcaseIndex);
    };
    onScroll();
    track.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(rafId);
      track.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [syncShowcaseIndex]);

  useEffect(() => {
    const nodes = document.querySelectorAll<HTMLElement>("[data-reveal]");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.18, rootMargin: "0px 0px -10% 0px" }
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const main = mainRef.current;
    if (!main) return;

    let rafId = 0;
    const onScroll = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        main.style.setProperty("--landing-parallax", `${Math.round(window.scrollY * 0.7)}px`);
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  function resetLoginFlow() {
    setCode("");
    setChallengeId("");
    setAuthStep("email");
    setDebugCode("");
    setResendCooldown(0);
    setError("");
    setLoading(false);
  }

  async function requestLoginCode(targetEmail: string): Promise<boolean> {
    const res = await fetchWithTimeout(
      "/api/auth/login/start",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: targetEmail }),
      },
      10_000,
    );
    if (!res.ok) {
      const failure = await resolveApiError(res, t.loginFailed);
      setError(failure.message);
      toast.error(failure.message);
      return false;
    }
    const body = (await res.json()) as AuthStartResponse;
    setChallengeId(body.challenge_id || "");
    setDebugCode(body.debug_code || "");
    setAuthStep("code");
    setResendCooldown(Math.max(10, Math.min(120, Number(body.expires_in_seconds || 60))));
    return true;
  }

  async function onResendCode() {
    if (loading || resendCooldown > 0 || !email.trim()) return;
    setLoading(true);
    setError("");
    try {
      const ok = await requestLoginCode(email);
      if (ok) {
        toast.success(t.codeResentHint);
      }
    } catch {
      setError(t.loginTimeout);
      toast.error(t.loginTimeout);
    } finally {
      setLoading(false);
    }
  }

  async function onLogin(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");

    if (authStep === "email") {
      try {
        const ok = await requestLoginCode(email);
        if (ok) {
          toast.success(t.codeSentHint);
        }
      } catch {
        setError(t.loginTimeout);
        toast.error(t.loginTimeout);
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await fetchWithTimeout(
        "/api/auth/login/verify",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email, challenge_id: challengeId, code }),
        },
        10_000,
      );
      if (!res.ok) {
        const failure = await resolveApiError(res, t.loginFailed);
        setError(failure.message);
        toast.error(failure.message);
        return;
      }

      const body = (await res.json()) as AuthResponse;
      saveEmail(body.user.email);
      setLoginOpen(false);
      resetLoginFlow();
      router.push(nextPath);
    } catch {
      setError(t.loginTimeout);
      toast.error(t.loginTimeout);
    } finally {
      setLoading(false);
    }
  }

  const guestLibraryHref = useMemo(() => "/library?mode=guest", []);

  return (
    <main ref={mainRef} className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto w-full max-w-6xl space-y-14 sm:space-y-16 lg:space-y-[72px]">
        <header className="landing-nav">
          <div className="flex items-center gap-2">
            <p className="landing-brand">OneFile</p>
            <span className="landing-brand-sub">· 一人档</span>
          </div>
          <div className="flex items-center gap-2">
            <a href="#landing-showcase" className="landing-mini-link">
              浏览案例
            </a>
            <Button variant="ghost" className="landing-secondary-btn h-10 px-5" onClick={() => setLoginOpen(true)}>
              开始使用 →
            </Button>
          </div>
        </header>

        <section className="landing-hero" data-reveal>
          <div>
            <h1 className="landing-hero-title">把想法变成可演化的OPC项目资产</h1>
            <p className="landing-hero-subtitle">一人公司 / 早期创业者专属，把零散灵感沉淀成可展示、可持续更新的项目档案。</p>
            <p className="landing-proof">已服务 50+ OPC 项目</p>
          </div>
          <aside className="landing-hero-panel landing-surface">
            <p className="landing-panel-title">从一个邮箱开始，进入你的项目空间</p>
            <p className="landing-panel-text">统一创建、更新、分享，形成可演化的项目记录闭环。</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button className="landing-cta-btn h-11 px-6" onClick={() => setLoginOpen(true)}>
                开始使用 →
              </Button>
              <Button variant="ghost" className="landing-secondary-btn h-11 px-5" onClick={() => router.push(guestLibraryHref)}>
                浏览公开项目
              </Button>
            </div>
          </aside>
        </section>

        <section data-reveal>
          <h2 className="landing-section-title">核心价值</h2>
          <div className="landing-value-grid">
            <article className="landing-card">
              <FileTextIcon className="landing-icon" />
              <h3 className="landing-card-title">结构化表达</h3>
              <p className="landing-card-text">OPC 标准 Schema 拆解，让项目目标、用户、商业模式一眼可读。</p>
            </article>
            <article className="landing-card">
              <RefreshCwIcon className="landing-icon" />
              <h3 className="landing-card-title">持续演化</h3>
              <p className="landing-card-text">更新自动沉淀到时间线，项目变化路径可追溯、可回放。</p>
            </article>
            <article className="landing-card">
              <Share2Icon className="landing-icon" />
              <h3 className="landing-card-title">传播回流</h3>
              <p className="landing-card-text">分享即形成增长闭环，把外部访问转化为新的项目创建。</p>
            </article>
          </div>
        </section>

        <section id="landing-showcase" data-reveal>
          <div className="flex items-center justify-between gap-3">
            <h2 className="landing-section-title">示例项目</h2>
            <div className="hidden items-center gap-2 md:flex">
              <Button
                type="button"
                variant="ghost"
                className="landing-showcase-nav-btn"
                onClick={() => onShowcaseStep(-1)}
                disabled={cardsLoading}
                aria-label="查看上一个案例"
              >
                ←
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="landing-showcase-nav-btn"
                onClick={() => onShowcaseStep(1)}
                disabled={cardsLoading}
                aria-label="查看下一个案例"
              >
                →
              </Button>
            </div>
          </div>
          <div className="landing-showcase-track-wrap">
            <div
              ref={showcaseTrackRef}
              className="landing-showcase-track"
              tabIndex={0}
              aria-label="示例项目案例带"
              onKeyDown={(event) => {
                if (event.key === "ArrowRight") {
                  event.preventDefault();
                  onShowcaseStep(1);
                } else if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  onShowcaseStep(-1);
                }
              }}
            >
            {cardsLoading
              ? SHOWCASE_BLUEPRINTS.map((item) => (
                  <article key={`skeleton-${item.key}`} className="landing-card landing-showcase-item skeleton-card">
                    <div className="skeleton-line h-5 w-2/3" />
                    <div className="skeleton-line h-4 w-1/2" />
                    <div className="skeleton-line h-4 w-full" />
                    <div className="skeleton-line h-4 w-5/6" />
                    <div className="skeleton-line h-9 w-full" />
                  </article>
                ))
              : showcaseCards.map((card, index) => {
                  const detailHref = card.projectId ? `/projects/${card.projectId}` : guestLibraryHref;
                  const shareHref = card.projectId ? `/share/${card.projectId}` : guestLibraryHref;
                  return (
                    <article
                      key={card.key}
                      className="landing-card landing-showcase-card landing-showcase-item"
                      ref={(node) => {
                        showcaseCardRefs.current[index] = node;
                      }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="landing-card-title">{card.title}</h3>
                        <span className="landing-update-tag">最近更新 · {card.updatedText}</span>
                      </div>
                      <p className="landing-card-text">用户：{card.audience}</p>
                      <p className="landing-card-text">{card.summary}</p>
                      <div className="mt-4 flex items-center gap-4 text-sm">
                        <Link className="landing-link-sweep" href={detailHref}>
                          查看档案 →
                        </Link>
                        <Link className="landing-link-sweep" href={shareHref}>
                          分享页 →
                        </Link>
                      </div>
                    </article>
                  );
                })}
            </div>
            <div className="landing-showcase-edge left" aria-hidden />
            <div className="landing-showcase-edge right" aria-hidden />
          </div>
          <div className="landing-showcase-dots" aria-label="案例位置指示">
            {(cardsLoading ? SHOWCASE_BLUEPRINTS : showcaseCards).map((item, index) => (
              <button
                key={`dot-${item.key}`}
                type="button"
                className={`landing-showcase-dot ${index === activeShowcaseIndex ? "is-active" : ""}`}
                aria-label={`查看第 ${index + 1} 个案例`}
                onClick={() => scrollToShowcaseIndex(index)}
                disabled={cardsLoading}
              />
            ))}
          </div>
        </section>

        <section data-reveal>
          <h2 className="landing-section-title">三步流程</h2>
          <div className="landing-flow-shell">
            <article className="landing-flow-item">
              <PenLineIcon className="landing-icon" />
              <h3 className="landing-card-title">输入想法</h3>
              <p className="landing-card-text">自然语言描述项目方向和当前阶段。</p>
            </article>
            <WaypointsIcon className="landing-flow-arrow" />
            <article className="landing-flow-item">
              <SparklesIcon className="landing-icon" />
              <h3 className="landing-card-title">AI结构化</h3>
              <p className="landing-card-text">自动生成标准 OPC 档案并给出下一步建议。</p>
            </article>
            <WaypointsIcon className="landing-flow-arrow" />
            <article className="landing-flow-item">
              <Share2Icon className="landing-icon" />
              <h3 className="landing-card-title">分享迭代</h3>
              <p className="landing-card-text">对外分享并持续更新，形成可验证的增长路径。</p>
            </article>
          </div>
        </section>

        <section className="landing-bottom-cta landing-surface" data-reveal>
          <p className="landing-bottom-title">开启你的 OPC 标准化项目记录</p>
          <Button className="landing-cta-btn h-11 px-7" onClick={() => setLoginOpen(true)}>
            开始使用 →
          </Button>
        </section>

        <footer className="landing-footer">
          <p>© 2026 OneFile · 一人档</p>
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            <a href="mailto:hello@onefile.app" className="landing-mini-link">
              商务合作：hello@onefile.app
            </a>
            <span className="text-slate-300">|</span>
            <a href="/privacy" className="landing-mini-link">
              隐私政策
            </a>
            <span className="text-slate-300">|</span>
            <a href="/terms" className="landing-mini-link">
              用户协议
            </a>
          </div>
        </footer>
      </div>

      <Dialog
        open={loginOpen}
        onOpenChange={(next) => {
          setLoginOpen(next);
          if (!next) {
            resetLoginFlow();
          }
        }}
      >
        <DialogContent className="landing-login-modal max-w-md border-0 bg-white p-6 shadow-xl">
          <DialogHeader>
            <DialogTitle className="text-xl text-slate-800">开始使用 OneFile</DialogTitle>
            <DialogDescription className="text-slate-500">输入邮箱，立即进入你的项目库并创建第一份档案。</DialogDescription>
          </DialogHeader>
          <form onSubmit={onLogin} className="space-y-3">
            <Input
              type="email"
              placeholder={t.emailPlaceholder}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="h-11 border-slate-200 bg-white text-slate-800 focus-visible:ring-[3px] focus-visible:ring-blue-500/30"
            />
            {authStep === "code" ? (
              <Input
                type="text"
                inputMode="numeric"
                placeholder={t.codePlaceholder}
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                required
                className="h-11 border-slate-200 bg-white text-slate-800 focus-visible:ring-[3px] focus-visible:ring-blue-500/30"
              />
            ) : null}
            <Button type="submit" className="landing-cta-btn h-11 w-full" disabled={loading}>
              {loading ? (authStep === "email" ? t.sendingCode : t.verifyingCode) : authStep === "email" ? t.sendCode : t.verifyCode}
            </Button>
            {authStep === "code" ? <p className="text-xs text-slate-500">{t.codeSentHint}</p> : null}
            {authStep === "code" ? (
              <p className="text-xs text-slate-500">
                {resendCooldown > 0 ? t.resendIn(resendCooldown) : t.resendReady}
              </p>
            ) : null}
            {authStep === "code" && debugCode ? (
              <p className="text-xs text-slate-500">
                {t.debugCodeHint}
                <span className="ml-1 font-semibold text-slate-700">{debugCode}</span>
              </p>
            ) : null}
            {authStep === "code" ? (
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  className="landing-secondary-btn h-10 w-full"
                  onClick={onResendCode}
                  disabled={loading || resendCooldown > 0}
                >
                  {t.resendCode}
                </Button>
                <Button type="button" variant="ghost" className="landing-secondary-btn h-10 w-full" onClick={resetLoginFlow}>
                  {t.switchEmail}
                </Button>
              </div>
            ) : null}
            {error ? <p className="text-sm text-red-500">{error}</p> : null}
          </form>
          <Button variant="ghost" className="landing-secondary-btn h-10 w-full" onClick={() => router.push(guestLibraryHref)}>
            先浏览公开项目
          </Button>
        </DialogContent>
      </Dialog>
    </main>
  );
}
