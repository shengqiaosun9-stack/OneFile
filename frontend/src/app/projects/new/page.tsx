"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { buildLoginRedirectPath, currentPathWithQuery } from "@/lib/auth-redirect";
import { copyZh } from "@/lib/copy-zh";
import { resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { saveEmail } from "@/lib/session";
import type { AuthMeResponse, BpExtractResponse, MutationResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default function NewProjectPage() {
  const t = copyZh.create;
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [authProbeTick, setAuthProbeTick] = useState(0);
  const [authProbeError, setAuthProbeError] = useState("");

  const [title, setTitle] = useState("");
  const [inputText, setInputText] = useState("");
  const [saving, setSaving] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [supplementalText, setSupplementalText] = useState("");
  const [bpMetaText, setBpMetaText] = useState("");
  const [bpParsing, setBpParsing] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");

  const descriptorKeywords = ["助手", "工具", "系统", "平台", "解决方案", "ai+"];

  function readCtaTokenFromUrl(): string {
    if (typeof window === "undefined") return "";
    const query = new URLSearchParams(window.location.search);
    return (query.get("cta_token") || "").trim();
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    (async () => {
      setAuthReady(false);
      setAuthProbeError("");
      try {
        const meRes = await fetchWithTimeout("/api/auth/me", { cache: "no-store" }, 10_000);
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

  function validateEntityName(rawTitle: string): { ok: boolean; warning?: string; error?: string } {
    const trimmed = rawTitle.trim();
    if (!trimmed) return { ok: false, error: t.entityRequired };
    if (trimmed.length < 2) return { ok: false, error: t.nameTooShort };
    if (trimmed.length > 30) return { ok: false, error: t.nameTooLong };
    const lower = trimmed.toLowerCase();
    if (descriptorKeywords.some((word) => lower.includes(word))) {
      return { ok: true, warning: t.nameKeywordHint };
    }
    return { ok: true };
  }

  async function onSelectBpFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError(t.uploadTypeInvalid);
      toast.error(t.uploadTypeInvalid);
      event.target.value = "";
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError(t.uploadTooLarge);
      toast.error(t.uploadTooLarge);
      event.target.value = "";
      return;
    }
    setBpParsing(true);
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetchWithTimeout("/api/uploads/bp-extract", {
        method: "POST",
        body: formData,
      }, 12_000);
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
        return;
      }
      const body = (await res.json()) as BpExtractResponse;
      const summary = `${t.uploadParsed}：${body.page_count} 页，${body.text_chars} 字${body.truncated ? "（已截断）" : ""}`;
      setSupplementalText(body.extracted_text || "");
      setBpMetaText(summary);
      toast.success(summary);
    } catch {
      setError(t.uploadNetworkFailed);
      toast.error(t.uploadNetworkFailed);
    } finally {
      setBpParsing(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email) {
      setError(t.missingEmail);
      toast.error(t.missingEmail);
      return;
    }
    const nameValidation = validateEntityName(title);
    if (!nameValidation.ok) {
      const msg = nameValidation.error || t.entityRequired;
      setError(msg);
      toast.error(msg);
      return;
    }
    if (nameValidation.warning) {
      setWarning(nameValidation.warning);
      toast.warning(nameValidation.warning);
    }

    setSaving(true);
    setError("");
    if (!nameValidation.warning) setWarning("");
    const ctaToken = readCtaTokenFromUrl();

    try {
      const res = await fetchWithTimeout(
        "/api/projects",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            title: title.trim(),
            input_text: inputText,
            supplemental_text: supplementalText,
            cta_token: ctaToken,
          }),
        },
        12_000,
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
        return;
      }

      const body = (await res.json()) as MutationResponse;
      if (body.used_fallback) {
        const warningMessage = body.warning || t.fallbackWarning;
        setWarning(warningMessage);
        toast.warning(warningMessage);
      }

      router.push(`/projects/${body.project.id}?created=1`);
    } catch {
      setError(t.createNetworkFailed);
      toast.error(t.createNetworkFailed);
    } finally {
      setSaving(false);
    }
  }

  if (authReady && !email) {
    const ctaToken = readCtaTokenFromUrl();
    const loginNext = ctaToken ? `/projects/new?cta_token=${encodeURIComponent(ctaToken)}` : "/projects/new";
    return (
      <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
        <div className="mx-auto max-w-3xl space-y-6">
          <section className="onefile-panel space-y-3 p-5 sm:p-6">
            <h1 className="text-xl font-semibold text-[var(--landing-title)]">{t.needLoginTitle}</h1>
            <p className="text-sm onefile-subtle">{t.needLoginDesc}</p>
            {authProbeError ? <p className="text-sm text-destructive">{authProbeError}</p> : null}
            {authProbeError ? (
              <Button variant="ghost" className="landing-secondary-btn h-10 px-4" onClick={() => setAuthProbeTick((prev) => prev + 1)}>
                {t.retryAuthCheck}
              </Button>
            ) : null}
            <Button className="landing-cta-btn h-10 px-5" onClick={() => router.push(`/?next=${encodeURIComponent(loginNext)}`)}>
              {t.goLogin}
            </Button>
          </section>
        </div>
      </main>
    );
  }

  if (!authReady) {
    return (
      <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
        <div className="mx-auto max-w-3xl">
          <section className="onefile-panel p-5 sm:p-6">
            <p className="text-sm onefile-subtle">{copyZh.common.loading}</p>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="landing-premium min-h-screen px-6 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="onefile-surface space-y-2 p-5 sm:p-6">
          <div className="flex items-center gap-2">
            <p className="landing-brand">OneFile</p>
            <span className="landing-brand-sub">· 一人档</span>
          </div>
          <h1 className="text-2xl font-semibold text-[var(--landing-title)]">{t.title}</h1>
          <p className="text-sm onefile-subtle">{t.subtitle}</p>
        </header>

        <section className="onefile-panel space-y-4 p-5 sm:p-6">
          <h2 className="onefile-section-title">{t.cardTitle}</h2>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--landing-title)]">{t.entityLabel}</label>
              <Input
                className="onefile-input h-11"
                placeholder={t.namePlaceholder}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
              <p className="text-xs onefile-caption">{t.entityHint}</p>
            </div>
            <Textarea
              className="onefile-input min-h-[13rem]"
              placeholder={t.inputPlaceholder}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              rows={10}
              required
            />
            <div className="rounded-xl border border-slate-200/80 bg-white/80 p-3">
              <button
                type="button"
                className="text-sm font-medium text-[var(--landing-title)]"
                onClick={() => setAdvancedOpen((prev) => !prev)}
              >
                {t.advancedToggle}
              </button>
              {advancedOpen ? (
                <div className="mt-3 space-y-2">
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    className="block w-full cursor-pointer text-sm text-[var(--landing-text)] file:mr-3 file:rounded-lg file:border file:border-slate-200 file:bg-white file:px-3 file:py-2 file:text-sm file:text-[var(--landing-title)]"
                    onChange={onSelectBpFile}
                  />
                  <p className="text-xs onefile-caption">{t.uploadHint}</p>
                  {bpParsing ? <p className="text-xs text-[var(--landing-text)]">{t.uploadParsing}</p> : null}
                  {bpMetaText ? <p className="text-xs text-emerald-700">{bpMetaText}</p> : null}
                  {supplementalText ? <p className="text-xs text-[var(--landing-text)]">{t.uploadMergedHint}</p> : null}
                </div>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" className="landing-cta-btn h-10 px-5" disabled={saving}>
                {saving ? t.submitting : t.submit}
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="landing-secondary-btn h-10 px-4"
                onClick={() => router.push("/library")}
              >
                {t.backLibrary}
              </Button>
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {warning ? <p className="text-sm text-amber-600">{warning}</p> : null}
          </form>
        </section>
      </div>
    </main>
  );
}
