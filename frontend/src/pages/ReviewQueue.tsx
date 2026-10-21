import { useState } from "react";

import { useDrafts } from "../api/hooks";
import DraftCard from "../components/DraftCard";
import { Empty, ErrorNote, Loading, cx } from "../components/ui";

const TABS = [
  { status: "pending_review", label: "To review" },
  { status: "approved", label: "Approved, not sent" },
  { status: "sent", label: "Sent" },
  { status: "rejected", label: "Rejected" },
  { status: "cancelled", label: "Auto-cancelled" },
];

export default function ReviewQueue() {
  const [status, setStatus] = useState("pending_review");
  const { data, error, isLoading } = useDrafts(status);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Review queue</h1>
        <p className="text-sm text-slate-500">
          Nothing is sent without a person. Edit, approve, then send, or reject.
        </p>
      </div>
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.status}
            type="button"
            onClick={() => setStatus(t.status)}
            className={cx(
              "-mb-px border-b-2 px-3 py-2 text-sm",
              status === t.status ? "border-indigo-600 font-medium text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <ErrorNote error={error} />
      {isLoading ? (
        <Loading />
      ) : !data?.length ? (
        <Empty>{status === "pending_review" ? "All caught up." : "Nothing here."}</Empty>
      ) : (
        <div className="grid gap-4 2xl:grid-cols-2">
          {data.map((d) => <DraftCard key={d.id} draft={d} lead={d.lead} />)}
        </div>
      )}
    </div>
  );
}
