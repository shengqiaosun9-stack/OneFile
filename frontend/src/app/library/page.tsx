"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ProjectCard } from "@/components/onefile/project-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { copyZh } from "@/lib/copy-zh";
import { resolveApiError } from "@/lib/error-zh";
import { fetchWithTimeout } from "@/lib/fetch-with-timeout";
import { clearEmail, saveEmail } from "@/lib/session";
import type { AuthMeResponse, BackupExportResponse, ListResponse, OneFileProject } from "@/lib/types";

export const dynamic = "force-dynamic";

const USER_SPLIT_RE = /[、，,\/|;；]+/;
const PAGE_SIZE = 12;

const FORM_FILTER_PRESETS = [
  "AI 原生应用",
  "SaaS",
  "API 服务",
  "智能体",
  "交易市场",
  "数据工具",
  "基础设施",
  "其他",
];

const BUSINESS_FILTER_PRESETS = ["ToB", "ToC", "B2B2C", "B2G", "C2C", "未知"];

const MODEL_FILTER_PRESETS = [
  "B2B 订阅",
  "B2C 订阅",
  "按量计费",
  "交易抽佣",
  "一次性付费",
  "外包/服务",
  "广告变现",
  "平台撮合",
  "混合模式",
  "未知模式",
];

function getFormLabel(project: OneFileProject): string {
  return (project.form_type_label || project.form_type || "").trim();
}

function getModelLabel(project: OneFileProject): string {
  return (project.model_type_label || project.model_type || "").trim();
}

function getUserTokens(users: string | undefined): string[] {
  if (!users) return [];
  return users
    .split(USER_SPLIT_RE)
    .map((item) => item.trim())
    .filter((item) => item && item !== "待补充");
}

function getBusinessModelLabel(project: OneFileProject): string {
  return (project.business_model_type_label || project.business_model_type || "").trim();
}

function includesUserToken(users: string | undefined, target: string): boolean {
  if (!target) return true;
  const tokens = getUserTokens(users);
  return tokens.some((token) => token.toLowerCase() === target.toLowerCase());
}

