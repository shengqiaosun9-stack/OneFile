"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { BpPagePreview } from "@/components/onepitch-bp/BpPagePreview";
import { PrimaryLink, PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet, bpSend } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

export default function BpPreviewPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [selected, setSelected] = useState(1);
  const [supplement, setSupplement] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    bpGet<BpBundle>(`/api/bp/diagnoses/${token}`)
      .then(setBundle)
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"))
      .finally(() => setLoading(false));
  }, [token]);

  const currentPage = useMemo(() => bundle?.pages.find((page) => page.page_number === selected) || bundle?.pages[0], [bundle, selected]);

  const saveSupplement = async () => {
    if (!supplement.trim()) return;
    setSaving(true);
    try {
      const next = await bpSend<BpBundle>(`/api/bp/diagnoses/${token}/supplements`, { title: `第 ${selected} 页补充材料`, content: supplement, related_page_number: selected });
      setBundle(next);
      setSupplement("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <PublicBpShell currentStep="bp" token={token}>
      <section className="mx-auto max-w-6xl px-5 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-white md:text-5xl">标准外部沟通结构预览</h1>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">
            这不是完整融资 BP，也不是 PPT 设计稿。这里展示的是项目进入外部沟通前通常需要回答的 14 个核心问题。完整页级文案和人工编辑内容不会在免费诊断里直接交付。
          </p>
        </div>
        {loading ? <div className="text-slate-400">正在读取 BP 清单...</div> : null}
        {error ? <div className="mb-4 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}
        {bundle && currentPage ? (
          <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
            <SectionPanel className="h-fit">
              <div className="mb-4 text-sm text-slate-300">14 个沟通模块</div>
              <div className="space-y-2">
                {bundle.pages.map((page) => (
                  <button
                    key={page.id}
                    onClick={() => setSelected(page.page_number)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm ${
                      selected === page.page_number ? "border-blue-400 bg-blue-500/15 text-blue-100" : "border-white/10 bg-black/20 text-slate-400 hover:text-white"
                    }`}
                  >
                    {page.page_number}. {page.title}
                  </button>
                ))}
              </div>
            </SectionPanel>
            <div className="space-y-5">
              <BpPagePreview page={currentPage} />
              <SectionPanel>
                <h2 className="text-xl font-semibold text-white">补充这一页材料</h2>
                <textarea className="bp-input mt-4 min-h-28" placeholder="补充这一页相关的客户、数据、证明、截图说明或访谈摘录" value={supplement} onChange={(event) => setSupplement(event.target.value)} />
                <div className="mt-4 flex flex-wrap gap-3">
                  <button onClick={saveSupplement} disabled={saving || !supplement.trim()} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60">
                    {saving ? "正在重新生成..." : "补充这一页材料"}
                  </button>
                  <SecondaryLink href={`/diagnose/${token}/service?type=bp_restructure`}>申请完整页级文案重构</SecondaryLink>
                </div>
              </SectionPanel>
              <div className="flex flex-wrap gap-3">
                <PrimaryLink href={`/diagnose/${token}/gaps`}>查看材料缺口汇总</PrimaryLink>
                <SecondaryLink href={`/diagnose/${token}`}>返回诊断报告</SecondaryLink>
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </PublicBpShell>
  );
}
