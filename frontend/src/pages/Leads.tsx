import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useLeads } from "../api/hooks";
import { STAGES } from "../api/types";
import NewLeadForm from "../components/NewLeadForm";
import { Badge, Button, Card, Empty, ErrorNote, Loading, TemperatureBadge, inputClass } from "../components/ui";
import { humanize, relative } from "../lib/format";

const PAGE = 25;

export default function Leads() {
  const [params, setParams] = useSearchParams();
  const [showNew, setShowNew] = useState(false);
  const filters = {
    temperature: params.get("temperature") ?? undefined,
    stage: params.get("stage") ?? undefined,
    needs_review: params.get("needs_review") === "true" ? true : undefined,
    q: params.get("q") ?? undefined,
    offset: Number(params.get("offset") ?? 0),
    limit: PAGE,
  };
  const { data, error, isLoading } = useLeads(filters);

  const set = (key: string, value: string | undefined) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Leads</h1>
          <p className="text-sm text-slate-500">{data ? `${data.total} total` : " "}</p>
        </div>
        <Button variant="primary" onClick={() => setShowNew((v) => !v)}>
          {showNew ? "Close" : "+ New lead"}
        </Button>
      </div>

      {showNew && (
        <Card title="Manual CRM entry">
          <NewLeadForm onDone={() => setShowNew(false)} />
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          className={`${inputClass} max-w-xs`}
          placeholder="Search business, contact or email"
          defaultValue={filters.q}
          onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)}
        />
        <select className={`${inputClass} w-auto`} value={filters.temperature ?? ""} onChange={(e) => set("temperature", e.target.value)}>
          <option value="">All temperatures</option>
          <option value="hot">Hot</option>
          <option value="warm">Warm</option>
          <option value="cold">Cold</option>
        </select>
        <select className={`${inputClass} w-auto`} value={filters.stage ?? ""} onChange={(e) => set("stage", e.target.value)}>
          <option value="">All stages</option>
          {STAGES.map((s) => (
            <option key={s} value={s}>{humanize(s)}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={!!filters.needs_review} onChange={(e) => set("needs_review", e.target.checked ? "true" : undefined)} />
          Needs review
        </label>
      </div>

      <ErrorNote error={error} />
      {isLoading ? (
        <Loading />
      ) : !data?.items.length ? (
        <Empty>No leads match these filters.</Empty>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-2 font-medium">Business</th>
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Stage</th>
                <th className="px-4 py-2 font-medium">Source</th>
                <th className="px-4 py-2 font-medium">Last inbound</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((l) => (
                <tr key={l.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5">
                    <Link to={`/leads/${l.id}`} className="font-medium text-slate-900 hover:text-indigo-600">{l.business_name}</Link>
                    <div className="text-xs text-slate-500">
                      {l.contact_name} · {humanize(l.business_category)}
                      {l.locations_count ? ` · ${l.locations_count} loc.` : ""}
                    </div>
                  </td>
                  <td className="px-4 py-2.5"><TemperatureBadge temperature={l.temperature} score={l.score} /></td>
                  <td className="px-4 py-2.5">
                    <span className="mr-1">{humanize(l.stage)}</span>
                    {l.needs_review && <Badge tone="amber">Review</Badge>}
                    {l.do_not_contact && <Badge tone="red">DNC</Badge>}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{humanize(l.source)}</td>
                  <td className="px-4 py-2.5 text-slate-600">{relative(l.last_inbound_at)}</td>
                  <td className="px-4 py-2.5 text-slate-600">{relative(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > PAGE && (
        <div className="flex items-center gap-2 text-sm">
          <Button disabled={filters.offset === 0} onClick={() => set("offset", String(Math.max(0, filters.offset - PAGE)))}>Previous</Button>
          <span className="text-slate-500">
            {filters.offset + 1}–{Math.min(filters.offset + PAGE, data.total)} of {data.total}
          </span>
          <Button disabled={filters.offset + PAGE >= data.total} onClick={() => set("offset", String(filters.offset + PAGE))}>Next</Button>
        </div>
      )}
    </div>
  );
}
