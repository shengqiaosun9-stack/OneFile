import Link from "next/link";
import type { ReactNode } from "react";

type PublicBpShellProps = {
  children: ReactNode;
  currentStep?: "diagnose" | "report" | "bp" | "gaps" | "service";
  token?: string;
};

const steps = [
  { key: "report", label: "项目诊断", href: (token: string) => `/diagnose/${token}` },
  { key: "bp", label: "BP 清单", href: (token: string) => `/diagnose/${token}/bp` },
  { key: "gaps", label: "材料缺口", href: (token: string) => `/diagnose/${token}/gaps` },
  { key: "service", label: "申请服务", href: (token: string) => `/diagnose/${token}/service` },
] as const;

export function PublicBpShell({ children, currentStep, token }: PublicBpShellProps) {
  return (
    <main className="min-h-screen bg-[#020617] text-slate-50">
      <header className="sticky top-0 z-30 border-b border-white/10 bg-[#020617]/92 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <Link href="/" className="text-sm font-semibold tracking-[0.18em] text-white">
            OnePitch
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-slate-300 md:flex">
            <Link href="/diagnose" className="hover:text-white">
              项目诊断
            </Link>
            {token ? (
              <>
                <Link href={`/diagnose/${token}/bp`} className="hover:text-white">
                  14页BP清单
                </Link>
                <Link href={`/diagnose/${token}/service`} className="hover:text-white">
                  申请服务
                </Link>
              </>
            ) : null}
            <Link href="/diagnose" className="rounded-md bg-blue-600 px-3 py-2 text-white hover:bg-blue-500">
              开始诊断
            </Link>
          </nav>
        </div>
        {token && currentStep && currentStep !== "diagnose" ? (
          <div className="mx-auto flex max-w-6xl gap-2 overflow-x-auto px-5 pb-4">
            {steps.map((step, index) => {
              const active = currentStep === step.key;
              return (
                <Link
                  key={step.key}
                  href={step.href(token)}
                  className={`min-w-fit rounded-md border px-3 py-2 text-xs ${
                    active ? "border-blue-500 bg-blue-500/15 text-blue-200" : "border-white/10 bg-white/[0.03] text-slate-400"
                  }`}
                >
                  {index + 1}. {step.label}
                </Link>
              );
            })}
          </div>
        ) : null}
      </header>
      {children}
    </main>
  );
}

export function SectionPanel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-lg border border-white/10 bg-white/[0.035] p-5 shadow-[0_18px_60px_rgba(2,6,23,0.35)] ${className}`}>{children}</section>;
}

export function FieldBlock({ label, value }: { label: string; value?: string | number | string[] }) {
  const rendered = Array.isArray(value) ? value.join("、") : String(value || "待补充");
  return (
    <div className="rounded-md border border-white/10 bg-black/20 p-4">
      <div className="mb-2 text-xs text-slate-500">{label}</div>
      <div className="text-sm leading-6 text-slate-100">{rendered}</div>
    </div>
  );
}

export function PrimaryLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex h-10 items-center justify-center rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500">
      {children}
    </Link>
  );
}

export function SecondaryLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex h-10 items-center justify-center rounded-md border border-white/10 px-4 text-sm font-medium text-slate-200 hover:border-white/25 hover:bg-white/[0.04]">
      {children}
    </Link>
  );
}
