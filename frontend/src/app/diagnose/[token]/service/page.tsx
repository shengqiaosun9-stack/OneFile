"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet, bpSend } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

const serviceTypes = [
  { value: "project_diagnosis", title: "项目表达体检 / 初诊", body: "适合不知道项目是否讲清楚的早期项目。交付：人工补充点评、3 个关键表达问题和下一步建议。" },
  { value: "manual_refinement", title: "标准项目档案人工精修", body: "适合已有材料但表达混乱的项目。交付：项目一句话、项目逻辑、资源诉求、1 页项目卡和外部沟通问答。" },
  { value: "bp_restructure", title: "园区 / 活动 / 路演材料重构", body: "适合准备参加园区申请、OPC 活动、项目路演或合作方沟通的项目。交付：路演口径、项目卡、BP 结构清单和关键页面文案。" },
  { value: "resource_path", title: "资源路径推进", body: "适合已有项目基础，但不知道下一步该找园区、客户、技术、投资人、算力还是内容资源的项目。" },
];

export default function ServiceRequestPage() {
  const { token } = useParams<{ token: string }>();
  const search = useSearchParams();
  const defaultType = search.get("type") || "project_diagnosis";
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [form, setForm] = useState({
    service_type: defaultType,
    contact_name: "",
    contact_wechat: "",
    contact_phone: "",
    contact_email: "",
    contact_preference: "",
    urgent_problem: "",
    budget_signal: "unknown",
    authorized_material_review: true,
    user_message: "",
  });
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    bpGet<BpBundle>(`/api/bp/diagnoses/${token}`).then(setBundle).catch(() => undefined);
  }, [token]);

  const selected = useMemo(() => serviceTypes.find((item) => item.value === form.service_type) || serviceTypes[0], [form.service_type]);

  const submit = async () => {
    setError("");
    if (!form.contact_name.trim() || ![form.contact_wechat, form.contact_phone, form.contact_email].some((item) => item.trim())) {
      setError("请填写称呼和至少一种联系方式。");
      return;
    }
    setLoading(true);
    try {
      await bpSend(`/api/bp/diagnoses/${token}/service-requests`, form);
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PublicBpShell currentStep="service" token={token}>
      <section className="mx-auto max-w-5xl px-5 py-12">
        {submitted ? (
          <SectionPanel>
            <h1 className="text-3xl font-semibold text-white">服务申请已提交</h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-400">我们已经收到你的项目材料和服务意向。下一步会先查看你的诊断报告和材料缺口，再决定适合的沟通方式。</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button onClick={() => navigator.clipboard?.writeText(`${window.location.origin}/diagnose/${token}`)} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500">
                复制诊断链接
              </button>
              <SecondaryLink href={`/diagnose/${token}`}>返回诊断报告</SecondaryLink>
            </div>
          </SectionPanel>
        ) : (
          <div className="space-y-6">
            <div>
              <h1 className="text-3xl font-semibold text-white md:text-5xl">申请真人项目服务</h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">如果你希望继续把项目材料整理成更适合园区、活动、投资人、技术方或合作方阅读的版本，可以提交服务申请。我们会先根据你的诊断报告和材料缺口，判断适合的服务方式。</p>
            </div>

            {bundle ? (
              <SectionPanel>
                <div className="text-sm text-slate-500">当前诊断项目</div>
                <div className="mt-2 text-xl font-semibold text-white">{bundle.project.name}</div>
                <div className="mt-2 text-sm text-slate-400">{bundle.project.recommended_path}</div>
              </SectionPanel>
            ) : null}

            <SectionPanel>
              <h2 className="text-xl font-semibold text-white">选择服务类型</h2>
              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {serviceTypes.map((item) => (
                  <button
                    key={item.value}
                    onClick={() => setForm({ ...form, service_type: item.value })}
                    className={`rounded-lg border p-4 text-left ${
                      form.service_type === item.value ? "border-blue-400 bg-blue-500/15" : "border-white/10 bg-black/20 hover:border-white/25"
                    }`}
                  >
                    <div className="font-semibold text-white">{item.title}</div>
                    <p className="mt-2 text-sm leading-6 text-slate-400">{item.body}</p>
                  </button>
                ))}
              </div>
              <p className="mt-4 text-sm text-blue-200">已选择：{selected.title}</p>
            </SectionPanel>

            <SectionPanel>
              <h2 className="text-xl font-semibold text-white">联系方式</h2>
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <input className="bp-input" placeholder="你的称呼" value={form.contact_name} onChange={(event) => setForm({ ...form, contact_name: event.target.value })} />
                <input className="bp-input" placeholder="微信号" value={form.contact_wechat} onChange={(event) => setForm({ ...form, contact_wechat: event.target.value })} />
                <input className="bp-input" placeholder="手机号（选填）" value={form.contact_phone} onChange={(event) => setForm({ ...form, contact_phone: event.target.value })} />
                <input className="bp-input" placeholder="邮箱（选填）" value={form.contact_email} onChange={(event) => setForm({ ...form, contact_email: event.target.value })} />
                <input className="bp-input md:col-span-2" placeholder="希望联系时间（选填）" value={form.contact_preference} onChange={(event) => setForm({ ...form, contact_preference: event.target.value })} />
                <select className="bp-input" value={form.budget_signal} onChange={(event) => setForm({ ...form, budget_signal: event.target.value })}>
                  <option value="unknown">预算情况：还不确定</option>
                  <option value="weak">预算较弱，先了解</option>
                  <option value="medium">有初步预算</option>
                  <option value="strong">预算明确，准备推进</option>
                </select>
                <label className="flex min-h-10 items-center gap-2 rounded-md border border-white/10 bg-white/[0.03] px-3 text-sm text-slate-300">
                  <input type="checkbox" checked={form.authorized_material_review} onChange={(event) => setForm({ ...form, authorized_material_review: event.target.checked })} />
                  授权 OnePitch 查看本次完整诊断材料
                </label>
                <textarea className="bp-input min-h-24 md:col-span-2" placeholder="当前最急的问题。例如：我想知道是否适合进园区，或者是否需要先补客户案例。" value={form.urgent_problem} onChange={(event) => setForm({ ...form, urgent_problem: event.target.value })} />
                <textarea className="bp-input min-h-28 md:col-span-2" placeholder="补充说明（选填）：希望达成什么结果、准备对接谁、是否有时间节点。" value={form.user_message} onChange={(event) => setForm({ ...form, user_message: event.target.value })} />
              </div>
              <p className="mt-4 text-xs leading-5 text-slate-500">你的联系方式只用于本次项目诊断和服务沟通，不会展示在公开页面。OnePitch 不承诺融资、入驻、成交或撮合结果。</p>
              {error ? <div className="mt-4 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}
              <div className="mt-6 flex flex-wrap gap-3">
                <button onClick={submit} disabled={loading} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60">
                  {loading ? "正在提交..." : "提交服务申请"}
                </button>
                <SecondaryLink href={`/diagnose/${token}`}>先不申请，保存诊断链接</SecondaryLink>
              </div>
            </SectionPanel>
          </div>
        )}
      </section>
    </PublicBpShell>
  );
}
