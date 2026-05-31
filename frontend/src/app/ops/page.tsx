"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, ClipboardList, FileText, Handshake, Inbox, MessagesSquare, Network, Plus, RefreshCw, Save, Target } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type {
  OpsContent,
  OpsInboxItem,
  OpsInteraction,
  OpsNeed,
  OpsNextAction,
  OpsOffer,
  OpsOrganization,
  OpsPerson,
  OpsOpportunity,
  OpsProject,
  OpsSummaryResponse,
} from "@/lib/types";

type TabKey = "inbox" | "opportunities" | "network" | "needs-offers" | "interactions" | "content" | "next-actions";
type RouteTarget = "person" | "organization" | "project" | "need" | "offer" | "interaction" | "content" | "archive";
type RelationshipMap = {
  entity: { type: string; id: string; label: string };
  related: {
    people: OpsPerson[];
    organizations: OpsOrganization[];
    projects: OpsProject[];
    needs: OpsNeed[];
    offers: OpsOffer[];
    interactions: OpsInteraction[];
    contents: OpsContent[];
  };
};

const tabs: Array<{ key: TabKey; label: string; icon: typeof Inbox }> = [
  { key: "inbox", label: "Inbox / 今日入口", icon: Inbox },
  { key: "opportunities", label: "Opportunities / 机会", icon: Target },
  { key: "network", label: "Network / 人脉与机构", icon: Network },
  { key: "needs-offers", label: "Needs & Offers", icon: Handshake },
  { key: "interactions", label: "Interactions / 沟通", icon: MessagesSquare },
  { key: "content", label: "Content / 内容复盘", icon: FileText },
  { key: "next-actions", label: "Next Actions / 行动", icon: ClipboardList },
];

const emptyInbox = {
  raw_text: "",
  capture_type: "note",
  who: "",
  source_channel: "douyin",
  source_detail: "",
  does_what: "",
  can_offer: "",
  currently_needs: "",
  tags: "",
};
const emptyPerson = {
  display_name: "",
  wechat_name: "",
  city: "",
  roles: "founder",
  source_channel: "",
  relationship_temperature: "warm",
  trust_level: "unknown",
  can_offer_summary: "",
  currently_needs_summary: "",
  next_action: "",
  next_action_at: "",
  private_notes: "",
  tags: "",
};
const emptyOrg = {
  name: "",
  type: "other",
  city: "",
  offers: "",
  needs: "",
  cooperation_status: "",
  relationship_temperature: "warm",
  notes: "",
  next_action: "",
  next_action_at: "",
};
const emptyInteraction = {
  date: new Date().toISOString().slice(0, 10),
  channel: "wechat",
  summary: "",
  commitments: "",
  next_action: "",
  next_action_at: "",
  raw_notes: "",
};
const emptyContent = {
  platform: "douyin",
  title: "",
  topic_tags: "",
  published_at: "",
  views: "0",
  likes: "0",
  comments: "0",
  saves: "0",
  shares: "0",
  follows: "0",
  dms: "0",
  insights: "",
  followup_content_ideas: "",
};

function splitList(value: string): string[] {
  return value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.message || "请求失败");
  return res.json() as Promise<T>;
}

async function apiSend<T>(path: string, method: "POST" | "PATCH", body: Record<string, unknown>): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.message || "保存失败");
  return res.json() as Promise<T>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-[var(--muted-foreground)]">
      {label}
      {children}
    </label>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted-foreground)]">{children}</span>;
}

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-[var(--foreground)]">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function SmallEmpty({ text }: { text: string }) {
  return <p className="rounded-md border border-dashed border-[var(--border)] p-4 text-sm text-[var(--muted-foreground)]">{text}</p>;
}

function priorityRank(value: string | undefined): number {
  return value === "high" ? 0 : value === "medium" ? 1 : 2;
}

function personLabel(person: OpsPerson): string {
  return person.name || person.display_name || person.alias || person.wechat_name || person.id;
}

function orgLabel(org: OpsOrganization): string {
  return org.name || org.id;
}

function joinText(value: string[] | undefined): string {
  return value?.filter(Boolean).join("、") || "-";
}

