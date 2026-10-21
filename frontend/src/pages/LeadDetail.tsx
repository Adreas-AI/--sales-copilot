import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useGenerateDraft,
  useLead,
  useLogActivity,
  useRequalify,
  useSequence,
  useTimeline,
  useUpdateLead,
} from "../api/hooks";
import { EMAIL_KINDS, type EmailKind, type Lead, OBJECTIONS, type Qualification, STAGES, type Sequence } from "../api/types";
import DraftCard from "../components/DraftCard";
import { Badge, Button, Card, Empty, ErrorNote, Field, Loading, StatusBadge, TemperatureBadge, cx, inputClass } from "../components/ui";
import { dateTime, getReviewer, humanize, relative } from "../lib/format";

export default function LeadDetail() {
  const { id = "" } = useParams();
  const { data, error, isLoading } = useLead(id);

  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorNote error={error ?? "Lead not found"} />;
  const { lead, latest_qualification: q, sequences, drafts } = data;
  const openDrafts = drafts.filter((d) => d.status === "pending_review" || d.status === "approved");
  const pastDrafts = drafts.filter((d) => !openDrafts.includes(d));

  return (
    <div className="space-y-6">
      <div>
        <Link to="/leads" className="text-sm text-slate-500 hover:text-indigo-600">← Leads</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">{lead.business_name}</h1>
          <TemperatureBadge temperature={lead.temperature} score={lead.score} />
          <Badge tone="indigo">{humanize(lead.stage)}</Badge>
          {lead.do_not_contact && <Badge tone="red">Do not contact</Badge>}
        </div>
        <p className="text-sm text-slate-500">
          {lead.contact_name} · {lead.email}
          {lead.phone && ` · ${lead.phone}`} · via {humanize(lead.source)} {relative(lead.created_at)}
        </p>
      </div>

      {lead.needs_review && <ReviewBanner lead={lead} />}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          {q ? <QualificationCard q={q} leadId={lead.id} /> : <Card title="Qualification"><Empty>Qualification is queued…</Empty></Card>}

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Drafts awaiting a person</h2>
            </div>
            {openDrafts.length ? openDrafts.map((d) => <DraftCard key={d.id} draft={d} />) : (
              <p className="text-sm text-slate-500">No open drafts.</p>
            )}
            <NewDraft lead={lead} />
          </section>

          <Timeline leadId={lead.id} />

          {pastDrafts.length > 0 && (
            <details className="rounded-xl border border-slate-200 bg-white p-4">
              <summary className="cursor-pointer text-sm font-medium">Earlier drafts ({pastDrafts.length})</summary>
              <div className="mt-3 space-y-3">{pastDrafts.map((d) => <DraftCard key={d.id} draft={d} />)}</div>
            </details>
          )}
        </div>

        <div className="space-y-6">
          <SequenceCard leadId={lead.id} sequences={sequences} />
          <LeadFacts lead={lead} />
          <LogActivity leadId={lead.id} />
        </div>
      </div>
    </div>
  );
}

function ReviewBanner({ lead }: { lead: Lead }) {
  const update = useUpdateLead(lead.id);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <span><b>Needs a person:</b> {lead.review_reason}</span>
      <Button onClick={() => update.mutate({ needs_review: false })} disabled={update.isPending}>Mark reviewed</Button>
    </div>
  );
}

