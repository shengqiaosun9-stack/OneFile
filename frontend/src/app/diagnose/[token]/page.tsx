"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { FieldBlock, PrimaryLink, PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet, bpSend } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

export default function DiagnosisReportPage() {
  const params = useParams<{ token: string }>();
  const [token, setToken] = useState("");
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [supplement, setSupplement] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const nextToken = params.token;
    setToken(nextToken);
    bpGet<BpBundle>(`/api/bp/diagnoses/${nextToken}`)
      .then(setBundle)
      .catch((err) => setError(err instanceof Error ? err.message : "没有找到这份诊断报告。"))
      .finally(() => setLoading(false));
  }, [params.token]);

  const regenerate = async () => {
    if (!token || !supplement.trim()) return;
    setSaving(true);
    setError("");
    try {
      const next = await bpSend<BpBundle>(`/api/bp/diagnoses/${token}/supplements`, { title: "用户补充材料", content: supplement });
      setBundle(next);
      setSupplement("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <PublicBpShell currentStep="report" token={token}>
      <section className="mx-auto max-w-6xl px-5 py-12">
        {loading ? <div className="text-slate-400">正在读取诊断报告...</div> : null}
        {error ? <ErrorBlock message={error} /> : null}
        {bundle ? (
          <div className="space-y-6">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div>
                <h1 className="text-3xl font-semibold text-white md:text-5xl">项目诊断报告</h1>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">这是根据你提交的材料生成的初步诊断。你可以继续补充材料并重新生成，也可以查看 BP 清单预览。</p>
              </div>
              <button
                onClick={() => navigator.clipboard?.writeText(window.location.href)}
                className="h-10 rounded-md border border-white/10 px-4 text-sm text-slate-200 hover:bg-white/[0.04]"
              >
                复制诊断链接
              </button>
            </div>

            <SectionPanel>
              <div className="grid gap-4 md:grid-cols-3">
                <FieldBlock label="项目名称" value={bundle.project.name} />
                <FieldBlock label="当前阶段" value={bundle.project.stage} />
                <FieldBlock label="推荐路径" value={bundle.project.recommended_path} />
                <FieldBlock label="一句话定位" value={bundle.project.tagline} />
                <FieldBlock label="目标客户" value={bundle.project.target_customer} />
                <FieldBlock label="当前资源诉求" value={bundle.project.current_resource_need} />
              </div>
            </SectionPanel>

            <SectionPanel>
              <div className="flex flex-col gap-6 md:flex-row md:items-center">
                <div className="flex size-32 items-center justify-center rounded-lg border border-blue-400/30 bg-blue-500/10 text-4xl font-semibold text-blue-100">
                  {bundle.project.readiness_score}
                </div>
                <div>
                  <h2 className="text-2xl font-semibold text-white">项目准备度</h2>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">这个分数只代表材料完整度和对外表达清晰度，不代表项目价值高低。</p>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                    {["项目定位", "业务基础", "客户/订单证明", "AI 相关性", "商业模式", "团队说明", "资源诉求"].map((item) => (
                      <span key={item} className="rounded-md border border-white/10 bg-black/20 px-2.5 py-1">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="mb-5 text-2xl font-semibold text-white">项目理解草稿</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <FieldBlock label="解决什么问题" value={bundle.insight.problem} />
                <FieldBlock label="解决方案" value={bundle.insight.solution} />
                <FieldBlock label="商业模式" value={bundle.insight.business_model} />
                <FieldBlock label="AI 相关性" value={bundle.insight.ai_relevance} />
                <FieldBlock label="当前进展" value={bundle.insight.traction} />
                <FieldBlock label="关键数据" value={bundle.insight.key_data} />
                <FieldBlock label="当前资源诉求" value={bundle.insight.resource_needs} />
                <FieldBlock label="来源说明" value="来自你提交的原始材料；待确认字段不会被当作事实。" />
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">补充材料并重新生成</h2>
              <textarea className="bp-input mt-4 min-h-32" placeholder="补充客户案例、订单、团队背景、资源诉求或其他说明" value={supplement} onChange={(event) => setSupplement(event.target.value)} />
              <div className="mt-4 flex flex-wrap gap-3">
                <button onClick={regenerate} disabled={saving || !supplement.trim()} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60">
                  {saving ? "正在重新生成..." : "保存并重新生成"}
                </button>
                <PrimaryLink href={`/diagnose/${token}/bp`}>查看 14 页 BP 清单预览</PrimaryLink>
                <SecondaryLink href={`/diagnose/${token}/service`}>申请人工项目初诊</SecondaryLink>
              </div>
            </SectionPanel>
          </div>
        ) : null}
      </section>
    </PublicBpShell>
  );
}

function ErrorBlock({ message }: { message: string }) {
  return (
    <SectionPanel>
      <h1 className="text-2xl font-semibold text-white">没有找到这份诊断报告</h1>
      <p className="mt-3 text-sm text-slate-400">{message}</p>
      <Link href="/diagnose" className="mt-5 inline-flex h-10 items-center rounded-md bg-blue-600 px-4 text-sm text-white">
        重新开始诊断
      </Link>
    </SectionPanel>
  );
}
