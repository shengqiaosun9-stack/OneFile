"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { bpGet } from "@/lib/bp-api";
import type { BpNextAction } from "@/lib/bp-types";

export default function OpsBpFollowupsPage() {
  const [actions, setActions] = useState<BpNextAction[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    bpGet<{ next_actions: BpNextAction[] }>("/api/ops/bp/followups")
      .then((body) => setActions(body.next_actions || []))
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"));
  }, []);

  return (
    <main className="min-h-screen bg-[#020617] text-slate-50">
      <header className="border-b border-white/10">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div>
            <Link href="/ops/bp" className="text-xs text-blue-300 hover:text-blue-200">
              返回 BP 工作台
            </Link>
            <h1 className="mt-1 text-xl font-semibold text-white">BP 服务跟进队列</h1>
          </div>
        </div>
      </header>
      <section className="mx-auto max-w-6xl px-5 py-8">
        {error ? <div className="rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}
        <div className="grid gap-4">
          {actions.map((action) => (
            <Link key={action.id} href={`/ops/bp/${action.project_id}`} className="rounded-lg border border-white/10 bg-white/[0.035] p-5 hover:border-blue-400/40 hover:bg-blue-500/10">
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span className="rounded-md border border-blue-400/30 bg-blue-500/10 px-2.5 py-1 text-blue-200">{action.priority}</span>
                <span>{action.status}</span>
                <span>{action.due_date || "未设截止时间"}</span>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">{action.action}</h2>
              <p className="mt-2 text-sm text-slate-400">负责人：{action.owner || "OnePitch"}</p>
            </Link>
          ))}
          {!actions.length ? <div className="rounded-lg border border-white/10 bg-white/[0.035] p-12 text-center text-slate-500">暂无待跟进动作。</div> : null}
        </div>
      </section>
    </main>
  );
}
