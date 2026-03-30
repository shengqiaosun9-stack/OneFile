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
import type { AuthResponse, AuthStartResponse } from "@/lib/types";

type LandingUsecase = {
  id: string;
  title: string;
  one_liner: string;
  description: string;
  business_model: string;
  target_user: string;
  stage: string;
  recent_update: string;
  key_metric: string;
};

const LANDING_USECASES: LandingUsecase[] = [
  {
    id: "1",
    title: "AutoDeck",
    one_liner: "AI自动生成融资Deck",
    description: "帮助早期创业者快速生成结构化融资材料，从想法到完整Pitch Deck只需几分钟。",
    business_model: "按次收费 + 订阅制",
    target_user: "早期创业者",
    stage: "已上线",
    recent_update: "刚刚 · 模板优化完成，生成成功率提升到92%",
    key_metric: "生成成功率92%",
  },
  {
    id: "2",
    title: "LegalFlow",
    one_liner: "AI自动生成标准合同",
    description: "为中小企业提供低成本、可定制的法律合同生成服务，降低对律师的依赖。",
    business_model: "按合同生成收费",
    target_user: "中小企业",
    stage: "测试中",
    recent_update: "2天前 · 上线合同模板库第一版",
    key_metric: "生成时间小于30秒",
  },
  {
    id: "3",
    title: "FounderOS",
    one_liner: "一人创业操作系统",
    description: "整合项目管理、融资和用户反馈的一体化工具，专为独立创业者设计。",
    business_model: "SaaS订阅",
    target_user: "独立开发者",
    stage: "构思阶段",
    recent_update: "3天前 · 完成产品结构设计",
    key_metric: "暂无",
  },
  {
    id: "4",
    title: "ComputeX",
    one_liner: "AI算力匹配平台",
    description: "连接算力供需双方，动态匹配训练与推理需求，帮助企业降低成本。",
    business_model: "撮合佣金 + 企业订阅",
    target_user: "AI公司",
    stage: "开发中",
    recent_update: "1天前 · 已接入第3家算力供应商",
    key_metric: "成本降低40%",
  },
  {
    id: "5",
    title: "InsightFeed",
    one_liner: "结构化行业研究流",
    description: "通过AI整理碎片信息，输出可直接用于决策的结构化行业洞察。",
    business_model: "订阅制 + 数据服务",
    target_user: "投资人",
    stage: "已上线",
    recent_update: "刚刚 · 日活用户突破500",
    key_metric: "留存率35%",
  },
  {
    id: "6",
    title: "CreatorGraph",
    one_liner: "创作者关系网络图谱",
    description: "帮助品牌和MCN快速找到合适创作者，建立更高效的合作关系。",
    business_model: "撮合佣金",
    target_user: "MCN机构",
    stage: "原型阶段",
    recent_update: "4天前 · 完成关系图谱模型设计",
    key_metric: "暂无",
  },
  {
    id: "7",
    title: "FactoryMind",
    one_liner: "工厂AI质量监控系统",
    description: "通过实时数据分析与预测模型，降低生产过程中的质量波动风险。",
    business_model: "企业SaaS + 定制部署",
    target_user: "制造企业",
    stage: "试点中",
    recent_update: "2天前 · 完成第一家工厂试点部署",
    key_metric: "良率提升15%",
  },
  {
    id: "8",
    title: "FundSignal",
    one_liner: "VC投资信号捕捉工具",
    description: "通过数据分析识别潜在融资机会，帮助投资人提高决策效率。",
    business_model: "订阅制",
    target_user: "投资人",
    stage: "已上线",
    recent_update: "刚刚 · 覆盖项目数量突破200个",
    key_metric: "信号准确率68%",
  },
];

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
  const showcaseCards = LANDING_USECASES;
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
  const canStepPrev = activeShowcaseIndex > 0;
  const canStepNext = activeShowcaseIndex < showcaseCards.length - 1;

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
            <h2 className="landing-section-title">{t.exampleTitle}</h2>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                className="landing-showcase-nav-btn"
                onClick={() => onShowcaseStep(-1)}
                disabled={!canStepPrev}
                aria-label={t.showcasePrevAria}
              >
                ←
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="landing-showcase-nav-btn"
                onClick={() => onShowcaseStep(1)}
                disabled={!canStepNext}
                aria-label={t.showcaseNextAria}
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
              aria-label={t.showcaseTrackAria}
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
              {showcaseCards.map((card, index) => (
                <article
                  key={card.id}
                  className="landing-card landing-showcase-card landing-showcase-item"
                  ref={(node) => {
                    showcaseCardRefs.current[index] = node;
                  }}
                >
                  <Link
                    href={guestLibraryHref}
                    className="landing-showcase-card-link"
                    aria-label={`${t.showcaseOpenAriaPrefix}：${card.title}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="landing-card-title">{card.title}</h3>
                        <p className="landing-card-text mt-1">{card.one_liner}</p>
                      </div>
                      <span className="landing-update-tag">{card.stage}</span>
                    </div>
                    <p className="landing-card-text">{card.description}</p>
                    <div className="landing-showcase-meta">
                      <p className="landing-card-text">
                        <span className="font-medium">目标用户：</span>
                        {card.target_user}
                      </p>
                      <p className="landing-card-text">
                        <span className="font-medium">商业模式：</span>
                        {card.business_model}
                      </p>
                    </div>
                    <p className="landing-card-text">
                      <span className="font-medium">最近进展：</span>
                      {card.recent_update}
                    </p>
                    <p className="landing-card-text">
                      <span className="font-medium">关键指标：</span>
                      {card.key_metric}
                    </p>
                  </Link>
                </article>
              ))}
            </div>
            <div className="landing-showcase-edge left" aria-hidden />
            <div className="landing-showcase-edge right" aria-hidden />
          </div>
          <div className="landing-showcase-dots" aria-label="案例位置指示">
            {showcaseCards.map((item, index) => (
              <button
                key={`dot-${item.id}`}
                type="button"
                className={`landing-showcase-dot ${index === activeShowcaseIndex ? "is-active" : ""}`}
                aria-label={t.showcaseDotAria(index + 1)}
                onClick={() => scrollToShowcaseIndex(index)}
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
