"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { PrimaryLink, PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

export default function ProjectShareCardPage() {
  const { token } = useParams<{ token: string }>();
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    bpGet<BpBundle>(`/api/bp/diagnoses/${token}`)
      .then(setBundle)
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"));
  }, [token]);

  const card = bundle?.insight.share_card;

  return (
    <PublicBpShell currentStep="card" token={token}>
      <section className="mx-auto max-w-5xl px-5 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-white md:text-5xl">可分享项目卡</h1>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">这是一张半公开项目卡，适合发给合伙人、园区、活动主办方、投资人或合作方。它不展示原始材料、内部判断和联系方式。</p>
        </div>
        {error ? <div className="rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}
        {bundle && card ? (
          <div className="space-y-6">
            <article className="overflow-hidden rounded-2xl border border-blue-400/20 bg-[#050b1f] shadow-[0_24px_80px_rgba(37,99,235,0.18)]">
              <div className="border-b border-white/10 p-6">
                <div className="text-xs tracking-[0.18em] text-blue-300">OnePitch 项目卡</div>
                <h2 className="mt-4 text-3xl font-semibold text-white">{card.title || bundle.project.name}</h2>
                <p className="mt-4 text-base leading-7 text-slate-300">{card.one_line || bundle.project.tagline}</p>
              </div>
              <div className="grid gap-4 p-6 md:grid-cols-2">
                <Info label="当前阶段" value={card.stage} />
                <Info label="目标客户 / 场景" value={card.target_customer} />
                <Info label="当前资源诉求" value={card.resource_ask} />
                <Info label="适合资源路径" value={card.recommended_path} />
              </div>
              <div className="grid gap-4 border-t border-white/10 p-6 md:grid-cols-2">
                <ListBlock title="项目亮点" items={card.highlights} />
                <ListBlock title="待补材料" items={card.gaps} tone="warning" />
              </div>
              <div className="border-t border-white/10 p-6 text-xs leading-5 text-slate-500">
                本卡由 OnePitch 根据项目方提交材料生成，仅用于项目表达和外部沟通参考，不代表项目价值结论，不构成融资、入驻、成交或资源撮合承诺。
              </div>
            </article>

            <SectionPanel>
              <div className="flex flex-wrap gap-3">
                <button onClick={() => navigator.clipboard?.writeText(window.location.href)} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500">
                  复制项目卡链接
                </button>
                <button disabled className="h-10 rounded-md border border-white/10 px-4 text-sm text-slate-500">
                  生成图片（后续开放）
                </button>
                <PrimaryLink href={`/diagnose/${token}/service?type=manual_refinement`}>申请项目档案精修</PrimaryLink>
                <SecondaryLink href={`/diagnose/${token}`}>回到诊断报告</SecondaryLink>
              </div>
            </SectionPanel>
          </div>
        ) : null}
      </section>
    </PublicBpShell>
  );
}

function Info({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-sm leading-6 text-slate-100">{value || "待补充"}</div>
    </div>
  );
}

function ListBlock({ title, items, tone = "default" }: { title: string; items?: string[]; tone?: "default" | "warning" }) {
  return (
    <div>
      <h3 className={`text-sm font-semibold ${tone === "warning" ? "text-amber-200" : "text-blue-200"}`}>{title}</h3>
      <div className="mt-3 space-y-2">
        {(items?.filter(Boolean).length ? items.filter(Boolean) : ["待补充"]).map((item, index) => (
          <div key={`${title}-${index}`} className="rounded-md border border-white/10 bg-black/20 p-3 text-sm leading-6 text-slate-300">
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}
