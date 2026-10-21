import { Link } from "react-router-dom";

import { useCadence, useLeads, useOverdue, useTasks } from "../api/hooks";
import type { Task } from "../api/types";
import { Card, Empty, Loading, StatusBadge } from "../components/ui";
import { dateTime, humanize, relative } from "../lib/format";

function TaskRow({ t }: { t: Task }) {
  return (
    <tr className="text-sm">
      <td className="py-2 pr-4"><Link to={`/leads/${t.lead_id}`} className="text-indigo-600 hover:underline">Open lead</Link></td>
      <td className="py-2 pr-4">Day {t.day} · {t.action === "manual_review" ? "Manual review" : "Follow-up draft"}</td>
      <td className="py-2 pr-4 text-slate-600">{dateTime(t.due_at)} <span className="text-slate-400">({relative(t.due_at)})</span></td>
      <td className="py-2"><StatusBadge status={t.status} /></td>
    </tr>
  );
}

export default function Followups() {
  const cadence = useCadence();
  const tasks = useTasks();
  const overdue = useOverdue();
  const review = useLeads({ needs_review: true, limit: 50 });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Follow-ups</h1>
        {cadence.data && (
          <p className="text-sm text-slate-500">
            Cadence: drafts on {cadence.data.step_days.map((d) => `Day ${d}`).join(", ")}, manual review on Day{" "}
            {cadence.data.manual_review_day}, for {cadence.data.temperatures.join(" & ")} leads. Stops on reply,
            unsubscribe, suppression or stage change. Configure with <code>FOLLOWUP_STEP_DAYS</code> /{" "}
            <code>MANUAL_REVIEW_DAY</code>.
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Drafts waiting past SLA">
          {overdue.isLoading ? <Loading /> : !overdue.data?.drafts.length ? <Empty>None. Nice.</Empty> : (
            <ul className="divide-y divide-slate-100">
              {overdue.data.drafts.map((d) => (
                <li key={d.id} className="flex items-center justify-between py-2 text-sm">
                  <Link to={`/leads/${d.lead_id}`} className="hover:text-indigo-600">{humanize(d.kind)}: {d.subject}</Link>
                  <span className="shrink-0 text-xs text-rose-600">{relative(d.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Manual review">
          {review.isLoading ? <Loading /> : !review.data?.items.length ? <Empty>No leads flagged.</Empty> : (
            <ul className="divide-y divide-slate-100">
              {review.data.items.map((l) => (
                <li key={l.id} className="py-2 text-sm">
                  <Link to={`/leads/${l.id}`} className="font-medium hover:text-indigo-600">{l.business_name}</Link>
                  <p className="text-xs text-slate-500">{l.review_reason}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {overdue.data && overdue.data.tasks.length > 0 && (
        <Card title="Tasks the worker hasn't processed (check the worker)">
          <table className="w-full"><tbody>{overdue.data.tasks.map((t) => <TaskRow key={t.id} t={t} />)}</tbody></table>
        </Card>
      )}

      <Card title="Upcoming">
        {tasks.isLoading ? <Loading /> : !tasks.data?.length ? <Empty>No scheduled follow-ups.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full"><tbody className="divide-y divide-slate-100">{tasks.data.map((t) => <TaskRow key={t.id} t={t} />)}</tbody></table>
          </div>
        )}
      </Card>
    </div>
  );
}
