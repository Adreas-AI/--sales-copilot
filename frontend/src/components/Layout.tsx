import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useSummary } from "../api/hooks";
import { getReviewer, setReviewer } from "../lib/format";
import { cx, inputClass } from "./ui";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/leads", label: "Leads" },
  { to: "/review", label: "Review queue", badge: "drafts" as const },
  { to: "/followups", label: "Follow-ups", badge: "review" as const },
  { to: "/suppressions", label: "Suppression list" },
  { to: "/jobs", label: "Jobs" },
];

export default function Layout() {
  const { data: summary } = useSummary();
  const [reviewer, setName] = useState(getReviewer());
  const counts = {
    drafts: summary?.drafts_pending_review ?? 0,
    review: summary?.needs_review ?? 0,
  };

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-5 py-4">
          <div className="grid size-8 place-items-center rounded-lg bg-indigo-600 text-sm font-bold text-white">B</div>
          <div>
            <div className="text-sm font-semibold">Sales Copilot</div>
            <div className="text-xs text-slate-500">BookFlow</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cx(
                  "flex items-center justify-between rounded-lg px-3 py-2 text-sm whitespace-nowrap",
                  isActive ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-600 hover:bg-slate-100",
                )
              }
            >
              {item.label}
              {item.badge && counts[item.badge] > 0 && (
                <span className="ml-2 rounded-full bg-indigo-600 px-1.5 text-xs font-medium text-white tabular-nums">
                  {counts[item.badge]}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="hidden px-5 pt-4 md:block">
          <label className="text-xs text-slate-500">
            Reviewing as
            <input
              className={cx(inputClass, "mt-1")}
              value={reviewer}
              onChange={(e) => {
                setName(e.target.value);
                setReviewer(e.target.value);
              }}
            />
          </label>
          <p className="mt-4 text-xs text-slate-400">
            AI: {summary ? (summary.ai_enabled ? "on" : "off (rules + templates)") : "…"}
          </p>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}
