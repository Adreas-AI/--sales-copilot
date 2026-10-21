import { Link } from "react-router-dom";

import { useLeads, useSummary, useUnanswered } from "../api/hooks";
import { STAGES } from "../api/types";
import { Card, Empty, ErrorNote, Loading, Stat, TemperatureBadge } from "../components/ui";
import { humanize, relative } from "../lib/format";

const TEMPS = [
  { key: "hot", label: "Hot", color: "bg-rose-500" },
  { key: "warm", label: "Warm", color: "bg-amber-400" },
  { key: "cold", label: "Cold", color: "bg-sky-400" },
];

export default function Overview() {
  const { data: s, error, isLoading } = useSummary();
  const unanswered = useUnanswered();
  const review = useLeads({ needs_review: true, limit: 8 });

  if (isLoading) return <Loading />;
  if (error || !s) return <ErrorNote error={error} />;

  const scored = TEMPS.reduce((n, t) => n + (s.by_temperature[t.key] ?? 0), 0);
  const maxStage = Math.max(1, ...Object.values(s.by_stage));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-sm text-slate-500">What needs a person today.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 [&>a]:block">
        <Link to="/review"><Stat label="Drafts to review" value={s.drafts_pending_review} hint={`${s.drafts_approved_unsent} approved, not sent`} /></Link>
        <Link to="/followups"><Stat label="Overdue drafts" value={s.overdue_drafts} tone={s.overdue_drafts ? "warn" : undefined} hint="waiting past the review SLA" /></Link>
        <Stat label="Unanswered" value={s.unanswered} tone={s.unanswered ? "warn" : undefined} hint="prospect wrote, we haven't replied" />
        <Link to="/leads?needs_review=true"><Stat label="Manual review" value={s.needs_review} hint="flagged by the follow-up engine" /></Link>
        <Stat label="Leads" value={s.total_leads} hint={`${s.new_last_7_days} in the last 7 days`} />
        <Stat label="Active sequences" value={s.active_sequences} hint={`${s.followups_due_24h} steps due in 24h`} />
        <Stat
          label="Median first response"
          value={s.median_first_response_hours == null ? "—" : `${s.median_first_response_hours}h`}
          hint="last 30 days"
        />
        <Link to="/jobs"><Stat label="Failed jobs" value={s.jobs.dead ?? 0} tone={s.jobs.dead ? "warn" : undefined} hint={`${s.jobs.queued ?? 0} queued`} /></Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Lead temperature">
          {scored === 0 ? (
            <Empty>No scored leads yet.</Empty>
          ) : (
            <>
              <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
                {TEMPS.map((t) => (
                  <div key={t.key} className={t.color} style={{ width: `${((s.by_temperature[t.key] ?? 0) / scored) * 100}%` }} />
                ))}
              </div>
              <div className="mt-3 flex gap-5 text-sm">
                {TEMPS.map((t) => (
                  <Link key={t.key} to={`/leads?temperature=${t.key}`} className="flex items-center gap-1.5 hover:underline">
                    <span className={`size-2.5 rounded-full ${t.color}`} />
                    {t.label} <span className="font-semibold tabular-nums">{s.by_temperature[t.key] ?? 0}</span>
                  </Link>
                ))}
              </div>
            </>
          )}
        </Card>

        <Card title="Pipeline">
          <div className="space-y-1.5">
            {STAGES.filter((st) => s.by_stage[st]).map((st) => (
              <Link key={st} to={`/leads?stage=${st}`} className="flex items-center gap-3 text-sm hover:underline">
                <span className="w-32 shrink-0 text-slate-600">{humanize(st)}</span>
                <span className="h-2 rounded-full bg-indigo-400" style={{ width: `${(s.by_stage[st] / maxStage) * 60}%` }} />
                <span className="tabular-nums">{s.by_stage[st]}</span>
              </Link>
            ))}
            {Object.keys(s.by_stage).length === 0 && <Empty>No leads yet.</Empty>}
          </div>
        </Card>

        <Card title="Waiting for a reply from us">
          {unanswered.data?.length ? (
            <ul className="divide-y divide-slate-100">
              {unanswered.data.map((l) => (
                <li key={l.id} className="flex items-center justify-between py-2 text-sm">
                  <Link to={`/leads/${l.id}`} className="font-medium hover:text-indigo-600">{l.business_name}</Link>
                  <span className="flex items-center gap-2 text-slate-500">
                    wrote {relative(l.last_inbound_at)} <TemperatureBadge temperature={l.temperature} score={l.score} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Everyone who wrote has had a reply.</Empty>
          )}
        </Card>

        <Card title="Flagged for manual review">
          {review.data?.items.length ? (
            <ul className="divide-y divide-slate-100">
              {review.data.items.map((l) => (
                <li key={l.id} className="py-2 text-sm">
                  <Link to={`/leads/${l.id}`} className="font-medium hover:text-indigo-600">{l.business_name}</Link>
                  <p className="text-xs text-slate-500">{l.review_reason}</p>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Nothing flagged.</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}
