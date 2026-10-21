// Mirrors the backend response models (app/schemas).

export type Temperature = "hot" | "warm" | "cold";
export type Stage =
  | "new"
  | "contacted"
  | "engaged"
  | "demo_scheduled"
  | "demo_completed"
  | "trial"
  | "negotiation"
  | "won"
  | "lost";
export type DraftStatus = "pending_review" | "approved" | "rejected" | "sent" | "cancelled";
export type EmailKind =
  | "initial_response"
  | "demo_invitation"
  | "post_demo_followup"
  | "trial_activation_reminder"
  | "objection_handling"
  | "re_engagement"
  | "follow_up";

export const STAGES: Stage[] = [
  "new",
  "contacted",
  "engaged",
  "demo_scheduled",
  "demo_completed",
  "trial",
  "negotiation",
  "won",
  "lost",
];

export const EMAIL_KINDS: EmailKind[] = [
  "initial_response",
  "demo_invitation",
  "post_demo_followup",
  "trial_activation_reminder",
  "objection_handling",
  "re_engagement",
  "follow_up",
];

export const OBJECTIONS = [
  "price",
  "switching_cost",
  "competitor",
  "timing",
  "staff_adoption",
  "missing_feature",
  "contract_lock_in",
] as const;

export const CATEGORIES = [
  "gym",
  "fitness_studio",
  "beauty_salon",
  "barbershop",
  "wellness_studio",
  "spa",
  "other",
] as const;

export const COMPANY_SIZES = ["1-5", "6-20", "21-50", "51-200", "200+"] as const;

export interface Lead {
  id: string;
  business_name: string;
  contact_name: string;
  email: string;
  phone: string | null;
  website: string | null;
  business_category: string;
  locations_count: number | null;
  company_size: string | null;
  product_interest: string[];
  message: string | null;
  source: string;
  source_detail: string | null;
  stage: Stage;
  owner: string | null;
  objections: string[];
  consent_email: boolean;
  consent_marketing: boolean;
  consent_captured_at: string | null;
  consent_source: string | null;
  preferred_channel: "email" | "phone";
  do_not_contact: boolean;
  unsubscribed_at: string | null;
  score: number | null;
  temperature: Temperature | null;
  qualified_at: string | null;
  needs_review: boolean;
  review_reason: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadPage {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}

export interface Factor {
  key: string;
  label: string;
  points: number;
  max_points: number;
  evidence: string;
}

export interface Qualification {
  id: string;
  lead_id: string;
  score: number;
  temperature: Temperature;
  confidence: number;
  rule_score: number;
  ai_adjustment: number | null;
  method: string;
  model: string | null;
  factors: Factor[];
  signals: string[];
  missing_information: string[];
  detected_objections: string[];
  ai_evidence: string[];
  reasoning: string;
  warnings: string[];
  created_at: string;
}

export interface Draft {
  id: string;
  lead_id: string;
  kind: EmailKind;
  subject: string;
  body: string;
  status: DraftStatus;
  generated_by: "ai" | "template";
  model: string | null;
  guardrail_warnings: string[];
  instructions: string | null;
  sequence_id: string | null;
  followup_step: number | null;
  created_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DraftWithLead extends Draft {
  lead: Lead;
}

export interface Task {
  id: string;
  sequence_id: string;
  lead_id: string;
  step: number;
  day: number;
  action: "followup_draft" | "manual_review";
  due_at: string;
  status: "scheduled" | "completed" | "skipped" | "cancelled";
  outcome: string | null;
  draft_id: string | null;
  completed_at: string | null;
}

export interface Sequence {
  id: string;
  lead_id: string;
  status: "active" | "stopped" | "completed";
  anchor_at: string;
  started_at: string;
  cadence: { step_days: number[]; manual_review_day: number };
  current_step: number;
  stop_reason: string | null;
  stopped_at: string | null;
  tasks: Task[];
}

export interface LeadDetail {
  lead: Lead;
  latest_qualification: Qualification | null;
  sequences: Sequence[];
  drafts: Draft[];
}

export interface Activity {
  id: string;
  kind: string;
  direction: "inbound" | "outbound" | "internal";
  subject: string | null;
  body: string | null;
  actor: string | null;
  meta: Record<string, unknown>;
  occurred_at: string;
}

export interface Cadence {
  step_days: number[];
  manual_review_day: number;
  temperatures: string[];
  draft_review_sla_hours: number;
}

export interface Overdue {
  tasks: Task[];
  drafts: Draft[];
}

export interface Suppression {
  id: string;
  kind: "email" | "domain";
  value: string;
  reason: string;
  source: string | null;
  note: string | null;
  created_at: string;
}

export interface Job {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "dead";
  idempotency_key: string | null;
  run_at: string;
  attempts: number;
  max_attempts: number;
  locked_by: string | null;
  last_error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface Summary {
  total_leads: number;
  new_last_7_days: number;
  by_temperature: Record<string, number>;
  by_stage: Record<string, number>;
  drafts_pending_review: number;
  drafts_approved_unsent: number;
  active_sequences: number;
  followups_due_24h: number;
  overdue_drafts: number;
  needs_review: number;
  unanswered: number;
  median_first_response_hours: number | null;
  jobs: Record<string, number>;
  ai_enabled: boolean;
}

export interface LeadCreatePayload {
  business_name: string;
  contact_name: string;
  email: string;
  phone?: string | null;
  business_category: string;
  locations_count?: number | null;
  company_size?: string | null;
  product_interest: string[];
  message?: string | null;
  preferred_channel: "email" | "phone";
  source: string;
  owner?: string | null;
  consent: { email: boolean; marketing: boolean; source_text?: string | null };
}
