import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useDraftAction, useEditDraft } from "../api/hooks";
import type { Draft, Lead } from "../api/types";
import { getReviewer, humanize, relative } from "../lib/format";
import { Badge, Button, ErrorNote, StatusBadge, TemperatureBadge, cx, inputClass } from "./ui";

/** A draft as a reviewer sees it: editable while open, with guardrail findings beside it. */
export default function DraftCard({ draft, lead }: { draft: Draft; lead?: Lead }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const edit = useEditDraft();
  const action = useDraftAction();

  useEffect(() => {
    setSubject(draft.subject);
    setBody(draft.body);
  }, [draft.subject, draft.body]);

  const open = draft.status === "pending_review" || draft.status === "approved";
  const dirty = subject !== draft.subject || body !== draft.body;
  const errors = draft.guardrail_warnings.filter((w) => w.startsWith("error:"));
  const warnings = draft.guardrail_warnings.filter((w) => !w.startsWith("error:"));
  const reviewer = getReviewer();

  const run = (kind: "approve" | "reject" | "send") => action.mutate({ id: draft.id, action: kind, reviewer });

  return (
    <article className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3 text-sm">
        <StatusBadge status={draft.status} />
        <span className="font-medium">{humanize(draft.kind)}</span>
        {draft.followup_step && <Badge>Step {draft.followup_step}</Badge>}
        <Badge tone={draft.generated_by === "ai" ? "indigo" : "slate"}>
          {draft.generated_by === "ai" ? `AI · ${draft.model}` : "Template"}
        </Badge>
        {lead && (
          <Link to={`/leads/${lead.id}`} className="ml-auto flex items-center gap-2 text-slate-600 hover:text-indigo-600">
            {lead.business_name}
            <TemperatureBadge temperature={lead.temperature} score={lead.score} />
          </Link>
        )}
        <span className={cx("text-xs text-slate-400", !lead && "ml-auto")}>created {relative(draft.created_at)}</span>
      </header>

      <div className="space-y-3 p-4">
        {lead && (
          <p className="text-xs text-slate-500">
            To {lead.contact_name} &lt;{lead.email}&gt;
          </p>
        )}
        <input
          className={cx(inputClass, "font-medium")}
          value={subject}
          disabled={!open}
          onChange={(e) => setSubject(e.target.value)}
          aria-label="Subject"
        />
        <textarea
          className={cx(inputClass, "min-h-56 font-mono text-[13px] leading-relaxed")}
          value={body}
          disabled={!open}
          onChange={(e) => setBody(e.target.value)}
          aria-label="Body"
        />
        {open && <p className="text-xs text-slate-400">An unsubscribe link is added automatically when sent.</p>}

        {(errors.length > 0 || warnings.length > 0) && (
          <ul className="space-y-1 text-xs">
            {errors.map((w) => (
              <li key={w} className="rounded bg-rose-50 px-2 py-1 text-rose-700">{w.replace(/^error:/, "")}</li>
            ))}
            {warnings.map((w) => (
              <li key={w} className="rounded bg-amber-50 px-2 py-1 text-amber-800">{w.replace(/^warning:/, "")}</li>
            ))}
          </ul>
        )}
        {draft.review_note && <p className="text-xs text-slate-500">Note: {draft.review_note}</p>}
        {draft.reviewed_by && (
          <p className="text-xs text-slate-500">
            {draft.status === "sent" ? "Sent" : "Reviewed"} by {draft.reviewed_by} {relative(draft.sent_at ?? draft.reviewed_at)}
          </p>
        )}
        <ErrorNote error={edit.error || action.error} />

        {open && (
          <div className="flex flex-wrap gap-2">
            {dirty ? (
              <>
                <Button
                  variant="primary"
                  disabled={edit.isPending}
                  onClick={() => edit.mutate({ id: draft.id, subject, body, editor: reviewer })}
                >
                  Save changes
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSubject(draft.subject);
                    setBody(draft.body);
                  }}
                >
                  Discard
                </Button>
              </>
            ) : draft.status === "pending_review" ? (
              <Button variant="primary" disabled={action.isPending || errors.length > 0} onClick={() => run("approve")}>
                Approve
              </Button>
            ) : (
              <Button variant="primary" disabled={action.isPending} onClick={() => run("send")}>
                Send now
              </Button>
            )}
            {!dirty && (
              <Button variant="danger" disabled={action.isPending} onClick={() => run("reject")}>
                Reject
              </Button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
