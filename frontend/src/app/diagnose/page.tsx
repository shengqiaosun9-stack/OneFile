"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpSend } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

const stages = [
  { value: "idea", label: "只有想法" },
  { value: "prototype", label: "已有 Demo / 原型" },
  { value: "pilot", label: "已有产品或客户试用" },
  { value: "delivery", label: "已有交付" },
  { value: "revenue", label: "已有订单 / 收入" },
  { value: "scaling", label: "已经参加活动 / 路演或进入规模化" },
];

const resourceOptions = ["园区 / 政策", "活动 / 路演", "技术团队", "客户 / 订单", "算力 / 私有化部署", "融资", "内容曝光", "合作伙伴", "还不确定"];

export default function DiagnosePage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    founder_name: "",
    tagline: "",
    stage: "unknown",
    raw_material: "",
    visibility: "private",
    contact_wechat: "",
    contact_phone: "",
    contact_email: "",
  });
  const [resources, setResources] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const toggleResource = (item: string) => {
    setResources((prev) => (prev.includes(item) ? prev.filter((value) => value !== item) : [...prev, item]));
  };

  const submit = async () => {
    setError("");
    if (!form.name.trim() || !form.raw_material.trim()) {
      setError("请至少填写项目名称和原始材料。");
      return;
    }
    setLoading(true);
    try {
      const body = await bpSend<BpBundle>("/api/bp/diagnoses", { ...form, current_resource_need: resources });
      router.push(`/diagnose/${body.project.user_visible_token}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PublicBpShell currentStep="diagnose">
      <section className="mx-auto max-w-5xl px-5 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-white md:text-5xl">先把你的项目材料丢进来</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-400">
            不用写得很正式。你可以粘贴项目介绍、BP 草稿、聊天记录、访谈纪要、园区反馈、活动报名材料、路演口径或口头表达整理稿。OnePitch 会先帮你生成项目初诊报告，并判断当前材料是否适合对外沟通。
          </p>
        </div>

        <SectionPanel>
          <div className="grid gap-5 md:grid-cols-2">
            <Field label="项目名称" required>
              <input className="bp-input" placeholder="例如：AI 慢病用药助手" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </Field>
            <Field label="创始人 / 团队名称">
              <input className="bp-input" placeholder="例如：药师小顾 / 某某团队" value={form.founder_name} onChange={(event) => setForm({ ...form, founder_name: event.target.value })} />
            </Field>
            <Field label="项目一句话" required className="md:col-span-2">
              <textarea className="bp-input min-h-24" placeholder="用一句话说明你在做什么，写不清也没关系" value={form.tagline} onChange={(event) => setForm({ ...form, tagline: event.target.value })} />
            </Field>
            <Field label="当前阶段">
              <select className="bp-input" value={form.stage} onChange={(event) => setForm({ ...form, stage: event.target.value })}>
                <option value="unknown">还不确定</option>
                {stages.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="上传材料">
              <button disabled className="h-10 w-full rounded-md border border-white/10 bg-white/[0.03] text-left text-sm text-slate-500">
                <span className="px-3">选择文件（暂未启用）</span>
              </button>
              <p className="mt-2 text-xs leading-5 text-slate-500">第一版可以先粘贴文本。PDF、Word、图片识别会在后续版本支持。</p>
            </Field>
          </div>

          <div className="mt-5">
            <div className="mb-3 text-sm text-slate-300">当前最想获得什么资源</div>
            <div className="flex flex-wrap gap-2">
              {resourceOptions.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => toggleResource(item)}
                  className={`rounded-md border px-3 py-2 text-sm ${
                    resources.includes(item) ? "border-blue-400 bg-blue-500/15 text-blue-100" : "border-white/10 bg-black/20 text-slate-400 hover:text-white"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <Field label="原始材料" required className="mt-5">
            <textarea
              className="bp-input min-h-64"
              placeholder="粘贴项目介绍、BP 文案、聊天记录、会议纪要、用户反馈、园区反馈等"
              value={form.raw_material}
              onChange={(event) => setForm({ ...form, raw_material: event.target.value })}
            />
          </Field>

          <div className="mt-5 grid gap-4 md:grid-cols-3">
            <Field label="微信">
              <input className="bp-input" placeholder="选填，用于后续服务沟通" value={form.contact_wechat} onChange={(event) => setForm({ ...form, contact_wechat: event.target.value })} />
            </Field>
            <Field label="手机号">
              <input className="bp-input" placeholder="选填" value={form.contact_phone} onChange={(event) => setForm({ ...form, contact_phone: event.target.value })} />
            </Field>
            <Field label="邮箱">
              <input className="bp-input" placeholder="选填" value={form.contact_email} onChange={(event) => setForm({ ...form, contact_email: event.target.value })} />
            </Field>
          </div>

          <div className="mt-5">
            <div className="mb-3 text-sm text-slate-300">项目卡可见方式</div>
            <div className="grid gap-3 md:grid-cols-3">
              {[
                { value: "private", title: "只生成私密诊断报告", body: "适合先自己看，不生成对外项目卡。" },
                { value: "share_card", title: "生成可分享项目卡", body: "适合发给园区、合伙人、活动主办方或合作方。" },
                { value: "anonymous_case", title: "允许匿名案例复盘", body: "隐藏身份后，后续可用于 OnePitch 内容复盘。" },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setForm({ ...form, visibility: item.value })}
                  className={`rounded-lg border p-4 text-left ${form.visibility === item.value ? "border-blue-400 bg-blue-500/15" : "border-white/10 bg-black/20 hover:border-white/25"}`}
                >
                  <div className="text-sm font-semibold text-white">{item.title}</div>
                  <p className="mt-2 text-xs leading-5 text-slate-400">{item.body}</p>
                </button>
              ))}
            </div>
          </div>

          {error ? <div className="mt-4 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <button onClick={submit} disabled={loading} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60">
              {loading ? "正在整理项目逻辑..." : "生成项目诊断报告"}
            </button>
            <SecondaryLink href="/">返回首页</SecondaryLink>
          </div>
          {loading ? <p className="mt-4 text-sm text-slate-500">正在识别表达缺口、资源路径准备度和下一步建议。</p> : null}
        </SectionPanel>
      </section>
    </PublicBpShell>
  );
}

function Field({ label, required, children, className = "" }: { label: string; required?: boolean; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <div className="mb-2 text-sm text-slate-300">
        {label}
        {required ? <span className="ml-1 text-blue-300">*</span> : null}
      </div>
      {children}
    </label>
  );
}
