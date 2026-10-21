import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, query } from "./client";
import type {
  Activity,
  Cadence,
  Draft,
  DraftWithLead,
  EmailKind,
  Job,
  Lead,
  LeadCreatePayload,
  LeadDetail,
  LeadPage,
  Overdue,
  Qualification,
  Sequence,
  Summary,
  Suppression,
  Task,
} from "./types";

export interface LeadFilters {
  temperature?: string;
  stage?: string;
  needs_review?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}

export const useSummary = () =>
  useQuery({ queryKey: ["summary"], queryFn: () => api<Summary>("/dashboard/summary") });

export const useLeads = (filters: LeadFilters) =>
  useQuery({
    queryKey: ["leads", filters],
    queryFn: () => api<LeadPage>(`/leads${query({ ...filters })}`),
    placeholderData: (prev) => prev,
  });

export const useUnanswered = () =>
  useQuery({ queryKey: ["leads", "unanswered"], queryFn: () => api<Lead[]>("/leads/unanswered") });

export const useLead = (id: string) =>
  useQuery({ queryKey: ["lead", id], queryFn: () => api<LeadDetail>(`/leads/${id}`) });

export const useTimeline = (id: string) =>
  useQuery({ queryKey: ["lead", id, "timeline"], queryFn: () => api<Activity[]>(`/leads/${id}/timeline`) });

export const useDrafts = (status: string) =>
  useQuery({
    queryKey: ["drafts", status],
    queryFn: () => api<DraftWithLead[]>(`/drafts${query({ status })}`),
  });

export const useCadence = () =>
  useQuery({ queryKey: ["cadence"], queryFn: () => api<Cadence>("/followups/cadence") });

export const useTasks = () =>
  useQuery({ queryKey: ["tasks"], queryFn: () => api<Task[]>("/followups/tasks?status=scheduled") });

export const useOverdue = () =>
  useQuery({ queryKey: ["overdue"], queryFn: () => api<Overdue>("/followups/overdue") });

export const useSuppressions = () =>
  useQuery({ queryKey: ["suppressions"], queryFn: () => api<Suppression[]>("/suppressions") });

export const useJobs = (status?: string) =>
  useQuery({
    queryKey: ["jobs", status],
    queryFn: () => api<Job[]>(`/jobs${query({ status })}`),
    refetchInterval: 5000,
  });

/** Every write can change counts, queues and timelines, so refresh broadly. */
function useInvalidateAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

export function useCreateLead() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (payload: LeadCreatePayload) =>
      api<{ lead: Lead; created: boolean }>("/leads", { method: "POST", json: payload }),
    onSuccess: invalidate,
  });
}

export function useUpdateLead(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      api<Lead>(`/leads/${id}`, { method: "PATCH", json: patch }),
    onSuccess: invalidate,
  });
}

export function useRequalify(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (useAi: boolean) =>
      api<Qualification>(`/leads/${id}/qualify${query({ use_ai: useAi })}`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useGenerateDraft(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: { kind: EmailKind; use_ai: boolean; instructions?: string }) =>
      api<Draft>(`/leads/${id}/drafts`, { method: "POST", json: body }),
    onSuccess: invalidate,
  });
}

export function useLogActivity(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: { kind: "note" | "call" | "inbound_email"; subject?: string; body: string }) =>
      api<Activity>(`/leads/${id}/activities`, { method: "POST", json: body }),
    onSuccess: invalidate,
  });
}

export function useSequence(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (action: "start" | "stop") =>
      api<Sequence | null>(`/leads/${id}/sequence`, { method: action === "start" ? "POST" : "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useDraftAction() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({
      id,
      action,
      reviewer,
      note,
    }: {
      id: string;
      action: "approve" | "reject" | "send";
      reviewer: string;
      note?: string;
    }) => api<Draft>(`/drafts/${id}/${action}`, { method: "POST", json: { reviewer, note } }),
    onSuccess: invalidate,
  });
}

export function useEditDraft() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, subject, body, editor }: { id: string; subject: string; body: string; editor: string }) =>
      api<Draft>(`/drafts/${id}`, { method: "PATCH", json: { subject, body, editor } }),
    onSuccess: invalidate,
  });
}

export function useAddSuppression() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (body: { kind: string; value: string; reason: string; note?: string }) =>
      api<Suppression>("/suppressions", { method: "POST", json: body }),
    onSuccess: invalidate,
  });
}

export function useDeleteSuppression() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/suppressions/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useRetryJob() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) => api<Job>(`/jobs/${id}/retry`, { method: "POST" }),
    onSuccess: invalidate,
  });
}