function QualificationCard({ q, leadId }: { q: Qualification; leadId: string }) {
  const requalify = useRequalify(leadId);
  return (
    <Card
      title="Qualification"
      actions={
        <>
          <span className="text-xs text-slate-400">{q.method === "rules+ai" ? `rules + ${q.model}` : "rules only"} · {relative(q.created_at)}</span>
          <Button onClick={() => requalify.mutate(true)} disabled={requalify.isPending}>Re-score</Button>
        </>
      }
    >
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <div className="text-4xl font-semibold tabular-nums">{q.score}</div>
        <div className="text-sm text-slate-600">
          <TemperatureBadge temperature={q.temperature} /> · confidence {Math.round(q.confidence * 100)}%
          {q.ai_adjustment != null && (
            <span> · rules {q.rule_score}, AI {q.ai_adjustment >= 0 ? "+" : ""}{q.ai_adjustment}</span>
          )}
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {q.factors.map((f) => (
          <div key={f.key} className="grid grid-cols-[120px_1fr_48px] items-center gap-3 text-sm">
            <span className="text-slate-600">{f.label}</span>
            <div>
              {f.max_points > 0 ? (
                <div className="h-2 rounded-full bg-slate-100">
                  <div className="h-2 rounded-full bg-indigo-500" style={{ width: `${(f.points / f.max_points) * 100}%` }} />
                </div>
              ) : null}
              <div className={cx("mt-0.5 text-xs", f.points < 0 ? "text-rose-600" : "text-slate-500")}>{f.evidence}</div>
            </div>
            <span className={cx("text-right tabular-nums", f.points < 0 && "text-rose-600")}>
              {f.points}{f.max_points > 0 && <span className="text-slate-400">/{f.max_points}</span>}
            </span>
          </div>
        ))}
      </div>

      <p className="mt-4 text-sm leading-relaxed text-slate-700">{q.reasoning}</p>
      {q.ai_evidence.length > 0 && (
        <div className="mt-3 space-y-1">
          {q.ai_evidence.map((e) => (
            <blockquote key={e} className="border-l-2 border-indigo-300 pl-3 text-sm text-slate-600 italic">“{e}”</blockquote>
          ))}
        </div>
      )}
      {q.missing_information.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">
          Not provided (never guessed): {q.missing_information.map(humanize).join(", ")}
        </p>
      )}
      {q.warnings.map((w) => (
        <p key={w} className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{w}</p>
      ))}
      <ErrorNote error={requalify.error} />
    </Card>
  );
}

function NewDraft({ lead }: { lead: Lead }) {
  const [kind, setKind] = useState<EmailKind>("follow_up");
  const [instructions, setInstructions] = useState("");
  const [useAi, setUseAi] = useState(true);
  const generate = useGenerateDraft(lead.id);
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Write a new draft">
          <select className={`${inputClass} w-56`} value={kind} onChange={(e) => setKind(e.target.value as EmailKind)}>
            {EMAIL_KINDS.map((k) => <option key={k} value={k}>{humanize(k)}</option>)}
          </select>
        </Field>
        <input
          className={`${inputClass} min-w-48 flex-1`}
          placeholder="Optional guidance, e.g. mention we can migrate from Mindbody"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /> AI
        </label>
        <Button
          variant="primary"
          disabled={generate.isPending}
          onClick={() => generate.mutate({ kind, use_ai: useAi, instructions: instructions || undefined }, { onSuccess: () => setInstructions("") })}
        >
          {generate.isPending ? "Writing…" : "Generate"}
        </Button>
      </div>
      <ErrorNote error={generate.error} />
    </div>
  );
}

function SequenceCard({ leadId, sequences }: { leadId: string; sequences: Sequence[] }) {
  const seq = useSequence(leadId);
  const current = sequences[0];
  const active = current?.status === "active";
  return (
    <Card
      title="Follow-up sequence"
      actions={
        active ? (
          <Button variant="danger" onClick={() => seq.mutate("stop")} disabled={seq.isPending}>Stop</Button>
        ) : (
          <Button onClick={() => seq.mutate("start")} disabled={seq.isPending}>Start from today</Button>
        )
      }
    >
      {!current ? (
        <Empty>No sequence.</Empty>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2 text-sm">
            <StatusBadge status={current.status} />
            {current.stop_reason && <span className="text-slate-500">{humanize(current.stop_reason)}</span>}
          </div>
          <ol className="relative space-y-3 border-l border-slate-200 pl-4">
            {current.tasks.map((t) => (
              <li key={t.id} className="text-sm">
                <span
                  className={cx(
                    "absolute -left-[5px] mt-1.5 size-2.5 rounded-full",
                    t.status === "completed" ? "bg-emerald-500" : t.status === "scheduled" ? "bg-indigo-400" : "bg-slate-300",
                  )}
                />
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">
                    Day {t.day}: {t.action === "manual_review" ? "Manual review" : "Follow-up draft"}
                  </span>
                  <StatusBadge status={t.status} />
                </div>
                <div className="text-xs text-slate-500">{t.outcome ?? `due ${dateTime(t.due_at)} (${relative(t.due_at)})`}</div>
              </li>
            ))}
          </ol>
        </>
      )}
      <ErrorNote error={seq.error} />
    </Card>
  );
}

