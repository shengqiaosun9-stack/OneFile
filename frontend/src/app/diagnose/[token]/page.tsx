"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { FieldBlock, PrimaryLink, PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet, bpSend } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

const scoreLabels: Record<string, string> = {
  clarity: "表达清晰度",
  evidence: "客户 / 场景证据",
  product: "产品 / Demo 完整度",
  business_model: "商业模式清晰度",
  ai_relevance: "AI 相关性说明",
  team: "团队 / 交付能力",
  resource_ask: "资源诉求明确度",
  material_completeness: "外部沟通材料完整度",
};

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

  const topGaps = useMemo(() => bundle?.gap_report.items.slice(0, 5) || [], [bundle]);
  const questions = bundle?.insight.likely_questions?.slice(0, 8) || [];
  const nextActions = bundle?.insight.next_actions?.slice(0, 3) || [];
  const scoreBreakdown = bundle?.insight.score_breakdown || {};

  return (
    <PublicBpShell currentStep="report" token={token}>
      <section className="mx-auto max-w-6xl px-5 py-12">
        {loading ? <div className="text-slate-400">正在读取诊断报告...</div> : null}
        {error ? <ErrorBlock message={error} /> : null}
        {bundle ? (
          <div className="space-y-6">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div>
                <div className="text-sm text-blue-300">项目进入资源方视野前的初步体检</div>
                <h1 className="mt-2 text-3xl font-semibold text-white md:text-5xl">项目初诊报告</h1>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
                  这份报告不是完整 BP，也不代表项目价值结论。它的作用是帮你看清：项目现在讲清楚了什么、还缺什么、资源方下一步最可能追问什么。
                </p>
              </div>
              <button onClick={() => navigator.clipboard?.writeText(window.location.href)} className="h-10 rounded-md border border-white/10 px-4 text-sm text-slate-200 hover:bg-white/[0.04]">
                复制私密诊断链接
              </button>
            </div>

            <section className="grid gap-5 lg:grid-cols-[1fr_320px]">
              <SectionPanel>
                <h2 className="text-2xl font-semibold text-white">我们目前理解你的项目是</h2>
                <div className="mt-5 grid gap-4 md:grid-cols-2">
                  <FieldBlock label="项目名称" value={bundle.project.name} />
                  <FieldBlock label="一句话理解" value={bundle.project.tagline || bundle.insight.solution} />
                  <FieldBlock label="当前阶段" value={bundle.project.stage} />
                  <FieldBlock label="目标客户 / 使用场景" value={bundle.project.target_customer || bundle.insight.resource_needs} />
                  <FieldBlock label="当前资源诉求" value={bundle.project.current_resource_need} />
                  <FieldBlock label="推荐优先路径" value={bundle.project.recommended_path} />
                </div>
              </SectionPanel>
              <SectionPanel>
                <div className="text-sm text-slate-500">当前对外沟通准备度</div>
                <div className="mt-4 flex items-end gap-2">
                  <span className="text-6xl font-semibold text-blue-100">{bundle.project.readiness_score}</span>
                  <span className="pb-2 text-sm text-slate-500">/ 100</span>
                </div>
                <p className="mt-4 text-sm leading-6 text-slate-400">这个分数只代表材料完整度和表达清晰度，不代表项目好坏、融资价值或商业成功概率。</p>
                <p className="mt-5 text-sm leading-6 text-slate-400">不方便直接发 BP 时，可以先发这张项目判断卡。</p>
                <Link href={`/diagnose/${token}/card`} className="mt-3 inline-flex h-10 items-center rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500">
                  生成项目判断卡
                </Link>
              </SectionPanel>
            </section>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">评分维度</h2>
              <div className="mt-5 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                {Object.entries(scoreLabels).map(([key, label]) => (
                  <div key={key} className="rounded-md border border-white/10 bg-black/20 p-4">
                    <div className="text-xs text-slate-500">{label}</div>
                    <div className="mt-2 text-2xl font-semibold text-white">{scoreBreakdown[key] ?? "待评估"}</div>
                  </div>
                ))}
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">资源路径准备度</h2>
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                {(bundle.insight.resource_readiness || []).map((item) => (
                  <article key={item.path} className="rounded-lg border border-white/10 bg-black/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="font-semibold text-white">{item.path}</h3>
                      <span className={`rounded-md border px-2.5 py-1 text-xs ${item.level === "高" ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : item.level === "中" ? "border-amber-400/30 bg-amber-500/10 text-amber-200" : "border-slate-500/30 bg-slate-500/10 text-slate-300"}`}>
                        {item.level}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-300">{item.reason}</p>
                    <p className="mt-3 text-sm leading-6 text-amber-200">还缺：{item.missing}</p>
                    <p className="mt-2 text-sm leading-6 text-blue-200">下一步：{item.next_step}</p>
                  </article>
                ))}
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">项目理解草稿</h2>
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <FieldBlock label="解决什么问题" value={bundle.insight.problem} />
                <FieldBlock label="面向谁 / 场景" value={bundle.project.target_customer || "待补充"} />
                <FieldBlock label="解决方案是什么" value={bundle.insight.solution} />
                <FieldBlock label="AI 在里面的作用" value={bundle.insight.ai_relevance} />
                <FieldBlock label="当前进展" value={bundle.insight.traction} />
                <FieldBlock label="商业模式" value={bundle.insight.business_model} />
                <FieldBlock label="已有证据" value={bundle.insight.key_data} />
                <FieldBlock label="当前资源诉求" value={bundle.insight.resource_needs} />
              </div>
            </SectionPanel>

            <section className="grid gap-5 lg:grid-cols-2">
              <SectionPanel>
                <h2 className="text-2xl font-semibold text-white">资源方现在还看不清的地方</h2>
                <div className="mt-5 space-y-3">
                  {topGaps.map((item, index) => (
                    <div key={`${item.gap_name}-${index}`} className="rounded-md border border-white/10 bg-black/20 p-4">
                      <div className="text-xs text-amber-300">{item.severity}</div>
                      <h3 className="mt-2 font-semibold text-white">{item.gap_name}</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-400">{item.recommended_fix}</p>
                    </div>
                  ))}
                </div>
              </SectionPanel>
              <SectionPanel>
                <h2 className="text-2xl font-semibold text-white">如果继续沟通，对方大概率会问</h2>
                <div className="mt-5 space-y-3">
                  {questions.map((item, index) => (
                    <div key={item} className="flex gap-3 rounded-md border border-white/10 bg-black/20 p-3 text-sm leading-6 text-slate-300">
                      <span className="text-blue-300">{index + 1}.</span>
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </SectionPanel>
            </section>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">标准外部沟通结构预览</h2>
              <p className="mt-3 text-sm leading-6 text-slate-400">这里展示的是项目进入外部沟通前通常需要回答的 14 个核心问题。完整页级文案和人工编辑内容不会在免费诊断里直接交付。</p>
              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {(bundle.insight.bp_structure_preview || []).map((item, index) => (
                  <div key={`${item.module}-${index}`} className="rounded-md border border-white/10 bg-black/20 p-4">
                    <div className="text-xs text-blue-300">{String(index + 1).padStart(2, "0")}</div>
                    <h3 className="mt-1 font-semibold text-white">{item.module}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-400">{item.question_to_answer}</p>
                    <p className="mt-2 text-xs text-amber-200">{item.current_status} {item.missing_material}</p>
                  </div>
                ))}
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">建议你下一步先做这 3 件事</h2>
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                {nextActions.map((item, index) => (
                  <div key={item} className="rounded-md border border-white/10 bg-black/20 p-4 text-sm leading-6 text-slate-300">
                    <span className="mb-3 flex size-7 items-center justify-center rounded-md bg-blue-600/20 text-xs text-blue-200">{index + 1}</span>
                    {item}
                  </div>
                ))}
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">如果你准备对接资源方，建议先做一次人工重构</h2>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
                AI 可以帮助你发现表达缺口，但项目能不能被园区、投资人、技术方或合作方继续看下去，关键在于项目逻辑、证据材料、资源诉求和沟通顺序是否成立。
              </p>
              <div className="mt-5 flex flex-wrap gap-3">
                <PrimaryLink href={`/diagnose/${token}/service?type=project_diagnosis`}>申请人工项目初诊</PrimaryLink>
                <SecondaryLink href={`/diagnose/${token}/service?type=bp_restructure`}>申请 BP 清单人工重构</SecondaryLink>
                <SecondaryLink href={`/diagnose/${token}/card`}>生成项目判断卡</SecondaryLink>
              </div>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-xl font-semibold text-white">补充材料并重新诊断</h2>
              <textarea className="bp-input mt-4 min-h-32" placeholder="补充客户案例、订单、团队背景、资源诉求或其他说明" value={supplement} onChange={(event) => setSupplement(event.target.value)} />
              <div className="mt-4 flex flex-wrap gap-3">
                <button onClick={regenerate} disabled={saving || !supplement.trim()} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60">
                  {saving ? "正在重新生成..." : "保存并重新诊断"}
                </button>
                <SecondaryLink href="/">返回首页</SecondaryLink>
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
