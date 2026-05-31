import type { BpGapReport } from "@/lib/bp-types";

const severityClass: Record<string, string> = {
  必须补: "border-red-400/30 bg-red-500/10 text-red-200",
  建议补: "border-amber-400/30 bg-amber-500/10 text-amber-200",
  可后补: "border-blue-400/30 bg-blue-500/10 text-blue-200",
};

export function GapReportView({ report }: { report: BpGapReport }) {
  return (
    <div className="space-y-4">
      {(report.items || []).map((item, index) => (
        <article key={`${item.page_number}-${index}`} className="rounded-lg border border-white/10 bg-black/20 p-5">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className={`rounded-md border px-2.5 py-1 text-xs ${severityClass[item.severity] || severityClass["建议补"]}`}>{item.severity}</span>
            <span className="text-xs text-slate-500">
              {item.page_number ? `第 ${item.page_number} 页 ${item.page_title}` : item.page_title || "整体"}
            </span>
          </div>
          <h3 className="text-base font-semibold text-white">{item.gap_name}</h3>
          <p className="mt-3 text-sm leading-6 text-slate-300">{item.why_it_matters}</p>
          <div className="mt-4 rounded-md border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-1 text-xs text-slate-500">建议补充</div>
            <p className="text-sm leading-6 text-slate-100">{item.recommended_fix}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