export default function LibraryPage() {
  const t = copyZh.library;
  const router = useRouter();
  const [authenticatedEmail, setAuthenticatedEmail] = useState("");
  const [authReady, setAuthReady] = useState(false);

  const [projects, setProjects] = useState<OneFileProject[]>([]);
  const [userId, setUserId] = useState("");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"all" | "public" | "mine">("all");
  const [formFilter, setFormFilter] = useState("all");
  const [usersFilter, setUsersFilter] = useState("all");
  const [businessFilter, setBusinessFilter] = useState("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadTick, setReloadTick] = useState(0);
  const [healthStatus, setHealthStatus] = useState<"checking" | "ok" | "down">("checking");
  const [healthMessage, setHealthMessage] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const [exportingBackup, setExportingBackup] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const meRes = await fetchWithTimeout("/api/auth/me", { cache: "no-store" }, 10_000);
        if (meRes.ok) {
          const meBody = (await meRes.json()) as AuthMeResponse;
          if (meBody.user?.email) {
            setAuthenticatedEmail(meBody.user.email);
            saveEmail(meBody.user.email);
          }
        }
      } catch {
        // Keep guest mode available when auth probe fails.
      } finally {
        setAuthReady(true);
      }
    })();
  }, []);

  const isAuthenticated = Boolean(authenticatedEmail);
  const richCreateHref = "/projects/new?mode=rich&from=library";
  const richCreateLoginHref = "/?next=%2Fprojects%2Fnew%3Fmode%3Drich%26from%3Dlibrary";

  useEffect(() => {
    if (!isAuthenticated && scope === "mine") {
      setScope("all");
    }
  }, [isAuthenticated, scope]);

  useEffect(() => {
    (async () => {
      setHealthStatus("checking");
      setHealthMessage("");
      try {
        const res = await fetchWithTimeout("/api/health", { cache: "no-store" }, 8_000);
        if (!res.ok) {
          const failure = await resolveApiError(res, t.healthDown);
          setHealthStatus("down");
          setHealthMessage(failure.message);
          return;
        }
        setHealthStatus("ok");
      } catch {
        setHealthStatus("down");
        setHealthMessage("");
      }
    })();
  }, [reloadTick, t.healthDown]);

  useEffect(() => {
    if (!authReady) return;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetchWithTimeout("/api/projects", { cache: "no-store" }, 12_000);
        if (!res.ok) {
          const failure = await resolveApiError(res, t.loadFailed);
          setError(failure.message);
          return;
        }
        const contentType = res.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
          setError(t.invalidResponse);
          return;
        }
        const body = (await res.json()) as ListResponse;
        setProjects(body.projects || []);
        setUserId(body.user?.id || "");
      } catch {
        setError(t.loadTimeout);
      } finally {
        setLoading(false);
      }
    })();
  }, [authReady, reloadTick, t.invalidResponse, t.loadFailed, t.loadTimeout]);

  const scopeProjects = useMemo(() => {
    let source = projects;
    if (scope === "public") {
      source = source.filter((item) => Boolean(item.share?.is_public));
    } else if (scope === "mine") {
      source = source.filter((item) => item.owner_user_id === userId);
    }
    return source;
  }, [projects, scope, userId]);

  const formOptions = useMemo(() => {
    const dynamic = Array.from(new Set(scopeProjects.map(getFormLabel).filter(Boolean)));
    return Array.from(new Set([...FORM_FILTER_PRESETS, ...dynamic])).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [scopeProjects]);

  const userOptions = useMemo(() => {
    return Array.from(new Set(scopeProjects.flatMap((item) => getUserTokens(item.users)))).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [scopeProjects]);

  const businessOptions = useMemo(() => {
    const dynamic = Array.from(new Set(scopeProjects.map(getBusinessModelLabel).filter(Boolean)));
    return Array.from(new Set([...BUSINESS_FILTER_PRESETS, ...dynamic])).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [scopeProjects]);

  const modelOptions = useMemo(() => {
    const dynamic = Array.from(new Set(scopeProjects.map(getModelLabel).filter(Boolean)));
    return Array.from(new Set([...MODEL_FILTER_PRESETS, ...dynamic])).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [scopeProjects]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let source = scopeProjects;

    source = source.filter((item) => {
      const formValue = getFormLabel(item);
      const businessValue = getBusinessModelLabel(item);
      const modelValue = getModelLabel(item);
      const formMatched = formFilter === "all" || formValue === formFilter;
      const usersMatched = usersFilter === "all" || includesUserToken(item.users, usersFilter);
      const businessMatched = businessFilter === "all" || businessValue === businessFilter;
      const modelMatched = modelFilter === "all" || modelValue === modelFilter;
      return formMatched && usersMatched && businessMatched && modelMatched;
    });

    if (!q) return source;
    return source.filter((item) => {
      return `${item.id} ${item.title} ${item.summary || ""} ${item.stage_label || ""} ${item.stage || ""} ${item.users || ""} ${getFormLabel(item)} ${getBusinessModelLabel(item)} ${getModelLabel(item)}`
        .toLowerCase()
        .includes(q);
    });
  }, [scopeProjects, query, formFilter, usersFilter, businessFilter, modelFilter]);

  useEffect(() => {
    setPage(1);
  }, [query, scope, formFilter, usersFilter, businessFilter, modelFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedProjects = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, currentPage]);

  const totalCount = projects.length;
  const publicCount = projects.filter((item) => Boolean(item.share?.is_public)).length;
  const mineCount = userId ? projects.filter((item) => item.owner_user_id === userId).length : 0;
  const hasAnyPublic = publicCount > 0;
  const hasActiveFilters =
    query.trim().length > 0 ||
    scope !== "all" ||
    formFilter !== "all" ||
    usersFilter !== "all" ||
    businessFilter !== "all" ||
    modelFilter !== "all";
  const firstPublicExampleId = useMemo(() => {
    const first = projects.find((item) => Boolean(item.id) && Boolean(item.share?.is_public));
    return first?.id || "";
  }, [projects]);
  const emptyHint = scope === "mine" ? t.emptyMineHint : hasAnyPublic ? t.emptyFilteredHint : t.emptyHint;

  function openDemoExample() {
    if (firstPublicExampleId) {
      router.push(`/card/${firstPublicExampleId}?from=library-empty-demo`);
      return;
    }
    toast.message(copyZh.landing.exampleEmpty);
    router.push("/#showcase");
  }

  function resetFilters() {
    setQuery("");
    setScope("all");
    setFormFilter("all");
    setUsersFilter("all");
    setBusinessFilter("all");
    setModelFilter("all");
    setPage(1);
  }

  async function onLogout() {
    setLoggingOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      clearEmail();
      setAuthenticatedEmail("");
      setUserId("");
      router.push("/library?mode=guest");
    }
  }

  async function onExportBackup() {
    if (!isAuthenticated || exportingBackup) return;
    setExportingBackup(true);
    try {
      const res = await fetch("/api/backup/export", { cache: "no-store" });
      if (!res.ok) {
        const failure = await resolveApiError(res, t.loadFailed);
        toast.error(failure.message);
        return;
      }
      const body = (await res.json()) as BackupExportResponse;
      const blob = new Blob([JSON.stringify(body, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `onepitch-backup-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success(t.exportBackup);
    } finally {
      setExportingBackup(false);
    }
  }

  return (
    <main className="app-shell app-shell--browse min-h-screen px-6 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto w-full max-w-7xl space-y-6 sm:space-y-8">
        <header className="library-section library-section--header library-browse-header p-5 sm:p-6">
          <div className="library-browse-header-main">
            <div className="library-browse-identity">
              <div className="flex items-center gap-2">
                <p className="brand-mark">{copyZh.common.brand}</p>
              </div>
              <h1 className="mt-2 text-2xl font-semibold text-[var(--landing-title)]">{t.title}</h1>
              <p className="mt-1 text-sm content-subtle">{t.subtitle}</p>
              <p className="mt-1 text-xs content-caption">
                {healthStatus === "ok"
                  ? t.healthOk
                  : healthStatus === "checking"
                    ? t.healthChecking
                    : `${t.healthDown}${healthMessage ? `：${healthMessage}` : ""}`}
              </p>
            </div>
            <div className="library-browse-actions">
              <div className="library-browse-primary-action">
                <Button className="action-primary-btn h-10 px-5" onClick={() => router.push(isAuthenticated ? richCreateHref : richCreateLoginHref)}>
                  {isAuthenticated ? t.createProject : t.createNeedLogin}
                </Button>
              </div>
              <div className="library-browse-action-cluster">
                {isAuthenticated ? <span className="library-browse-account">{t.signedInAs}：{authenticatedEmail}</span> : null}
                <Link href="/" className="inline-nav-link library-browse-secondary-action">
                  {t.backLanding}
                </Link>
                {isAuthenticated ? (
                  <button
                    type="button"
                    className="inline-nav-link library-browse-secondary-action"
                    disabled={exportingBackup}
                    onClick={onExportBackup}
                  >
                    {exportingBackup ? t.exportingBackup : t.exportBackup}
                  </button>
                ) : null}
                {isAuthenticated ? (
                  <button type="button" className="inline-nav-link library-browse-secondary-action" disabled={loggingOut} onClick={onLogout}>
                    {loggingOut ? t.loggingOut : t.logout}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </header>

        <section className="library-section library-section--rail library-browse-rail p-4 sm:p-5">
          <div className="library-search-wrap">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.searchPlaceholder}
              className="field-input library-search-input h-11 w-full pr-10"
            />
            {query.trim().length > 0 ? (
              <button type="button" className="library-search-clear" aria-label="清空搜索" onClick={() => setQuery("")}>
                清除
              </button>
            ) : null}
          </div>
          <div className="library-scope-row">
            <Button variant="ghost" className={`filter-chip h-9 px-4 ${scope === "all" ? "is-active" : ""}`} onClick={() => setScope("all")}>
              {t.filterAll}
            </Button>
            <Button variant="ghost" className={`filter-chip h-9 px-4 ${scope === "public" ? "is-active" : ""}`} onClick={() => setScope("public")}>
              {t.filterPublic}
            </Button>
            {isAuthenticated ? (
              <Button variant="ghost" className={`filter-chip h-9 px-4 ${scope === "mine" ? "is-active" : ""}`} onClick={() => setScope("mine")}>
                {t.filterMine}
              </Button>
            ) : null}
          </div>
          <div className="library-filter-row">
            <label className="space-y-1">
              <span className="text-xs content-caption">{t.filterFormLabel}</span>
              <select className="field-select library-filter-select h-10 w-full rounded-lg px-3 text-sm" value={formFilter} onChange={(e) => setFormFilter(e.target.value)}>
                <option value="all">{t.filterAnyForm}</option>
                {formOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs content-caption">{t.filterUsersLabel}</span>
              <select className="field-select library-filter-select h-10 w-full rounded-lg px-3 text-sm" value={usersFilter} onChange={(e) => setUsersFilter(e.target.value)}>
                <option value="all">{t.filterAnyUsers}</option>
                {userOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs content-caption">{t.filterBusinessLabel}</span>
              <select className="field-select library-filter-select h-10 w-full rounded-lg px-3 text-sm" value={businessFilter} onChange={(e) => setBusinessFilter(e.target.value)}>
                <option value="all">{t.filterAnyBusiness}</option>
                {businessOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs content-caption">{t.filterModelLabel}</span>
              <select className="field-select library-filter-select h-10 w-full rounded-lg px-3 text-sm" value={modelFilter} onChange={(e) => setModelFilter(e.target.value)}>
                <option value="all">{t.filterAnyModel}</option>
                {modelOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <section className="library-section library-section--stats library-stats-strip p-3 sm:px-5 sm:py-3">
          <div className="library-stat-item">
            <p className="text-xs content-caption">{t.statAll}</p>
            <p className="mt-1 text-lg font-semibold text-[var(--landing-title)]/90">{totalCount}</p>
          </div>
          <div className="library-stat-item">
            <p className="text-xs content-caption">{t.statPublic}</p>
            <p className="mt-1 text-lg font-semibold text-[var(--landing-title)]/90">{publicCount}</p>
          </div>
          <div className="library-stat-item">
            <p className="text-xs content-caption">{t.statMine}</p>
            <p className="mt-1 text-lg font-semibold text-[var(--landing-title)]/90">{mineCount}</p>
          </div>
        </section>

        {loading ? (
          <div className="space-y-3">
            <p className="text-sm content-subtle">{t.loadingCards}</p>
            <section className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:gap-6 xl:grid-cols-3 2xl:grid-cols-4">
              {Array.from({ length: 8 }).map((_, index) => (
                <div key={`library-skeleton-${index}`} className="content-panel p-4">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="mt-3 h-4 w-full" />
                  <Skeleton className="mt-2 h-4 w-4/5" />
                  <Skeleton className="mt-4 h-8 w-full" />
                </div>
              ))}
            </section>
          </div>
        ) : null}

        {error ? (
          <div className="library-section library-state-panel space-y-3 p-4">
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="ghost" className="library-inline-action h-9 px-3" onClick={() => setReloadTick((prev) => prev + 1)}>
              {t.retryLoad}
            </Button>
          </div>
        ) : null}

        {!loading && !error && filtered.length === 0 ? (
          <div className="library-section library-state-panel space-y-4 p-10 text-center">
            <p className="text-sm content-subtle">{emptyHint}</p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button
                className="action-primary-btn h-10 px-5"
                onClick={() => router.push(isAuthenticated ? richCreateHref : richCreateLoginHref)}
              >
                {isAuthenticated ? t.createProject : t.createNeedLogin}
              </Button>
              {hasAnyPublic || hasActiveFilters ? (
                <Button variant="ghost" className="library-inline-action h-10 px-3" onClick={resetFilters}>
                  {t.clearFilters}
                </Button>
              ) : (
                <Button variant="ghost" className="library-inline-action h-10 px-3" onClick={openDemoExample} disabled={loading}>
                  {t.openDemo}
                </Button>
              )}
            </div>
          </div>
        ) : null}

        {!loading && !error && filtered.length > 0 ? (
          <section className="library-section library-section--pagination library-pagination-strip flex flex-wrap items-center justify-between gap-3 p-3 sm:px-4 sm:py-3">
            <p className="text-sm content-subtle">
              共 {filtered.length} 个项目 · 第 {currentPage}/{totalPages} 页
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                className="action-secondary-btn h-9 px-3"
                disabled={currentPage <= 1}
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              >
                上一页
              </Button>
              <Button
                variant="ghost"
                className="action-secondary-btn h-9 px-3"
                disabled={currentPage >= totalPages}
                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              >
                下一页
              </Button>
            </div>
          </section>
        ) : null}

	        <section className="library-grid-section grid grid-cols-1 gap-5 md:grid-cols-2 xl:gap-6 xl:grid-cols-3 2xl:grid-cols-4">
	          {pagedProjects.map((project) => (
	            <ProjectCard key={project.id} project={project} isOwner={Boolean(userId && project.owner_user_id === userId)} />
	          ))}
	        </section>

        {!loading && !error && filtered.length > 0 ? (
          <section className="library-section library-section--pagination library-pagination-strip flex flex-wrap items-center justify-between gap-3 p-3 sm:px-4 sm:py-3">
            <p className="text-sm content-subtle">
              共 {filtered.length} 个项目 · 第 {currentPage}/{totalPages} 页
            </p>
	            <div className="flex items-center gap-2">
	              <Button
	                variant="ghost"
	                className="action-secondary-btn h-9 px-3"
	                disabled={currentPage <= 1}
	                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
	              >
	                上一页
	              </Button>
	              <Button
	                variant="ghost"
	                className="action-secondary-btn h-9 px-3"
	                disabled={currentPage >= totalPages}
	                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
	              >
	                下一页
	              </Button>
	            </div>
	          </section>
	        ) : null}
	      </div>
	    </main>
	  );
}
