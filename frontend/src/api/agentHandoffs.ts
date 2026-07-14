import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from './client';

export type HandoffTriggerReason =
  | 'low_confidence'
  | 'policy_boundary'
  | 'missing_data'
  | 'execution_error'
  | 'stop_condition'
  | 'requires_approval'
  | 'max_steps'
  | 'kill_requested'
  | 'review_queue';

export type HandoffStatus =
  | 'pending'
  | 'approved'
  | 'edited_approved'
  | 'rejected'
  | 'taken_over'
  | 'expired'
  | 'acknowledged';

export interface RecordLink {
  entity: string;
  id: string;
  label: string;
  api_url: string;
}

export interface AgentHandoff {
  id: string;
  run_id: string;
  agent_name: string;
  agent_slug: string;
  trigger_reason: HandoffTriggerReason;
  trigger_detail: string;
  proposed_action: Record<string, unknown> | null;
  proposed_reasoning: string;
  confidence: number | null;
  data_gathered: Record<string, unknown>;
  record_links: RecordLink[];
  status: HandoffStatus;
  resolved_by_id: string | null;
  resolved_at: string | null;
  resolution_notes: string;
  created_at: string;
}

/** Handoffs that suspend the run until a human decides — everything except review_queue. */
export function isSuspending(h: Pick<AgentHandoff, 'trigger_reason'>): boolean {
  return h.trigger_reason !== 'review_queue';
}

const HANDOFFS_KEY = ['agents', 'handoffs'];

export function useHandoffs(status?: string) {
  return useQuery<AgentHandoff[]>({
    queryKey: [...HANDOFFS_KEY, status ?? 'pending'],
    queryFn: () =>
      api
        .get('/agents/handoffs', { params: status ? { status } : undefined })
        .then(r => r.data),
    refetchInterval: 20000, // no push infra yet (ADR-0001 open question) — poll
  });
}

export function useHandoff(id: string | null) {
  return useQuery<AgentHandoff>({
    queryKey: [...HANDOFFS_KEY, 'detail', id],
    queryFn: () => api.get(`/agents/handoffs/${id}`).then(r => r.data),
    enabled: Boolean(id),
  });
}

interface ActionResponse {
  ok: boolean;
  message: string;
}

function useResolveMutation<TVars>(
  buildRequest: (vars: TVars) => { url: string; body: Record<string, unknown> }
) {
  const qc = useQueryClient();
  return useMutation<ActionResponse, unknown, TVars>({
    mutationFn: (vars: TVars) => {
      const { url, body } = buildRequest(vars);
      return api.post(url, body).then(r => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: HANDOFFS_KEY });
    },
  });
}

export function useApproveHandoff() {
  return useResolveMutation<{ id: string; notes?: string }>(({ id, notes }) => ({
    url: `/agents/handoffs/${id}/approve`,
    body: { notes: notes ?? '' },
  }));
}

export function useEditApproveHandoff() {
  return useResolveMutation<{ id: string; editedPayload: Record<string, unknown>; notes?: string }>(
    ({ id, editedPayload, notes }) => ({
      url: `/agents/handoffs/${id}/edit-approve`,
      body: { edited_payload: editedPayload, notes: notes ?? '' },
    })
  );
}

export function useRejectHandoff() {
  return useResolveMutation<{ id: string; reason: string }>(({ id, reason }) => ({
    url: `/agents/handoffs/${id}/reject`,
    body: { reason },
  }));
}

export function useTakeOverHandoff() {
  return useResolveMutation<{ id: string; notes?: string }>(({ id, notes }) => ({
    url: `/agents/handoffs/${id}/take-over`,
    body: { notes: notes ?? '' },
  }));
}

export function useAcknowledgeHandoff() {
  return useResolveMutation<{ id: string; notes?: string }>(({ id, notes }) => ({
    url: `/agents/handoffs/${id}/acknowledge`,
    body: { notes: notes ?? '' },
  }));
}