function LeadFacts({ lead }: { lead: Lead }) {
  const update = useUpdateLead(lead.id);
  const toggleObjection = (o: string) => {
    const next = lead.objections.includes(o) ? lead.objections.filter((x) => x !== o) : [...lead.objections, o];
    update.mutate({ objections: next });
  };
  const rows: [string, string][] = [
    ["Category", humanize(lead.business_category)],
    ["Locations", lead.locations_count?.toString() ?? "Not provided"],
    ["Staff", lead.company_size ?? "Not provided"],
    ["Interested in", lead.product_interest.join(", ") || "Not provided"],
    ["Preferred channel", humanize(lead.preferred_channel)],
    ["Email consent", lead.consent_email ? `Yes (${lead.consent_source ?? "source not recorded"})` : "No"],
    ["Marketing consent", lead.consent_marketing ? "Yes" : "No"],
    ["Owner", lead.owner ?? "Unassigned"],
  ];
  return (
    <Card title="Lead">
      <dl className="space-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[120px_1fr] gap-2">
            <dt className="text-slate-500">{k}</dt>
            <dd className="text-slate-800">{v}</dd>
          </div>
        ))}
      </dl>
      {lead.message && (
        <blockquote className="mt-4 rounded-lg bg-slate-50 p-3 text-sm whitespace-pre-line text-slate-700">{lead.message}</blockquote>
      )}

      <div className="mt-4 space-y-3">
        <Field label="Stage">
          <select className={inputClass} value={lead.stage} onChange={(e) => update.mutate({ stage: e.target.value, owner: lead.owner ?? getReviewer() })}>
            {STAGES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
        </Field>
        <div>
          <span className="mb-1 block text-xs font-medium text-slate-600">Objections</span>
          <div className="flex flex-wrap gap-1.5">
            {OBJECTIONS.map((o) => (
              <button
                key={o}
                type="button"
                onClick={() => toggleObjection(o)}
                className={cx(
                  "rounded-full px-2 py-0.5 text-xs ring-1 ring-inset",
                  lead.objections.includes(o) ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50",
                )}
              >
                {humanize(o)}
              </button>
            ))}
          </div>
        </div>
        {!lead.do_not_contact && (
          <Button variant="danger" onClick={() => confirm("Stop all outreach to this lead?") && update.mutate({ do_not_contact: true })}>
            Mark do-not-contact
          </Button>
        )}
      </div>
      <ErrorNote error={update.error} />
    </Card>
  );
}

function LogActivity({ leadId }: { leadId: string }) {
  const [kind, setKind] = useState<"inbound_email" | "note" | "call">("inbound_email");
  const [body, setBody] = useState("");
  const log = useLogActivity(leadId);
  return (
    <Card title="Log activity">
      <div className="space-y-2">
        <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="inbound_email">Prospect replied (stops follow-ups)</option>
          <option value="call">Call</option>
          <option value="note">Note</option>
        </select>
        <textarea className={inputClass} rows={3} value={body} onChange={(e) => setBody(e.target.value)} placeholder="What happened?" />
        <Button variant="primary" disabled={!body.trim() || log.isPending} onClick={() => log.mutate({ kind, body }, { onSuccess: () => setBody("") })}>
          Save
        </Button>
        <ErrorNote error={log.error} />
      </div>
    </Card>
  );
}

const ACTIVITY_STYLE: Record<string, string> = {
  inbound: "border-emerald-300 bg-emerald-50/50",
  outbound: "border-indigo-300 bg-indigo-50/40",
  internal: "border-slate-200 bg-white",
};

function Timeline({ leadId }: { leadId: string }) {
  const { data } = useTimeline(leadId);
  return (
    <Card title="Timeline">
      {!data?.length ? (
        <Empty>No activity yet.</Empty>
      ) : (
        <ul className="space-y-2">
          {data.map((a) => (
            <li key={a.id} className={cx("rounded-lg border-l-4 px-3 py-2 text-sm", ACTIVITY_STYLE[a.direction])}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                <span className="font-medium text-slate-700">{humanize(a.kind)}{a.actor ? ` · ${a.actor}` : ""}</span>
                <span title={a.occurred_at}>{dateTime(a.occurred_at)}</span>
              </div>
              {a.subject && <div className="mt-0.5 font-medium">{a.subject}</div>}
              {a.body && <p className="mt-0.5 whitespace-pre-line text-slate-700">{a.body}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
