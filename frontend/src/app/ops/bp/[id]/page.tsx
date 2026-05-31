"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { BpPagePreview } from "@/components/onepitch-bp/BpPagePreview";
import { GapReportView } from "@/components/onepitch-bp/GapReport";
import { FieldBlock, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet, bpSend } from "@/lib/bp-api";
import type { BpBundle, BpPage } from "@/lib/bp-types";

const tabs = ["概览", "理解草稿", "14页BP", "材料缺口", "服务申请", "原始材料", "版本记录"] as const;

export default function OpsBpProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [tab, setTab] = useState<(typeof tabs)[number]>("概览");
  const [selectedPage, setSelectedPage] = useState(1);
  const [internal, setInternal] = useState({ internal_status: "", priority: "", budget_signal: "", decision_power: "", service_quote: "", internal_notes: "", private_feedback: "", next_action: "" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    bpGet<BpBundle>(`/api/ops/bp/projects/${id}`)
      .then((body) => {
        setBundle(body);
        setInternal({
          internal_status: body.project.internal_status || "submitted",
          priority: body.project.priority || "medium",
          budget_signal: body.project.budget_signal || "unknown",
          decision_power: body.project.decision_power || "unknown",
          service_quote: body.project.service_quote || "",
          internal_notes: body.project.internal_notes || "",
          private_feedback: body.project.private_feedback || "",
          next_action: body.project.next_action || "",
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"));
  };

  useEffect(load, [id]);

  const currentPage = useMemo(() => bundle?.pages.find((page) => page.page_number === selectedPage) || bundle?.pages[0], [bundle, selectedPage]);

  const saveInternal = async () => {
    setSaving(true);
    try {
      await bpSend(`/api/ops/bp/projects/${id}`, internal, "PATCH");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败。");
    } finally {
      setSaving(false);
    }
  };

  const savePage = async (page: BpPage, patch: Partial<BpPage>) => {
    const next = await bpSend<{ page: BpPage }>(`/api/ops/bp/pages/${page.id}`, patch, "PATCH");
    setBundle((prev) => {
      if (!prev) return prev;
      return { ...prev, pages: prev.pages.map((item) => (item.id === next.page.id ? next.page : item)) };
    });
  };

  return (
    <main className="min-h-screen bg-[#020617] text-slate-50">
      <header className="border-b border-white/10">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <Link href="/ops/bp" className="text-xs text-blue-300 hover:text-blue-200">
              返回提交项目
            </Link>
            <h1 className="mt-1 text-xl font-semibold text-white">{bundle?.project.name || "BP 项目交付台"}</h1>
          </div>
          {bundle ? (
            <Link href={`/diagnose/${bundle.project.user_visible_token}`} className="rounded-md border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/[0.04]">
              打开用户报告
            </Link>
          ) : null}
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-5 py-8">
        {error ? <div className="mb-4 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}
        {bundle ? (
          <div className="space-y-6">
            <div className="flex gap-2 overflow-x-auto">
              {tabs.map((item) => (
                <button key={item} onClick={() => setTab(item)} className={`rounded-md border px-3 py-2 text-sm ${tab === item ? "border-blue-400 bg-blue-500/15 text-blue-100" : "border-white/10 text-slate-400"}`}>
                  {item}
                </button>
              ))}
            </div>

            {tab === "概览" ? (
              <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
                <SectionPanel>
                  <div className="grid gap-4 md:grid-cols-2">
                    <FieldBlock label="一句话定位" value={bundle.project.tagline} />
                    <FieldBlock label="推荐路径" value={bundle.project.recommended_path} />
                    <FieldBlock label="准备度" value={bundle.project.readiness_score} />
                    <FieldBlock label="资源诉求" value={bundle.project.current_resource_need} />
                    <FieldBlock label="服务申请数" value={bundle.service_requests.length} />
                    <FieldBlock label="下一步" value={bundle.project.next_action || "待判断"} />
                  </div>
                </SectionPanel>
                <SectionPanel>
                  <h2 className="text-lg font-semibold text-white">内部承接字段</h2>
                  <div className="mt-4 space-y-3">
                    <select className="bp-input" value={internal.internal_status} onChange={(event) => setInternal({ ...internal, internal_status: event.target.value })}>
                      {["submitted", "new_service_request", "to_contact", "contacted", "to_quote", "quoted", "refining", "delivered", "paused", "abandoned"].map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                    <select className="bp-input" value={internal.priority} onChange={(event) => setInternal({ ...internal, priority: event.target.value })}>
                      {["high", "medium", "low"].map((item) => (
                        <option key={item} value={item}>
                          priority: {item}
                        </option>
                      ))}
                    </select>
                    <select className="bp-input" value={internal.budget_signal} onChange={(event) => setInternal({ ...internal, budget_signal: event.target.value })}>
                      {["unknown", "weak", "medium", "strong"].map((item) => (
                        <option key={item} value={item}>
                          budget: {item}
                        </option>
                      ))}
                    </select>
                    <input className="bp-input" placeholder="下一步动作" value={internal.next_action} onChange={(event) => setInternal({ ...internal, next_action: event.target.value })} />
                    <textarea className="bp-input min-h-24" placeholder="内部备注" value={internal.internal_notes} onChange={(event) => setInternal({ ...internal, internal_notes: event.target.value })} />
                    <button onClick={saveInternal} disabled={saving} className="h-10 w-full rounded-md bg-blue-600 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60">
                      {saving ? "保存中..." : "保存内部判断"}
                    </button>
                  </div>
                </SectionPanel>
              </div>
            ) : null}

            {tab === "理解草稿" ? (
              <SectionPanel>
                <div className="grid gap-4 md:grid-cols-2">
                  <FieldBlock label="解决什么问题" value={bundle.insight.problem} />
                  <FieldBlock label="解决方案" value={bundle.insight.solution} />
                  <FieldBlock label="商业模式" value={bundle.insight.business_model} />
                  <FieldBlock label="AI 相关性" value={bundle.insight.ai_relevance} />
                  <FieldBlock label="当前进展" value={bundle.insight.traction} />
                  <FieldBlock label="关键数据" value={bundle.insight.key_data} />
                </div>
              </SectionPanel>
            ) : null}

            {tab === "14页BP" && currentPage ? (
              <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
                <SectionPanel className="h-fit">
                  <div className="space-y-2">
                    {bundle.pages.map((page) => (
                      <button key={page.id} onClick={() => setSelectedPage(page.page_number)} className={`w-full rounded-md border px-3 py-2 text-left text-sm ${selectedPage === page.page_number ? "border-blue-400 bg-blue-500/15 text-blue-100" : "border-white/10 text-slate-400"}`}>
                        {page.page_number}. {page.title}
                      </button>
                    ))}
                  </div>
                </SectionPanel>
                <div className="space-y-5">
                  <BpPagePreview page={currentPage} />
                  <SectionPanel>
                    <h2 className="text-lg font-semibold text-white">后台交付稿编辑</h2>
                    <textarea className="bp-input mt-4 min-h-36" value={currentPage.draft_copy} onChange={(event) => savePage(currentPage, { draft_copy: event.target.value })} />
                    <textarea className="bp-input mt-4 min-h-24" placeholder="内部修改记录" value={currentPage.internal_notes || ""} onChange={(event) => savePage(currentPage, { internal_notes: event.target.value })} />
                  </SectionPanel>
                </div>
              </div>
            ) : null}

            {tab === "材料缺口" ? <GapReportView report={bundle.gap_report} /> : null}

            {tab === "服务申请" ? (
              <div className="grid gap-4">
                {bundle.service_requests.map((request) => (
                  <SectionPanel key={request.id}>
                    <div className="text-sm text-blue-300">{request.service_type}</div>
                    <h2 className="mt-2 text-xl font-semibold text-white">{request.contact_name || "未填写称呼"}</h2>
                    <div className="mt-3 grid gap-3 text-sm text-slate-300 md:grid-cols-3">
                      <div>微信：{request.contact_wechat || "无"}</div>
                      <div>手机：{request.contact_phone || "无"}</div>
                      <div>邮箱：{request.contact_email || "无"}</div>
                    </div>
                    <p className="mt-4 text-sm leading-6 text-slate-400">{request.user_message || "无服务诉求说明"}</p>
                  </SectionPanel>
                ))}
              </div>
            ) : null}

            {tab === "原始材料" ? (
              <div className="grid gap-4">
                {bundle.raw_materials.map((material) => (
                  <SectionPanel key={material.id}>
                    <div className="text-sm text-blue-300">{material.title}</div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">{material.content}</p>
                  </SectionPanel>
                ))}
              </div>
            ) : null}

            {tab === "版本记录" ? (
              <div className="grid gap-4">
                {bundle.versions.map((version) => (
                  <SectionPanel key={version.id}>
                    <div className="text-sm text-slate-500">{version.created_at}</div>
                    <h2 className="mt-2 font-semibold text-white">{version.version_name}</h2>
                    <p className="mt-2 text-sm text-slate-400">{version.change_summary}</p>
                  </SectionPanel>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
