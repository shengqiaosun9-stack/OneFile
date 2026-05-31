import type { BpPage } from "@/lib/bp-types";

export function BpPagePreview({ page }: { page: BpPage }) {
  return (
    <article className="rounded-lg border border-white/10 bg-black/20 p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-blue-300">第 {page.page_number} 页</div>
          <h2 className="mt-1 text-xl font-semibold text-white">{page.title}</h2>
        </div>
        <span className="rounded-md border border-blue-400/30 bg-blue-500/10 px-2.5 py-1 text-xs text-blue-200">预览版</span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <InfoList title="本页要回答什么" items={[page.question]} />
        <InfoList title="当前已有材料" items={page.existing_materials} />
        <InfoList title="缺失材料" items={page.missing_materials} tone="warning" />
        <InfoList title="资源方可能追问" items={page.likely_questions} />
      </div>
      <div className="mt-4 rounded-md border border-white/10 bg-[#020617] p-4">
        <div className="mb-2 text-xs text-slate-500">页面文案预览</div>
        <p className="text-sm leading-6 text-slate-200">{page.draft_copy}</p>
      </div>
    </article>
  );
}

function InfoList({ title, items, tone = "default" }: { title: string; items: string[]; tone?: "default" | "warning" }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.025] p-4">
      <div className={`mb-2 text-xs ${tone === "warning" ? "text-amber-300" : "text-slate-500"}`}>{title}</div>
      <ul className="space-y-2 text-sm leading-6 text-slate-200">
        {(items?.length ? items : ["待补充"]).map((item, index) => (
          <li key={`${title}-${index}`} className="flex gap-2">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
