"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { bpGet } from "@/lib/bp-api";
import type { BpProject } from "@/lib/bp-types";

const statusLabel: Record<string, string> = {
  submitted: "已提交",
  new_service_request: "新服务申请",
  to_contact: "待联系",
  contacted: "已联系",
  to_quote: "待报价",
  quoted: "已报价",
  refining: "精修中",
  delivered: "已交付",
  paused: "暂停",
  abandoned: "放弃",
};

export default function OpsBpProjectsPage() {
  const [projects, setProjects] = useState<BpProject[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    bpGet<{ projects: BpProject[] }>("/api/ops/bp/projects")
      .then((body) => setProjects(body.projects || []))
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"));
  }, []);

  const serviceCount = projects.filter((item) => item.internal_status === "new_service_request").length;
  const highCount = projects.filter((item) => item.priority === "high").length;

  return (
    <main className="min-h-screen bg-[#020617] text-slate-50">
      <header className="border-b border-white/10 bg-[#020617]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <div className="text-sm font-semibold tracking-[0.16em] text-white">OnePitch Ops</div>
            <div className="mt-1 text-xs text-slate-500">BP 提交项目交付工作台</div>
          </div>
          <div className="flex gap-3">
            <Link href="/" className="rounded-md border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/[0.04]">
              前台首页
            </Link>
            <Link href="/ops/bp/followups" className="rounded-md bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-500">
              跟进队列
            </Link>
          </div>
        </div>
      </header>
      <section className="mx-auto max-w-7xl px-5 py-8">
        <div className="grid gap-4 md:grid-cols-4">
          <Kpi label="提交项目" value={projects.length} />
          <Kpi label="新服务申请" value={serviceCount} />
          <Kpi label="高优先级" value={highCount} />
          <Kpi label="待下一步" value={projects.filter((item) => item.next_action).length} />
        </div>

        {error ? <div className="mt-5 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}

        <div className="mt-6 overflow-hidden rounded-lg border border-white/10">
          <table className="w-full min-w-[960px] border-collapse bg-white/[0.025] text-sm">
            <thead className="bg-white/[0.04] text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">项目</th>
                <th className="px-4 py-3">阶段</th>
                <th className="px-4 py-3">准备度</th>
                <th className="px-4 py-3">推荐路径</th>
                <th className="px-4 py-3">服务状态</th>
                <th className="px-4 py-3">预算信号</th>
                <th className="px-4 py-3">下一步</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id} className="border-t border-white/10">
                  <td className="px-4 py-4">
                    <Link href={`/ops/bp/${project.id}`} className="font-medium text-white hover:text-blue-200">
                      {project.name}
                    </Link>
                    <div className="mt-1 max-w-sm truncate text-xs text-slate-500">{project.tagline}</div>
                  </td>
                  <td className="px-4 py-4 text-slate-300">{project.stage}</td>
                  <td className="px-4 py-4 text-blue-200">{project.readiness_score}</td>
                  <td className="px-4 py-4 text-slate-300">{project.recommended_path}</td>
                  <td className="px-4 py-4 text-slate-300">{statusLabel[project.internal_status || "submitted"] || project.internal_status}</td>
                  <td className="px-4 py-4 text-slate-300">{project.budget_signal || "unknown"}</td>
                  <td className="px-4 py-4 text-slate-300">{project.next_action || "待判断"}</td>
                </tr>
              ))}
              {!projects.length ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    还没有用户提交项目。前台 `/diagnose` 生成后会出现在这里。
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-3xl font-semibold text-white">{value}</div>
    </div>
  );
}
