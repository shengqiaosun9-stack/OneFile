"use client";

import Image from "next/image";
import { forwardRef, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";

import { PrimaryLink, PublicBpShell, SecondaryLink, SectionPanel } from "@/components/onepitch-bp/PublicBpShell";
import { bpGet } from "@/lib/bp-api";
import type { BpBundle, BpProjectInsight } from "@/lib/bp-types";

const boundaryText = "这张卡不包含完整 BP、客户名单、财务数据、原始材料和技术细节。更详细信息需在建立沟通后，由项目方授权单独提供。";

export default function ProjectShareCardPage() {
  const { token } = useParams<{ token: string }>();
  const [bundle, setBundle] = useState<BpBundle | null>(null);
  const [error, setError] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [notice, setNotice] = useState("");
  const [imageLoading, setImageLoading] = useState(false);
  const [generatedImage, setGeneratedImage] = useState("");
  const posterRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    setShareUrl(window.location.href);
  }, []);

  useEffect(() => {
    bpGet<BpBundle>(`/api/bp/diagnoses/${token}`)
      .then(setBundle)
      .catch((err) => setError(err instanceof Error ? err.message : "读取失败。"));
  }, [token]);

  useEffect(() => {
    if (!shareUrl) return;
    let canceled = false;
    async function buildQr() {
      const QRCode = await import("qrcode");
      const nextQr = await QRCode.toDataURL(shareUrl, {
        width: 220,
        margin: 1,
        color: { dark: "#0f172a", light: "#ffffff" },
      });
      if (!canceled) setQrDataUrl(nextQr);
    }
    buildQr().catch(() => setQrDataUrl(""));
    return () => {
      canceled = true;
    };
  }, [shareUrl]);

  const card = bundle?.insight.share_card;
  const cardTitle = card?.title || bundle?.project.name || "项目判断卡";
  const cardFileName = useMemo(() => `${cardTitle.replace(/[\\/:*?"<>|]+/g, "-")}-OnePitch项目判断卡.png`, [cardTitle]);

  const copyLink = async () => {
    try {
      await navigator.clipboard?.writeText(shareUrl || window.location.href);
      setNotice("项目卡链接已复制。");
    } catch {
      setNotice("复制失败，可以直接复制浏览器地址栏链接。");
    }
  };

  const createImage = async (download: boolean) => {
    if (!posterRef.current) return;
    setImageLoading(true);
    setNotice("");
    try {
      const { toPng } = await import("html-to-image");
      const dataUrl = await toPng(posterRef.current, {
        backgroundColor: "#f5f7fb",
        cacheBust: true,
        pixelRatio: 2,
      });
      setGeneratedImage(dataUrl);
      if (download) {
        const link = document.createElement("a");
        link.download = cardFileName;
        link.href = dataUrl;
        link.click();
        setNotice("已生成并下载项目判断卡图片。");
      } else {
        setNotice("项目卡图片已生成，可以继续点击下载。");
      }
    } catch {
      setNotice("图片生成失败。链接复制仍可使用，建议直接截图竖版卡区域。");
    } finally {
      setImageLoading(false);
    }
  };

  return (
    <PublicBpShell currentStep="card" token={token}>
      <section className="mx-auto max-w-6xl px-5 py-12">
        <div className="mb-8 grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
          <div>
            <div className="text-sm text-blue-300">OnePitch 项目判断卡</div>
            <h1 className="mt-2 text-3xl font-semibold text-white md:text-5xl">还不方便发完整 BP？先发这张项目判断卡。</h1>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">
              让对方先看懂项目方向、当前阶段、资源诉求和是否值得继续聊；完整 BP、客户数据和技术细节可以等建立信任后再单独沟通。
            </p>
          </div>
          <SectionPanel className="p-4">
            <div className="text-xs text-slate-500">分享边界</div>
            <p className="mt-2 text-sm leading-6 text-slate-300">{card?.sensitive_info_boundary || boundaryText}</p>
          </SectionPanel>
        </div>

        {error ? <div className="rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div> : null}

        {bundle && card ? (
          <div className="grid gap-6 lg:grid-cols-[1fr_480px]">
            <div className="space-y-6">
              <SectionPanel>
                <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
                  <div>
                    <div className="text-xs tracking-[0.18em] text-blue-300">一句话判断</div>
                    <h2 className="mt-3 text-3xl font-semibold text-white">{text(card.title, bundle.project.name)}</h2>
                    <p className="mt-4 text-base leading-7 text-slate-300">{text(card.one_line, bundle.project.tagline)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge>{text(card.stage, bundle.project.stage)}</Badge>
                    <Badge>{text(card.category, "AI / OPC 项目")}</Badge>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 md:grid-cols-2">
                  <Info label="方向 / 类型" value={card.category} />
                  <Info label="推荐沟通路径" value={card.recommended_path} />
                </div>
              </SectionPanel>

              <SectionPanel>
                <h2 className="text-2xl font-semibold text-white">项目在解决什么</h2>
                <div className="mt-5 grid gap-4 md:grid-cols-2">
                  <Info label="场景" value={card.scenario} />
                  <Info label="目标用户" value={card.target_user || card.target_customer} />
                  <Info label="核心问题" value={card.core_problem} />
                  <Info label="解决方案" value={card.solution} />
                  <Info label="AI 的作用" value={card.ai_role} className="md:col-span-2" />
                </div>
              </SectionPanel>

              <SectionPanel>
                <h2 className="text-2xl font-semibold text-white">现在做到哪一步</h2>
                <div className="mt-5 grid gap-4 md:grid-cols-2">
                  <Info label="当前进展" value={card.current_progress} />
                  <Info label="已有轻证据" value={card.evidence} />
                  <Info label="商业模式状态" value={card.business_model_status} />
                  <ListBlock title="待补材料" items={card.gaps} tone="warning" />
                </div>
              </SectionPanel>

              <SectionPanel>
                <h2 className="text-2xl font-semibold text-white">供需关系</h2>
                <div className="mt-5 grid gap-4 md:grid-cols-3">
                  <ListBlock title="当前需要" items={card.current_needs || asList(card.resource_ask)} />
                  <ListBlock title="可以提供" items={card.can_provide} />
                  <ListBlock title="适合对接" items={card.suitable_for} />
                </div>
              </SectionPanel>

              <SectionPanel>
                <div className="flex flex-wrap gap-3">
                  <button onClick={copyLink} className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500">
                    复制项目卡链接
                  </button>
                  <button onClick={() => createImage(false)} disabled={imageLoading} className="h-10 rounded-md border border-white/10 px-4 text-sm font-medium text-slate-200 hover:border-white/25 hover:bg-white/[0.04] disabled:opacity-60">
                    {imageLoading ? "正在生成..." : "生成项目卡图片"}
                  </button>
                  <button onClick={() => createImage(true)} disabled={imageLoading} className="h-10 rounded-md border border-blue-400/40 px-4 text-sm font-medium text-blue-100 hover:bg-blue-500/10 disabled:opacity-60">
                    下载带二维码项目卡
                  </button>
                  <SecondaryLink href={`/diagnose/${token}`}>回到诊断报告</SecondaryLink>
                  <PrimaryLink href={`/diagnose/${token}/service?type=manual_refinement`}>申请项目档案精修</PrimaryLink>
                </div>
                {generatedImage ? (
                  <a href={generatedImage} download={cardFileName} className="mt-4 inline-flex text-sm text-blue-200 hover:text-blue-100">
                    已生成图片，点击这里再次下载
                  </a>
                ) : null}
                {notice ? <p className="mt-4 text-sm text-slate-400">{notice}</p> : null}
              </SectionPanel>
            </div>

            <div className="lg:sticky lg:top-28 lg:self-start">
              <SharePoster ref={posterRef} bundle={bundle} qrDataUrl={qrDataUrl} />
            </div>
          </div>
        ) : !error ? (
          <div className="text-slate-400">正在生成项目判断卡...</div>
        ) : null}
      </section>
    </PublicBpShell>
  );
}

const SharePoster = forwardRef<HTMLElement, { bundle: BpBundle; qrDataUrl: string }>(function SharePoster({ bundle, qrDataUrl }, ref) {
  const card = bundle.insight.share_card || ({} as NonNullable<BpProjectInsight["share_card"]>);
  return (
    <article ref={ref} className="mx-auto w-full max-w-[460px] rounded-lg bg-[#f5f7fb] p-5 text-[#111827] shadow-[0_24px_90px_rgba(15,23,42,0.35)]">
      <div className="rounded-md bg-[#0f172a] p-5 text-white">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] font-medium tracking-[0.22em] text-blue-200">ONEPITCH</div>
            <div className="mt-2 text-xs text-slate-300">项目判断卡</div>
          </div>
          <span className="rounded-md bg-blue-500/15 px-2.5 py-1 text-[11px] text-blue-100">半公开</span>
        </div>
        <h2 className="mt-6 text-2xl font-semibold leading-tight">{text(card.title, bundle.project.name)}</h2>
        <p className="mt-3 text-sm leading-6 text-slate-200">{text(card.one_line, bundle.project.tagline)}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <PosterBadge>{text(card.stage, bundle.project.stage)}</PosterBadge>
          <PosterBadge>{text(card.category, "AI / OPC 项目")}</PosterBadge>
        </div>
      </div>

      <PosterSection title="项目在解决什么">
        <PosterField label="目标用户" value={card.target_user || card.target_customer} />
        <PosterField label="核心问题" value={card.core_problem} />
        <PosterField label="解决方案" value={card.solution} />
        <PosterField label="AI 作用" value={card.ai_role} />
      </PosterSection>

      <PosterSection title="现在做到哪一步">
        <PosterField label="当前进展" value={card.current_progress} />
        <PosterField label="已有轻证据" value={card.evidence} />
        <PosterField label="商业模式" value={card.business_model_status} />
      </PosterSection>

      <PosterSection title="供需关系">
        <PosterList label="当前需要" items={card.current_needs || asList(card.resource_ask)} />
        <PosterList label="可以提供" items={card.can_provide} />
        <PosterList label="适合对接" items={card.suitable_for} />
      </PosterSection>

      <div className="mt-4 grid grid-cols-[1fr_96px] gap-4 rounded-md bg-white p-4">
        <div>
          <div className="text-xs font-semibold text-slate-900">分享边界</div>
          <p className="mt-2 text-[11px] leading-5 text-slate-500">{card.sensitive_info_boundary || boundaryText}</p>
          <p className="mt-3 text-[10px] leading-4 text-slate-400">Generated by OnePitch. 本卡仅用于项目表达参考，不构成融资、入驻、成交或资源撮合承诺。</p>
        </div>
        <div className="flex flex-col items-center justify-start">
          <div className="flex size-24 items-center justify-center rounded-md border border-slate-200 bg-white">
            {qrDataUrl ? <Image src={qrDataUrl} alt="项目卡二维码" width={88} height={88} unoptimized /> : <span className="text-[10px] text-slate-400">二维码</span>}
          </div>
          <div className="mt-2 text-center text-[10px] text-slate-500">扫码查看项目卡</div>
        </div>
      </div>
    </article>
  );
});

