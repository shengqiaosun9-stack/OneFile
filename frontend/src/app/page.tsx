import Link from "next/link";
import { ArrowRight, ClipboardCheck, FileSearch, Route, Share2, UserCheck } from "lucide-react";

import { PublicBpShell, PrimaryLink, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";

const outputs = [
  { title: "项目初诊", body: "先判断项目是否被讲清楚，而不是直接生成一份看似完整的 BP。", icon: FileSearch },
  { title: "准备度评分", body: "评估材料完整度和表达清晰度，不代表项目好坏或融资价值。", icon: ClipboardCheck },
  { title: "资源路径准备度", body: "分别判断园区、活动、客户、技术、融资、内容等路径还缺什么。", icon: Route },
  { title: "项目判断卡", body: "生成适合先发给合伙人、园区、活动主办方或投资人的半公开判断卡。", icon: Share2 },
  { title: "人工服务入口", body: "当项目准备对外沟通时，进入项目档案精修或园区/路演材料重构。", icon: UserCheck },
];

const fitItems = ["AI/OPC 早期项目", "准备报名活动、路演或闭门会的项目", "正在找园区、政策、客户、技术或算力资源的项目", "已有业务但外部表达不清楚的传统产业 AI 项目", "想把聊天记录、访谈纪要或 BP 草稿整理成项目档案的团队"];

const services = ["项目表达体检", "项目初诊电话", "标准项目档案精修", "园区 / 活动 / 路演材料重构", "资源路径推进"];

export default function HomePage() {
  return (
    <PublicBpShell>
      <section className="mx-auto grid max-w-6xl gap-10 px-5 py-20 lg:grid-cols-[1.04fr_0.96fr] lg:items-center">
        <div>
          <h1 className="max-w-4xl text-4xl font-semibold leading-tight text-white md:text-6xl">先判断你的 AI / OPC 项目，是否已经准备好进入资源方视野</h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
            OnePitch 帮 AI / OPC 早期项目完成项目初诊、材料缺口识别、资源路径准备度判断和项目判断卡生成，让园区、活动主办方、技术方、客户、投资人和合作伙伴更快看懂你是谁、缺什么、下一步能不能聊。
          </p>
          <div className="mt-6 flex flex-wrap gap-2 text-sm text-slate-300">
            {["不是 BP 生成器", "不是项目广场", "先诊断表达和材料", "再进入人工精修"].map((item) => (
              <span key={item} className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2">
                {item}
              </span>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <PrimaryLink href="/diagnose">
              开始项目诊断 <ArrowRight className="ml-2 size-4" />
            </PrimaryLink>
            <SecondaryLink href="#services">了解人工服务</SecondaryLink>
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
            <h2 className="text-2xl font-semibold text-white">从提交材料到服务转化</h2>
            <div className="mt-6 space-y-4">
              {["粘贴项目材料", "生成项目初诊报告", "识别资源路径和材料缺口", "生成项目判断卡", "申请人工精修或资源路径推进"].map((item, index) => (
                <div key={item} className="flex items-center gap-3 text-sm text-slate-300">
                  <span className="flex size-7 items-center justify-center rounded-md bg-blue-600/20 text-xs text-blue-200">{index + 1}</span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </SectionPanel>
        </div>
      </section>

      <section id="services" className="border-y border-white/10 bg-white/[0.02]">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <h2 className="text-2xl font-semibold text-white">免费诊断发现问题，人工服务完成交付</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            OnePitch 不承诺融资、入驻、成交或自动撮合。人工服务聚焦项目表达、材料重构、资源路径判断和对外沟通准备。
          </p>
          <div className="mt-8 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {services.map((item) => (
              <div key={item} className="rounded-md border border-white/10 bg-[#020617] p-4 text-sm text-slate-300">
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
