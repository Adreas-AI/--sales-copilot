export const humanize = (value: string | null | undefined) =>
  (value ?? "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

export function relative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  for (const [unit, ms] of UNITS) {
    if (Math.abs(diff) >= ms || unit === "minute") return rtf.format(Math.round(diff / ms), unit);
  }
  return "";
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const REVIEWER_KEY = "copilot.reviewer";

export function getReviewer(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) || "rep";
  } catch {
    return "rep";
  }
}

export function setReviewer(name: string) {
  try {
    localStorage.setItem(REVIEWER_KEY, name);
  } catch {
    /* storage unavailable: keep the default */
  }
}