function Info({ label, value, className = "" }: { label: string; value?: string; className?: string }) {
  return (
    <div className={`rounded-md border border-white/10 bg-black/20 p-4 ${className}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-sm leading-6 text-slate-100">{text(value)}</div>
    </div>
  );
}

function ListBlock({ title, items, tone = "default" }: { title: string; items?: string[]; tone?: "default" | "warning" }) {
  const safeItems = list(items);
  return (
    <div className="rounded-md border border-white/10 bg-black/20 p-4">
      <h3 className={`text-sm font-semibold ${tone === "warning" ? "text-amber-200" : "text-blue-200"}`}>{title}</h3>
      <div className="mt-3 space-y-2">
        {safeItems.map((item, index) => (
          <div key={`${title}-${index}`} className="text-sm leading-6 text-slate-300">
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}

function PosterSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-4 rounded-md bg-white p-4">
      <h3 className="text-xs font-semibold text-slate-900">{title}</h3>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function PosterField({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="mt-1 text-xs leading-5 text-slate-800">{text(value)}</div>
    </div>
  );
}

function PosterList({ label, items }: { label: string; items?: string[] }) {
  return (
    <div>
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {list(items).map((item) => (
          <span key={item} className="rounded-md bg-slate-100 px-2 py-1 text-[11px] leading-4 text-slate-700">
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <span className="rounded-md border border-blue-400/30 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-100">{children}</span>;
}

function PosterBadge({ children }: { children: ReactNode }) {
  return <span className="rounded-md border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] text-slate-100">{children}</span>;
}

function text(value?: string, fallback = "待补充") {
  const next = String(value || "").trim();
  return next || fallback;
}

function asList(value?: string) {
  return String(value || "")
    .split(/[，,、/；;|]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function list(items?: string[]) {
  const safe = (items || []).map((item) => String(item || "").trim()).filter(Boolean);
  return safe.length ? safe : ["待补充"];
}
