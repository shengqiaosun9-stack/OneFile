import Link from "next/link";
import { ArrowRight, FileCheck2, ListChecks, SearchCheck } from "lucide-react";

import { PublicBpShell, PrimaryLink, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";

const outputs = [
  {
    title: "项目理解草稿",
    body: "把项目名、一句话、阶段、客户、问题、方案、商业模式和资源诉求先梳理清楚。",
    icon: SearchCheck,
  },
  {
    title: "14 页 BP 清单预览",
    body: "不是直接生成融资 PPT，而是告诉你对外沟通时每一页应该讲什么、缺什么。",
    icon: ListChecks,
  },
  {
    title: "材料缺口报告",
    body: "指出园区、投资人、技术方或合作方可能继续追问的问题。",
    icon: FileCheck2,
  },
];

const fitItems = ["AI/OPC 早期项目", "准备进园区或对接政策资源的项目", "想找技术、订单、算力、资金或合作方的项目", "已有业务但不知道如何讲清楚的传统产业 AI 项目", "准备做访谈、路演、闭门会介绍的项目"];

export default function HomePage() {
  return (
    <PublicBpShell>
      <section className="mx-auto grid max-w-6xl gap-10 px-5 py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-white md:text-6xl">把混乱项目材料，整理成资源方看得懂的 BP 清单</h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
            OnePitch 帮 AI/OPC 早期项目完成项目诊断、BP 缺口识别和外部沟通材料预整理，让园区、投资人、技术方和合作方更快判断你在做什么、缺什么、下一步能不能聊。
          </p>
          <div className="mt-6 flex flex-wrap gap-2 text-sm text-slate-300">
            {["不做完整融资 BP", "不做花哨 PPT", "先判断项目是否讲清楚"].map((item) => (
              <span key={item} className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2">
                {item}
              </span>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <PrimaryLink href="/diagnose">
              开始项目诊断 <ArrowRight className="ml-2 size-4" />
            </PrimaryLink>
            <SecondaryLink href="#bp-structure">查看 14 页清单结构</SecondaryLink>
          </div>
        </div>
        <SectionPanel>
          <div className="mb-5 text-sm text-blue-300">诊断输出预览</div>
          <div className="space-y-4">
            {outputs.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.title} className="rounded-md border border-white/10 bg-[#020617] p-4">
                  <div className="flex items-center gap-3">
                    <Icon className="size-5 text-blue-300" />
                    <h2 className="font-medium text-white">{item.title}</h2>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-400">{item.body}</p>
                </div>
              );
            })}
          </div>
        </SectionPanel>
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-20">
        <div className="grid gap-5 md:grid-cols-2">
          <SectionPanel>
            <h2 className="text-2xl font-semibold text-white">适合这些项目先做一次诊断</h2>
            <div className="mt-6 space-y-3">
              {fitItems.map((item) => (
                <div key={item} className="flex gap-3 rounded-md border border-white/10 bg-black/20 p-3 text-sm text-slate-300">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </SectionPanel>
          <SectionPanel>
            <h2 className="text-2xl font-semibold text-white">从混乱材料到可沟通清单</h2>
            <div className="mt-6 space-y-4">
              {["粘贴项目材料", "生成项目理解草稿", "查看 14 页 BP 清单", "识别材料缺口", "申请真人精修或资源路径建议"].map((item, index) => (
                <div key={item} className="flex items-center gap-3 text-sm text-slate-300">
                  <span className="flex size-7 items-center justify-center rounded-md bg-blue-600/20 text-xs text-blue-200">{index + 1}</span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </SectionPanel>
        </div>
      </section>

      <section id="bp-structure" className="border-y border-white/10 bg-white/[0.02]">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <h2 className="text-2xl font-semibold text-white">14 页标准外部沟通 BP 清单</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">它不是完整融资 BP，也不是 PPT 设计稿，而是一份外部沟通前的页级结构清单。</p>
          <div className="mt-8 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {["项目封面", "项目逻辑", "行业痛点", "市场切口", "现有方案缺口", "当前进展 / 业务基础", "为什么现在", "产品闭环", "产品 / 系统结构", "商业模式", "竞争定位", "核心壁垒", "增长计划", "团队与资源诉求"].map((item, index) => (
              <div key={item} className="rounded-md border border-white/10 bg-[#020617] p-4 text-sm text-slate-300">
                <span className="mr-2 text-blue-300">{String(index + 1).padStart(2, "0")}</span>
                {item}
              </div>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <PrimaryLink href="/diagnose">开始项目诊断</PrimaryLink>
            <Link href="/library" className="text-sm text-slate-500 hover:text-slate-300">
              查看旧项目库
            </Link>
          </div>
        </div>
      </section>
    </PublicBpShell>
  );
}
