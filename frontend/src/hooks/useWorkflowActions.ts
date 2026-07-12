import { useState, useMemo } from 'react';
import api from '../api/client';
import type { EntityMeta, WorkflowTransition } from '../meta/types';

interface UseWorkflowActionsResult {
  availableTransitions: WorkflowTransition[];
  loading: boolean;
  trigger: (action: string) => Promise<Record<string, unknown>>;
}

/**
 * Returns the workflow transitions available from the record's current status,
 * plus a trigger() function that calls the appropriate action endpoint.
 *
 * Action URL pattern: {meta.api_path}/{id}/{action-slug}
 * where action-slug is the transition's `action` field lowercased with
 * underscores replaced by hyphens.
 */
export function useWorkflowActions(
  meta: EntityMeta,
  record: Record<string, unknown> | null | undefined
): UseWorkflowActionsResult {
  const [loading, setLoading] = useState(false);

  const availableTransitions = useMemo<WorkflowTransition[]>(() => {
    if (!meta.workflow || !record) return [];
    const currentStatus = record.status as string | null | undefined;
    return meta.workflow.transitions.filter(
      t => t.from === currentStatus && t.action != null
    );
  }, [meta, record]);

  async function trigger(action: string): Promise<Record<string, unknown>> {
    if (!record?.id) throw new Error('No record id');
    const actionSlug = action.toLowerCase().replace(/_/g, '-');
    const url = `${meta.api_path}/${record.id}/${actionSlug}`;
    setLoading(true);
    try {
      const res = await api.post(url, { id: record.id });
      return res.data as Record<string, unknown>;
    } finally {
      setLoading(false);
    }
  }

  return { availableTransitions, loading, trigger };
}
