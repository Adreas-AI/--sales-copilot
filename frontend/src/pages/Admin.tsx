import { type FormEvent, useState } from "react";

import { useAddSuppression, useDeleteSuppression, useJobs, useRetryJob, useSuppressions } from "../api/hooks";
import { Badge, Button, Card, Empty, ErrorNote, Loading, StatusBadge, cx, inputClass } from "../components/ui";
import { dateTime, humanize } from "../lib/format";

export function Suppressions() {
  const list = useSuppressions();
  const add = useAddSuppression();
  const remove = useDeleteSuppression();

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    add.mutate(
      {
        kind: String(f.get("kind")),
        value: String(f.get("value")),
        reason: String(f.get("reason")),
        note: String(f.get("note") || "") || undefined,
      },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Suppression list</h1>
        <p className="text-sm text-slate-500">
          Addresses and domains that are never emailed. Adding one stops any running sequence and cancels open drafts.
          Opt-outs can only be reversed by the recipient.
        </p>
      </div>
      <Card title="Add">
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <select name="kind" className={`${inputClass} w-auto`}>
            <option value="email">Email</option>
            <option value="domain">Domain</option>
          </select>
          <input name="value" required placeholder="name@company.com or company.com" className={`${inputClass} max-w-xs`} />
          <select name="reason" className={`${inputClass} w-auto`} defaultValue="manual">
            {["manual", "bounce", "complaint", "legal"].map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
          </select>
          <input name="note" placeholder="Note (optional)" className={`${inputClass} max-w-xs`} />
          <Button type="submit" variant="primary" disabled={add.isPending}>Suppress</Button>
        </form>
        <ErrorNote error={add.error || remove.error} />
      </Card>
      {list.isLoading ? <Loading /> : !list.data?.length ? <Empty>The list is empty.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {list.data.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2"><Badge>{s.kind}</Badge> <span className="ml-1 font-medium">{s.value}</span></td>
                  <td className="px-4 py-2">{humanize(s.reason)}</td>
                  <td className="px-4 py-2 text-slate-500">{s.source} {s.note && `· ${s.note}`}</td>
                  <td className="px-4 py-2 text-slate-500">{dateTime(s.created_at)}</td>
                  <td className="px-4 py-2 text-right">
                    {!["unsubscribe", "complaint"].includes(s.reason) && (
                      <Button variant="ghost" onClick={() => remove.mutate(s.id)}>Remove</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function Jobs() {
  const [status, setStatus] = useState<string | undefined>();
  const jobs = useJobs(status);
  const retry = useRetryJob();
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Jobs</h1>
        <p className="text-sm text-slate-500">
          The database-backed queue behind qualification and follow-ups. Jobs retry with backoff; after the last
          attempt they're marked dead and can be retried here.
        </p>
      </div>
      <div className="flex gap-1">
        {[undefined, "queued", "running", "succeeded", "dead"].map((s) => (
          <button
            key={s ?? "all"}
            type="button"
            onClick={() => setStatus(s)}
            className={cx("rounded-lg px-3 py-1 text-sm", status === s ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100")}
          >
            {s ? humanize(s) : "All"}
          </button>
        ))}
      </div>
      {jobs.isLoading ? <Loading /> : !jobs.data?.length ? <Empty>No jobs.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-2 font-medium">Kind</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Attempts</th>
                <th className="px-4 py-2 font-medium">Run at</th>
                <th className="px-4 py-2 font-medium">Error</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {jobs.data.map((j) => (
                <tr key={j.id}>
                  <td className="px-4 py-2 font-mono text-xs">{j.kind}</td>
                  <td className="px-4 py-2"><StatusBadge status={j.status} /></td>
                  <td className="px-4 py-2 tabular-nums">{j.attempts}/{j.max_attempts}</td>
                  <td className="px-4 py-2 text-slate-500">{dateTime(j.run_at)}</td>
                  <td className="max-w-md truncate px-4 py-2 text-xs text-rose-700" title={j.last_error ?? ""}>{j.last_error}</td>
                  <td className="px-4 py-2 text-right">
                    {j.status === "dead" && <Button onClick={() => retry.mutate(j.id)}>Retry</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
