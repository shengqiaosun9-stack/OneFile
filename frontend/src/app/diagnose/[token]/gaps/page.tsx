"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { GapReportView } from "@/components/onepitch-bp/GapReport";
import { PrimaryLink, PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet } from "@/lib/bp-api";
import type { BpBundle } from "@/lib/bp-types";

const services = [
  {
    title: "项目初诊",
    body: "适合：你不确定项目现在是否适合对外沟通。产出：一次项目表达和资源路径判断。",
    hrefType: "project_diagnosis",
  },
  {
    title: "标准项目档案人工精修",
    body: "适合：你已有材料，但表达混乱。产出：一份更清楚的项目档案和对外介绍。",
    hrefType: "manual_refinement",
  },
  {
    title: "BP 清单 / 园区材料人工重构",
    body: "适合：你准备对接园区、投资人或合作方。产出：更适合外部沟通的 BP 页级清单。",
    hrefType: "bp_restructure",
  },
  {
    title: "资源路径推进",
    body: "适合：你已有项目基础，但不知道下一步该找谁。产出：资源路径建议和对接前材料准备。",
    hrefType: "resource_path",
  },
];

export default function GapReportPage() {
  const { token } = useParams<{ token: string }>();
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    bpGet<BpBundle>(`/api/bp/diagnoses/${token}`)
      .then(setBundle)
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"));
  }, [token]);

  return (
    <PublicBpShell currentStep="gaps" token={token}>
      <section className="mx-auto max-w-6xl px-5 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-white md:text-5xl">材料缺口报告</h1>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">下面这些缺口，会直接影响园区、投资人、技术方或合作方是否愿意继续沟通。</p>
        </div>
        {error ? <div className="rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}
        {bundle ? (
          <div className="space-y-8">
            <GapReportView report={bundle.gap_report} />
            <SectionPanel>
              <h2 className="text-2xl font-semibold text-white">如果你需要继续推进</h2>
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                {services.map((item) => (
                  <a key={item.title} href={`/diagnose/${token}/service?type=${item.hrefType}`} className="rounded-lg border border-white/10 bg-black/20 p-5 hover:border-blue-400/40 hover:bg-blue-500/10">
                    <h3 className="font-semibold text-white">{item.title}</h3>
                    <p className="mt-3 text-sm leading-6 text-slate-400">{item.body}</p>
                  </a>
                ))}
              </div>
              <div className="mt-6 flex flex-wrap gap-3">
                <PrimaryLink href={`/diagnose/${token}/service`}>申请真人服务</PrimaryLink>
                <SecondaryLink href={`/diagnose/${token}/bp`}>返回 BP 清单</SecondaryLink>
              </div>
            </SectionPanel>
          </div>
        ) : null}
      </section>
    </PublicBpShell>
  );
}
