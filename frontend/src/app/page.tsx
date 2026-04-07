"use client";

import { FormEvent, KeyboardEvent, PointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { copyZh } from "@/lib/copy-zh";
import { getApiErrorMessage, resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { saveLastGeneratedCardId } from "@/lib/last-generated-card";
import { createRequestId } from "@/lib/request-id";
import { saveEmail } from "@/lib/session";
import type { AuthResponse, AuthStartResponse, MutationResponse } from "@/lib/types";

type ExampleCard = {
  cardId: string;
  title: string;
  audience: string;
  input: string;
  summary: string;
  scenario: string;
};

type PromptBarState = "idle" | "focused" | "typing" | "submitting" | "failed";

const EXAMPLES: ExampleCard[] = [
  {
    cardId: "7451c54f",
    title: "北极星协作",
    audience: "早期 SaaS 团队",
    input: "帮早期 SaaS 团队把客户反馈、当前验证状态和下一步动作收进一个共享工作区，让潜在客户和投资人能快速判断这个产品现在值不值得继续跟进。",
    summary: "让外部人用几分钟就能判断一个早期 SaaS 项目现在值不值得继续跟进。",
    scenario: "发给投资人或潜在客户，对方会立刻知道你验证到了哪一步。",
  },
  {
    cardId: "9c28454f",
    title: "画境工作室",
    audience: "国风游戏美术团队",
    input: "给国风游戏美术团队做一个 AI 绘画工作台，让制作人不用看长文档也能快速判断这套风格方案是否适合当前项目。",
    summary: "让游戏制作团队先看懂风格方向和合作价值，再决定要不要继续推进合作。",
    scenario: "发给制作人或外包合作方，对方能一眼判断风格和合作切入点。",
  },
  {
    cardId: "c36ea7f2",
    title: "合同快线",
    audience: "中小企业法务负责人",
    input: "做一个帮助中小企业快速生成标准合同初稿的服务，让法务负责人在第一次看到时就知道这套方案能不能缩短签约流程。",
    summary: "让法务负责人快速判断这套合同服务能不能缩短签约流程和沟通成本。",
    scenario: "发给企业法务或创始人，对方会立刻知道适不适合进入试用。",
  },
];

function getCarouselOffset(index: number, activeIndex: number, total: number) {
  let offset = index - activeIndex;
  const midpoint = Math.floor(total / 2);
  if (offset > midpoint) offset -= total;
  if (offset < -midpoint) offset += total;
  return offset;
}

function HeroPoster({
  titleLines,
  subtitle,
  socialProof,
  promptBar,
}: {
  titleLines: readonly [string, string, string];
  subtitle: string;
  socialProof: string;
  promptBar: ReactNode;
}) {
  const title = Array.isArray(titleLines) ? titleLines.join("") : String(titleLines);

  return (
    <section className="landing-reset-hero" data-landing-hero-poster>
      <header className="landing-reset-brandbar">
        <div className="landing-reset-brandlockup">
          <span className="landing-reset-brand">OnePitch</span>
          <span className="landing-reset-brand-sub">· 一眼项目</span>
        </div>
      </header>

      <div className="landing-reset-hero-copy">
        <p className="landing-reset-overline">Shareable project object</p>
        <h1 className="landing-reset-title" suppressHydrationWarning>
          {title}
        </h1>
        <p className="landing-reset-subtitle">{subtitle}</p>
        {promptBar}
        <p className="landing-reset-proof">{socialProof}</p>
      </div>
    </section>
  );
}

function PromptBar({
  value,
  onChange,
  onSubmit,
  onFocus,
  onBlur,
  state,
  loading,
  error,
  hint,
  emptyHint,
  onHintClick,
  inputRef,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onFocus: () => void;
  onBlur: () => void;
  state: PromptBarState;
  loading: boolean;
  error: string;
  hint: string;
  emptyHint: string;
  onHintClick: () => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  placeholder: string;
}) {
  return (
    <form className="landing-prompt-bar" data-prompt-bar data-state={state} onSubmit={onSubmit}>
      <div className="landing-prompt-shell">
        <textarea
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          className="landing-prompt-input"
          maxLength={300}
          rows={3}
          aria-label="项目一句话输入"
        />
        <button type="submit" className="landing-prompt-submit" disabled={loading || !value.trim()}>
          {loading ? "正在生成项目卡..." : "生成项目卡"}
        </button>
      </div>
      <div className="landing-prompt-support">
        <button type="button" className="landing-prompt-hint" onClick={onHintClick}>
          {hint}
        </button>
        <span className="landing-prompt-count">{value.length}/300</span>
      </div>
      {!error && !value.trim() ? <p className="landing-prompt-empty-hint">{emptyHint}</p> : null}
      {error ? <p className="landing-prompt-error">{error}</p> : null}
    </form>
  );
}

function ExampleObjectCard({
  example,
  selected,
  position,
  offset,
  onSelect,
  onGenerate,
}: {
  example: ExampleCard;
  selected: boolean;
  position: "center" | "left" | "right";
  offset: number;
  onSelect: () => void;
  onGenerate: () => void;
}) {
  const preview = !selected;
  return (
    <article
      className="landing-example-object"
      data-showcase-card
      data-state={selected ? "selected" : "rest"}
      data-density={selected ? "full" : "preview"}
      data-position={position}
      style={{ ["--showcase-offset" as string]: String(offset) }}
      onClick={selected ? undefined : onSelect}
      tabIndex={selected ? 0 : -1}
    >
      <div className="landing-example-object-inner">
        <div className="landing-example-copy">
          <p className="landing-example-summary">{example.summary}</p>
          <p className="landing-example-meta">
            {example.title} · 面向 {example.audience}
          </p>
          {!preview ? <p className="landing-example-scenario">{example.scenario}</p> : null}
        </div>
        {!preview ? (
          <div className="landing-example-actions">
            <button
              type="button"
              className="landing-example-primary"
              onClick={(event) => {
                event.stopPropagation();
                onGenerate();
              }}
            >
              用一句话生成我的项目卡
            </button>
            <Link
              href={`/card/${example.cardId}?from=landing-example`}
              className="landing-example-link"
              onClick={(event) => event.stopPropagation()}
            >
              查看项目卡
            </Link>
          </div>
        ) : (
          <p className="landing-example-preview-note">示例预览</p>
        )}
      </div>
    </article>
  );
}

function ShowcaseCarousel({
  title,
  subtitle,
  examples,
  activeIndex,
  onCycle,
  onSelect,
  onGenerate,
  onKeyDown,
  onPointerDown,
  onPointerUp,
}: {
  title: string;
  subtitle: string;
  examples: ExampleCard[];
  activeIndex: number;
  onCycle: (direction: 1 | -1) => void;
  onSelect: (index: number) => void;
  onGenerate: (example: ExampleCard) => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
}) {
  return (
    <section
      className="landing-showcase-carousel"
      aria-label="示例项目轮播区"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
    >
      <div className="landing-showcase-head">
        <div>
          <p className="landing-showcase-kicker">Result showcase</p>
          <h2 className="landing-showcase-title">{title}</h2>
          <p className="landing-showcase-subtitle">{subtitle}</p>
        </div>
        <div className="landing-showcase-controls" aria-label="showcase controls">
          <button type="button" className="landing-showcase-control" onClick={() => onCycle(-1)} aria-label="查看上一个案例">
            ←
          </button>
          <button type="button" className="landing-showcase-control landing-showcase-control--active" onClick={() => onCycle(1)} aria-label="查看下一个案例">
            →
          </button>
        </div>
      </div>
      <div className="landing-showcase-stage">
        {examples.map((example, index) => {
          const offset = getCarouselOffset(index, activeIndex, examples.length);
          const position = offset === 0 ? "center" : offset < 0 ? "left" : "right";
          return (
            <ExampleObjectCard
              key={example.cardId}
              example={example}
              selected={offset === 0}
              position={position}
              offset={offset}
              onSelect={() => onSelect(index)}
              onGenerate={() => onGenerate(example)}
            />
          );
        })}
      </div>
    </section>
  );
}

function NarrativeRail({
  title,
  lead,
  items,
}: {
  title: string;
  lead: string;
  items: readonly { title: string; desc: string }[];
}) {
  return (
    <section className="landing-narrative-rail" data-narrative-rail>
      <div className="landing-narrative-intro">
        <p className="landing-narrative-kicker">Usage framing</p>
        <h2 className="landing-narrative-title">{title}</h2>
        <p className="landing-narrative-lead">{lead}</p>
      </div>
      <div className="landing-narrative-track">
        {items.map((item, index) => (
          <article key={item.title} className="landing-narrative-step">
            <div className="landing-narrative-node">{String(index + 1).padStart(2, "0")}</div>
            <div className="landing-narrative-step-copy">
              <h3 className="landing-narrative-step-title">{item.title}</h3>
              <p className="landing-narrative-step-text">{item.desc}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function LandingPage() {
  const t = copyZh.landing;
  const router = useRouter();
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const dragStartRef = useRef<number | null>(null);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loginOpen, setLoginOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [authStep, setAuthStep] = useState<"email" | "code">("email");
  const [debugCode, setDebugCode] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [nextPathRaw, setNextPathRaw] = useState("");
  const [reasonRaw, setReasonRaw] = useState("");
  const [ctaToken, setCtaToken] = useState("");
  const [promptFocused, setPromptFocused] = useState(false);
  const [activeExampleIndex, setActiveExampleIndex] = useState(0);

  const nextPath = useMemo(() => {
    const candidate = nextPathRaw.trim();
    if (!candidate) return "/library";
    if (!candidate.startsWith("/") || candidate.startsWith("//")) return "/library";
    return candidate;
  }, [nextPathRaw]);

  const activeExample = EXAMPLES[activeExampleIndex] ?? EXAMPLES[0];
  const promptState: PromptBarState = loading ? "submitting" : promptFocused ? "focused" : input.trim() ? "typing" : error ? "failed" : "idle";

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = new URLSearchParams(window.location.search);
    setNextPathRaw(query.get("next") || "");
    setReasonRaw((query.get("reason") || "").trim());
    setCtaToken(query.get("cta_token") || "");
  }, []);

  useEffect(() => {
    if (nextPathRaw) setLoginOpen(true);
  }, [nextPathRaw]);

  useEffect(() => {
    if (!reasonRaw) return;
    const message = getApiErrorMessage({ error: reasonRaw, message: "" }, t.loginFailed);
    setAuthError(message);
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

  function fillExample(example: ExampleCard) {
    setInput(example.input);
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => composerRef.current?.focus(), 220);
  }

  function selectExample(index: number) {
    setActiveExampleIndex((index + EXAMPLES.length) % EXAMPLES.length);
  }

  function cycleExample(direction: 1 | -1) {
    setActiveExampleIndex((current) => (current + direction + EXAMPLES.length) % EXAMPLES.length);
  }

  function handleShowcaseKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      cycleExample(-1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      cycleExample(1);
    }
  }

  function handleShowcasePointerDown(event: PointerEvent<HTMLElement>) {
    dragStartRef.current = event.clientX;
  }

  function handleShowcasePointerUp(event: PointerEvent<HTMLElement>) {
    if (dragStartRef.current === null) return;
    const delta = event.clientX - dragStartRef.current;
    dragStartRef.current = null;
    if (Math.abs(delta) < 40) return;
    cycleExample(delta < 0 ? 1 : -1);
  }

  async function handleGenerate(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetchWithTimeout(
        "/api/cards/generate",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            raw_input: input.trim(),
            optional_title: "",
            cta_token: ctaToken,
            request_id: createRequestId("card"),
          }),
        },
        60_000,
      );
      if (!res.ok) {
        const failure = await resolveApiError(res, "生成失败，请稍后重试。");
        setError(failure.message);
        toast.error(failure.message);
        return;
      }
      const body = (await res.json()) as MutationResponse;
      if (body.project?.id) {
        saveLastGeneratedCardId(body.project.id);
        router.push(`/card/${body.project.id}`);
        return;
      }
      setError("生成结果异常，请稍后重试。");
    } catch {
      setError("服务暂时不可用，请稍后重试。");
      toast.error("服务暂时不可用，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  function resetLoginFlow() {
    setCode("");
    setChallengeId("");
    setAuthStep("email");
    setDebugCode("");
    setResendCooldown(0);
    setAuthError("");
    setAuthLoading(false);
  }

  async function requestLoginCode(targetEmail: string): Promise<boolean> {
    const res = await fetchWithTimeout(
      "/api/auth/login/start",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: targetEmail }),
      },
      30_000,
    );
    if (!res.ok) {
      const failure = await resolveApiError(res, t.loginFailed);
      setAuthError(failure.message);
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

  async function handleLoginSubmit(event: FormEvent) {
    event.preventDefault();
    if (authLoading) return;
    setAuthLoading(true);
    setAuthError("");
    try {
      if (authStep === "email") {
        const ok = await requestLoginCode(email);
        if (ok) toast.success(t.codeSentHint);
        return;
      }

      const res = await fetchWithTimeout(
        "/api/auth/login/verify",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email, challenge_id: challengeId, code }),
        },
        30_000,
      );
      if (!res.ok) {
        const failure = await resolveApiError(res, t.loginFailed);
        setAuthError(failure.message);
        toast.error(failure.message);
        return;
      }
      const body = (await res.json()) as AuthResponse;
      saveEmail(body.user?.email || email);
      setLoginOpen(false);
      resetLoginFlow();
      router.push(nextPath);
    } catch {
      setAuthError(t.loginTimeout);
      toast.error(t.loginTimeout);
    } finally {
      setAuthLoading(false);
    }
  }

  async function onResendCode() {
    if (authLoading || resendCooldown > 0 || !email.trim()) return;
    setAuthLoading(true);
    setAuthError("");
    try {
      const ok = await requestLoginCode(email);
      if (ok) toast.success(t.codeResentHint);
    } catch {
      setAuthError(t.loginTimeout);
      toast.error(t.loginTimeout);
    } finally {
      setAuthLoading(false);
    }
  }

  return (
    <main className="landing-reset-page">
      <div className="landing-reset-backdrop" aria-hidden="true" />
      <div className="landing-reset-stack">
        <HeroPoster
          titleLines={t.heroTitleLines as [string, string, string]}
          subtitle={t.heroSubtitle}
          socialProof={t.socialProof}
          promptBar={
            <PromptBar
              value={input}
              onChange={setInput}
              onSubmit={handleGenerate}
              onFocus={() => setPromptFocused(true)}
              onBlur={() => setPromptFocused(false)}
              state={promptState}
              loading={loading}
              error={error}
              hint={t.promptHint}
              emptyHint={t.promptEmptyHint}
              onHintClick={() => fillExample(activeExample)}
              inputRef={composerRef}
              placeholder={t.promptPlaceholder}
            />
          }
        />

        <ShowcaseCarousel
          title={t.exampleTitle}
          subtitle={t.exampleSubtitle}
          examples={EXAMPLES}
          activeIndex={activeExampleIndex}
          onCycle={cycleExample}
          onSelect={selectExample}
          onGenerate={fillExample}
          onKeyDown={handleShowcaseKeyDown}
          onPointerDown={handleShowcasePointerDown}
          onPointerUp={handleShowcasePointerUp}
        />

        <NarrativeRail title={t.valueTitle} lead={t.valueLead} items={t.valueItems} />

        <section className="landing-reset-final-cta">
          <div className="landing-reset-final-copy">
            <p className="landing-reset-final-kicker">Ready to send</p>
            <h2 className="landing-reset-final-title">{t.ctaTitle}</h2>
            <p className="landing-reset-final-text">{t.ctaDesc}</p>
          </div>
          <div className="landing-reset-final-actions">
            <button type="button" className="landing-final-primary" onClick={() => composerRef.current?.focus()}>
              现在生成一张项目卡
            </button>
            <button type="button" className="landing-final-link" onClick={() => setLoginOpen(true)}>
              登录后继续编辑
            </button>
          </div>
        </section>

        <footer className="landing-reset-footer">
          <span className="landing-reset-footer-brand">OnePitch · 一眼项目</span>
          <div className="landing-reset-footer-links">
            <button type="button" className="landing-reset-footer-link" onClick={() => router.push("/library")}>
              查看项目库
            </button>
            <Link href="/privacy" className="landing-reset-footer-link">
              隐私
            </Link>
            <Link href="/terms" className="landing-reset-footer-link">
              条款
            </Link>
          </div>
        </footer>
      </div>

      <Dialog
        open={loginOpen}
        onOpenChange={(open) => {
          setLoginOpen(open);
          if (!open) resetLoginFlow();
        }}
      >
        <DialogContent className="auth-dialog-sheet data-[open]:auth-dialog-sheet border-white/12 bg-[var(--bg-surface-2)] text-[var(--text-primary)] sm:max-w-md">
          <DialogHeader>
            <DialogTitle>登录后继续编辑</DialogTitle>
            <DialogDescription>生成和分享不需要登录，只有认领和编辑才需要。</DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={handleLoginSubmit}>
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t.emailPlaceholder}
              className="field-input h-12"
            />
            {authStep === "code" ? (
              <Input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder={t.codePlaceholder}
                className="field-input h-12"
              />
            ) : null}
            {debugCode ? <p className="text-xs content-caption">{t.debugCodeHint} {debugCode}</p> : null}
            {authError ? <p className="text-sm text-red-500">{authError}</p> : null}
            <Button type="submit" className="action-primary-btn h-11 w-full" disabled={authLoading}>
              {authLoading ? (authStep === "email" ? t.sendingCode : t.verifyingCode) : authStep === "email" ? t.sendCode : t.verifyCode}
            </Button>
            {authStep === "code" ? (
              <div className="flex items-center justify-between text-sm">
                <button type="button" className="inline-nav-link" onClick={onResendCode} disabled={resendCooldown > 0 || authLoading}>
                  {resendCooldown > 0 ? t.resendIn(resendCooldown) : t.resendCode}
                </button>
                <button type="button" className="inline-nav-link" onClick={resetLoginFlow}>
                  {t.switchEmail}
                </button>
              </div>
            ) : null}
          </form>
        </DialogContent>
      </Dialog>
    </main>
  );
}