export default function OpsPage() {
  const [tab, setTab] = useState<TabKey>("inbox");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<OpsSummaryResponse["summary"] | null>(null);
  const [inbox, setInbox] = useState<OpsInboxItem[]>([]);
  const [people, setPeople] = useState<OpsPerson[]>([]);
  const [organizations, setOrganizations] = useState<OpsOrganization[]>([]);
  const [opportunities, setOpportunities] = useState<OpsOpportunity[]>([]);
  const [needs, setNeeds] = useState<OpsNeed[]>([]);
  const [offers, setOffers] = useState<OpsOffer[]>([]);
  const [interactions, setInteractions] = useState<OpsInteraction[]>([]);
  const [contents, setContents] = useState<OpsContent[]>([]);
  const [nextActions, setNextActions] = useState<OpsNextAction[]>([]);
  const [relationship, setRelationship] = useState<RelationshipMap | null>(null);
  const [capture, setCapture] = useState(emptyInbox);
  const [routeTarget, setRouteTarget] = useState<RouteTarget>("person");
  const [personForm, setPersonForm] = useState(emptyPerson);
  const [orgForm, setOrgForm] = useState(emptyOrg);
  const [interactionForm, setInteractionForm] = useState(emptyInteraction);
  const [contentForm, setContentForm] = useState(emptyContent);

  async function loadAll() {
    setLoading(true);
    try {
      const [summaryBody, inboxBody, peopleBody, orgBody, opportunityBody, needBody, offerBody, interactionBody, contentBody, nextActionBody] = await Promise.all([
        apiGet<OpsSummaryResponse>("/api/ops/summary"),
        apiGet<{ items: OpsInboxItem[] }>("/api/ops/inbox"),
        apiGet<{ items: OpsPerson[] }>("/api/ops/people"),
        apiGet<{ items: OpsOrganization[] }>("/api/ops/organizations"),
        apiGet<{ items: OpsOpportunity[] }>("/api/ops/opportunities"),
        apiGet<{ items: OpsNeed[] }>("/api/ops/needs"),
        apiGet<{ items: OpsOffer[] }>("/api/ops/offers"),
        apiGet<{ items: OpsInteraction[] }>("/api/ops/interactions"),
        apiGet<{ items: OpsContent[] }>("/api/ops/contents"),
        apiGet<{ items: OpsNextAction[] }>("/api/ops/next-actions"),
      ]);
      setSummary(summaryBody.summary);
      setInbox(inboxBody.items || []);
      setPeople(peopleBody.items || []);
      setOrganizations(orgBody.items || []);
      setOpportunities(opportunityBody.items || []);
      setNeeds(needBody.items || []);
      setOffers(offerBody.items || []);
      setInteractions(interactionBody.items || []);
      setContents(contentBody.items || []);
      setNextActions(nextActionBody.items || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载 Ops 数据失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  const openInbox = useMemo(() => inbox.filter((item) => item.status !== "routed" && item.status !== "archived"), [inbox]);

  async function submitCapture(event: FormEvent) {
    event.preventDefault();
    try {
      await apiSend("/api/ops/inbox", "POST", { ...capture, tags: splitList(capture.tags) });
      setCapture(emptyInbox);
      toast.success("已进入 Inbox");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function routeInbox(item: OpsInboxItem, target: RouteTarget) {
    try {
      await apiSend(`/api/ops/inbox/${item.id}/route`, "POST", { target_type: target, payload: {} });
      toast.success(target === "archive" ? "已归档" : "已分流");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "分流失败");
    }
  }

  async function createPerson(event: FormEvent) {
    event.preventDefault();
    try {
      await apiSend("/api/ops/people", "POST", { ...personForm, roles: splitList(personForm.roles), tags: splitList(personForm.tags) });
      setPersonForm(emptyPerson);
      toast.success("人脉已保存");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function createOrg(event: FormEvent) {
    event.preventDefault();
    try {
      await apiSend("/api/ops/organizations", "POST", orgForm);
      setOrgForm(emptyOrg);
      toast.success("机构已保存");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function createInteraction(event: FormEvent) {
    event.preventDefault();
    try {
      await apiSend("/api/ops/interactions", "POST", interactionForm);
      setInteractionForm(emptyInteraction);
      toast.success("沟通已记录");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function createContent(event: FormEvent) {
    event.preventDefault();
    try {
      await apiSend("/api/ops/contents", "POST", {
        platform: contentForm.platform,
        title: contentForm.title,
        topic_tags: splitList(contentForm.topic_tags),
        published_at: contentForm.published_at,
        metrics: {
          views: Number(contentForm.views || 0),
          likes: Number(contentForm.likes || 0),
          comments: Number(contentForm.comments || 0),
          saves: Number(contentForm.saves || 0),
          shares: Number(contentForm.shares || 0),
          follows: Number(contentForm.follows || 0),
          dms: Number(contentForm.dms || 0),
        },
        insights: contentForm.insights,
        followup_content_ideas: contentForm.followup_content_ideas,
      });
      setContentForm(emptyContent);
      toast.success("内容复盘已保存");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  }

  async function showRelationship(entityType: "person" | "organization" | "project", entityId: string) {
    try {
      const body = await apiGet<RelationshipMap>(`/api/ops/relationship-map/${entityType}/${entityId}`);
      setRelationship(body);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "关系视图加载失败");
    }
  }

  async function copyMessage(text: string) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("话术已复制");
    } catch {
      toast.error("复制失败，可以手动选中文字复制");
    }
  }

  return (
    <main className="min-h-screen bg-[var(--background)] px-4 py-6 text-[var(--foreground)]">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">Local AI/OPC CRM</p>
            <h1 className="text-2xl font-semibold">OneFile Ops</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" onClick={() => void loadAll()} disabled={loading}>
              <RefreshCw className="size-4" />
              刷新
            </Button>
            <Link className="rounded-md px-3 py-2 text-sm text-[var(--muted-foreground)] hover:bg-[var(--muted)]" href="/library">
              公开项目库
            </Link>
          </div>
        </header>

        <div className="grid gap-3 md:grid-cols-4 lg:grid-cols-8">
          {[
            ["Inbox", summary?.inbox_count ?? 0],
            ["People", summary?.people_count ?? 0],
            ["Orgs", summary?.organization_count ?? 0],
            ["Opportunities", summary?.opportunity_count ?? 0],
            ["Needs", summary?.need_count ?? 0],
            ["Offers", summary?.offer_count ?? 0],
            ["Next Actions", summary?.next_action_count ?? 0],
            ["High Priority", summary?.high_priority_next_action_count ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3">
              <p className="text-xs text-[var(--muted-foreground)]">{label}</p>
              <p className="mt-1 text-xl font-semibold">{value}</p>
            </div>
          ))}
        </div>

        <nav className="flex gap-2 overflow-x-auto border-b border-[var(--border)] pb-2">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm ${tab === key ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "bg-[var(--muted)] text-[var(--foreground)]"}`}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </nav>

        {tab === "inbox" ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_1fr]">
            <Section title="Quick Capture">
              <form className="grid gap-3" onSubmit={submitCapture}>
                <Field label="原始内容">
                  <Textarea value={capture.raw_text} onChange={(event) => setCapture({ ...capture, raw_text: event.target.value })} rows={7} placeholder="粘贴私信、聊天摘要、语音转写、项目描述或新想法" />
                </Field>
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="是谁">
                    <Input value={capture.who} onChange={(event) => setCapture({ ...capture, who: event.target.value })} />
                  </Field>
                  <Field label="从哪来">
                    <Input value={capture.source_channel} onChange={(event) => setCapture({ ...capture, source_channel: event.target.value })} />
                  </Field>
                </div>
                <Field label="做什么">
                  <Input value={capture.does_what} onChange={(event) => setCapture({ ...capture, does_what: event.target.value })} />
                </Field>
                <Field label="能提供什么">
                  <Input value={capture.can_offer} onChange={(event) => setCapture({ ...capture, can_offer: event.target.value })} />
                </Field>
                <Field label="缺什么">
                  <Input value={capture.currently_needs} onChange={(event) => setCapture({ ...capture, currently_needs: event.target.value })} />
                </Field>
                <Field label="标签，逗号分隔">
                  <Input value={capture.tags} onChange={(event) => setCapture({ ...capture, tags: event.target.value })} />
                </Field>
                <Button type="submit">
                  <Plus className="size-4" />
                  保存到 Inbox
                </Button>
              </form>
            </Section>
            <Section title={`待清理 Inbox (${openInbox.length})`}>
              <div className="grid gap-3">
                {openInbox.length ? (
                  openInbox.map((item) => (
                    <article key={item.id} className="rounded-md border border-[var(--border)] p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium">{item.who || item.does_what || "未命名线索"}</h3>
                          <p className="mt-1 text-sm text-[var(--muted-foreground)]">{item.source_channel || "未记录来源"} · {item.updated_at}</p>
                        </div>
                        <select className="rounded-md border border-[var(--border)] bg-transparent px-2 py-1 text-sm" value={routeTarget} onChange={(event) => setRouteTarget(event.target.value as RouteTarget)}>
                          {["person", "organization", "project", "need", "offer", "interaction", "content", "archive"].map((target) => (
                            <option key={target} value={target}>{target}</option>
                          ))}
                        </select>
                      </div>
                      <p className="mt-2 line-clamp-3 text-sm">{item.raw_text || item.does_what}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Chip>供给：{item.can_offer || "-"}</Chip>
                        <Chip>需求：{item.currently_needs || "-"}</Chip>
                      </div>
                      <div className="mt-3 flex gap-2">
                        <Button size="sm" type="button" onClick={() => void routeInbox(item, routeTarget)}>
                          <Save className="size-4" />
                          分流
                        </Button>
                        <Button size="sm" type="button" variant="outline" onClick={() => void routeInbox(item, "archive")}>
                          <Archive className="size-4" />
                          归档
                        </Button>
                      </div>
                    </article>
                  ))
                ) : (
                  <SmallEmpty text="Inbox 已清空。新私信、新项目、新想法先从左侧 Quick Capture 进入。" />
                )}
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "opportunities" ? (
          <Section title={`机会优先级总表 (${opportunities.length})`}>
            <div className="grid gap-3">
              {opportunities
                .slice()
                .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority))
                .map((opportunity) => (
                  <article key={opportunity.id} className="rounded-md border border-[var(--border)] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-medium">{opportunity.opportunity_name}</h3>
                        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                          {opportunity.stage || opportunity.current_stage || "unknown"} · 优先级 {opportunity.priority} · 预算信号 {opportunity.budget_signal}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Chip>{opportunity.decision_power_status || opportunity.decision_process || "决策待确认"}</Chip>
                        <Chip>{opportunity.my_role || opportunity.my_possible_role || "角色待确认"}</Chip>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <p className="text-sm"><span className="text-[var(--muted-foreground)]">相关人物：</span>{joinText(opportunity.related_people)}</p>
                      <p className="text-sm"><span className="text-[var(--muted-foreground)]">相关机构：</span>{joinText(opportunity.related_organizations)}</p>
                      <p className="text-sm"><span className="text-[var(--muted-foreground)]">核心需求：</span>{opportunity.core_need || "-"}</p>
                      <p className="text-sm"><span className="text-[var(--muted-foreground)]">为什么现在：</span>{opportunity.why_now || opportunity.why_it_matters || "-"}</p>
                    </div>
                    <div className="mt-3 rounded-md bg-[var(--muted)] p-3 text-sm">
                      <p><span className="text-[var(--muted-foreground)]">下一步：</span>{opportunity.next_action}</p>
                      <p className="mt-1"><span className="text-[var(--muted-foreground)]">本周建议：</span>{opportunity.recommended_action_this_week || "-"}</p>
                      <p className="mt-1"><span className="text-[var(--muted-foreground)]">风险：</span>{opportunity.risk || opportunity.risks || "-"}</p>
                    </div>
                  </article>
                ))}
              {!opportunities.length ? <SmallEmpty text="还没有机会数据。以后确认后的 seed data 会写入 ops_opportunities，并在这里展示。" /> : null}
            </div>
          </Section>
        ) : null}

        {tab === "network" ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,360px)_minmax(0,360px)_1fr]">
            <Section title="新建人脉">
              <form className="grid gap-3" onSubmit={createPerson}>
                <Field label="姓名"><Input value={personForm.display_name} onChange={(event) => setPersonForm({ ...personForm, display_name: event.target.value })} /></Field>
                <Field label="微信名"><Input value={personForm.wechat_name} onChange={(event) => setPersonForm({ ...personForm, wechat_name: event.target.value })} /></Field>
                <Field label="城市"><Input value={personForm.city} onChange={(event) => setPersonForm({ ...personForm, city: event.target.value })} /></Field>
                <Field label="角色，逗号分隔"><Input value={personForm.roles} onChange={(event) => setPersonForm({ ...personForm, roles: event.target.value })} /></Field>
                <Field label="能提供"><Textarea value={personForm.can_offer_summary} onChange={(event) => setPersonForm({ ...personForm, can_offer_summary: event.target.value })} rows={3} /></Field>
                <Field label="当前需要"><Textarea value={personForm.currently_needs_summary} onChange={(event) => setPersonForm({ ...personForm, currently_needs_summary: event.target.value })} rows={3} /></Field>
                <Field label="下一步"><Input value={personForm.next_action} onChange={(event) => setPersonForm({ ...personForm, next_action: event.target.value })} /></Field>
                <Field label="下一步日期"><Input type="date" value={personForm.next_action_at} onChange={(event) => setPersonForm({ ...personForm, next_action_at: event.target.value })} /></Field>
                <Button type="submit">保存人脉</Button>
              </form>
            </Section>
            <Section title="新建机构">
              <form className="grid gap-3" onSubmit={createOrg}>
                <Field label="机构名称"><Input value={orgForm.name} onChange={(event) => setOrgForm({ ...orgForm, name: event.target.value })} /></Field>
                <Field label="类型"><Input value={orgForm.type} onChange={(event) => setOrgForm({ ...orgForm, type: event.target.value })} /></Field>
                <Field label="城市"><Input value={orgForm.city} onChange={(event) => setOrgForm({ ...orgForm, city: event.target.value })} /></Field>
                <Field label="供给"><Textarea value={orgForm.offers} onChange={(event) => setOrgForm({ ...orgForm, offers: event.target.value })} rows={3} /></Field>
                <Field label="需求"><Textarea value={orgForm.needs} onChange={(event) => setOrgForm({ ...orgForm, needs: event.target.value })} rows={3} /></Field>
                <Field label="下一步"><Input value={orgForm.next_action} onChange={(event) => setOrgForm({ ...orgForm, next_action: event.target.value })} /></Field>
                <Field label="下一步日期"><Input type="date" value={orgForm.next_action_at} onChange={(event) => setOrgForm({ ...orgForm, next_action_at: event.target.value })} /></Field>
                <Button type="submit">保存机构</Button>
              </form>
            </Section>
            <Section title="人脉与机构">
              <div className="grid gap-3">
                {[...people.map((item) => ({ kind: "person" as const, item })), ...organizations.map((item) => ({ kind: "organization" as const, item }))].map(({ kind, item }) => (
                  <article key={`${kind}-${item.id}`} className="rounded-md border border-[var(--border)] p-3">
                    <div className="flex flex-wrap justify-between gap-2">
                      <h3 className="font-medium">{"display_name" in item ? personLabel(item) : orgLabel(item)}</h3>
                      <Button size="sm" variant="outline" onClick={() => void showRelationship(kind, item.id)}>关系视图</Button>
                    </div>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">{"roles" in item ? (item.role_tags || item.roles).join(", ") : item.type} · {item.city || "未记录城市"} · {"relationship_status" in item ? item.relationship_status || item.relationship_temperature : item.relationship_temperature}</p>
                    <p className="mt-2 text-sm">{"can_offer_summary" in item ? item.can_offer || item.can_offer_summary : item.can_offer || item.offers}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Chip>需求：{"currently_needs_summary" in item ? item.currently_needs || item.currently_needs_summary || "-" : item.currently_needs || item.needs || "-"}</Chip>
                      {"priority" in item ? <Chip>优先级：{item.priority || "medium"}</Chip> : null}
                      <Chip>下一步：{item.next_action || "-"}</Chip>
                    </div>
                  </article>
                ))}
                {!people.length && !organizations.length ? <SmallEmpty text="还没有人脉或机构。优先从 Inbox 分流，重要对象再补充详情。" /> : null}
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "interactions" ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_1fr]">
            <Section title="记录一次重要沟通">
              <form className="grid gap-3" onSubmit={createInteraction}>
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="日期"><Input type="date" value={interactionForm.date} onChange={(event) => setInteractionForm({ ...interactionForm, date: event.target.value })} /></Field>
                  <Field label="渠道"><Input value={interactionForm.channel} onChange={(event) => setInteractionForm({ ...interactionForm, channel: event.target.value })} /></Field>
                </div>
                <Field label="对方真实需求 / 沟通摘要"><Textarea value={interactionForm.summary} onChange={(event) => setInteractionForm({ ...interactionForm, summary: event.target.value })} rows={4} /></Field>
                <Field label="我答应了什么"><Textarea value={interactionForm.commitments} onChange={(event) => setInteractionForm({ ...interactionForm, commitments: event.target.value })} rows={3} /></Field>
                <Field label="下一步"><Input value={interactionForm.next_action} onChange={(event) => setInteractionForm({ ...interactionForm, next_action: event.target.value })} /></Field>
                <Field label="下一步日期"><Input type="date" value={interactionForm.next_action_at} onChange={(event) => setInteractionForm({ ...interactionForm, next_action_at: event.target.value })} /></Field>
                <Button type="submit">保存沟通</Button>
              </form>
            </Section>
            <Section title={`沟通记录 (${interactions.length})`}>
              <div className="grid gap-3">
                {interactions.map((item) => (
                  <article key={item.id} className="rounded-md border border-[var(--border)] p-3">
                    <div className="flex flex-wrap justify-between gap-2">
                      <h3 className="font-medium">{item.title || item.summary || "未命名沟通"}</h3>
                      <Chip>{item.channel} · {item.date}</Chip>
                    </div>
                    <p className="mt-2 text-sm">{item.summary}</p>
                    {item.participants?.length ? <p className="mt-2 text-sm text-[var(--muted-foreground)]">参与者：{joinText(item.participants)}</p> : null}
                    {item.key_points?.length ? <p className="mt-2 text-sm text-[var(--muted-foreground)]">要点：{joinText(item.key_points)}</p> : null}
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Chip>下一步：{item.next_action || joinText(item.next_actions)}</Chip>
                      <Chip>保密级别：{item.confidentiality_level || "private"}</Chip>
                    </div>
                  </article>
                ))}
                {!interactions.length ? <SmallEmpty text="还没有沟通记录。每次重要沟通后只记真实需求、承诺和下一步。" /> : null}
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "needs-offers" ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title={`Needs / 需求 (${needs.length})`}>
              <div className="grid gap-3">
                {needs.map((need) => (
                  <article key={need.id} className="rounded-md border border-[var(--border)] p-3">
                    <div className="flex flex-wrap justify-between gap-2">
                      <h3 className="font-medium">{need.owner || need.owner_id || "未命名需求方"}</h3>
                      <Chip>{need.need_type || need.category} · {need.urgency}</Chip>
                    </div>
                    <p className="mt-2 text-sm">{need.description}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Chip>状态：{need.status}</Chip>
                      <Chip>可匹配：{joinText(need.possible_matches)}</Chip>
                      <Chip>下一步：{need.next_action || "-"}</Chip>
                    </div>
                  </article>
                ))}
                {!needs.length ? <SmallEmpty text="还没有独立需求。后续从机会或沟通中拆出来。" /> : null}
              </div>
            </Section>
            <Section title={`Offers / 供给 (${offers.length})`}>
              <div className="grid gap-3">
                {offers.map((offer) => (
                  <article key={offer.id} className="rounded-md border border-[var(--border)] p-3">
                    <div className="flex flex-wrap justify-between gap-2">
                      <h3 className="font-medium">{offer.owner || offer.owner_id || "未命名供给方"}</h3>
                      <Chip>{offer.offer_type || offer.category}</Chip>
                    </div>
                    <p className="mt-2 text-sm">{offer.description}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Chip>适合：{offer.suitable_for || joinText(offer.available_for)}</Chip>
                      <Chip>验证：{offer.needs_verification || "-"}</Chip>
                      <Chip>下一步：{offer.next_action || "-"}</Chip>
                    </div>
                  </article>
                ))}
                {!offers.length ? <SmallEmpty text="还没有独立供给。技术、园区、算力、内容、医疗健康资源会在这里沉淀。" /> : null}
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "content" ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_1fr]">
            <Section title="新增内容复盘">
              <form className="grid gap-3" onSubmit={createContent}>
                <Field label="标题"><Input value={contentForm.title} onChange={(event) => setContentForm({ ...contentForm, title: event.target.value })} /></Field>
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="平台"><Input value={contentForm.platform} onChange={(event) => setContentForm({ ...contentForm, platform: event.target.value })} /></Field>
                  <Field label="发布日期"><Input type="date" value={contentForm.published_at} onChange={(event) => setContentForm({ ...contentForm, published_at: event.target.value })} /></Field>
                </div>
                <Field label="主题标签"><Input value={contentForm.topic_tags} onChange={(event) => setContentForm({ ...contentForm, topic_tags: event.target.value })} /></Field>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {["views", "likes", "comments", "dms"].map((key) => (
                    <Field key={key} label={key}><Input type="number" value={contentForm[key as keyof typeof contentForm]} onChange={(event) => setContentForm({ ...contentForm, [key]: event.target.value })} /></Field>
                  ))}
                </div>
                <Field label="洞察"><Textarea value={contentForm.insights} onChange={(event) => setContentForm({ ...contentForm, insights: event.target.value })} rows={4} /></Field>
                <Field label="后续选题"><Textarea value={contentForm.followup_content_ideas} onChange={(event) => setContentForm({ ...contentForm, followup_content_ideas: event.target.value })} rows={4} /></Field>
                <Button type="submit">保存内容复盘</Button>
              </form>
            </Section>
            <Section title="内容线索">
              <div className="grid gap-3">
                {contents.map((item) => (
                  <article key={item.id} className="rounded-md border border-[var(--border)] p-3">
                    <h3 className="font-medium">{item.content_title || item.title}</h3>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">{item.platform} · {item.published_at || "未发布"} · DM {item.metrics.dms} · 优先级 {item.publish_priority || "medium"}</p>
                    <p className="mt-2 text-sm">{item.content_angle || item.insights}</p>
                    {item.key_message ? <p className="mt-2 text-sm text-[var(--muted-foreground)]">核心信息：{item.key_message}</p> : null}
                    <p className="mt-2 text-sm text-[var(--muted-foreground)]">后续：{item.possible_followup || item.followup_content_ideas || "-"}</p>
                  </article>
                ))}
                {!contents.length ? <SmallEmpty text="内容页先做轻量复盘：哪条内容带来线索、观众关心什么、后续拍什么。" /> : null}
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "next-actions" ? (
          <Section title={`本周行动清单 (${nextActions.length})`}>
            <div className="grid gap-3">
              {nextActions
                .slice()
                .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority))
                .map((item) => (
                  <article key={item.id} className="rounded-md border border-[var(--border)] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-medium">{item.action}</h3>
                        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                          {item.related_person || item.related_person_or_opportunity || "未绑定对象"} · {item.deadline_or_timing || "未排期"} · {item.priority}
                        </p>
                      </div>
                      {item.message_needed ? (
                        <Button type="button" size="sm" variant="outline" onClick={() => void copyMessage(item.message_needed)}>
                          复制微信话术
                        </Button>
                      ) : null}
                    </div>
                    {item.expected_outcome ? <p className="mt-3 text-sm"><span className="text-[var(--muted-foreground)]">预期结果：</span>{item.expected_outcome}</p> : null}
                    {item.reason ? <p className="mt-2 text-sm"><span className="text-[var(--muted-foreground)]">原因：</span>{item.reason}</p> : null}
                    {item.message_needed ? (
                      <pre className="mt-3 whitespace-pre-wrap rounded-md bg-[var(--muted)] p-3 text-sm font-sans text-[var(--foreground)]">{item.message_needed}</pre>
                    ) : null}
                  </article>
                ))}
              {!nextActions.length ? <SmallEmpty text="还没有行动清单。以后确认后的 next_actions 会直接出现在这里。" /> : null}
            </div>
          </Section>
        ) : null}

        {relationship ? (
          <Section title={`关系视图：${relationship.entity.label}`} action={<Button type="button" size="sm" variant="ghost" onClick={() => setRelationship(null)}>关闭</Button>}>
            <div className="grid gap-3 md:grid-cols-3">
              {Object.entries(relationship.related).map(([key, items]) => (
                <div key={key} className="rounded-md border border-[var(--border)] p-3">
                  <h3 className="mb-2 text-sm font-semibold">{key}</h3>
                  <div className="grid gap-2">
                    {items.slice(0, 6).map((item) => (
                      <p key={item.id} className="truncate text-sm text-[var(--muted-foreground)]">
                        {"display_name" in item ? item.display_name || item.wechat_name : "name" in item ? item.name : "description" in item ? item.description : "title" in item ? item.title : item.summary}
                      </p>
                    ))}
                    {!items.length ? <p className="text-sm text-[var(--muted-foreground)]">无关联</p> : null}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        ) : null}
      </div>
    </main>
  );
}
